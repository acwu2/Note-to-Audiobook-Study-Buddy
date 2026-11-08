/** Shapes returned by the Study Buddy API (server/app.py, contract v2). */

export type FormatId = 'full_episode' | 'quick_recap' | 'deep_dive';

/** One entry on the fixed menu, titled from the student's notes. */
export interface PodcastOption {
  id: FormatId;
  label: string;
  minutes: number;
  title: string;
  description: string;
  topic?: string;
}

export interface NotePage {
  transcript: string;
  /** Words the vision model marked [unclear]. */
  unclearCount: number;
}

export interface Note {
  noteId: string;
  topic: string;
  pages: NotePage[];
  options: PodcastOption[];
}

export type PodcastStatus = 'queued' | 'writing' | 'recording' | 'mixing' | 'ready' | 'failed';

/**
 * Where a line's content came from. Shown to the student, because the promise
 * is that they can tell their own material apart from what the narrator added
 * to teach it. Older podcasts predate the label, so treat a missing value
 * as 'notes'.
 */
export type LineSource = 'notes' | 'added';

/**
 * What a line is doing in the lesson. A 'check' is a question put to the student
 * and is followed by a long silence in the audio, so they can answer out loud
 * before the lesson continues — that pause is what makes this studying rather
 * than listening. Older podcasts predate the field; treat a missing value as 'teach'.
 */
export type LineRole = 'hook' | 'teach' | 'check' | 'answer' | 'recap';

export interface ScriptLine {
  host: 'Heart' | 'Michael';
  text: string;
  source?: LineSource;
  role?: LineRole;
}

/**
 * A point the listener can jump to. `startSeconds` is exact: the mixer knows
 * every line's rendered duration before it concatenates, so offsets come out of
 * that loop rather than being estimated from word counts. Seek straight to it.
 *
 * Absent when no sound chapter plan could be made — a wrong chapter is worse
 * than none, so the server drops the whole list rather than emit a bad one.
 */
export interface Chapter {
  title: string;
  startLine: number;
  startSeconds: number;
}

export interface Podcast {
  id: string;
  noteId: string;
  /** 'custom' when the student typed their own request instead of picking a card. */
  optionId: FormatId | 'custom';
  title: string;
  format: string;
  status: PodcastStatus;
  script?: ScriptLine[];
  chapters?: Chapter[];
  /** Echo of what the student asked for, when they asked in their own words. */
  requestText?: string;
  seconds?: number;
  audioUrl?: string;
  error?: string;
}

export interface Health {
  ok: boolean;
  fakeAi: boolean;
  fakeTts: boolean;
  model: string | null;
}

/** A file the student added, with a preview for photos. */
export interface Upload {
  file: File;
  previewUrl: string | null;
}
