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
  /**
   * One or two sentences stating what this chapter teaches, written to be read
   * on the page while it plays. It states the facts rather than trailing them,
   * so a student who reads it has learned the thing with the sound off.
   */
  summary?: string;
  /**
   * Review points this chapter teaches, when a review exists for these notes
   * and the match was convincing. Lets a point the student got wrong in the
   * quiz link straight to the audio that explains it. Absent or empty means no
   * confident match — show no link rather than a wrong one.
   */
  pointIds?: string[];
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
  /**
   * Where each script line begins in the audio, in seconds, aligned with `script`.
   * The audio also has a spoken opening and chapter announcements that are not in
   * `script`, so use these rather than adding up durations. Replay a missed
   * question from lineStarts[scriptLines[0]].
   */
  lineStarts?: number[];
  /**
   * The audiobook as text, to show beneath the player: a contents list with
   * times, then a section per chapter. `outline.text` is the whole thing as
   * plain text; `outline.entries` is the same, structured, so each contents row
   * can seek to its startSeconds. Absent until the podcast is ready.
   */
  outline?: Outline;
  /** The same audiobook as .m4b, with its chapters, for audiobook apps. */
  audiobookUrl?: string;
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
 * What the server really serves (read from app.py, not from memory):
 *
 *   POST /api/reviews  { noteId, podcastId? }
 *        -> { reviewId, noteId, podcastId?, title, points: ReviewPoint[],
 *             quiz: { id, podcastId, questions: [{ id, q, options }] } }
 *      The quiz carries NO answers: they stay on the server until the attempt.
 *
 *   POST /api/reviews/{reviewId}/attempt  { reviewId, answers: { [questionId]: optionIndex } }
 *        -> an Attempt (above) plus { deck: Deck } and, per gap, scriptLines.
 *
 * Those two response shapes are declared in lib/api.ts as ReviewDoc and
 * AttemptResult, next to the calls that return them, so they cannot drift from
 * the code. An earlier version of this section declared Review, ReviewQuestion,
 * ReviewResult, ReviewCard and Marks for a /marks route that was merged away;
 * nothing served them, tsc stayed green over them, and they cost a build cycle.
 * Only the point shape is shared across files, so only it lives here.
 */

export interface ReviewPoint {
  id: string;
  heading: string;
  body: string;
  source: LineSource;
  /** True only where the notes themselves flag it as examinable. */
  exam: boolean;
  /**
   * Lines of the lesson script that taught this point, when the review was
   * made from a podcast. Use with that podcast's chapters to replay the
   * stretch a missed point came from. Empty when there is nothing to replay.
   */
  lineRefs?: number[];
}

/* ---- Ask: a free question, answered from the notes by the podcast's hosts ----
 *
 * POST /api/ask  { noteId, question, podcastId? }  -> Answer
 * GET  audioUrl  -> the answer spoken by Heart and Michael, the same voices as
 *                   the lesson. Rendered on first request (a few seconds, then cached).
 */

export interface AskLine {
  host: 'Heart' | 'Michael';
  text: string;
}

export interface Answer {
  answerId: string;
  noteId: string;
  question: string;
  /** Two to four lines, Heart first. Show as a short exchange; the audio is this. */
  lines: AskLine[];
  /** The lines joined, for anything that wants plain text. */
  answer: string;
  /**
   * False means the notes do not contain the answer and the hosts said so.
   * Style that differently from an answer; it is the product working, not failing.
   */
  found: boolean;
  /**
   * An exact phrase from the student's notes that supports the answer. Verified
   * against the notes on the server; empty rather than unverified.
   */
  quote: string;
  /** Lines of the lesson (when podcastId was sent) that said it, for replay. May be empty. */
  scriptLines: number[];
  audioUrl: string;
}

/* ---- The audiobook outline: front matter in text ---- */

export interface OutlineEntry {
  number: number;
  title: string;
  startSeconds: number;
  /** "1:51", ready to show beside the title. */
  timestamp: string;
  /** What the chapter teaches, written as text (symbols as in the notes). May be empty. */
  summary: string;
  /** [first, last] script line of the chapter. */
  lines: [number, number];
  /** How many questions this chapter stops to ask. */
  questions: number;
  /** Review points the chapter teaches, once the student has a review. May be empty. */
  pointIds: string[];
}

export interface Outline {
  title: string;
  totalSeconds: number;
  totalTimestamp: string;
  entries: OutlineEntry[];
  /** Title, length, contents and a section per chapter, as plain text. */
  text: string;
}

/* ---- Spoken quiz: the questions read aloud, and a judge for the reply ----
 *
 * POST /api/reviews/{reviewId}/voice-quiz { answerSeconds? }  -> VoiceQuiz   (first call renders ~25s)
 * GET  audioUrl                                               -> mp3, each question a chapter in the file
 * POST /api/voice-quizzes/{quizId}/judge  multipart: recording (any audio) and/or text -> Judgement
 *
 * To turn the misses into flashcards, send Judgement.answers to
 * POST /api/reviews/{reviewId}/attempt, as for a quiz taken on screen.
 */

export interface VoiceQuizQuestion {
  /** The quiz question id; the key in Judgement.answers. */
  id: string;
  number: number;
  q: string;
  options: string[];
  startSeconds: number;
  /** The silence the student answers in. Slice or highlight this range of the audio. */
  answerStartSeconds: number;
  answerEndSeconds: number;
}

export interface VoiceQuiz {
  quizId: string;
  reviewId: string;
  title: string;
  /** How long the audio waits after each question. */
  answerSeconds: number;
  seconds: number;
  questions: VoiceQuizQuestion[];
  audioUrl: string;
}

export interface JudgedAnswer {
  questionId: string;
  number: number;
  q: string;
  options: string[];
  /** What the student was heard to say for this question. Show it, so a misheard answer can be spotted. */
  heard: string;
  /** Index of the option they chose, or null when no answer was heard or it matched no option. */
  picked: number | null;
  skipped: boolean;
  correct: boolean;
  answer: number;
  /** The stored explanation, with the right answer named when they missed. Never model-written. */
  feedback: string;
}

export interface Judgement {
  quizId: string;
  reviewId: string;
  score: number;
  total: number;
  results: JudgedAnswer[];
  /** { questionId: optionIndex } for the questions they answered. Pass to /attempt. */
  answers: Record<string, number>;
}

/* ---- My notes: GET /api/notes ---- */

export interface NoteSummary {
  noteId: string;
  topic: string;
  pages: number;
  unclear: number;
  /** When the notes were last saved (ISO), newest first. */
  savedAt: string;
  /** Finished audiobooks made from these notes. */
  podcasts: { id: string; title: string; format: string; status: string; seconds?: number }[];
}
