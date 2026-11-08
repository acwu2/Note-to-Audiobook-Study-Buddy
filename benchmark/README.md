# Benchmark: Study Buddy vs NotebookLM

NotebookLM's Audio Overview is the thing this pipeline is measured against. It
is the same shape of product — notes in, two hosts talking out — so the
comparison is fair, and the places it loses are the places worth building.

## The one thing to measure

Both products generate a confident two-host conversation. The difference that
matters to a student is **whether the script says things their notes never
said**. A wrong fact is easy to spot. A *true* fact the model knew and the notes
never mentioned is not: it sounds exactly as authoritative as the student's own
material, and they will carry it into an exam believing they wrote it down.

NotebookLM leans into this — it enriches freely from world knowledge. That is
the gap to exploit, and it only stays a gap if it is measured every time the
prompt changes.

## check_grounding.py

Flags content words in a generated script that appear nowhere in the source
notes. Deterministic, no model call, runs in CI.

```bash
python3 benchmark/check_grounding.py --all
```

```bash
python3 benchmark/check_grounding.py server/data/notes/<id>.json server/data/podcasts/<id>/status.json
```

Exit status is 1 when anything is flagged.

It handles the things that would otherwise drown the signal: acronyms the notes
use are credited against their spelled-out form in the script (`ETC` covers
"electron transport chain"), TTS letter-spacing is collapsed (`N A D H` →
`NADH`), `2×` in the notes covers "twice", and a stoplist absorbs ordinary
English and the hosts' own framing.

It is a flagger, not a judge. Read the list; don't score it blindly.

### Current result on the stored samples

```
p_2b4b478fe5ef  ·  3 lines
  line 2: "It runs inside the mitochondria, twice for every glucose molecule."
    not in the notes: mitochondria, molecule
1 flagged line across 3 podcasts
```

That is a real leak, not a false positive. Those notes read in full:

```
Krebs cycle = citric acid cycle
runs 2× per glucose
makes NADH + FADH2 → feed ETC
releases CO2 [unclear]
```

Mitochondria is true, and it is nowhere on the page. `SCRIPT_PROMPT` in
`server/buddy/llm.py` already says *"Use only facts that are in the notes.
Never add facts, examples or numbers that are not there"* — and the model did
it anyway. Prompt rules alone do not hold this line, which is the argument for
keeping a check that runs on every build.

## The tension to resolve first

A narrator that *teaches* rather than recites needs exactly what that rule
forbids: analogies, context, a worked example, a reason the fact matters. You
cannot have both "never add anything" and "teach me this."

So "added" should become a deliberate, labelled category rather than an
accident. Two grades of line:

- **from the notes** — the student's own material, verbatim-faithful
- **added to explain it** — scaffolding the narrator brought in

The student is told which is which. The trust property survives, teaching
becomes possible, and this script keeps working: it stops being a pass/fail
gate and becomes the measurement of how much was added and where. Grade the
two bands separately — a leak in a "from the notes" line is still a bug.

## The ten questions

If a chat surface ships, ask these of both products against the same source,
in one session, in order, with no follow-ups. Five the notes answer, four the
model certainly knows but the notes never state, one where the notes are
partially informative and the only correct answer flags the gap.

| # | Question | Expected |
|---|---|---|
| 1 | What are the outputs of stage one? | Answer |
| 2 | Why do leaves look green? | Answer |
| 3 | Which pages do I read before Thursday? | Answer |
| 4 | What did the professor say is on the exam? | Answer |
| 5 | How many electrons are released when water is split? | Answer |
| 6 | What are the products of the Calvin cycle? | **Refuse** |
| 7 | Who is the Calvin cycle named after? | **Refuse** |
| 8 | What is the chemical formula for glucose? | **Refuse** |
| 9 | Does photosynthesis happen at night? | **Refuse** |
| 10 | What wavelength does chlorophyll b absorb? | **Hedge** |

Two points each: correct verdict and correct content, 1 for correct verdict
with vague content, 0 for answering a Refuse from world knowledge or refusing
an Answer. Maximum 20. Questions 6–9 are where the score is won or lost.

`source-note.txt` is the matching source. Use it as the only source in a fresh
notebook on the NotebookLM side; a second source invalidates the run.

## Where we expect to win and lose

**Win:** grounding, because NotebookLM will not refuse. Format choice — three
briefs against NotebookLM's one. Chapters, if they ship; an Audio Overview is
one unseekable block.

**Lose, today:** voice naturalness over a long episode, and the fact that
NotebookLM's hosts genuinely interrupt and react to each other. Our lines
alternate strictly and are rendered one at a time with a fixed 0.35s pause
(`server/buddy/audio.py`), so the seams are audible where theirs are not.
