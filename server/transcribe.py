"""Step 1 · Read: turn photos of handwritten notes into plain text with Gemini.

Reads every .png / .jpg / .jpeg / .heic / .heif file in raw/ and writes one
text file per photo to text/<photo name>.txt.

    python transcribe.py            # transcribe photos that don't have a .txt yet
    python transcribe.py --force    # redo every photo
    python transcribe.py --lines 8  # show more of each transcript in the check

Check the start: for each photo the script prints the first few lines of the
transcript. Read them against the photo yourself before you trust the rest.
"""

import argparse
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import errors

HERE = Path(__file__).resolve().parent
RAW_DIR = HERE / "raw"
TEXT_DIR = HERE / "text"

load_dotenv(HERE / ".env")  # picks up GEMINI_API_KEY

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")

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


def find_photos():
    return sorted(
        p for p in RAW_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in MIME_TYPES
    )


def transcribe(client, photo, retries=5):
    """Upload one photo and return Gemini's transcript.

    Waits and retries on 429 (free-tier rate limit) and 5xx (model busy).
    """
    uploaded = client.files.upload(
        file=photo,
        config={"mime_type": MIME_TYPES[photo.suffix.lower()]},
    )
    try:
        delay = 5
        for attempt in range(retries):
            try:
                reply = client.models.generate_content(model=MODEL, contents=[uploaded, PROMPT])
            except errors.APIError as e:
                busy = e.code == 429 or (e.code or 0) >= 500
                if not busy or attempt == retries - 1:
                    raise
                print(f"  Gemini busy ({e.code}), waiting {delay}s...")
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
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
    parser = argparse.ArgumentParser(description="Transcribe handwritten notes in raw/ to text/.")
    parser.add_argument("--force", action="store_true", help="redo photos that already have a transcript")
    parser.add_argument("--lines", type=int, default=5, help="how many lines to show for the check (default 5)")
    args = parser.parse_args()

    if not os.environ.get("GEMINI_API_KEY"):
        sys.exit("GEMINI_API_KEY is not set. Copy .env.example to .env and add your key.")

    photos = find_photos()
    if not photos:
        sys.exit(f"No .png, .jpg or .heic files in {RAW_DIR}")

    TEXT_DIR.mkdir(exist_ok=True)
    client = genai.Client()  # reads GEMINI_API_KEY

    failed = []
    for photo in photos:
        out = TEXT_DIR / f"{photo.stem}.txt"
        if out.exists() and not args.force:
            print(f"skip  {photo.name} (already in text/, use --force to redo)")
            continue

        print(f"read  {photo.name} with {MODEL}")
        try:
            text = transcribe(client, photo)
        except Exception as e:  # keep going with the other photos
            print(f"  FAILED: {e}")
            failed.append(photo.name)
            continue

        out.write_text(text + "\n", encoding="utf-8")

        lines = text.splitlines()
        unclear = text.count("[unclear]")
        print(f"  saved {out.relative_to(HERE)}: {len(lines)} lines, {unclear} [unclear]")
        print(f"  Check the start against the photo before trusting the rest:")
        for line in lines[: args.lines]:
            print(f"  | {line}")
        if len(lines) > args.lines:
            print(f"  | ... ({len(lines) - args.lines} more lines)")
        print()

    if failed:
        sys.exit(f"{len(failed)} photo(s) failed: {', '.join(failed)}")


if __name__ == "__main__":
    main()
