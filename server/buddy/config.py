"""Settings, read once from the environment (and server/.env)."""

import os
from pathlib import Path

from dotenv import load_dotenv

SERVER_DIR = Path(__file__).resolve().parent.parent
load_dotenv(SERVER_DIR / ".env")

DATA_DIR = Path(os.environ.get("STUDY_BUDDY_DATA", SERVER_DIR / "data"))

# The workshop uses this model on Gemini's free tier. Check
# aistudio.google.com/docs/models for the current free Flash model.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# Test modes: run the whole flow without a Gemini key (FAKE_AI) or without
# Kokoro (FAKE_TTS). Fake AI returns sample notes; fake TTS makes tones.
FAKE_AI = os.environ.get("FAKE_AI") == "1"
FAKE_TTS = os.environ.get("FAKE_TTS") == "1"

# Bump when a prompt, format or voice changes, so cached results are rebuilt.
PIPELINE_VERSION = "3"

SAMPLE_RATE = 24_000  # Kokoro's output rate
PAUSE_SECONDS = 0.35  # silence between lines
THINK_SECONDS = 3.5   # silence after a "check" line, so the student can answer aloud
MP3_BITRATE = "96k"

MAX_FILES = 10
MAX_FILE_BYTES = 15 * 1024 * 1024
ALLOWED_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
    "application/pdf",
}
