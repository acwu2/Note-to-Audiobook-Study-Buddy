"""Step 1 · Read: turn photos of handwritten notes into plain text with Gemini.

Reads every .png / .jpg / .jpeg / .heic / .heif file in raw/, in filename
order, and combines them into one file: text/notes.txt. Each page starts with
a "--- page N: <photo name> ---" line. Name photos so they sort in page order
(page1.jpg, page2.jpg, ... page10.jpg sorts correctly).

    python transcribe.py            # transcribe every photo into text/notes.txt
    python transcribe.py --lines 8  # show more of each page in the check

Check the start: for each photo the script prints the first few lines of the
transcript. Read them against the photo yourself before you trust the rest.
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

HERE = Path(__file__).resolve().parent
RAW_DIR = HERE / "raw"
TEXT_DIR = HERE / "text"
OUT_FILE = TEXT_DIR / "notes.txt"

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

# Set the type explicitly: Python's mimetypes doesn't know HEIC on every system.
MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".heic": "image/heic",
    ".heif": "image/heif",
}

PROMPT = """Transcribe the handwriting in this photo into plain text.

Rules:
- Plain text only. No markdown, no headings, no bullet formatting you add yourself.
- No commentary, no preamble, no explanation. Output only the transcribed words.
- Keep the reading order: top to bottom, left to right. Keep the writer's line breaks.
- Copy exactly what is written, including shorthand, symbols and spelling. Do not correct or expand anything.
- Never guess. If you cannot read a word with confidence, write [unclear] in its place.
- Margin notes are separate from the main text. Never merge a margin note into a main-text line or split it across lines. Put each margin note whole on its own line, starting with "Margin note:", directly after the main-text line it sits beside or points to.
- Ignore the paper itself (ruled lines, margins, holes) and anything crossed out."""


def page_order(path):
    """Sort by filename, treating digits as numbers so page2 comes before page10."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", path.name)]


def find_photos():
    return sorted(
        (p for p in RAW_DIR.iterdir() if p.is_file() and p.suffix.lower() in MIME_TYPES),
        key=page_order,
    )


def log(step, started):
    print(f"  [{time.monotonic() - started:5.1f}s] {step}", flush=True)


def transcribe(client, photo, retries=5):
    """Upload one photo and return Gemini's transcript.

    Prints each step with the time since this photo started, so you can see
    whether it is working or waiting. Waits and retries on 429 (free-tier rate
    limit), 5xx (model busy) and requests that time out.
    """
    started = time.monotonic()
    size_mb = photo.stat().st_size / 1_000_000
    log(f"uploading photo ({size_mb:.1f} MB)...", started)
    uploaded = client.files.upload(
        file=photo,
        config={"mime_type": MIME_TYPES[photo.suffix.lower()]},
    )
    try:
        delay = 5
        for attempt in range(retries):
            last = attempt == retries - 1
            log(f"asking Gemini to read it (attempt {attempt + 1}/{retries}, usually 5-30s)...", started)
            try:
                reply = client.models.generate_content(model=MODEL, contents=[uploaded, PROMPT])
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
            return reply.text.strip()
    finally:
        # Uploads expire after 48h anyway; clean up now.
        try:
            client.files.delete(name=uploaded.name)
        except errors.APIError:
            pass


def main():
    parser = argparse.ArgumentParser(description="Transcribe handwritten notes in raw/ into text/notes.txt.")
    parser.add_argument("--lines", type=int, default=5, help="how many lines of each page to show for the check (default 5)")
    args = parser.parse_args()

    if not os.environ.get("GEMINI_API_KEY"):
        sys.exit("GEMINI_API_KEY is not set. Copy .env.example to .env and add your key.")

    photos = find_photos()
    if not photos:
        sys.exit(f"No .png, .jpg or .heic files in {RAW_DIR}")

    TEXT_DIR.mkdir(exist_ok=True)
    client = genai.Client(  # reads GEMINI_API_KEY
        http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_SECONDS * 1000),
    )

    pages = []
    failed = []
    for number, photo in enumerate(photos, start=1):
        print(f"read  page {number}/{len(photos)}: {photo.name} with {MODEL}", flush=True)
        header = f"--- page {number}: {photo.name} ---"
        try:
            text = transcribe(client, photo)
        except Exception as e:  # keep going with the other photos
            print(f"  FAILED: {e}")
            failed.append(photo.name)
            pages.append(f"{header}\n[page not transcribed: {e}]")
            continue

        pages.append(f"{header}\n{text}")

        lines = text.splitlines()
        print(f"  {len(lines)} lines, {text.count('[unclear]')} [unclear]")
        print("  Check the start against the photo before trusting the rest:")
        for line in lines[: args.lines]:
            print(f"  | {line}")
        if len(lines) > args.lines:
            print(f"  | ... ({len(lines) - args.lines} more lines)")
        print()

    OUT_FILE.write_text("\n\n".join(pages) + "\n", encoding="utf-8")
    print(f"saved {OUT_FILE.relative_to(HERE)}: {len(photos)} page(s)")

    if failed:
        sys.exit(f"{len(failed)} page(s) failed and are marked in the file: {', '.join(failed)}")


if __name__ == "__main__":
    main()
