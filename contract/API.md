# Study Buddy HTTP contract

The thing both server implementations have to agree on, so that it does not
matter which one ships.

## Why this file exists

The engineers' build is Flask; this build is FastAPI behind a React SPA. That
difference is cheap **as long as nothing about the framework leaks into the
contract.** Today almost nothing does:

```
server/buddy/   801 lines   pure Python, zero web-framework imports
server/app.py   149 lines   the only FastAPI-specific file
```

`buddy/` is the whole product — transcription, the format menu, script writing,
Kokoro rendering, the job runner, the store. A Flask app can `import buddy` and
use it unchanged. Only the 149-line HTTP layer gets rewritten, and this file
says exactly what that layer must do.

The same contract is what makes the frontend question moot. A React SPA and
Flask server-side templates are both just clients of these five endpoints.

## The one real trap: the error envelope

FastAPI's `HTTPException` serialises as:

```json
{ "detail": "Add at least one photo of your notes." }
```

`src/lib/api.ts` reads `body.detail` and falls back to `"The server answered
400."` when it is missing. A Flask implementation returning `{"error": "..."}`
or Flask's default HTML error page will **not** crash — it will silently
replace every friendly message with a status code. Every careful error string
in the codebase disappears and nobody gets a stack trace telling them why.

**Any implementation must return `{"detail": "<plain sentence>"}` with the
right status code.** This is the single highest-risk difference between the
two stacks, and `conformance.py` checks it on every error path.

## Endpoints

### `GET /api/health`

```json
{ "ok": true, "fakeAi": false, "fakeTts": false, "model": "gemini-2.5-flash" }
```

`model` is `null` when `fakeAi` is true.

### `POST /api/notes`

`multipart/form-data`, one or more parts named **`photos`**.

Returns a Note:

```json
{
  "noteId": "n_84ef497b3698",
  "topic": "Cellular respiration",
  "pages": [{ "transcript": "...", "unclearCount": 1 }],
  "options": [
    { "id": "full_episode", "label": "Full episode", "minutes": 8,
      "title": "...", "description": "..." },
    { "id": "quick_recap",  "label": "Quick recap",  "minutes": 3, "title": "...", "description": "..." },
    { "id": "deep_dive",    "label": "Deep dive",    "minutes": 5, "title": "...", "description": "...", "topic": "The Krebs cycle" }
  ]
}
```

**Idempotent by content.** `noteId` is derived from the uploaded bytes, so the
same files always return the same note and skip the model entirely. An
implementation that mints a fresh id per request is wrong — it re-bills every
upload and breaks the cache.

Errors: `400` no files, an empty file, or more than `MAX_FILES`; `415`
unsupported type; `413` a file over `MAX_FILE_BYTES`; `502` the pipeline
failed (the message is the student-facing sentence from `PipelineError`).

### `POST /api/podcasts` → `202`

```json
{ "noteId": "n_84ef497b3698", "optionId": "deep_dive" }
```

Returns `{ "id": "p_2b4b478fe5ef" }` and starts the job in the background. The
status code is **202**, not 200 — the work has not happened yet.

**Also idempotent**: the id is derived from note + option + `PIPELINE_VERSION`,
so asking twice resumes the same job rather than making a second one.

Errors: `404` unknown `noteId`; `400` an `optionId` not in that note's options.

### `GET /api/podcasts/{id}`

```json
{
  "id": "p_...", "noteId": "n_...", "optionId": "deep_dive",
  "title": "The Krebs cycle, explained simply",
  "format": "Deep dive",
  "status": "ready",
  "script": [{ "host": "Heart", "text": "...", "source": "notes", "role": "teach" }],
  "seconds": 17.8,
  "audioUrl": "/api/podcasts/p_.../audio.mp3"
}
```

`status` is one of `queued` `writing` `recording` `mixing` `ready` `failed`.
`seconds` and `audioUrl` appear only when `ready`; `error` appears only when
`failed`. Clients poll this.

On a script line, `host` and `text` are always present. `source` (`notes` |
`added`) and `role` are newer, so **treat a missing `source` as `notes`** —
podcasts generated before those fields existed are still on disk.

Errors: `404` unknown id.

### `GET /api/podcasts/{id}/audio.mp3?download=<bool>`

`audio/mpeg`. `Content-Disposition` is `inline` by default and `attachment`
when `download` is truthy, with a filename slugged from the title
(`the-krebs-cycle-explained-simply.mp3`).

Errors: `404` when the id is unknown, the job is not `ready`, or the file is
missing.

## Notes for a Flask implementation

- **`import buddy` and call it.** Do not reimplement transcription, formats,
  script writing or rendering — that is 800 lines of tested product and it has
  no framework dependency.
- **Async is not a blocker.** `app.py` marks `create_note` `async` and hands
  the blocking work to `run_in_threadpool`. Under Flask (sync WSGI) just call
  `_build_note` directly; the semantics are identical. `jobs.start` already
  runs the podcast on its own thread, so nothing else needs an event loop.
- **Keep the paths exactly.** `src/lib/api.ts` has them hard-coded, and
  `audioUrl` is built server-side as a literal string in `jobs.py`.
- **`202` on create.** Returning 200 will not break the client today, but it
  misreports a queued job as a finished one.
- **Serving the frontend is orthogonal.** Flask can serve the Vite build as
  static files, or render its own templates, or serve nothing and let Vite's
  dev server proxy `/api`. All three work against this contract unchanged.

## Checking an implementation

```bash
python3 contract/conformance.py http://localhost:8000
```

No dependencies — standard library only, so it runs against a Flask server, a
FastAPI server, or anything else without installing into their environment.
Run it with `FAKE_AI=1 FAKE_TTS=1` on the server for a fast, deterministic,
no-cost pass.
