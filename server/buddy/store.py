"""Results on disk, keyed by content hashes, so the same input gives the same output."""

import hashlib
import json
import os
import re
from pathlib import Path

from . import config

NOTE_ID = re.compile(r"^n_[0-9a-f]{12}$")
PODCAST_ID = re.compile(r"^p_[0-9a-f]{12}$")


def _mode() -> str:
    ai = "fake" if config.FAKE_AI else config.GEMINI_MODEL
    tts = "fake" if config.FAKE_TTS else "kokoro"
    return f"v{config.PIPELINE_VERSION}|{ai}|{tts}"


def note_id_for(files: list[tuple[bytes, str]]) -> str:
    h = hashlib.sha256(_mode().encode())
    for data, mime in files:
        h.update(mime.encode() + b"\0" + len(data).to_bytes(8, "big") + data)
    return "n_" + h.hexdigest()[:12]


def normalize_request(text: str) -> str:
    """Fold trivial differences so the same ask reuses the same podcast."""
    return re.sub(r"\s+", " ", text or "").strip().lower()


def podcast_id_for(note_id: str, option_id: str, request: str = "") -> str:
    """Same notes plus the same ask always give the same podcast.

    A free-text request is part of the key, not an exception to it: determinism
    was always about reproducibility, not about ids specifically.
    """
    key = f"{_mode()}|{note_id}|{option_id}|{normalize_request(request)}".encode()
    return "p_" + hashlib.sha256(key).hexdigest()[:12]


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    os.replace(tmp, path)


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _note_path(note_id: str) -> Path:
    return config.DATA_DIR / "notes" / f"{note_id}.json"


def save_note(note: dict) -> None:
    _write_json(_note_path(note["noteId"]), note)


def load_note(note_id: str) -> dict | None:
    return _read_json(_note_path(note_id)) if NOTE_ID.match(note_id) else None


def podcast_dir(podcast_id: str) -> Path:
    return config.DATA_DIR / "podcasts" / podcast_id


def audio_path(podcast_id: str) -> Path:
    return podcast_dir(podcast_id) / "audio.mp3"


def save_status(podcast_id: str, status: dict) -> None:
    _write_json(podcast_dir(podcast_id) / "status.json", status)


def load_status(podcast_id: str) -> dict | None:
    if not PODCAST_ID.match(podcast_id):
        return None
    return _read_json(podcast_dir(podcast_id) / "status.json")


def save_script(podcast_id: str, lines: list[dict], chapters: list[dict] | None = None) -> None:
    _write_json(
        podcast_dir(podcast_id) / "script.json",
        {"lines": lines, "chapters": chapters or []},
    )


def load_script(podcast_id: str) -> tuple[list[dict], list[dict]] | None:
    """The written lesson and its chapter plan, or None when nothing is cached."""
    saved = _read_json(podcast_dir(podcast_id) / "script.json")
    if not saved:
        return None
    return saved["lines"], saved.get("chapters", [])
