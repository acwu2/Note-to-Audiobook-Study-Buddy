"""Every model call: fixed prompts, JSON out, temperature 0, retry on rate limits."""

import logging
import os
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

SCRIPT_PROMPT = """Write a two-host podcast script that teaches a student their own notes.
Hosts: Heart and Michael. They take turns, and Heart speaks first.
Episode: {label}. {brief}
Length: at most {words} words in total. Shorter is fine when the notes are short. Never pad.

Teach, do not recite. Explain the notes so that a student who is new to the subject
can follow them, and say why each thing matters.

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


class Line(BaseModel):
    host: Host
    text: str
    source: Source = Source.NOTES


class Script(BaseModel):
    lines: list[Line]


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


def write_script(transcripts: list[str], format_id: str, topic: str | None) -> list[Line]:
    fmt = FORMATS[format_id]
    if config.FAKE_AI:
        return [Line(**line) for line in fake.SCRIPTS[format_id]]
    prompt = SCRIPT_PROMPT.format(
        label=fmt.label,
        brief=fmt.brief.format(topic=topic or "the main topic"),
        words=fmt.minutes * WORDS_PER_MINUTE,
        notes=_notes_block(transcripts),
    )
    script = _generate(prompt, Script)
    lines = [line for line in script.lines if line.text.strip()][:200]
    if not lines:
        raise PipelineError("The AI wrote an empty script. Try a clearer photo.")
    return lines
