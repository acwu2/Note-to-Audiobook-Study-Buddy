# Note-to-Audiobook Study Buddy

Turn a photo of handwritten notes into an audiobook and a study buddy you can question. The UI uses NotebookLM's layout as its benchmark: sources on the left, chat in the middle, studio on the right.

This is the **frontend first draft**. It runs on sample data, and nothing calls a backend yet.

## Run it

```bash
npm install
npm run dev
```

## What's here

| Panel | What it does | Pipeline step |
| --- | --- | --- |
| Sources | Upload photos; each page has Photo / Transcript / Read-aloud tabs; toggle which pages answers may use | 1 · Read, 2 · Prepare |
| Ask your notes | Notebook guide, grounded chat with numbered source citations, read-aloud on answers | 4 · Ask |
| Studio | Audiobook player (speed, Kokoro voice, MP3 download), study tools, saved notes | 3 · Speak |

On screens narrower than 900px, a tab bar shows one panel at a time.

```
src/
  App.tsx                 page layout + shared state
  components/             TopBar, SourcesPanel, ChatPanel, StudioPanel, Icons
  data/sampleNotebook.ts  sample notes, voices, suggested questions
  lib/api.ts              backend contract (stubs) — one function per step
  lib/useAudiobookPlayer.ts  simulated player; swap for an <audio> element
  types.ts
```

## Next: the backend

`src/lib/api.ts` defines the four endpoints the UI expects:

1. `POST /transcribe`: photo → text (Gemini vision; unreadable words marked `[unclear]`)
2. `POST /prepare`: text → text written for the ear
3. `POST /speak`: text + voice → MP3 (Kokoro)
4. `POST /ask`: question + enabled source ids → grounded answer + citations

Keep the Gemini API key on the server. Set `VITE_API_BASE` if the API isn't served at `/api`.
