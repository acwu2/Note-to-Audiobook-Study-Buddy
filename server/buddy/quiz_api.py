"""HTTP routes for the listen → quiz → weak-point deck loop.

Kept as a router in its own file so app.py needs two lines to mount it.

Error bodies are {"detail": "<sentence>"} like the rest of the API — see
contract/API.md. The sentence is what the student reads, so it says what
happened and what to do, never a status code.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from . import jobs, quiz, store
from .formats import PipelineError

router = APIRouter()


class AttemptBody(BaseModel):
    # {questionId: chosenIndex}. A question left out counts as unanswered.
    answers: dict[str, int] = {}


def _ready_lesson(podcast_id: str) -> list[dict]:
    """The script of a finished podcast, or the reason it cannot be quizzed yet."""
    status = jobs.status(podcast_id)
    if status is None:
        raise HTTPException(404, "No podcast with that id.")
    if status.get("status") != "ready":
        raise HTTPException(409, "Finish making the podcast before taking the quiz.")
    script = status.get("script") or []
    if not script:
        raise HTTPException(409, "That podcast has no script to quiz you on.")
    return script


@router.post("/api/podcasts/{podcast_id}/quiz")
async def create_quiz(podcast_id: str, count: int = 5) -> dict:
    """The quiz for a lesson, without the answers. Cached: same lesson, same quiz."""
    lesson = _ready_lesson(podcast_id)
    try:
        built = await run_in_threadpool(quiz.build_quiz, podcast_id, lesson, count)
    except PipelineError as e:
        raise HTTPException(502, str(e)) from e
    return quiz.public_quiz(built)


@router.get("/api/quizzes/{quiz_id}")
def get_quiz(quiz_id: str) -> dict:
    found = quiz.load_quiz(quiz_id)
    if found is None:
        raise HTTPException(404, "No quiz with that id.")
    return quiz.public_quiz(found)


@router.post("/api/quizzes/{quiz_id}/attempt")
def submit_attempt(quiz_id: str, body: AttemptBody) -> dict:
    """Grade an attempt. Marking happens here, so the page never holds the answers."""
    found = quiz.load_quiz(quiz_id)
    if found is None:
        raise HTTPException(404, "No quiz with that id.")
    attempt = quiz.grade(found, body.answers or {})
    quiz.save_attempt(attempt)
    return attempt


@router.get("/api/attempts/{attempt_id}")
def get_attempt(attempt_id: str) -> dict:
    found = quiz.load_attempt(attempt_id)
    if found is None:
        raise HTTPException(404, "No attempt with that id.")
    return found


@router.post("/api/attempts/{attempt_id}/flashcards")
async def create_deck(attempt_id: str) -> dict:
    """Cards for the gaps this attempt exposed.

    A clean sweep returns an empty deck rather than an error: nothing went wrong,
    there is just nothing to drill.
    """
    attempt = quiz.load_attempt(attempt_id)
    if attempt is None:
        raise HTTPException(404, "No attempt with that id.")
    lesson = _ready_lesson(attempt["podcastId"])
    try:
        deck = await run_in_threadpool(quiz.build_deck, attempt, lesson)
    except PipelineError as e:
        raise HTTPException(502, str(e)) from e
    return deck


@router.get("/api/decks/{deck_id}")
def get_deck(deck_id: str) -> dict:
    found = quiz.load_deck(deck_id)
    if found is None:
        raise HTTPException(404, "No deck with that id.")
    return found
