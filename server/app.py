"""Study Buddy API. Run from server/:  .venv/bin/uvicorn app:app --port 8000"""

import logging
import mimetypes
import re

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from buddy import config, jobs, llm, store
from buddy.formats import FORMAT_ORDER, FORMATS, PipelineError

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="Study Buddy API")


@app.exception_handler(RequestValidationError)
def malformed_request(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Keep every error body shaped {"detail": "<sentence>"} — see contract/API.md.

    FastAPI's default puts a list of validation objects in `detail`. The client
    checks `typeof detail === 'string'` and falls back to "The server answered
    422.", so without this the student loses every friendly message. Any other
    implementation of this API has to return the same shape.
    """
    missing = {tuple(e.get("loc", ())) for e in exc.errors() if e.get("type") == "missing"}
    if any("photos" in loc for loc in missing):
        message = "Add at least one photo of your notes."
    else:
        message = "That request was not in the shape the server expected."
    return JSONResponse(status_code=400, content={"detail": message})


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "fakeAi": config.FAKE_AI,
        "fakeTts": config.FAKE_TTS,
        "model": None if config.FAKE_AI else config.GEMINI_MODEL,
    }


# ---- 1 · Upload: read every page, then offer the fixed menu ----


def _build_note(note_id: str, files: list[tuple[bytes, str]]) -> dict:
    transcripts: list[str] = []
    for data, mime in files:
        transcripts.extend(llm.transcribe(data, mime))
    transcripts = [t for t in transcripts if t.strip()]
    if not transcripts:
        raise PipelineError("We couldn't find any writing in these photos. Try a clearer, closer photo.")

    named = llm.name_options(transcripts)
    titles = {
        "full_episode": named.full_episode_title,
        "quick_recap": named.quick_recap_title,
        "deep_dive": named.deep_dive_title,
    }
    options = []
    for format_id in FORMAT_ORDER:
        fmt = FORMATS[format_id]
        topic = named.deep_dive_topic.strip() if format_id == "deep_dive" else None
        options.append({
            "id": fmt.id,
            "label": fmt.label,
            "minutes": fmt.minutes,
            "title": titles[format_id].strip(),
            "description": fmt.description.format(topic=topic or ""),
            **({"topic": topic} if topic else {}),
        })

    note = {
        "noteId": note_id,
        "topic": named.topic.strip(),
        "pages": [{"transcript": t, "unclearCount": t.count("[unclear]")} for t in transcripts],
        "options": options,
    }
    store.save_note(note)
    return note


def _mime_of(upload: UploadFile) -> str:
    mime = (upload.content_type or "").lower()
    if mime in config.ALLOWED_TYPES:
        return mime
    guessed = (mimetypes.guess_type(upload.filename or "")[0] or "").lower()
    return guessed


@app.post("/api/notes")
async def create_note(photos: list[UploadFile] = File(...)) -> dict:
    if not photos:
        raise HTTPException(400, "Add at least one photo of your notes.")
    if len(photos) > config.MAX_FILES:
        raise HTTPException(400, f"Add at most {config.MAX_FILES} files at a time.")
    files: list[tuple[bytes, str]] = []
    for upload in photos:
        mime = _mime_of(upload)
        if mime not in config.ALLOWED_TYPES:
            raise HTTPException(415, "Only photos (JPG, PNG, WebP, HEIC) or PDFs.")
        data = await upload.read()
        if not data:
            raise HTTPException(400, f"{upload.filename or 'A file'} is empty.")
        if len(data) > config.MAX_FILE_BYTES:
            raise HTTPException(413, f"{upload.filename or 'A file'} is over 15 MB.")
        files.append((data, mime))

    note_id = store.note_id_for(files)
    cached = store.load_note(note_id)
    if cached:
        return cached
    try:
        return await run_in_threadpool(_build_note, note_id, files)
    except PipelineError as e:
        raise HTTPException(502, str(e)) from e


# ---- 2 · Pick: ids in, a job out ----


class PodcastRequest(BaseModel):
    noteId: str
    optionId: str | None = None
    request: str | None = None  # the student's own words; one of optionId | request


MAX_REQUEST_CHARS = 500


@app.post("/api/podcasts", status_code=202)
def create_podcast(req: PodcastRequest) -> dict:
    note = store.load_note(req.noteId)
    if note is None:
        raise HTTPException(404, "Those notes aren't on the server any more. Upload them again.")

    asked = (req.request or "").strip()
    if asked:
        if len(asked) > MAX_REQUEST_CHARS:
            raise HTTPException(400, f"Keep the request under {MAX_REQUEST_CHARS} characters.")
        # A request the student typed is its own option: same shape as a preset, so
        # everything downstream — status, caching, the job — stays unchanged.
        option = {
            "id": "custom",
            "label": "Your request",
            "title": asked if len(asked) <= 60 else asked[:57].rstrip() + "…",
            "request": asked,
        }
    else:
        option = next((o for o in note["options"] if o["id"] == req.optionId), None)
        if option is None:
            raise HTTPException(400, "Pick one of the options shown, or say what you want.")

    podcast_id = store.podcast_id_for(note["noteId"], option["id"], option.get("request", ""))
    jobs.start(podcast_id, note, option)
    return {"id": podcast_id}


# ---- 3 · Listen ----


@app.get("/api/podcasts/{podcast_id}")
def get_podcast(podcast_id: str) -> dict:
    status = jobs.status(podcast_id)
    if status is None:
        raise HTTPException(404, "No podcast with that id.")
    return status


@app.get("/api/podcasts/{podcast_id}/audio.mp3")
def get_audio(podcast_id: str, download: bool = False) -> FileResponse:
    status = jobs.status(podcast_id)
    path = store.audio_path(podcast_id)
    if status is None or status["status"] != "ready" or not path.exists():
        raise HTTPException(404, "This podcast isn't ready yet.")
    name = re.sub(r"[^A-Za-z0-9]+", "-", status.get("title", "podcast")).strip("-").lower()
    return FileResponse(
        path,
        media_type="audio/mpeg",
        filename=f"{name or 'podcast'}.mp3",
        content_disposition_type="attachment" if download else "inline",
    )
