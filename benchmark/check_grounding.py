#!/usr/bin/env python3
"""Flag content words in a generated podcast script that the source notes never mention.

The pipeline's whole promise is that a script is built from the student's own
notes. The failure that matters is not a wrong fact — it is a *true* fact the
model knew and the notes never said. Those read as authoritative and a student
cannot tell them apart from their own material.

This is a flagger, not a judge. It reports candidates for a human to look at,
and it is deliberately tuned to miss few rather than to be quiet. Expect some
false positives from ordinary English; read the list, don't score it blindly.

Usage:
    python3 check_grounding.py <note.json> <status-or-script.json>
    python3 check_grounding.py --all          # every stored podcast

Exit status is 1 when anything is flagged, so CI can gate on it.
"""

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "server" / "data"

# Ordinary English that carries no claim. Kept deliberately short: a word only
# belongs here if a student would never call it a fact about their subject.
STOP = set("""
a about above after again against all also am an and another any are as at
back be because been before being below between both but by came can cannot
come could did do does doing done down during each either else even ever every
for from further get gets getting give given go goes going got had has have
having he her here hers herself him himself his how however i if in into is it
its itself just keep let lets like little look made make makes making many may
me might more most much must my myself never new next no nor not now of off on
once one only onto or other others our ours ourselves out over own part put
rather really right said same say says see seen she should since so some still
such take takes than that the their theirs them themselves then there these
they thing things think this those though through thus to together too two up
upon us use used uses using very want was way we well went were what when
where which while who whole whom why will with within without would yes yet you
your yours yourself
actually always bit certain clear course easy exactly fine first good great
hard idea important kind lot maybe mean means mind okay point pretty quick
quickly remember second short simple simply slow slowly sort start starts sure
thanks third time understand whatever yeah
""".split())

# Framing the hosts use to refer to the source itself.
STOP |= set("notes note page pages wrote writes written says said lecture class".split())

# Positional and conversational filler the hosts use to stitch lines together.
STOP |= set("""
inside outside call called calls ready stage stages step steps three four five
six seven eight nine ten most least more less best worst top bottom end ends
begin begins next last final finally also again plus minus each per
""".split())

# Number words, so '2x' in the notes covers 'twice' in the script.
NUMBER_WORDS = {
    "1": {"one", "once", "single"}, "2": {"two", "twice", "double", "pair"},
    "3": {"three", "thrice", "triple"}, "4": {"four"}, "5": {"five"},
    "6": {"six"}, "7": {"seven"}, "8": {"eight"}, "9": {"nine"}, "10": {"ten"},
}


def collapse_spelled(text: str) -> str:
    """TTS scripts spell acronyms out: 'N A D H' -> 'NADH', 'C O 2' -> 'CO2'."""
    def join(m):
        return m.group(0).replace(" ", "")
    return re.sub(r"\b(?:[A-Za-z0-9] ){1,7}[A-Za-z0-9]\b", join, text)


def words(text: str) -> list[str]:
    text = collapse_spelled(text)
    # keep digits attached to letters (FADH2, CO2, 2x)
    return re.findall(r"[A-Za-z][A-Za-z0-9]*|\d+", text.lower())


def variants(w: str) -> set[str]:
    """Cheap morphology, so 'releases' in the note covers 'release' in the script."""
    out = {w}
    for suf in ("s", "es", "ed", "ing", "'s"):
        if w.endswith(suf) and len(w) > len(suf) + 2:
            out.add(w[: -len(suf)])
    out.add(w + "s")
    if w.endswith("y") and len(w) > 3:
        out.add(w[:-1] + "ies")
    return out


def expand_acronyms(vocab: set[str], script: list[dict]) -> set[str]:
    """'ETC' in the notes grounds 'electron transport chain' in the script.

    For every acronym in the notes, look for a run of script words whose
    initials spell it, and treat those words as covered.
    """
    acronyms = {w for w in vocab if 3 <= len(w) <= 6 and w.isalpha()}
    if not acronyms:
        return set()
    covered: set[str] = set()
    for line in script:
        ws = words(str(line.get("text", "")))
        for n in (2, 3, 4, 5):
            for i in range(len(ws) - n + 1):
                run = ws[i : i + n]
                if "".join(w[0] for w in run) in acronyms:
                    covered |= set(run)
    return covered


def note_vocab(note: dict) -> set[str]:
    vocab: set[str] = set()
    for page in note.get("pages", []):
        for w in words(page.get("transcript", "")):
            vocab |= variants(w)
    vocab |= set(words(note.get("topic", "")))
    for digit, spelled in NUMBER_WORDS.items():
        if digit in vocab:
            vocab |= spelled
    # the fixed menu's own wording is the product's, not a claim about the subject
    for opt in note.get("options", []):
        for field in ("label", "title", "description"):
            vocab |= set(words(str(opt.get(field, ""))))
    return vocab


def host_names(script: list[dict]) -> set[str]:
    return {w for line in script for w in words(str(line.get("host", "")))}


def check(note: dict, script: list[dict]) -> list[tuple[int, str, str, list[str]]]:
    vocab = note_vocab(note)
    vocab |= expand_acronyms(vocab, script)
    skip = STOP | host_names(script)
    findings = []
    for i, line in enumerate(script):
        text = str(line.get("text", ""))
        source = str(line.get("source", "notes"))
        unknown, seen = [], set()
        for w in words(text):
            if w in skip or len(w) < 3 or w in vocab or w in seen:
                continue
            if variants(w) & vocab:
                continue
            seen.add(w)
            unknown.append(w)
        if unknown:
            findings.append((i, text, source, unknown))
    return findings


def load_script(path: Path) -> list[dict]:
    doc = json.loads(path.read_text())
    if isinstance(doc, dict):
        return doc.get("script") or doc.get("lines") or []
    return doc


def report(note_path: Path, script_path: Path) -> int:
    note = json.loads(note_path.read_text())
    script = load_script(script_path)
    if not script:
        print(f"  no script lines in {script_path.name}")
        return 0
    findings = check(note, script)
    added = sum(1 for line in script if str(line.get("source", "notes")) == "added")
    header = f"\n{script_path.parent.name}  ·  note {note.get('noteId', '?')}  ·  {len(script)} lines"
    if added:
        header += f"  ({added} labelled 'added')"
    print(header)

    # A line labelled "added" is *expected* to carry new words — that is the point
    # of the label. Only an unsourced word inside a "notes" line is a bug.
    leaks = [f for f in findings if f[2] != "added"]
    for i, text, _source, unknown in leaks:
        print(f'  LEAK line {i + 1}: "{text}"')
        print(f"    not in the notes, but the line claims to be: {', '.join(unknown)}")
    for i, text, _source, unknown in (f for f in findings if f[2] == "added"):
        print(f'  ok   line {i + 1} (added): brings in {", ".join(unknown)}')
    if not leaks:
        print("  no unlabelled additions")
    else:
        print(f"  {len(leaks)} of {len(script)} lines leak")
    return len(leaks)


def main() -> int:
    args = sys.argv[1:]
    if args[:1] == ["--all"]:
        total = 0
        pods = sorted((DATA / "podcasts").glob("*/status.json"))
        if not pods:
            print("no stored podcasts found under server/data/podcasts")
            return 0
        for status in pods:
            note_id = json.loads(status.read_text()).get("noteId")
            note_path = DATA / "notes" / f"{note_id}.json"
            if not note_path.exists():
                print(f"\n{status.parent.name}: note {note_id} is missing, skipped")
                continue
            total += report(note_path, status)
        print(f"\n{'=' * 52}\n{total} flagged line(s) across {len(pods)} podcast(s)")
        return 1 if total else 0
    if len(args) != 2:
        print(__doc__)
        return 2
    return 1 if report(Path(args[0]), Path(args[1])) else 0


if __name__ == "__main__":
    sys.exit(main())
