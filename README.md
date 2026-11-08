# Study Buddy

Photograph your handwritten notes. Get a review to read, a quiz on it, flashcards for what you missed, and an audio lesson that teaches the notes back to you.

```
upload notes -> review -> quiz -> flashcards from your weak points
             \-> audio lesson (two hosts, questions you answer out loud, chapters)
```

## Run it

```bash
# 1. API key (free): https://aistudio.google.com  -> Get API key (starts with AIza or AQ.)
cp server/.env.example server/.env     # then put the key after GEMINI_API_KEY=

# 2. API (checks your setup first, real mode only)
./server/run.sh            # http://127.0.0.1:8000, replaces only what's on that port

# 3. App
npm install && npm run dev # http://localhost:5173
```

Confirm `http://127.0.0.1:8000/api/health` says `"fakeAi": false`. If it says `true`
you are looking at canned samples, whatever you upload.

## What it does

| Step | What happens |
| --- | --- |
| Upload | Photos or PDFs, read by Gemini vision. Unreadable words become `[unclear]`, never guesses. |
| Review | 4-9 discrete points, each labelled `notes` or `added`, with `exam` set only where *your* notes flag it. |
| Quiz | One question per point, plausible wrong answers, marked on the server (answers never reach the page). |
| Flashcards | Only for points you missed or skipped. A wrong answer's card names the exact confusion you picked. |
| Lesson | Hook, teach, check, answer, recap. A question is followed by 3.5s of silence so you can answer aloud. Chapters seek to exact offsets. |
| Length | Ask for any 1-20 minutes, or say it in words ("a 5 minute overview"). |
| Replay | A missed question maps back to the lines of the lesson that taught it (`scriptLines`). |

## Limits you will hit (verified, not guessed)

- **Free tier is 20 generate requests per day per model.** A full session is roughly 8-10 requests. The server falls back to the next model when one runs out, and the last resort is `gemini-3.1-flash-lite`, which writes noticeably **shorter** lessons. Check `askedMinutes` against `seconds` on the result.
- **`gemini-2.5-flash` is retired for new keys** (listed, but returns 404). Default is `gemini-3.5-flash`.
- **Long length requests can undershoot.** Measured: a 6 minute request gave 4.85 minutes on a strong model. The word budget is calibrated on real lessons (Kokoro speaks ~146 wpm, not the 184 fixtures suggested) but a fresh generation on a strong model has **not** been re-verified since the recalibration.
- Notes uploaded before a pipeline change keep their old shape (for example, no `suggestions`). Upload again.

## Checks

```bash
./server/.venv/bin/python server/check_setup.py --live     # key, model, ffmpeg, Kokoro, one real call
python3 benchmark/check_grounding.py --all                  # flags words in a script the notes never said
```

`benchmark/README.md` has the NotebookLM comparison and the grounding method.
