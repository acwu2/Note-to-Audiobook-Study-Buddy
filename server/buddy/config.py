"""Settings, read once from the environment (and server/.env)."""

import os
from pathlib import Path

from dotenv import load_dotenv

SERVER_DIR = Path(__file__).resolve().parent.parent
load_dotenv(SERVER_DIR / ".env")

DATA_DIR = Path(os.environ.get("STUDY_BUDDY_DATA", SERVER_DIR / "data"))

# gemini-2.5-flash is retired for new API keys — it is still listed by
# ListModels but generateContent returns 404 NOT_FOUND with "no longer
# available to new users". Verified working on a fresh key: gemini-3.5-flash
# and gemini-3.8-flash. Free tier allows 20 requests per day PER MODEL, so
# switching model also resets the quota.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")

# Free-tier quota is per model, so a spent daily allowance on one is not a spent
# allowance on the next. When the primary runs dry the server walks this list
# instead of failing the demo. Cache ids key on GEMINI_MODEL only, so being
# served by a fallback never invalidates cached results.
GEMINI_FALLBACKS = [
    m.strip()
    for m in os.environ.get(
        "GEMINI_FALLBACKS", "gemini-3.7-flash,gemini-3.6-flash,gemini-3.8-flash,gemini-3.1-flash-lite"
    ).split(",")
    if m.strip()
]

# Test modes: run the whole flow without a Gemini key (FAKE_AI) or without
# Kokoro (FAKE_TTS). Fake AI returns sample notes; fake TTS makes tones.
FAKE_AI = os.environ.get("FAKE_AI") == "1"
FAKE_TTS = os.environ.get("FAKE_TTS") == "1"

# Bump when a prompt, format or voice changes, so cached results are rebuilt.
PIPELINE_VERSION = "6"  # 6: transcription prompt now handles margin notes and crossings-out

# Seconds to wait on one Gemini request before giving up and retrying. The
# engineer's transcribe.py uses 120; ours also writes long scripts, so 180.
REQUEST_TIMEOUT_SECONDS = 180

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
