"""Shared Gemini setup for the server scripts: client, model, retries, timeouts."""

import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

HERE = Path(__file__).resolve().parent

load_dotenv(HERE / ".env")  # picks up GEMINI_API_KEY

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")

# Give up on a single request after this long instead of hanging forever.
REQUEST_TIMEOUT_SECONDS = 120


def _timeout_errors():
    """The SDK talks HTTP through httpx or httpx2, depending on what is installed."""
    found = []
    for name in ("httpx", "httpx2"):
        try:
            found.append(__import__(name).TimeoutException)
        except ImportError:
            pass
    return tuple(found)


TIMEOUT_ERRORS = _timeout_errors()


def make_client():
    if not os.environ.get("GEMINI_API_KEY"):
        sys.exit("GEMINI_API_KEY is not set. Copy .env.example to .env and add your key.")
    return genai.Client(  # reads GEMINI_API_KEY
        http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_SECONDS * 1000),
    )


def log(step, started):
    """Print a step with the seconds since `started`, so you can see it is working."""
    print(f"  [{time.monotonic() - started:5.1f}s] {step}", flush=True)


def generate(client, contents, *, config=None, started=None, what="asking Gemini", retries=5):
    """Call Gemini and return the reply.

    Waits and retries on 429 (free-tier rate limit), 5xx (model busy) and
    requests that time out. Raises if the reply has no text.
    """
    started = started if started is not None else time.monotonic()
    delay = 5
    for attempt in range(retries):
        last = attempt == retries - 1
        log(f"{what} (attempt {attempt + 1}/{retries}, usually 5-30s)...", started)
        try:
            reply = client.models.generate_content(model=MODEL, contents=contents, config=config)
        except errors.APIError as e:
            busy = e.code == 429 or (e.code or 0) >= 500
            if not busy or last:
                raise
            log(f"Gemini busy ({e.code}), waiting {delay}s before retrying...", started)
            time.sleep(delay)
            delay = min(delay * 2, 60)
            continue
        except TIMEOUT_ERRORS:
            if last:
                raise RuntimeError(f"no answer after {retries} tries of {REQUEST_TIMEOUT_SECONDS}s each")
            log(f"no answer after {REQUEST_TIMEOUT_SECONDS}s, retrying...", started)
            continue
        log("done", started)
        if not reply.text:
            reason = reply.candidates[0].finish_reason if reply.candidates else "no answer"
            raise RuntimeError(f"Gemini returned no text ({reason})")
        return reply
