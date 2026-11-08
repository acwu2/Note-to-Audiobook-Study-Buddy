import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ApiError, createNote, createPodcast, createReview, getPodcast, submitAttempt,
  type AttemptResult, type Pick, type ReviewDoc,
} from './api';
import type { FormatId, Note, Podcast, Upload } from '../types';

export type Step =
  | 'upload' | 'reading' | 'pick' | 'audiobook' | 'making' | 'ready'
  // the study loop: read the review, take the quiz it was written with, drill what you missed
  | 'review' | 'quiz' | 'marks';

const POLL_MS = 1500;
const ACCEPTED = /^(image\/(jpeg|png|webp|heic|heif)|application\/pdf)$/;

const message = (e: unknown) =>
  e instanceof ApiError ? e.message : 'Something went wrong. Try again.';

/** The whole upload → pick → listen flow, with no free text anywhere. */
export function useStudyBuddy() {
  const [step, setStep] = useState<Step>('upload');
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [note, setNote] = useState<Note | null>(null);
  const [picked, setPicked] = useState<FormatId>('full_episode');
  const [podcast, setPodcast] = useState<Podcast | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [request, setRequest] = useState('');
  /** null means "whatever the card or the request implies". */
  const [minutes, setMinutes] = useState<number | null>(null);
  const [review, setReview] = useState<ReviewDoc | null>(null);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [marks, setMarks] = useState<AttemptResult | null>(null);
  const [replayLine, setReplayLine] = useState<number | null>(null);
  const uploadsRef = useRef<Upload[]>([]);
  uploadsRef.current = uploads;
  const lastPick = useRef<Pick | null>(null);

  const clearPreviews = () =>
    uploadsRef.current.forEach((u) => u.previewUrl && URL.revokeObjectURL(u.previewUrl));
  useEffect(() => clearPreviews, []);

  const addFiles = useCallback(async (list: FileList | File[]) => {
    const files = Array.from(list).filter((f) => ACCEPTED.test(f.type) || /\.(heic|heif)$/i.test(f.name));
    if (files.length === 0) {
      setError('Add photos (JPG, PNG, WebP, HEIC) or a PDF of your notes.');
      return;
    }
    clearPreviews();
    const next = files.map((file) => ({
      file,
      previewUrl: file.type.startsWith('image/') ? URL.createObjectURL(file) : null,
    }));
    setUploads(next);
    setError(null);
    setStep('reading');
    try {
      const result = await createNote(files);
      setNote(result);
      setPicked(result.options[0]?.id ?? 'full_episode');
      setStep('pick');
    } catch (e) {
      setError(message(e));
      setStep('upload');
    }
  }, []);

  /**
   * Start a podcast: the selected card by default, or the student's own words
   * when a request is passed. The last choice is kept so Try again repeats it.
   */
  const make = useCallback(
    async (pick?: Pick) => {
      if (!note) return;
      const choice: Pick = pick ?? { optionId: picked };
      lastPick.current = choice;
      setError(null);
      setPodcast(null);
      setStep('making');
      try {
        const { id } = await createPodcast(note.noteId, choice);
        setPodcast(await getPodcast(id));
      } catch (e) {
        setError(message(e));
        setStep('pick');
      }
    },
    [note, picked],
  );

  const retry = useCallback(() => make(lastPick.current ?? undefined), [make]);

  // ---- the study loop ----
  const startReview = useCallback(async () => {
    if (!note) return;
    setError(null);
    setMarks(null);
    setAnswers({});
    setStep('review');
    // Reuse only when it was written for these notes AND this lesson, since
    // lineRefs point into one specific script.
    if (review?.noteId === note.noteId && review.podcastId === podcast?.id) return;
    setReview(null);
    try {
      setReview(await createReview(note.noteId, podcast?.id));
    } catch (e) {
      setError(message(e));
      setStep('ready');
    }
  }, [note, review, podcast]);

  const answer = useCallback(
    (pointId: string, option: number) => setAnswers((a) => ({ ...a, [pointId]: option })),
    [],
  );

  const submitQuiz = useCallback(async () => {
    if (!review) return;
    setError(null);
    try {
      setMarks(await submitAttempt(review.reviewId, answers));
      setStep('marks');
    } catch (e) {
      setError(message(e));
    }
  }, [review, answers]);

  /**
   * A missed point asks to hear the lesson again. The line is handed to the
   * player, which maps it to the nearest chapter and seeks there.
   */
  const requestReplay = useCallback((line: number) => {
    setReplayLine(line);
    setStep('ready');
  }, []);
  const clearReplay = useCallback(() => setReplayLine(null), []);

  const retakeQuiz = useCallback(() => {
    setAnswers({});
    setMarks(null);
    setStep('quiz');
  }, []);

  // While making, check the job until it is ready or failed.
  const podcastId = podcast?.id;
  const podcastStatus = podcast?.status;
  useEffect(() => {
    if (step !== 'making' || !podcastId) return;
    if (podcastStatus === 'ready') {
      setStep('ready');
      return;
    }
    if (podcastStatus === 'failed') return;
    const t = setTimeout(async () => {
      try {
        setPodcast(await getPodcast(podcastId));
      } catch (e) {
        setError(message(e));
      }
    }, POLL_MS);
    return () => clearTimeout(t);
  }, [step, podcastId, podcastStatus, podcast]);

  const backToPick = useCallback(() => {
    setError(null);
    setPodcast(null);
    setStep('pick');
  }, []);

  const reset = useCallback(() => {
    clearPreviews();
    setUploads([]);
    setNote(null);
    setPodcast(null);
    setError(null);
    setRequest('');
    setMinutes(null);
    setReview(null);
    setAnswers({});
    setMarks(null);
    lastPick.current = null;
    setStep('upload');
  }, []);

  return {
    step, setStep, uploads, note, picked, setPicked, podcast, error,
    request, setRequest, minutes, setMinutes,
    review, answers, marks, startReview, answer, submitQuiz, retakeQuiz,
    replayLine, requestReplay, clearReplay,
    addFiles, make, retry, backToPick, reset,
  };
}

export type StudyBuddy = ReturnType<typeof useStudyBuddy>;
