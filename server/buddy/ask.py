"""A free question, answered only from the student's notes, by the podcast's hosts.

Grounding is the point. The notes are the only context, a line the answer says it
came from is checked against them, and "it isn't in your notes" is a valid answer.

The answer is a short exchange between Heart and Michael, rendered with the same
voices, trimming and pacing as the lessons, so it sounds like part of the same show.
"""

from __future__ import annotations

import hashlib
import re
import threading
import unicodedata

from pydantic import BaseModel

from . import audio, config, llm, store
from .formats import PipelineError

MAX_QUESTION_CHARS = 500
MAX_LINES = 4

# Kokoro is loaded once and the lesson worker renders on its own thread. Answers
# render one at a time so two requests never drive the same pipeline at once.
_render_lock = threading.Lock()

ASK_PROMPT = """You are two study-buddy hosts, Heart and Michael, answering one question from a student.
The only thing you know is the student's notes below.

- Answer using the notes alone. Never use outside knowledge to fill a gap, even when you are
  confident about the subject.
- If the notes do not contain the answer, say so plainly and name what they do cover that is
  closest. Set found to false and leave quote empty.
- If the notes only partly answer it, give the part they support, say what they leave out,
  and set found to true.
- If the student asks for a simpler explanation, use plainer words, but every fact must still
  come from the notes.

Write it as a short spoken exchange, between two and four lines. Heart speaks first. The second
host adds or confirms something, or says what the notes leave out; neither host just repeats the
other. Each line is one or two sentences, written for the ear: no markdown, spell out symbols,
numbers and abbreviations the way a person says them.

quote: the shortest phrase copied exactly from the notes that supports the answer. Copy it as
written, including abbreviations and symbols; do not tidy it. Empty when found is false.

Notes:
{notes}

Student's question:
{question}"""


class AskLine(BaseModel):
    host: llm.Host
    text: str


class AskReply(BaseModel):
    lines: list[AskLine]
    found: bool
    quote: str = ""


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or "")).lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def answer_id_for(note_id: str, question: str, podcast_id: str = "") -> str:
    """Same notes, same question, same answer — cached like everything else."""
    key = f"{store._mode()}|ask|{note_id}|{podcast_id}|{_norm(question)}"
    return "a_" + hashlib.sha256(key.encode()).hexdigest()[:12]


def _dir(answer_id: str):
    return config.DATA_DIR / "answers" / answer_id


def audio_path(answer_id: str):
    return _dir(answer_id) / "audio.mp3"


def load(answer_id: str) -> dict | None:
    if not re.fullmatch(r"a_[0-9a-f]{12}", answer_id or ""):
        return None
    return store._read_json(_dir(answer_id) / "data.json")


def _locate(quote: str, script: list[dict] | None) -> list[int]:
    """Which line of the lesson said it, so the answer can replay that stretch."""
    if not quote or not script:
        return []
    qt = {w for w in _norm(quote).split() if len(w) > 2}
    if len(qt) < 2:
        return []
    best, best_score = -1, 0.0
    for i, line in enumerate(script):
        words = set(_norm(line.get("text", "")).split())
        score = len(qt & words) / len(qt)
        if score > best_score:
            best, best_score = i, score
    return [best] if best_score >= 0.6 else []


def answer(note: dict, question: str, podcast_id: str = "", script: list[dict] | None = None) -> dict:
    question = re.sub(r"\s+", " ", question or "").strip()
    if not question:
        raise PipelineError("Type a question first.")
    if len(question) > MAX_QUESTION_CHARS:
        raise PipelineError(f"Keep the question under {MAX_QUESTION_CHARS} characters.")

    answer_id = answer_id_for(note["noteId"], question, podcast_id)
    cached = load(answer_id)
    if cached:
        return cached

    transcripts = [p["transcript"] for p in note["pages"]]
    if config.FAKE_AI:
        reply = AskReply(
            lines=[
                AskLine(host=llm.Host.HEART, text="This is a sample answer, not one written from your notes."),
                AskLine(host=llm.Host.MICHAEL, text="Add a Gemini key and you will get a real one."),
            ],
            found=False,
        )
    else:
        prompt = ASK_PROMPT.format(notes=llm._notes_block(transcripts), question=question)
        reply = llm._generate(prompt, AskReply)

    lines = [
        {"host": l.host.value, "text": re.sub(r"\s+", " ", l.text).strip()}
        for l in reply.lines
        if l.text.strip()
    ][:MAX_LINES]
    if not lines:
        raise PipelineError("The AI gave no answer. Try asking it another way.")

    # A quote the notes do not contain is worse than none: it reads as evidence.
    found = bool(reply.found)
    quote = reply.quote.strip()
    if not found or len(_norm(quote)) < 4 or _norm(quote) not in _norm(" ".join(transcripts)):
        quote = ""

    doc = {
        "answerId": answer_id,
        "noteId": note["noteId"],
        "question": question,
        "lines": lines,
        "answer": " ".join(l["text"] for l in lines),
        "found": found,
        "quote": quote,
        "scriptLines": _locate(quote, script),
        "audioUrl": f"/api/answers/{answer_id}/audio.mp3",
    }
    store._write_json(_dir(answer_id) / "data.json", doc)
    return doc


def ensure_audio(doc: dict):
    """Render the answer in the hosts' voices once, then serve the file."""
    path = audio_path(doc["answerId"])
    if path.exists():
        return path
    with _render_lock:
        if not path.exists():
            audio.render([(l["host"], l["text"], "teach") for l in doc["lines"]], path)
    return path
