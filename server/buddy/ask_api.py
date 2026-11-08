"""Routes for free-form questions. Mounted from app.py with two lines."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import ask, store
from .formats import PipelineError

router = APIRouter()


class AskRequest(BaseModel):
    noteId: str
    question: str
    # When the student is listening to a lesson, a grounded answer also says
    # which line of it covered the point, so the player can replay that.
    podcastId: str | None = None


@router.post("/api/ask")
def ask_question(req: AskRequest) -> dict:
    note = store.load_note(req.noteId)
    if note is None:
        raise HTTPException(404, "Those notes aren't on the server any more. Upload them again.")
    script = None
    if req.podcastId:
        loaded = store.load_script(req.podcastId)
        script = loaded[0] if loaded else None
    try:
        return ask.answer(note, req.question, req.podcastId or "", script)
    except PipelineError as e:
        raise HTTPException(400, str(e))


@router.get("/api/answers/{answer_id}/audio.mp3")
def answer_audio(answer_id: str, download: bool = False) -> FileResponse:
    doc = ask.load(answer_id)
    if doc is None:
        raise HTTPException(404, "That answer isn't on the server any more. Ask again.")
    try:
        path = ask.ensure_audio(doc)
    except PipelineError as e:
        raise HTTPException(500, str(e))
    return FileResponse(
        path,
        media_type="audio/mpeg",
        filename="answer.mp3",
        content_disposition_type="attachment" if download else "inline",
    )
