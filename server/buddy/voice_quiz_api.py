"""Routes for the spoken quiz. Mounted from app.py with two lines."""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import review_quiz, store, voice_quiz
from .formats import PipelineError

router = APIRouter()


class VoiceQuizRequest(BaseModel):
    # How long the audio waits after each question. Their pace, not ours.
    answerSeconds: int = 10


def _built(doc: dict) -> dict:
    review = store.load_review(doc["reviewId"])
    if review is None:
        raise HTTPException(404, "That review has expired. Make a new one from your notes.")
    return review_quiz.build(doc["reviewId"], review["points"])


@router.post("/api/reviews/{review_id}/voice-quiz")
def create_voice_quiz(review_id: str, req: VoiceQuizRequest | None = None) -> dict:
    """Voice the review's quiz. The first request renders the audio, about half a minute."""
    review = store.load_review(review_id)
    if review is None:
        raise HTTPException(404, "That review has expired. Make a new one from your notes.")
    try:
        built = review_quiz.build(review_id, review["points"])
        return voice_quiz.build(review, built, (req.answerSeconds if req else 10))
    except PipelineError as e:
        raise HTTPException(400, str(e))


@router.get("/api/voice-quizzes/{quiz_id}")
def get_voice_quiz(quiz_id: str) -> dict:
    doc = voice_quiz.load(quiz_id)
    if doc is None:
        raise HTTPException(404, "That quiz isn't on the server any more. Make it again.")
    return doc


@router.get("/api/voice-quizzes/{quiz_id}/audio.mp3")
def voice_quiz_audio(quiz_id: str, download: bool = False) -> FileResponse:
    doc = voice_quiz.load(quiz_id)
    path = voice_quiz.audio_path(quiz_id)
    if doc is None or not path.exists():
        raise HTTPException(404, "That quiz isn't on the server any more. Make it again.")
    return FileResponse(path, media_type="audio/mpeg", filename="quiz.mp3",
                        content_disposition_type="attachment" if download else "inline")


@router.post("/api/voice-quizzes/{quiz_id}/judge")
async def judge_voice_quiz(
    quiz_id: str,
    recording: UploadFile | None = File(None),
    text: str = Form(""),
) -> dict:
    """Judge the student's answers: a recording of them speaking, or typed text."""
    doc = voice_quiz.load(quiz_id)
    if doc is None:
        raise HTTPException(404, "That quiz isn't on the server any more. Make it again.")
    data = None
    if recording is not None:
        data = await recording.read()
        if len(data) > voice_quiz.MAX_RECORDING_BYTES:
            raise HTTPException(413, "That recording is too large. Keep it under 25 MB.")
    try:
        return voice_quiz.judge(doc, _built(doc), data or None, text)
    except PipelineError as e:
        raise HTTPException(400, str(e))
