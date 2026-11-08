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
  /**
   * Three example requests written from these notes, for showing beside the
   * request box. May be empty — render nothing rather than a placeholder.
   */
  suggestions?: string[];
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
  /** The length that was asked for, when one was. Compare with `seconds`. */
  askedMinutes?: number;
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

/* ---- Listen → quiz → flashcards for what you missed ---------------------- */

/**
 * A quiz question as the student receives it. The correct answer and the
 * explanation are deliberately absent: marking happens on the server, so the
 * answers are never sitting in the page.
 */
export interface QuizQuestion {
  id: string;
  q: string;
  options: string[];
}

export interface Quiz {
  id: string;
  podcastId: string;
  questions: QuizQuestion[];
}

/** One marked question, returned after an attempt is submitted. */
export interface QuizResult {
  questionId: string;
  q: string;
  options: string[];
  /** What they chose, or null when they left it blank. */
  chosen: number | null;
  answer: number;
  correct: boolean;
  why: string;
  /** The idea this question tested. Missing it is what makes it a weak point. */
  concept: string;
}

/**
 * A weakness the attempt exposed. One gap per concept, however many questions
 * on that concept were missed — two misses on the same idea is one weakness.
 */
export interface Gap {
  concept: string;
  misses: { q: string; chose: string | null; right: string; skipped: boolean }[];
  /** Lesson lines that taught this, so the UI can offer to replay them. */
  lineRefs: number[];
}

export interface Attempt {
  id: string;
  quizId: string;
  podcastId: string;
  score: number;
  total: number;
  results: QuizResult[];
  gaps: Gap[];
}

/**
 * A card written against a gap, not a replay of the question. `because` names
 * the mistake it answers ("you picked the cytoplasm"), so the student can see
 * why this card is in front of them.
 */
export interface Flashcard {
  front: string;
  back: string;
  concept: string;
  because: string;
}

/** Empty `cards` is a clean sweep, not a failure: there is nothing to drill. */
export interface Deck {
  id: string;
  attemptId: string;
  cards: Flashcard[];
}

/* ---- Study loop: read a review, take the quiz, drill what you missed ----
 *
 * These three are one loop, not three features. `pointId` is the thread: every
 * quiz question names the review point it tests, and a flashcard is only ever
 * made from a point this student actually got wrong.
 */

export interface ReviewPoint {
  id: string;
  heading: string;
  body: string;
  source: LineSource;
  /** True only where the notes themselves flag it as examinable. */
  exam: boolean;
}

export interface QuizQuestion {
  /** The review point this tests. Always matches a ReviewPoint.id. */
  pointId: string;
  q: string;
  /** Exactly four, all distinct. */
  options: string[];
  /** Index into options. Present so the UI can mark without a round trip. */
  answer: number;
  why: string;
}

export interface Review {
  reviewId: string;
  noteId: string;
  title: string;
  points: ReviewPoint[];
  /** Written with the review and stored beside it, so the two cannot drift. */
  questions: QuizQuestion[];
}

export interface QuizResult {
  pointId: string;
  /** What the student picked, or null if they skipped it. */
  picked: number | null;
  correct: boolean;
  answer: number;
  why: string;
}

export interface Flashcard {
  /** The missed point this drills. */
  pointId: string;
  front: string;
  back: string;
}

export interface Marks {
  reviewId: string;
  score: number;
  total: number;
  results: QuizResult[];
  missedPointIds: string[];
  /** Empty on a perfect score — there is nothing to reinforce. */
  cards: Flashcard[];
}
