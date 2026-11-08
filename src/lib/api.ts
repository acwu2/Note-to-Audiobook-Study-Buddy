/**
 * Frontend contract for the backend. Every function here is a stub for now.
 * Each one maps to a step in the workshop pipeline; swap the body for a
 * fetch() to your server when it exists. Keep API keys on the server —
 * never call Gemini from the browser with a key baked into the bundle.
 */

const API_BASE = import.meta.env.VITE_API_BASE ?? '/api';

/** Step 1 · Read — POST /transcribe (photo → text, Gemini vision). */
export async function transcribe(photo: File): Promise<{ transcript: string; unclearCount: number }> {
  void API_BASE;
  void photo;
  throw new Error('transcribe() is not connected to a backend yet');
}

/** Step 2 · Prepare — POST /prepare (text → text written for the ear). */
export async function prepareForSpeech(transcript: string): Promise<{ spoken: string }> {
  void transcript;
  throw new Error('prepareForSpeech() is not connected to a backend yet');
}

/** Step 3 · Speak — POST /speak (text → MP3 URL, Kokoro). */
export async function speak(text: string, voice: string): Promise<{ audioUrl: string; seconds: number }> {
  void text;
  void voice;
  throw new Error('speak() is not connected to a backend yet');
}

/** Step 4 · Ask — POST /ask (question + enabled sources → grounded answer). */
export async function ask(
  question: string,
  sourceIds: string[],
): Promise<{ answer: string; citations: string[] }> {
  void question;
  void sourceIds;
  throw new Error('ask() is not connected to a backend yet');
}
