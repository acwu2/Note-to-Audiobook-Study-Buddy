#!/usr/bin/env bash
# Start the API in REAL mode (real Gemini, real Kokoro).  Usage: ./run.sh [port]
#
# - Refuses to start if the setup check fails (missing key, ffmpeg, Kokoro).
# - Unsets FAKE_AI / FAKE_TTS so a leftover shell variable cannot silently put
#   you back on canned samples.
# - Replaces only the server on THIS port. It never pattern-kills other servers.
cd "$(dirname "$0")" || exit 1
PORT="${1:-8000}"

./.venv/bin/python check_setup.py || { echo "Fix the above, then run again."; exit 1; }

old=$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null | head -1)
if [ -n "$old" ]; then echo "Replacing the server on port $PORT (pid $old)"; kill "$old"; sleep 1; fi

echo "Starting on http://127.0.0.1:$PORT  (health: /api/health must say fakeAi:false)"
exec env -u FAKE_AI -u FAKE_TTS ./.venv/bin/python -m uvicorn app:app --port "$PORT"
