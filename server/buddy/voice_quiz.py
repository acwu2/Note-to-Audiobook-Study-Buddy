"""A spoken quiz: the questions read aloud with time to answer, and a judge for the reply.

The audio is its own output, not the lesson: Heart asks each question, Michael reads
the four options, then the file goes quiet for as long as the student asked for.
Each question is a chapter in the file, so an audiobook app can skip between them.

The student's answer comes back as a recording (any format a browser makes) or as
typed text. The model only maps what they said onto options A to D. It is never shown
which option is correct, and it does not decide right or wrong: the server compares the
pick with the key, and the feedback is the stored explanation. So the verdict cannot be
talked into a near-miss, and the explanation cannot contradict the verdict.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import tempfile
import threading
import unicodedata
from pathlib import Path

from pydantic import BaseModel, Field

from . import audio, audiobook, config, llm, store
from .formats import PipelineError

NARRATOR = "Heart"
READER = "Michael"
LETTERS = "ABCD"
MIN_ANSWER_SECONDS, MAX_ANSWER_SECONDS = 3, 30
MAX_RECORDING_BYTES = 25 * 1024 * 1024
MAX_RECORDING_SECONDS = 15 * 60

_render_lock = threading.Lock()


# ---- Making the text speakable ----------------------------------------------

_SUP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻", "0123456789+-")
_SUB = str.maketrans("₀₁₂₃₄₅₆₇₈₉ₐₑₒₓ₊₋", "0123456789aeox+-")
_SPOKEN_DIGITS = {"1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine"}


def speakable(text: str) -> str:
    """Read a symbol the way a person says it. Not exhaustive: it covers what notes use."""
    t = str(text or "")
    # 10⁻¹⁴ / 10^-14 -> "ten to the negative fourteen". The exponent has to be
    # explicit (a caret or superscript digits) so "100%" stays one hundred.
    t = re.sub(r"10\s*\^\s*([⁻\-−]?)(\d+)", lambda m: "ten to the " + ("negative " if m.group(1) else "") + m.group(2), t)
    t = re.sub(r"10([⁻]?)([⁰¹²³⁴⁵⁶⁷⁸⁹]+)", lambda m: "ten to the " + ("negative " if m.group(1) else "") + m.group(2).translate(_SUP), t)
    # ions and charges: H⁺ -> "H plus", OH⁻ -> "O H minus"
    t = re.sub(r"([A-Za-z\]\)])([⁺⁻])", lambda m: m.group(1) + (" plus" if m.group(2) == "⁺" else " minus"), t)
    t = t.translate(_SUP).translate(_SUB)
    t = re.sub(r"\[([^\[\]]+)\]", r"the concentration of \1", t)
    for sym, said in (("×", " times "), ("≈", " approximately "), ("→", " leads to "), ("±", " plus or minus "),
                      ("°C", " degrees Celsius"), ("%", " percent"), (" = ", " equals "), ("=", " equals "), (" + ", " plus ")):
        t = t.replace(sym, said)
    t = re.sub(r"\bOH\b", "O H", t)
    return re.sub(r"\s+", " ", t).strip()


# ---- Building the audio -----------------------------------------------------


def voice_quiz_id_for(review_id: str, answer_seconds: int) -> str:
    key = f"{store._mode()}|voicequiz|{review_id}|{answer_seconds}"
    return "sq_" + hashlib.sha256(key.encode()).hexdigest()[:12]


def _dir(quiz_id: str) -> Path:
    return config.DATA_DIR / "voicequizzes" / quiz_id


def audio_path(quiz_id: str) -> Path:
    return _dir(quiz_id) / "audio.mp3"


def load(quiz_id: str) -> dict | None:
    if not re.fullmatch(r"sq_[0-9a-f]{12}", quiz_id or ""):
        return None
    return store._read_json(_dir(quiz_id) / "data.json")


def build(review: dict, built_quiz: dict, answer_seconds: int = 10) -> dict:
    answer_seconds = max(MIN_ANSWER_SECONDS, min(MAX_ANSWER_SECONDS, int(answer_seconds)))
    quiz_id = voice_quiz_id_for(review["reviewId"], answer_seconds)
    cached = load(quiz_id)
    if cached and audio_path(quiz_id).exists():
        return cached

    questions = built_quiz["questions"]
    n = len(questions)
    title = review.get("title", "your notes")
    items: list[tuple] = [
        (NARRATOR,
         f"Quiz time. {n} question{'s' if n != 1 else ''} on {speakable(title)}. After each one you have "
         f"{answer_seconds} seconds to answer out loud. Say the letter, or say the answer in your own words.",
         "front")
    ]
    tags: list[tuple] = [("intro",)]
    for i, q in enumerate(questions):
        items.append((NARRATOR, f"Question {i + 1}. {speakable(q['q'])}", "ask-q"))
        tags.append(("question", i))
        options = " ".join(f"{LETTERS[k]}. {speakable(o)}." for k, o in enumerate(q["options"]))
        # The role carries the answer window, so the silence after the options is exactly it.
        items.append((READER, options, f"ask:{answer_seconds}"))
        tags.append(("options", i))
    items.append((NARRATOR, "That is the end of the quiz. Upload your recording to find out how you did.", "end"))
    tags.append(("end",))

    path = audio_path(quiz_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _render_lock:
        r = audio.render(items, path)

    starts = {}
    for tag, start in zip(tags, r.line_starts):
        starts[tag] = start
    end_start = starts[("end",)]
    out_questions = []
    for i, q in enumerate(questions):
        opts_start = starts[("options", i)]
        next_start = starts[("question", i + 1)] if i + 1 < n else end_start
        out_questions.append({
            "id": q["id"],
            "number": i + 1,
            "q": q["q"],
            "options": q["options"],
            "startSeconds": starts[("question", i)],
            "optionsStartSeconds": opts_start,
            # The silence the student answers in: the whole gap after the options.
            "answerStartSeconds": round(next_start - answer_seconds, 2),
            "answerEndSeconds": next_start,
        })

    marks = [("Introduction", 0.0)] + [(f"Question {x['number']}", x["startSeconds"]) for x in out_questions] + [("End of quiz", end_start)]
    ffmeta = path.with_suffix(".ffmeta")
    audiobook._write_ffmeta(ffmeta, f"Quiz: {title}", title, marks, r.seconds)
    audiobook._tag(path, ffmeta)

    doc = {
        "quizId": quiz_id,
        "reviewId": review["reviewId"],
        "title": f"Quiz: {title}",
        "answerSeconds": answer_seconds,
        "seconds": r.seconds,
        "questions": out_questions,
        "audioUrl": f"/api/voice-quizzes/{quiz_id}/audio.mp3",
    }
    store._write_json(_dir(quiz_id) / "data.json", doc)
    return doc


# ---- Judging the reply ------------------------------------------------------


class Heard(BaseModel):
    questionId: str
    heard: str = ""  # their words for this question, short; empty when they said nothing
    # A letter, not an index. Asked for an index, the model counted from 0 for audio and
    # from 1 for typed text; a letter cannot be miscounted.
    letter: str = Field("", description='"A", "B", "C" or "D": the option they chose. "" when they gave no answer or it matches no option.')


class HeardAll(BaseModel):
    answers: list[Heard]


JUDGE_PROMPT = """A student took a spoken quiz. The quiz read each question and four options (A, B, C, D), then
paused for them to answer. Below is what they said back, in order, followed by the questions.

For each question, work out which option the student chose.
- They may say a letter, "option B", the text of an option, or the idea in their own words. Pick the
  option that matches what they committed to.
- If they changed their mind, use the answer they ended on.
- If they said nothing, said they did not know, or said something that matches none of the options,
  leave letter empty.
- If a quiz voice is audible in the recording, ignore it. Only the student's own answers count.
- letter: the option they chose, as A, B, C or D.
- heard: what the student said for this question, copied briefly. Empty when they said nothing.
- Use the question ids exactly as given. Return one entry per question, in order.
- Do not judge whether an answer is right. You are only working out what they chose.

{reply}

Questions:
{questions}"""


def _to_mp3(data: bytes) -> bytes:
    """Any browser recording, as small mono mp3. Rejects what is not audio or runs too long."""
    if not shutil.which("ffmpeg"):
        raise PipelineError("The server needs ffmpeg to read recordings. Install it with: brew install ffmpeg")
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp) / "in", Path(tmp) / "out.mp3"
        src.write_bytes(data)
        try:
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-t", str(MAX_RECORDING_SECONDS),
                            "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k", str(dst)], check=True, timeout=120)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            raise PipelineError("That doesn't look like an audio recording. Try recording it again.") from e
        out = dst.read_bytes()
    if len(out) < 1500:
        raise PipelineError("That recording is empty. Try recording it again.")
    return out


_FILLER = set(
    "the a an of to is are was be it its and or in on for with that this which as at by from not no "
    "i you we they he she my your me um uh hmm well so then think maybe guess honestly really just "
    "answer option letter question one two three four five wait actually".split()
)


def _content(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKD", text).lower()) if w not in _FILLER and len(w) > 1}


def supported(heard: str, picked: int, options: list[str]) -> bool:
    """Is the pick backed by what the student actually said?

    The model maps speech onto options, and a model can be wrong in a way that earns
    credit: given "I honestly do not know this one" it picked the correct option. So a
    pick only stands if the words support it, either way:
      - the last standalone capital letter A-D they said is that letter ("I think D, no
        wait, actually C" ends on C), or
      - their words overlap the picked option more than any other, and cover enough of it.
    "I don't know" says no letter and shares nothing with any option, so it is a blank.
    """
    if not heard.strip() or not (0 <= picked < len(options)):
        return False
    said = []
    for m in re.finditer(r"\b([A-D])\b", heard):
        if m.group(1) == "A":
            # "A buffer resists change" is an article. A capital A only counts as the
            # letter when it ends the thought, or something like "option" or "I think"
            # comes before it.
            rest = heard[m.end():].strip()
            before = heard[: m.start()].lower().rstrip()
            says_letter = re.search(r"(option|letter|answer|choose|pick|think|say|is|it's|go with)$", before)
            if rest[:1].islower() and not says_letter and not rest.lower().startswith(("no wait", "actually")):
                continue
        said.append(m.group(1))
    if said and said[-1] == LETTERS[picked]:
        return True
    words = _content(heard)
    if not words:
        return False
    overlaps = [len(words & _content(o)) for o in options]
    mine = overlaps[picked]
    others = max((v for k, v in enumerate(overlaps) if k != picked), default=0)
    return mine >= 2 and mine > others and mine / max(1, len(words)) >= 0.4


def _fake_heard(questions: list[dict], key: dict[str, int]) -> HeardAll:
    """FAKE_AI: right, then wrong, then blanks. Enough to build a UI against."""
    out = []
    for i, q in enumerate(questions):
        if i == 0:
            out.append(Heard(questionId=q["id"], heard="sample answer", letter=LETTERS[key[q["id"]]]))
        elif i == 1:
            out.append(Heard(questionId=q["id"], heard="sample wrong answer", letter=LETTERS[(key[q["id"]] + 1) % 4]))
        else:
            out.append(Heard(questionId=q["id"], heard="", letter=""))
    return HeardAll(answers=out)


def judge(doc: dict, built_quiz: dict, recording: bytes | None, text: str = "") -> dict:
    questions = built_quiz["questions"]
    key = {q["id"]: q["answer"] for q in questions}
    why = {q["id"]: q.get("why", "") for q in questions}

    if not recording and not (text or "").strip():
        raise PipelineError("Record your answers, or type them, then send them in.")

    if config.FAKE_AI:
        heard = _fake_heard(questions, key)
    else:
        listing = "\n\n".join(
            f"[{q['id']}] {q['q']}\n" + "\n".join(f"  {LETTERS[k]}. {o}" for k, o in enumerate(q["options"]))
            for q in questions
        )
        if recording:
            from google.genai import types

            part = types.Part.from_bytes(data=_to_mp3(recording), mime_type="audio/mpeg")
            contents = [part, JUDGE_PROMPT.format(reply="The student's recorded answers are the attached audio.", questions=listing)]
        else:
            contents = JUDGE_PROMPT.format(reply=f"The student typed their answers:\n{text.strip()}", questions=listing)
        heard = llm._generate(contents, HeardAll)

    by_id = {h.questionId: h for h in heard.answers}
    results, answers = [], {}
    for i, q in enumerate(questions):
        h = by_id.get(q["id"])
        letter = (h.letter if h else "").strip().upper()[:1]
        picked = LETTERS.index(letter) if letter in LETTERS and LETTERS.index(letter) < len(q["options"]) else None
        if picked is not None and not supported(h.heard if h else "", picked, q["options"]):
            picked = None  # the model chose, but nothing the student said backs it
        correct = picked == q["answer"]
        if picked is not None:
            answers[q["id"]] = picked
        right = q["options"][q["answer"]]
        if picked is None:
            feedback = f"No answer heard. It was {LETTERS[q['answer']]}: {right}. {why[q['id']]}".strip()
        elif correct:
            feedback = f"Right. {why[q['id']]}".strip()
        else:
            feedback = f"Not quite. It was {LETTERS[q['answer']]}: {right}. {why[q['id']]}".strip()
        results.append({
            "questionId": q["id"], "number": i + 1, "q": q["q"], "options": q["options"],
            "heard": (h.heard if h else "").strip(), "picked": picked, "skipped": picked is None,
            "correct": correct, "answer": q["answer"], "feedback": feedback,
        })
    return {
        "quizId": doc["quizId"], "reviewId": doc["reviewId"],
        "score": sum(1 for r in results if r["correct"]), "total": len(results),
        "results": results,
        # In the shape POST /api/reviews/{id}/attempt takes, to turn the misses into a deck.
        "answers": answers,
    }
