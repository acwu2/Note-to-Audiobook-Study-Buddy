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
PIPELINE_VERSION = "4"

SAMPLE_RATE = 24_000  # Kokoro's output rate
# Pacing. Kokoro leaves ~0.3s before and ~0.5s after each line; audio._trim strips
# that so these gaps are the real ones a listener hears.
TRIM_THRESHOLD = 0.004      # below this is silence
TRIM_KEEP_SECONDS = 0.04    # breath left on each end, so nothing clips
SAME_HOST_SECONDS = 0.12    # one host carrying on from themselves
TURN_SECONDS = 0.24         # handing over to the other host
SECTION_SECONDS = 0.55      # a beat before a hook or a recap
THINK_SECONDS = 3.5         # after a "check", so the student can answer aloud
TAIL_SECONDS = 0.40         # after the last line
PAUSE_SECONDS = 0.35        # kept for anything still calling it
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
