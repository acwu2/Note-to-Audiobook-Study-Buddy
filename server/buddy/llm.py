"""Every model call: fixed prompts, JSON out, temperature 0, retry on rate limits."""

import logging
import os
import re
import time
from enum import Enum

from pydantic import BaseModel, ValidationError

from . import config, fake
from .formats import FORMATS, WORDS_PER_MINUTE, PipelineError

log = logging.getLogger("buddy.llm")

# ---- Prompts (fixed; bump config.PIPELINE_VERSION when you change one) ----

TRANSCRIBE_PROMPT = """Transcribe the handwritten notes in this file exactly, in reading order.
Rules:
- Plain text only. No markdown, no commentary.
- Keep the line breaks as they are on the page.
- If you cannot read a word, write [unclear] in its place. Never guess.
- Return one entry per page. A photo is one page."""

OPTIONS_PROMPT = """These are a student's transcribed notes. Say what they are about, and title three podcast episodes made only from them.
- topic: what the notes cover, in at most 6 words.
- full_episode_title: an episode covering everything in the notes, at most 8 words.
- quick_recap_title: a short recap of the key facts, at most 8 words.
- deep_dive_topic: the one sub-topic the notes cover in the most detail, in at most 6 words.
- deep_dive_title: an episode about only that sub-topic, at most 8 words.
Use only what the notes say. Ignore anything marked [unclear]. Plain words, no quotation marks.

Notes:
{notes}"""

SCRIPT_PROMPT = """Write a two-host audio lesson from a student's notes.
Hosts: Heart and Michael. They take turns, and Heart speaks first.
Lesson: {label}. {brief}
Length: at most {words} words in total. Shorter is fine when the notes are short. Never pad.

This is a lesson someone studies from, not an episode they listen to. The test is
whether a student knows the material better at the end than at the start. Reading
the notes aloud in a friendly voice fails that test.

Every line has a role, and the lesson must have a shape:
- "hook": why this matters, or where it sits in the bigger picture. Open with one.
- "teach": the explanation itself. One idea per line. Build in the order that makes
  the ideas easiest to learn, not necessarily the order they were written down.
- "check": a question put straight to the student, who is given silence to answer
  out loud before the lesson continues. Ask about something already taught. Ask real
  questions with real answers, never "does that make sense?".
- "answer": the answer to the check immediately before it. Confirm, then move on.
- "recap": pull the thread together at the end. Finish with one.

Rules for the shape:
- Every "check" is followed immediately by its "answer".
- Space the checks out. Teach something before you test it.
- A lesson of more than about six lines has at least two checks.
- Never two "hook" lines in a row, and never open with a check.

Every line says where its content came from, and the student is shown those labels.
Be strict about this; it is the whole promise of the product.
- source "notes": every fact, name, number and relationship in the line is in the notes
  below. This is the student's own material, read back to them.
- source "added": the line brings in something the notes do not say — context, an
  analogy, a worked example, why a fact matters, or the meaning of a term the notes
  use without explaining.

Rules:
- Prefer "notes" lines. Add only what a student genuinely needs in order to understand
  the notes. This is not an invitation to pad with background.
- Never let an unsourced fact sit inside a "notes" line. If a line would mix the two,
  split it into one of each.
- Everything in an "added" line must be true and must never contradict the notes.
- Skip anything marked [unclear]. Do not guess what it says.
- Write for the ear: spell out symbols and abbreviations ("→" becomes "leads to", "e.g." becomes "for example", "~50%" becomes "about fifty percent", "2×" becomes "twice").
- Plain spoken sentences. No stage directions, sound effects, emoji or markdown.
- Each line is one or two sentences.

Also divide the lesson into chapters the listener can jump between.
- Between two and seven chapters, in order, the first starting at line 0.
- A chapter starts where a new idea begins, never in the middle of one, and never
  between a check and its answer.
- Title each in two to five words, using the notes' own vocabulary.

Notes:
{notes}"""


# ---- Response shapes ----


class Page(BaseModel):
    text: str


class Transcription(BaseModel):
    pages: list[Page]


class Options(BaseModel):
    topic: str
    full_episode_title: str
    quick_recap_title: str
    deep_dive_topic: str
    deep_dive_title: str


class Host(str, Enum):
    HEART = "Heart"
    MICHAEL = "Michael"


class Source(str, Enum):
    """Where a line's content came from. Shown to the student."""

    NOTES = "notes"
    ADDED = "added"


class Role(str, Enum):
    """What a line is doing in the lesson. Drives pacing and the transcript view."""

    HOOK = "hook"      # why this matters, where it sits
    TEACH = "teach"    # the explanation itself
    CHECK = "check"    # a question put to the student; silence follows
    ANSWER = "answer"  # the answer, after the pause
    RECAP = "recap"    # consolidation at the end


class Line(BaseModel):
    host: Host
    text: str
    source: Source = Source.NOTES
    role: Role = Role.TEACH


class ChapterPlan(BaseModel):
    title: str
    startLine: int


class Script(BaseModel):
    lines: list[Line]
    chapters: list[ChapterPlan] = []


# ---- Calls ----

_client = None
_RETRY_CODES = {429, 500, 502, 503, 504}


def _gemini():
    global _client
    if _client is None:
        if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
            raise PipelineError(
                "The server has no Gemini API key. Add GEMINI_API_KEY to server/.env, "
                "or start it with FAKE_AI=1 to test without one."
            )
        from google import genai

        _client = genai.Client()
    return _client


def _generate(contents, schema: type[BaseModel]) -> BaseModel:
    from google.genai import errors, types

    cfg = types.GenerateContentConfig(
        temperature=0,
        seed=0,
        response_mime_type="application/json",
        response_schema=schema,
    )
    delay = 2.0
    for attempt in range(6):
        try:
            resp = _gemini().models.generate_content(
                model=config.GEMINI_MODEL, contents=contents, config=cfg
            )
        except errors.APIError as e:
            if e.code in _RETRY_CODES and attempt < 5:
                log.warning("Gemini returned %s; retrying in %.0fs", e.code, delay)
                time.sleep(delay)
                delay = min(delay * 2, 30)
                continue
            if e.code == 429:
                raise PipelineError(
                    "The free Gemini tier is busy right now. Wait a minute and try again."
                ) from e
            if e.code in (401, 403):
                raise PipelineError("The server's Gemini API key was rejected.") from e
            raise PipelineError("The AI service couldn't handle this request.") from e
        if isinstance(resp.parsed, schema):
            return resp.parsed
        try:
            return schema.model_validate_json(resp.text or "")
        except ValidationError as e:
            raise PipelineError("The AI's answer came back in the wrong shape.") from e
    raise PipelineError("The AI service didn't answer. Try again in a minute.")


def transcribe(data: bytes, mime: str) -> list[str]:
    """One uploaded file → the text of each page on it."""
    if config.FAKE_AI:
        return fake.transcribe(data, mime)
    from google.genai import types

    part = types.Part.from_bytes(data=data, mime_type=mime)
    result = _generate([part, TRANSCRIBE_PROMPT], Transcription)
    return [p.text.strip() for p in result.pages]


def _notes_block(transcripts: list[str]) -> str:
    return "\n\n".join(f"[Page {i + 1}]\n{t}" for i, t in enumerate(transcripts))


def name_options(transcripts: list[str]) -> Options:
    if config.FAKE_AI:
        return Options(**fake.OPTIONS)
    return _generate(OPTIONS_PROMPT.format(notes=_notes_block(transcripts)), Options)


MINUTES = re.compile(r"(\d{1,3})\s*(?:-|\s)?\s*(?:minute|minutes|min|mins)\b", re.I)


def minutes_in(request: str, default: int = 5) -> int:
    """Pull a length out of the student's own words: '5 minute overview' -> 5."""
    m = MINUTES.search(request or "")
    if not m:
        return default
    return max(1, min(20, int(m.group(1))))


def write_script(
    transcripts: list[str],
    format_id: str | None,
    topic: str | None,
    request: str = "",
) -> tuple[list[Line], list[ChapterPlan]]:
    """Write the lesson from a preset format, or from the student's own request."""
    if request.strip():
        label = "Your request"
        brief = (
            "The student asked for this in their own words, so follow it as closely as "
            "the notes allow:\n\n"
            f'"{request.strip()}"\n\n'
            "Honour what they asked for in shape as well as in content. If they asked "
            "for an overview, do not go deep on one part. If they named a topic, stay "
            "on it. If the notes cannot support part of the request, cover what they do "
            "support and do not invent the rest."
        )
        minutes = minutes_in(request)
    else:
        fmt = FORMATS[format_id]
        label, minutes = fmt.label, fmt.minutes
        brief = fmt.brief.format(topic=topic or "the main topic")

    if config.FAKE_AI:
        key = format_id if format_id in fake.SCRIPTS else "full_episode"
        lines = [Line(**line) for line in fake.SCRIPTS[key]]
        return _repair_arc(lines), _fake_chapters(lines)

    prompt = SCRIPT_PROMPT.format(
        label=label,
        brief=brief,
        words=minutes * WORDS_PER_MINUTE,
        notes=_notes_block(transcripts),
    )
    script = _generate(prompt, Script)
    lines = [line for line in script.lines if line.text.strip()][:200]
    if not lines:
        raise PipelineError("The AI wrote an empty script. Try a clearer photo.")
    lines = _repair_arc(lines)
    return lines, _clean_chapters(script.chapters, lines)


def _fake_chapters(lines: list[Line]) -> list[ChapterPlan]:
    """A plausible plan for FAKE_AI: start a chapter at each hook and each check."""
    plan = [ChapterPlan(title="Where this fits", startLine=0)]
    for i, line in enumerate(lines):
        if i and line.role is Role.CHECK:
            plan.append(ChapterPlan(title=f"Check {len(plan)}", startLine=i))
    return _clean_chapters(plan, lines)


def _clean_chapters(plan: list[ChapterPlan], lines: list[Line]) -> list[ChapterPlan]:
    """Keep a chapter list only if it is sound. A wrong chapter is worse than none.

    Must ascend, not repeat, stay in range, start at 0, and never split a check
    from its answer — landing there would drop the listener into an answer to a
    question they never heard.
    """
    out: list[ChapterPlan] = []
    for ch in plan or []:
        title = re.sub(r"\s+", " ", str(ch.title or "")).strip()[:64]
        start = int(ch.startLine)
        if not title or not (0 <= start < len(lines)):
            continue
        if out and start <= out[-1].startLine:
            continue
        if lines[start].role is Role.ANSWER:
            continue
        out.append(ChapterPlan(title=title, startLine=start))
    if len(out) < 2:
        return []
    out[0] = ChapterPlan(title=out[0].title, startLine=0)
    return out[:7]


def _repair_arc(lines: list[Line]) -> list[Line]:
    """Keep the lesson shape sound even when the model drifts from the brief.

    Only fixes what would actually mislead a listener: a question with no answer
    after it, or an answer with no question before it. Both leave the student
    sitting in silence waiting for something that never comes.
    """
    # Order matters: each pass can create work for the next, so they run from the
    # start of the lesson outwards.

    # 1. A lesson never opens on a question.
    if lines and lines[0].role is Role.CHECK:
        lines[0] = lines[0].model_copy(update={"role": Role.HOOK})

    # 2. An ANSWER only makes sense directly after a CHECK.
    for i, line in enumerate(lines):
        if line.role is Role.ANSWER and (i == 0 or lines[i - 1].role is not Role.CHECK):
            lines[i] = line.model_copy(update={"role": Role.TEACH})

    # 3. A CHECK must be answered. If the model forgot, the question still works as
    #    teaching, and the student is not left hanging in a 3.5 second silence.
    for i, line in enumerate(lines):
        if line.role is Role.CHECK:
            answered = i + 1 < len(lines) and lines[i + 1].role is Role.ANSWER
            if not answered:
                lines[i] = line.model_copy(update={"role": Role.TEACH})

    return lines
