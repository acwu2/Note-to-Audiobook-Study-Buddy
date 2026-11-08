#!/usr/bin/env python3
"""Confirm the server can actually do the real pipeline, before you rely on it.

Checks the four things that silently fall back or fail: the Gemini key, the model
name, Kokoro, and ffmpeg. Never prints the key.

    ./.venv/bin/python check_setup.py           # config only, no API calls
    ./.venv/bin/python check_setup.py --live    # also makes one tiny Gemini call
"""

import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

OK, WARN, BAD = "  ok  ", " warn ", " FAIL "
failures = 0
warnings = 0


def say(mark: str, label: str, detail: str = "") -> None:
    global failures, warnings
    if mark is BAD:
        failures += 1
    if mark is WARN:
        warnings += 1
    print(f"[{mark}] {label}" + (f"  — {detail}" if detail else ""))


def main() -> int:
    live = "--live" in sys.argv
    from buddy import config

    print("\nStudy Buddy server setup\n" + "=" * 46)

    # --- the key -----------------------------------------------------------
    env_file = config.SERVER_DIR / ".env"
    say(OK if env_file.exists() else WARN, f"server/.env {'found' if env_file.exists() else 'not found'}",
        "" if env_file.exists() else "copy .env.example to .env and fill in the key")

    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        say(OK, "GEMINI_API_KEY is set", f"{len(key)} chars, ending {key[-4:]}")
    else:
        say(BAD, "GEMINI_API_KEY is missing", "the server cannot read real handwriting without it")

    # --- fake modes --------------------------------------------------------
    if config.FAKE_AI:
        say(BAD, "FAKE_AI=1 is on",
            "every upload returns the canned Cellular respiration sample, and free-text "
            "requests are ignored entirely")
    else:
        say(OK, "FAKE_AI is off", "real transcription and real scripts")

    if config.FAKE_TTS:
        say(BAD, "FAKE_TTS=1 is on", "the voices are sine tones, not Kokoro")
    else:
        say(OK, "FAKE_TTS is off", "real Kokoro voices")

    say(OK, "model", config.GEMINI_MODEL)

    # --- audio -------------------------------------------------------------
    if shutil.which("ffmpeg"):
        say(OK, "ffmpeg found")
    else:
        say(BAD, "ffmpeg missing", "brew install ffmpeg")

    try:
        import kokoro  # noqa: F401
        say(OK, "kokoro importable")
    except Exception as e:
        say(BAD, "kokoro not importable", str(e)[:80])

    # --- one real call -----------------------------------------------------
    if live and key and not config.FAKE_AI:
        print("\nmaking one small Gemini call…")
        try:
            from buddy import llm
            opts = llm.name_options(["Krebs cycle = citric acid cycle\nruns 2x per glucose"])
            say(OK, "Gemini replied", f'topic: "{opts.topic}"')
        except Exception as e:
            msg = str(e)
            hint = ""
            low = msg.lower()
            if "api key" in low or "permission" in low or "401" in low or "403" in low:
                hint = "the key looks wrong or lacks access"
            elif "429" in low or "quota" in low or "rate" in low:
                hint = "rate limited or out of free quota — the key itself is probably fine"
            elif "not found" in low or "404" in low:
                hint = f"check GEMINI_MODEL ({config.GEMINI_MODEL}) against aistudio.google.com/docs/models"
            say(BAD, "Gemini call failed", f"{msg[:110]}" + (f"  [{hint}]" if hint else ""))
    elif live:
        say(WARN, "skipped the live call", "needs a key and FAKE_AI off")

    print("=" * 46)
    if failures:
        print(f"{failures} blocking problem(s). The real pipeline will not run.\n")
        return 1
    if warnings:
        print(f"ready, with {warnings} warning(s).\n")
        return 0
    print("ready.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
