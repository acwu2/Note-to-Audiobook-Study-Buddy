/**
 * Client for the Study Buddy API (server/app.py). The student either picks a
 * card or asks in their own words; either way the same notes and the same
 * choice reuse the same script and MP3, because the server hashes the request
 * into the podcast id. The Gemini key lives on the server only.
 */
import type {
  Attempt, Deck, FormatId, Health, Note, Podcast, Quiz, ReviewPoint,
} from '../types';

const API_BASE = (import.meta.env.VITE_API_BASE ?? '/api').replace(/\/$/, '');

export class ApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(API_BASE + path, init);
  } catch {
    throw new ApiError("Can't reach the Study Buddy server. Is it running?");
  }
  if (!res.ok) {
    let message = `The server answered ${res.status}.`;
    try {
      const body = await res.json();
      if (typeof body?.detail === 'string') message = body.detail;
    } catch {
      /* keep the generic message */
    }
    throw new ApiError(message);
  }
  return res.json() as Promise<T>;
}

export const getHealth = () => request<Health>('/health');

/** Step 1 · Upload: reads every page, then returns the fixed menu of options. */
export function createNote(files: File[]): Promise<Note> {
  const form = new FormData();
  files.forEach((f) => form.append('photos', f));
  return request<Note>('/notes', { method: 'POST', body: form });
}

/**
 * Step 2 · Pick: starts (or finds) the podcast for this note.
 *
 * Either a card from the fixed menu, or the student's own words. A request is
 * still deterministic: the server folds a normalised hash of it into the
 * podcast id, so the same notes and the same ask reuse the same script and MP3.
 */
export type Pick = ({ optionId: FormatId } | { request: string }) & {
  /** 1-20. Overrides any length in the request, and re-times a card. */
  minutes?: number;
};

export function createPodcast(noteId: string, pick: Pick): Promise<{ id: string }> {
  return request('/podcasts', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ noteId, ...pick }),
  });
}

/** Step 3 · Listen: poll until status is "ready" or "failed". */
export const getPodcast = (id: string) => request<Podcast>(`/podcasts/${encodeURIComponent(id)}`);

export function podcastAudioUrl(id: string, download = false): string {
  return `${API_BASE}/podcasts/${encodeURIComponent(id)}/audio.mp3${download ? '?download=1' : ''}`;
}

/**
 * Step 4 · Study: a written review of the notes, with the quiz that tests it
 * written at the same time and stored beside it, so the two cannot drift.
 */
/**
 * What POST /api/reviews actually returns. Note `quiz`, not `questions`:
 * types.ts still carries an older `Review`/`Marks` pair that no route serves,
 * so these are declared against the live shape instead.
 */
export interface ReviewDoc {
  reviewId: string;
  noteId: string;
  podcastId?: string;
  title: string;
  points: ReviewPoint[];
  /** Answers are withheld until the attempt is marked. */
  quiz: Quiz;
}

/** The attempt, plus the deck built from the gaps it exposed. */
export interface AttemptResult extends Attempt {
  deck: Deck;
}

export const createReview = (noteId: string, podcastId?: string) =>
  request<ReviewDoc>('/reviews', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    // Binding it to the lesson is what gives each gap its lineRefs, so a
    // missed question can replay the stretch of audio that taught it.
    body: JSON.stringify(podcastId ? { noteId, podcastId } : { noteId }),
  });

/** Marks the attempt and returns cards for the gaps it exposed. */
export const submitAttempt = (reviewId: string, answers: Record<string, number>) =>
  request<AttemptResult>(`/reviews/${encodeURIComponent(reviewId)}/attempt`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ answers }),
  });

/** Later: grounded questions about the notes (POST /ask). Not in v1. */
export async function ask(question: string, noteId: string): Promise<{ answer: string }> {
  void question;
  void noteId;
  throw new ApiError('Asking questions is not in this version yet.');
}
