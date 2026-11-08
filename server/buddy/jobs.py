"""Podcast jobs: one at a time in a background thread, status saved to disk."""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from . import audio, llm, store
from .formats import PipelineError

log = logging.getLogger("buddy.jobs")

# One worker: Kokoro runs on this machine and the free Gemini tier is rate-limited.
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="podcast")
_running: set[str] = set()
_lock = threading.Lock()

TERMINAL = {"ready", "failed"}


def start(podcast_id: str, note: dict, option: dict) -> None:
    """Start making a podcast unless it is already made or being made."""
    with _lock:
        current = store.load_status(podcast_id)
        if current and current["status"] == "ready" and store.audio_path(podcast_id).exists():
            return
        if podcast_id in _running:
            return
        _running.add(podcast_id)
        store.save_status(podcast_id, _status(podcast_id, note, option, "queued"))
    _executor.submit(_run, podcast_id, note, option)


def _status(podcast_id: str, note: dict, option: dict, state: str, **extra) -> dict:
    return {
        "id": podcast_id,
        "noteId": note["noteId"],
        "optionId": option["id"],
        "title": option["title"],
        "format": option["label"],
        "status": state,
        **extra,
    }


def _run(podcast_id: str, note: dict, option: dict) -> None:
    def set_state(state: str, **extra) -> None:
        store.save_status(podcast_id, _status(podcast_id, note, option, state, **extra))

    try:
        lines = store.load_script(podcast_id)
        if lines is None:
            set_state("writing")
            transcripts = [p["transcript"] for p in note["pages"]]
            written = llm.write_script(transcripts, option["id"], option.get("topic"))
            lines = [
                {
                    "host": line.host.value,
                    "text": line.text.strip(),
                    "source": line.source.value,
                    "role": line.role.value,
                }
                for line in written
            ]
            store.save_script(podcast_id, lines)
        set_state("recording", script=lines)
        seconds = audio.render(
            [(line["host"], line["text"], line.get("role", "teach")) for line in lines],
            store.audio_path(podcast_id),
            on_mixing=lambda: set_state("mixing", script=lines),
        )
        set_state(
            "ready",
            script=lines,
            seconds=seconds,
            audioUrl=f"/api/podcasts/{podcast_id}/audio.mp3",
        )
    except PipelineError as e:
        set_state("failed", error=str(e))
    except Exception:
        log.exception("Podcast %s failed", podcast_id)
        set_state("failed", error="Something went wrong while making the podcast. Try again.")
    finally:
        with _lock:
            _running.discard(podcast_id)


def status(podcast_id: str) -> dict | None:
    current = store.load_status(podcast_id)
    if current is None:
        return None
    with _lock:
        orphaned = current["status"] not in TERMINAL and podcast_id not in _running
    if orphaned:
        current = {**current, "status": "failed",
                   "error": "The server restarted before this finished. Try again."}
    return current
