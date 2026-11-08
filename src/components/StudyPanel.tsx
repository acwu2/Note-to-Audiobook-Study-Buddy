import type { AttemptResult, ReviewDoc } from '../lib/api';
import type { ReviewPoint } from '../types';

/**
 * The study loop: read the review, take the quiz written alongside it, then
 * drill only the points that were actually missed. `pointId` is the thread
 * through all three, so a card can never be about something untested.
 */

function PointBody({ point }: { point: ReviewPoint }) {
  return (
    <li className="point">
      <div className="point-head">
        <h3 className="point-heading">{point.heading}</h3>
        {point.exam && <span className="exam-tag">on the exam</span>}
        {point.source === 'added' && (
          <span className="added-tag" title="Added to teach the topic, not from your notes">added</span>
        )}
      </div>
      <p className="point-body">{point.body}</p>
    </li>
  );
}

export function ReviewStep({
  review,
  onStartQuiz,
  onBack,
}: {
  review: ReviewDoc | null;
  onStartQuiz: () => void;
  onBack: () => void;
}) {
  if (!review) {
    return (
      <section className="card">
        <h2 className="lede">Writing your review</h2>
        <p className="sub">Pulling out the points worth knowing, and the questions that test them.</p>
      </section>
    );
  }

  // The notes' own starred points first — those are the ones that matter most.
  const points = [...review.points].sort((a, b) => Number(b.exam) - Number(a.exam));

  return (
    <>
      <section className="card">
        <h2 className="lede">{review.title}</h2>
        <p className="sub">
          Read this through, then answer {review.quiz.questions.length}{' '}
          {review.quiz.questions.length === 1 ? 'question' : 'questions'} on it. Anything you miss becomes a card.
        </p>
        <ol className="points">
          {points.map((p) => (
            <PointBody key={p.id} point={p} />
          ))}
        </ol>
      </section>
      <div className="action-bar">
        <button type="button" className="btn primary" onClick={onStartQuiz}>
          I have read it — start the quiz
        </button>
        <button type="button" className="btn quiet" onClick={onBack}>
          Back to the podcast
        </button>
      </div>
    </>
  );
}

export function QuizStep({
  review,
  answers,
  onAnswer,
  onSubmit,
  onBack,
}: {
  review: ReviewDoc;
  answers: Record<string, number>;
  onAnswer: (questionId: string, option: number) => void;
  onSubmit: () => void;
  onBack: () => void;
}) {
  const qs = review.quiz.questions;
  const answered = qs.filter((q) => answers[q.id] !== undefined).length;
  const total = qs.length;

  return (
    <>
      <section className="card">
        <div className="quiz-head">
          <h2 className="lede">Quiz</h2>
          <span className="quiz-count">{answered} of {total} answered</span>
        </div>
        <ol className="questions">
          {qs.map((q, qi) => (
            <li className="question" key={q.id}>
              <p className="q-text">
                <span className="q-n">{qi + 1}</span>
                {q.q}
              </p>
              <div className="choices">
                {q.options.map((opt, oi) => {
                  const id = `${q.id}-${oi}`;
                  return (
                    <label className="choice" key={oi} htmlFor={id}>
                      <input
                        type="radio"
                        id={id}
                        name={q.id}
                        checked={answers[q.id] === oi}
                        onChange={() => onAnswer(q.id, oi)}
                      />
                      <span>{opt}</span>
                    </label>
                  );
                })}
              </div>
            </li>
          ))}
        </ol>
      </section>
      <div className="action-bar">
        <button type="button" className="btn primary" onClick={onSubmit}>
          {answered === total ? 'Mark my answers' : `Mark my answers (${total - answered} blank)`}
        </button>
        <button type="button" className="btn quiet" onClick={onBack}>
          Back to the review
        </button>
      </div>
      {answered < total && (
        <p className="later-note">A blank answer counts as missed, and makes a card like a wrong one does.</p>
      )}
    </>
  );
}

export function MarksStep({
  marks,
  onRetake,
  onBackToPodcast,
  onStartOver,
  onReplay,
}: {
  marks: AttemptResult;
  onRetake: () => void;
  onBackToPodcast: () => void;
  onStartOver: () => void;
  /** Absent when the lesson has no chapters to seek to. */
  onReplay?: (line: number) => void;
}) {
  const perfect = marks.deck.cards.length === 0 && marks.score === marks.total;
  // Gaps carry the lesson lines that taught the missed idea.
  const refsByConcept = new Map(marks.gaps.map((g) => [g.concept, g.lineRefs ?? []]));

  return (
    <>
      <section className={'card score-card' + (perfect ? ' is-perfect' : '')}>
        <p className="score">
          {marks.score} <span className="score-of">/ {marks.total}</span>
        </p>
        {perfect ? (
          <>
            <h2 className="lede">Every one right.</h2>
            <p className="sub">
              There is nothing to drill, so there are no cards — that is the point of them.
              Come back and retake it tomorrow to see whether it stuck.
            </p>
          </>
        ) : (
          <>
            <h2 className="lede">
              {marks.gaps.length === 1
                ? 'One idea to go back over'
                : `${marks.gaps.length} ideas to go back over`}
            </h2>
            <p className="sub">Cards below are built from exactly those, and nothing else.</p>
          </>
        )}
      </section>

      <section className="card">
        <h3 className="eyebrow">Your answers</h3>
        <ol className="results">
          {marks.results.map((r) => {
            const refs = refsByConcept.get(r.concept) ?? [];
            // Only offer a replay when the lesson actually has a place to go.
            const replayable = !r.correct && onReplay && refs.length > 0;
            return (
              <li className="result" key={r.questionId} data-ok={r.correct}>
                <div className="result-head">
                  <span className={'verdict' + (r.correct ? ' ok' : '')}>
                    {r.correct ? 'Right' : r.chosen === null ? 'Blank' : 'Wrong'}
                  </span>
                  <span className="result-q">{r.q}</span>
                </div>
                {!r.correct && (
                  <p className="result-line">
                    {r.chosen === null
                      ? 'You left this blank. '
                      : `You picked “${r.options[r.chosen as number] ?? '—'}”. `}
                    The answer is “{r.options[r.answer] ?? '—'}”.
                  </p>
                )}
                <p className="result-why">{r.why}</p>
                {replayable && (
                  <button type="button" className="chip jump" onClick={() => onReplay(refs[0])}>
                    ▸ Replay the bit that taught this
                  </button>
                )}
              </li>
            );
          })}
        </ol>
      </section>

      {marks.deck.cards.length > 0 && (
        <section className="card">
          <h3 className="eyebrow">Cards for what you missed</h3>
          <ol className="cards">
            {marks.deck.cards.map((c, i) => (
              <li className="flashcard" key={i}>
                <p className="card-front">{c.front}</p>
                <p className="card-back">{c.back}</p>
                <p className="card-why">
                  {c.because || c.concept}
                </p>
              </li>
            ))}
          </ol>
        </section>
      )}

      <div className="action-bar">
        <button type="button" className="btn primary" onClick={onRetake}>
          Take it again
        </button>
        <button type="button" className="btn quiet" onClick={onBackToPodcast}>
          Back to the podcast
        </button>
        <button type="button" className="btn quiet" onClick={onStartOver}>
          Start over with new notes
        </button>
      </div>
    </>
  );
}
