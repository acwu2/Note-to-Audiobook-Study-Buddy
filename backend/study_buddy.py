"""Study Buddy: handwritten note -> text -> spoken text -> audiobook -> Q&A.

The four workshop steps, each usable on its own:
    read_note(path)          Step 1: vision model transcribes the handwriting
    prepare_for_ear(text)    Step 2: rewrite symbols/shorthand so it sounds right
    speak(text, out_mp3)     Step 3: Kokoro text-to-speech -> MP3
    ask(note_text, question) Step 4: answer questions grounded in the note

CLI:
    python study_buddy.py note.jpg --read-only     # step 1 only: print the transcription
    python study_buddy.py note.jpg                 # transcribe + make note.mp3
    python study_buddy.py note.jpg --ask "..."     # also answer a question aloud
"""

import argparse
import io
import mimetypes
import os
import re
import subprocess
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

load_dotenv()  # picks up GEMINI_API_KEY from .env

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
VOICE = "af_heart"
SAMPLE_RATE = 24000

_client = None
_tts = None


def client():
    global _client
    if _client is None:
        _client = genai.Client()  # reads GEMINI_API_KEY
    return _client


def generate(contents, retries=5, config=None):
    """Call Gemini, waiting and retrying when it is busy (never hammer).

    Retries on 429 (free-tier rate limit) and 5xx (e.g. 503 "model is experiencing high demand").
    If GEMINI_FALLBACK_MODEL is set, the last attempt uses that model instead.
    """
    delay = 5
    fallback = os.environ.get("GEMINI_FALLBACK_MODEL")
    for attempt in range(retries):
        last = attempt == retries - 1
        model = fallback if (last and fallback) else MODEL
        try:
            reply = client().models.generate_content(model=model, contents=contents, config=config)
            if not reply.text:
                reason = reply.candidates[0].finish_reason if reply.candidates else "no answer"
                raise RuntimeError(f"Gemini returned no text ({reason}).")
            return reply.text
        except errors.APIError as e:
            busy = e.code == 429 or (e.code or 0) >= 500
            if not busy or last:
                raise
            print(f"Gemini busy ({e.code}), waiting {delay}s...")
            time.sleep(delay)
            delay = min(delay * 2, 40)


# Step 1 · Read
READ_RULES = """You transcribe photos of handwritten study notes for students who will listen to them.

Rules:
- Copy the words exactly as written, in reading order: top to bottom, left to right.
- Keep the writer's line breaks. Keep their shorthand, symbols and spelling (e.g. "w/", "->", "eg:"); do not expand or correct them.
- Plain text only: no markdown, no headings, no commentary, no preamble.
- Never guess. If you cannot read a word, write [unclear] in its place.
- Notes in the margin go on their own line, starting with "Margin note:", placed next to the line they point to.
- Ignore the paper itself (ruled lines, holes, spiral binding) and anything crossed out.
- If there is no handwriting in the photo, reply with exactly: [no handwriting found]"""

MAX_SIDE = 2048  # px; bigger photos are slower to send and are not read any better


def load_photo(image_path):
    """Return (bytes, mime type), upright and not too large.

    Phone photos are often stored sideways with an EXIF "rotate me" tag; fix that
    so the model sees the page the right way up. Needs Pillow; without it the file
    is sent as-is.
    """
    path = Path(image_path)
    data = path.read_bytes()
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return data, mime
    try:
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
    except Exception:
        return data, mime  # a format Pillow cannot open (e.g. HEIC): let Gemini handle it
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    img.convert("RGB").save(out, "JPEG", quality=90)
    return out.getvalue(), "image/jpeg"


def clean_transcript(text):
    """Remove markdown fences or a preamble the model sometimes adds anyway."""
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text).strip()
    text = re.sub(r"^(here is|here's) (the )?transcription[^\n]*:\s*", "", text, flags=re.I)
    return text


def read_note(image_path):
    """Step 1: photo of a handwritten note -> plain text, unreadable words as [unclear]."""
    data, mime = load_photo(image_path)
    photo = types.Part.from_bytes(data=data, mime_type=mime)
    config = types.GenerateContentConfig(system_instruction=READ_RULES, temperature=0)
    text = clean_transcript(generate([photo, "Transcribe this handwritten note."], config=config))
    if text == "[no handwriting found]":
        raise ValueError("No handwriting found in that photo. Try a clearer, closer picture of the page.")
    return text


def first_lines(text, n=3):
    """Check the start: the workshop's advice is to read these yourself before trusting the rest."""
    return "\n".join(text.splitlines()[:n])


# Step 2 · Prepare
def prepare_for_ear(text):
    ask = (
        "Rewrite this so it sounds natural read aloud. Spell out symbols and "
        "abbreviations (e.g. '1st' -> 'first', 'A→B' -> 'A leads to B', "
        "'~50%' -> 'about fifty percent'). Keep every fact. Plain text only.\n\n"
    )
    return generate(ask + text)


# Step 3 · Speak
def speak(text, out_mp3, voice=VOICE):
    global _tts
    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline

    if _tts is None:
        _tts = {}
    lang = voice[0]  # Kokoro voice ids start with their language: "a" = American, "b" = British English
    if lang not in _tts:
        _tts[lang] = KPipeline(lang_code=lang)
    parts = [audio for _, _, audio in _tts[lang](text, voice=voice)]
    out_mp3 = Path(out_mp3)
    wav = out_mp3.with_suffix(".wav")
    sf.write(wav, np.concatenate(parts), SAMPLE_RATE)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-b:a", "96k", str(out_mp3)],
        check=True,
    )
    wav.unlink()
    return out_mp3


# Step 4 · Ask
def ask(note_text, question):
    rules = "Answer only from this note. If it is not in the note, say so. Plain text only."
    return generate([rules, note_text, question])


def quiz(note_text):
    return ask(note_text, "Ask me three questions about this note to help me revise.")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("image", type=Path, help="photo of a handwritten note")
    p.add_argument("--ask", help="a question to answer from the note")
    p.add_argument("--read-only", action="store_true", help="only run step 1 and print the text")
    args = p.parse_args()

    text = read_note(args.image)
    print("--- Transcription ---\n" + text)
    print(f"\n--- Check the start against your page ---\n{first_lines(text)}")
    unclear = text.count("[unclear]")
    if unclear:
        print(f"({unclear} word{'s' if unclear > 1 else ''} marked [unclear])")
    if args.read_only:
        return

    spoken = prepare_for_ear(text)
    print("\n--- Prepared for the ear ---\n" + spoken)

    mp3 = speak(spoken, args.image.with_suffix(".mp3"))
    print(f"\nAudiobook saved: {mp3}")

    if args.ask:
        answer = ask(text, args.ask)
        print("\n--- Answer ---\n" + answer)
        print(f"Answer audio: {speak(answer, args.image.with_name(args.image.stem + '_answer.mp3'))}")


if __name__ == "__main__":
    main()
