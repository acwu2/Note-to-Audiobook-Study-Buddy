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
import re
import sys
import time

from google.genai import errors

from gemini import HERE, MODEL, generate, log, make_client

RAW_DIR = HERE / "raw"
TEXT_DIR = HERE / "text"
OUT_FILE = TEXT_DIR / "notes.txt"

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


def transcribe(client, photo):
    """Upload one photo and return Gemini's transcript.

    Prints each step with the time since this photo started, so you can see
    whether it is working or waiting.
    """
    started = time.monotonic()
    size_mb = photo.stat().st_size / 1_000_000
    log(f"uploading photo ({size_mb:.1f} MB)...", started)
    uploaded = client.files.upload(
        file=photo,
        config={"mime_type": MIME_TYPES[photo.suffix.lower()]},
    )
    try:
        reply = generate(client, [uploaded, PROMPT], started=started, what="asking Gemini to read it")
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

    photos = find_photos()
    if not photos:
        sys.exit(f"No .png, .jpg or .heic files in {RAW_DIR}")

    TEXT_DIR.mkdir(exist_ok=True)
    client = make_client()

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
