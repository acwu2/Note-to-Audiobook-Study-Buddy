"""Study Buddy API. Run from server/:  .venv/bin/uvicorn app:app --port 8000"""

import logging
import mimetypes
import re

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from buddy import ask_api, audiobook, config, jobs, llm, quiz, quiz_api, review_quiz, store, voice_quiz_api
from buddy.formats import FORMAT_ORDER, FORMATS, PipelineError

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="Study Buddy API")

# Listen → quiz → flashcards for what you missed. Routes live in buddy/quiz_api.py.
app.include_router(quiz_api.router)
app.include_router(ask_api.router)
app.include_router(voice_quiz_api.router)


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

    # Example asks, written from these notes. A blank request box is a hard
    # start; three concrete examples show what the box will accept.
    suggestions = [s.strip().rstrip(".") for s in (named.suggestions or []) if s and s.strip()][:3]

    note = {
        "noteId": note_id,
        "topic": named.topic.strip(),
        "pages": [{"transcript": t, "unclearCount": t.count("[unclear]")} for t in transcripts],
        "options": options,
        "suggestions": suggestions,
    }
    store.save_note(note)
    return note


# Python's mimetypes does not know HEIC on every system (the engineer hit this in
# server/transcribe.py), and phones save HEIC by default, so name it outright.
_EXT_MIME = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".heic": "image/heic", ".heif": "image/heif",
    ".pdf": "application/pdf",
}


def _mime_of(upload: UploadFile) -> str:
    mime = (upload.content_type or "").lower()
    if mime in config.ALLOWED_TYPES:
        return mime
    name = (upload.filename or "").lower()
    for ext, known in _EXT_MIME.items():
        if name.endswith(ext):
            return known
    return (mimetypes.guess_type(name)[0] or "").lower()


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
    minutes: float | None = None  # how long they want it; overrides any length in `request`


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
    elif req.minutes and req.optionId:
        # A preset at a length they chose is still that preset, just re-timed.
        base = next((o for o in note["options"] if o["id"] == req.optionId), None)
        if base is None:
            raise HTTPException(400, "Pick one of the options shown, or say what you want.")
        option = dict(base)
    else:
        option = next((o for o in note["options"] if o["id"] == req.optionId), None)
        if option is None:
            raise HTTPException(400, "Pick one of the options shown, or say what you want.")

    minutes = req.minutes
    if minutes is not None:
        if not (0.5 <= minutes <= 20):
            raise HTTPException(400, "Pick a length between 1 and 20 minutes.")
        option["minutes"] = minutes

    # The asked-for length is part of what makes a podcast that podcast.
    cache_note = f"{option.get('request', '')}|{option.get('minutes', '')}"
    podcast_id = store.podcast_id_for(note["noteId"], option["id"], cache_note)
    jobs.start(podcast_id, note, option)
    return {"id": podcast_id}


# ---- 3 · Listen ----


@app.get("/api/podcasts/{podcast_id}")
def get_podcast(podcast_id: str) -> dict:
    status = jobs.status(podcast_id)
    if status is None:
        raise HTTPException(404, "No podcast with that id.")
    return status


@app.get("/api/podcasts/{podcast_id}/audio.m4b")
def get_audiobook(podcast_id: str) -> FileResponse:
    """The lesson as an .m4b with its chapters, the format audiobook apps expect."""
    status = jobs.status(podcast_id)
    mp3 = store.audio_path(podcast_id)
    if status is None or status["status"] != "ready" or not mp3.exists():
        raise HTTPException(404, "This podcast isn't ready yet.")
    try:
        path = audiobook.ensure_m4b(mp3)
    except PipelineError as e:
        raise HTTPException(500, str(e))
    name = re.sub(r"[^A-Za-z0-9]+", "-", status.get("title", "audiobook")).strip("-").lower()
    return FileResponse(path, media_type="audio/mp4", filename=f"{name or 'audiobook'}.m4b")


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


# ---- Study loop: read a review, take the quiz, drill what you missed ----
#
# The review is written here; the quiz and deck come from the engine in quiz.py,
# pointed at the review's points instead of a lesson script. See review_quiz.


class ReviewRequest(BaseModel):
    noteId: str
    # When the review follows a lesson, each point records which lines of that
    # lesson's script taught it, so a missed question can replay that stretch.
    podcastId: str | None = None


class AnswerSheet(BaseModel):
    # questionId -> the index the student picked. A missing entry is a blank,
    # which marks as wrong but is recorded as skipped, so the deck can tell a
    # guess from a gap.
    answers: dict[str, int] = {}


@app.post("/api/reviews")
def create_review(req: ReviewRequest) -> dict:
    """The page to read, plus the quiz on it — with the answers withheld."""
    note = store.load_note(req.noteId)
    if note is None:
        raise HTTPException(404, "Those notes aren't on the server any more. Upload them again.")

    script = None
    if req.podcastId:
        loaded = store.load_script(req.podcastId)
        if loaded is None:
            raise HTTPException(404, "That lesson isn't on the server any more.")
        script = loaded[0]

    # A review of the notes and a review of a lesson made from them are
    # different documents, so the lesson is part of the key.
    review_id = store.review_id_for(req.noteId, req.podcastId or "")
    cached = store.load_review(review_id)
    if cached is None:
        doc = llm.write_review([p["transcript"] for p in note["pages"]], script)
        cached = {
            "reviewId": review_id,
            "noteId": req.noteId,
            **({"podcastId": req.podcastId} if req.podcastId else {}),
            "title": doc.title or note.get("topic", "Review"),
            "points": [p.model_dump(mode="json") for p in doc.points],
        }
        store.save_review(review_id, cached)

    built = review_quiz.build(review_id, cached["points"])
    # Return the declared fields rather than spreading the stored document. A
    # review saved by an older build carries its own "questions" key, and
    # spreading it shipped those alongside the real quiz — the client showed the
    # stale ones and the attempt marked the real ones, so every answer was wrong.
    return {
        "reviewId": cached["reviewId"],
        "noteId": cached["noteId"],
        **({"podcastId": cached["podcastId"]} if cached.get("podcastId") else {}),
        "title": cached["title"],
        "points": cached["points"],
        "quiz": quiz.public_quiz(built),
    }


@app.post("/api/reviews/{review_id}/attempt")
def attempt_review_quiz(review_id: str, sheet: AnswerSheet) -> dict:
    """Mark the quiz, name the gaps, and build cards for those gaps alone."""
    review = store.load_review(review_id)
    if review is None:
        raise HTTPException(404, "That review has expired. Make a new one from your notes.")

    built = review_quiz.build(review_id, review["points"])
    attempt = quiz.grade(built, sheet.answers)
    attempt["reviewId"] = review_id
    quiz.save_attempt(attempt)
    deck = review_quiz.deck_for(attempt, review["points"])
    # A gap's lineRefs index the review's points; each point knows which lines of
    # the lesson taught it. Resolve that here so the player gets script lines it
    # can seek to, with no second lookup.
    points = review["points"]
    for gap in attempt.get("gaps", []):
        lines = {
            ln
            for i in gap.get("lineRefs", [])
            if isinstance(i, int) and 0 <= i < len(points)
            for ln in points[i].get("lineRefs", [])
        }
        gap["scriptLines"] = sorted(lines)
    return {**attempt, "deck": deck, **({"podcastId": review["podcastId"]} if review.get("podcastId") else {})}
