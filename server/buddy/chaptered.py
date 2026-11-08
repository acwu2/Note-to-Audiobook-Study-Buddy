"""Write a long lesson one chapter at a time, so it is as long as it was asked to be.

Asked for one long script, a model returns about half of it. Measured on real runs:
told to write 962 words it wrote 552, told 1906 it wrote 723, and a single expansion
pass moved those by 19 words. Better wording does not fix that: the prompt already
says the length is a target, not a ceiling. What models do hit reliably is a modest
target in one call (our 3 minute lessons landed on theirs), so the length is built
from several modest calls instead of one large one.

A plan call decides the chapters. Each chapter is then written by its own call with
its own word target and sight of how the last one ended. Chapter boundaries fall out
of the assembly exactly, rather than being guessed afterwards by the model.
"""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel

from . import llm
from .formats import PipelineError

log = logging.getLogger("buddy.chaptered")

# Below this a single call lands close enough to its target (a 349 word ask landed
# on target; a ~900 word ask landed at 75%, so the line is drawn around 520).
MIN_TARGET_WORDS = 520
# Words per chapter. Chosen from what single calls reliably hit.
CHUNK_WORDS = 380
MAX_CHAPTERS = 10
# A chapter this far under what it was asked for gets one more try. Ordinary undershoot
# (models return about 75-85%) is corrected by asking the next chapter for more, so a
# retry is reserved for a chapter that failed outright; retrying the ordinary case
# spends a call that cannot help.
RETRY_BELOW = 0.6


class OutlineChapter(BaseModel):
    title: str
    summary: str = ""
    covers: str = ""


class LessonPlan(BaseModel):
    title: str = ""
    chapters: list[OutlineChapter]


class Section(BaseModel):
    lines: list[llm.Line]


PLAN_PROMPT = """Plan a {n} chapter audio lesson from a student's notes.
Lesson: {label}. {brief}

Split what the notes teach into exactly {n} chapters, in the order that makes them easiest
to learn. Each chapter is about {per} words of teaching, so give each real work to do.
If the notes are short, the chapters go deeper in turn rather than ending early: first the
idea itself, then a worked example, then the common mistakes and how to avoid them, then
how it connects to the rest. Chapters must not repeat one another.

- title: the chapter's subject in two to five words, using the notes' own vocabulary
  ("Why leaves look green", "Splitting water"). Never name the move instead of the
  subject: no "Introduction", "Recap", "Check 1".
- covers: what this chapter must teach, as a sentence a writer can follow. Name the
  specific facts and numbers from the notes it takes, so chapters do not overlap.
- summary: one or two sentences stating what the chapter teaches, for a table of contents
  a student reads and never hears. Write it as text, not speech: symbols, units and numbers
  exactly as in the notes (25°C, Ka, 10⁻¹⁴), never spelled out.

Also give the whole lesson a title of at most eight words naming what it covers, not what
was requested.

Notes:
{notes}"""

SECTION_PROMPT = """You are writing chapter {k} of {n} of a two-host audio lesson built from a
student's notes. Hosts: Heart and Michael, taking turns.
Lesson: {label}. {brief}

The whole lesson, in order:
{outline}

Chapter {k} is "{title}". It teaches: {covers}
{position}

Length: about {words} words, and never fewer than {floor}. The student asked for a lesson of
this length, so that is a target to hit, not a ceiling. If the notes on this point are short,
teach it more thoroughly: smaller steps, a worked example, a common mistake, why it matters.
Do not repeat what earlier chapters said, and never pad by restating an idea in new words.

This is a lesson someone studies from. Every line has a role:
- "hook": why this matters. Only in the opening chapter, and only as its first line.
- "teach": the explanation. One idea per line.
- "check": a question put to the student, who is given silence to answer aloud. Ask about
  something already taught here, and ask a real question with a real answer.
- "answer": the answer to the check immediately before it.
- "recap": pulls the lesson together. Only in the final chapter, and only as its last line.
Every check is followed immediately by its answer. Teach before you test. Include at least
one check and its answer in this chapter. The first line of the chapter is never a check or
an answer.

Every line says where its content came from, and the student is shown it:
- source "notes": every fact, name, number and relationship in the line is in the notes.
- source "added": the line brings in something the notes do not say: context, an analogy,
  a worked example, why a fact matters. Everything added must be true.
Prefer "notes" lines. Never let an unsourced fact sit inside a "notes" line; split it.
Skip anything marked [unclear]. Do not guess at it.

Write for the ear: spell out symbols and abbreviations ("→" becomes "leads to", "e.g." becomes
"for example", "~50%" becomes "about fifty percent", "2×" becomes "twice"). Plain spoken
sentences, no stage directions or markdown. Each line is one or two sentences.

{previous}
Notes:
{notes}"""


def _outline(chapters: list[OutlineChapter]) -> str:
    return "\n".join(f"{i + 1}. {c.title}: {c.covers or c.summary}" for i, c in enumerate(chapters))


def _position(k: int, n: int) -> str:
    if n == 1:
        return "This is the whole lesson: open with a hook line and finish with a recap line."
    if k == 1:
        return "This is the opening chapter: start with a hook line saying why this matters."
    if k == n:
        return "This is the final chapter: finish with a recap line that pulls the whole lesson together."
    return "This is a middle chapter: do not open with a hook or finish with a recap. The lesson carries on."


def _previous(lines: list[llm.Line]) -> str:
    if not lines:
        return ""
    tail = "\n".join(f"{l.host.value}: {l.text}" for l in lines[-4:])
    return (
        "How the lesson has gone so far (the last lines said). Pick up from here and keep "
        f"the hosts alternating naturally; do not repeat any of it:\n{tail}\n\n"
    )


def _clean(lines: list[llm.Line], first: bool, last: bool) -> list[llm.Line]:
    """Keep the shape a chapter is allowed to have, whatever the model drifted into."""
    out = [l for l in lines if l.text.strip()]
    # A chapter never opens on a question or on a reply to one: someone jumping there
    # would land in the middle of an exchange. Drop the strays rather than demote the
    # real opening line that follows them.
    while out and out[0].role in (llm.Role.CHECK, llm.Role.ANSWER):
        out.pop(0)
    if not out:
        return out
    # A hook belongs only to the opening, a recap only to the close.
    fixed = []
    for i, l in enumerate(out):
        role = l.role
        if role is llm.Role.HOOK and not (first and i == 0):
            role = llm.Role.TEACH
        if role is llm.Role.RECAP and not (last and i == len(out) - 1):
            role = llm.Role.TEACH
        fixed.append(l.model_copy(update={"role": role}))
    return fixed


def write(transcripts: list[str], label: str, brief: str, target: int) -> tuple[list[llm.Line], list[llm.ChapterPlan], str] | None:
    """The lesson as (lines, chapters, title), or None when it cannot be planned."""
    n = max(2, min(MAX_CHAPTERS, round(target / CHUNK_WORDS)))
    notes = llm._notes_block(transcripts)
    plan = llm._generate(
        PLAN_PROMPT.format(n=n, per=target // n, label=label, brief=brief, notes=notes), LessonPlan
    )
    chapters = [c for c in plan.chapters if c.title.strip()][:n]
    if len(chapters) < 2:
        log.warning("plan came back with %d usable chapters; falling back to one call", len(chapters))
        return None

    per = target // len(chapters)
    outline = _outline(chapters)
    lines: list[llm.Line] = []
    chapter_plans: list[llm.ChapterPlan] = []
    asked_total = got_total = 0
    for k, ch in enumerate(chapters, start=1):
        # Models land consistently short of what they are asked for (about 82% on a real
        # run). Measure how much of each request actually comes back and ask the next
        # chapter for proportionally more, and ask the last one for exactly what is
        # still missing. Costs no extra calls, and corrects itself for whichever model
        # answered, which matters because the fallback chain changes the model.
        yield_ = (got_total / asked_total) if asked_total else 1.0
        yield_ = max(0.5, min(1.0, yield_))
        if k == len(chapters) and asked_total:
            ask_words = (target - got_total) / yield_
        else:
            ask_words = per / yield_
        ask_words = int(max(per * 0.8, min(per * 1.6, ask_words)))

        def ask(extra: str = "") -> list[llm.Line]:
            prompt = SECTION_PROMPT.format(
                k=k, n=len(chapters), label=label, brief=brief, outline=outline, title=ch.title,
                covers=ch.covers or ch.summary, position=_position(k, len(chapters)),
                words=ask_words, floor=int(ask_words * 0.85), previous=_previous(lines), notes=notes,
            ) + extra
            return _clean(llm._generate(prompt, Section).lines, k == 1, k == len(chapters))

        got = ask()
        words = llm._word_count(got)
        if words < ask_words * RETRY_BELOW:
            log.info("chapter %d came back at %d words against %d; asking again", k, words, ask_words)
            retry = ask(
                f"\n\nAn earlier attempt came back at only {words} words. Write this chapter again "
                f"at the full {ask_words} words: keep what you had, then teach each idea in smaller "
                "steps, work an example, and add a check with its answer. Do not repeat yourself."
            )
            if llm._word_count(retry) > words:
                got, words = retry, llm._word_count(retry)
        if not got:
            continue
        asked_total += ask_words
        got_total += words
        chapter_plans.append(llm.ChapterPlan(title=ch.title.strip(), startLine=len(lines), summary=re.sub(r"\s+", " ", ch.summary).strip()))
        lines.extend(got)

    if len(chapter_plans) < 2 or not lines:
        raise PipelineError("The AI could not write this lesson. Try again.")
    log.info("chaptered lesson: %d chapters, %d words against a %d target", len(chapter_plans), llm._word_count(lines), target)
    return lines, chapter_plans, re.sub(r"\s+", " ", plan.title or "").strip()[:80]
