import { useRef, useState } from 'react';
import ListenPanel from './components/ListenPanel';
import { MarksStep, QuizStep, ReviewStep } from './components/StudyPanel';
import { CameraIcon, RefreshIcon } from './components/Icons';
import TopBar from './components/TopBar';
import MakeGrid from './components/MakeGrid';
import { useStudyBuddy, type Step } from './lib/useStudyBuddy';
import type { PodcastStatus } from './types';

const STEPS: { key: string; label: string }[] = [
  { key: 'upload', label: 'Upload' },
  { key: 'make', label: 'Make' },
  { key: 'listen', label: 'Listen' },
  { key: 'study', label: 'Study' },
];

const LENGTHS = [3, 5, 8, 10, 15, 20];

const railPosition = (step: Step) =>
  step === 'upload' || step === 'reading' ? 0
    : step === 'pick' ? 1
    : step === 'audiobook' || step === 'making' || step === 'ready' ? 2
    : 3;

/** The podcast job's stages, in the order the server reports them. */
const MAKING: { status: PodcastStatus; label: string; detail: string }[] = [
  { status: 'writing', label: 'Writing the script', detail: 'Two hosts, using only facts from your notes' },
  { status: 'recording', label: 'Recording two voices', detail: 'Kokoro · Heart and Michael' },
  { status: 'mixing', label: 'Mixing the MP3', detail: 'Lines joined with short pauses' },
];

const CheckIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M20 6L9 17l-5-5" />
  </svg>
);

function StageRow({ state, label, detail }: { state: 'done' | 'active' | 'pending'; label: string; detail: string }) {
  return (
    <li className="stage" data-state={state}>
      <span className={'dot' + (state === 'active' ? ' pulse' : '')} aria-hidden="true">
        {state === 'done' ? <CheckIcon /> : null}
      </span>
      <span className="stage-text">
        <span className="stage-label">{label}</span>
        <span className="stage-detail">{detail}</span>
      </span>
    </li>
  );
}

export default function App() {
  const sb = useStudyBuddy();
  const fileRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  const pos = railPosition(sb.step);
  const status = sb.podcast?.status;
  const failed = status === 'failed';
  const stageIndex = MAKING.findIndex((s) => s.status === status);
  const pageCount = sb.uploads.length || sb.note?.pages.length || 0;
  const unclear = sb.note?.pages.reduce((n, p) => n + p.unclearCount, 0) ?? 0;

  // Typing a request takes over from the selected card, so there is one action.
  const asking = sb.request.trim().length > 0;
  const pickedOption = sb.note?.options.find((o) => o.id === sb.picked);
  const lengthDefaultLabel = asking
    ? 'However long it needs'
    : pickedOption
      ? `As suggested (${pickedOption.minutes} min)`
      : 'As suggested';

  const start = () =>
    void sb.make({
      ...(asking ? { request: sb.request.trim() } : { optionId: sb.picked }),
      ...(sb.minutes ? { minutes: sb.minutes } : {}),
    });

  return (
    <>
      <TopBar crumb={sb.note?.topic} />
      <div className="page">

      <main className="flow">
        <ol className="rail" aria-label="Steps">
          {STEPS.map((s, i) => (
            <li key={s.key} data-state={i < pos ? 'done' : i === pos ? 'here' : 'ahead'}>
              <span className="pip" aria-hidden="true">{i < pos ? <CheckIcon /> : i + 1}</span>
              <span className="rail-label">{s.label}</span>
            </li>
          ))}
        </ol>

        {sb.error && (
          <div className="notice" role="alert">
            <span>{sb.error}</span>
          </div>
        )}

        {/* ---------- 1 · Upload ---------- */}
        {sb.step === 'upload' && (
          <section className="card">
            <h1 className="lede">Turn a photo of your notes into a podcast</h1>
            <p className="sub">
              Add the pages you want to revise. Study Buddy reads them, offers a few podcasts it can make,
              and records the one you pick with two hosts.
            </p>
            <button
              type="button"
              className={'drop' + (over ? ' is-over' : '')}
              onClick={() => fileRef.current?.click()}
              onDragEnter={(e) => { e.preventDefault(); setOver(true); }}
              onDragOver={(e) => { e.preventDefault(); setOver(true); }}
              onDragLeave={() => setOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setOver(false);
                if (e.dataTransfer.files.length) void sb.addFiles(e.dataTransfer.files);
              }}
            >
              <span className="drop-mark" aria-hidden="true"><CameraIcon /></span>
              <span className="drop-title">Add photos of your notes</span>
              <span className="drop-hint">Drop images or PDFs here, or take a photo with your phone.</span>
            </button>
            <input
              ref={fileRef}
              type="file"
              accept="image/*,application/pdf"
              multiple
              hidden
              onChange={(e) => {
                if (e.target.files?.length) void sb.addFiles(e.target.files);
                e.target.value = '';
              }}
            />
          </section>
        )}

        {/* ---------- Reading ---------- */}
        {sb.step === 'reading' && (
          <section className="card">
            <h2 className="lede">Reading your notes</h2>
            {sb.uploads.length > 0 && (
              <div className="thumbs">
                {sb.uploads.map((u, i) =>
                  u.previewUrl ? (
                    <span className="thumb" key={i}><img src={u.previewUrl} alt={`Page ${i + 1}`} /></span>
                  ) : (
                    <span className="thumb" key={i}>PDF</span>
                  ),
                )}
              </div>
            )}
            <ol className="stages">
              <StageRow
                state="active"
                label={pageCount === 1 ? 'Reading your page' : `Reading your ${pageCount} pages`}
                detail="Handwriting becomes text. Words it cannot make out are marked, never guessed."
              />
              <StageRow
                state="pending"
                label="Finding what you can make"
                detail="Picks from a fixed menu of podcast formats"
              />
            </ol>
          </section>
        )}

        {/* ---------- 2 · Pick ---------- */}
        {sb.step === 'pick' && sb.note && (
          <MakeGrid
            topic={sb.note.topic}
            pageCount={sb.note.pages.length}
            onAudiobook={() => sb.setStep('audiobook')}
            onQuiz={() => void sb.startReview()}
            onStudyGuide={() => void sb.startReview()}
            onBack={sb.reset}
          />
        )}

        {sb.step === 'audiobook' && sb.note && (
          <>
            <section className="card">
              <h2 className="lede">
                Your notes are on {sb.note.topic}. Which podcast do you want?
              </h2>
              {unclear > 0 && (
                <p className="sub">
                  <span className="unclear-tag">{unclear} unclear {unclear === 1 ? 'word' : 'words'}</span>{' '}
                  were too hard to read, so they are left out of the script.
                </p>
              )}
              <div className="options">
                {sb.note.options.map((o) => (
                  <button
                    key={o.id}
                    type="button"
                    className="option"
                    aria-pressed={sb.picked === o.id}
                    onClick={() => sb.setPicked(o.id)}
                  >
                    <span className="option-top">
                      <span className="option-format">{o.label}</span>
                      <span className="option-length">About {o.minutes} min</span>
                    </span>
                    <span className="option-title">{o.title}</span>
                    <span className="option-desc">{o.description}</span>
                  </button>
                ))}
              </div>
              <div className="later">
                <span className="later-note">Later:</span>
                <span className="later-chip">Quiz</span>
                <span className="later-chip">Study guide</span>
                <span className="later-chip">Flashcards</span>
              </div>
            </section>

            <section className="card">
              <div className="ask-head">
                <h3 className="eyebrow">Or ask for exactly what you want</h3>
                <p className="sub">
                  Say how long it should be and what it should cover. Asking the same thing twice
                  gives you the same episode back.
                </p>
              </div>
              {sb.note.suggestions && sb.note.suggestions.length > 0 && (
                <div className="suggestions">
                  <span className="later-note">From your notes:</span>
                  {sb.note.suggestions.map((s, i) => (
                    <button key={i} type="button" className="chip-suggest" onClick={() => sb.setRequest(s)}>
                      {s}
                    </button>
                  ))}
                </div>
              )}
              <label className="visually-hidden" htmlFor="request">Your request</label>
              <textarea
                id="request"
                className="ask-box"
                rows={3}
                value={sb.request}
                placeholder="A 5 minute overview of everything in my notes, broken into chapters covering everything I should know."
                onChange={(e) => sb.setRequest(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && asking) {
                    e.preventDefault();
                    start();
                  }
                }}
              />
            </section>

            {/* One action, so it is never ambiguous which thing gets made. */}
            <div className="action-bar">
              <label className="length">
                <span>Length</span>
                <select
                  value={sb.minutes ?? ''}
                  onChange={(e) => sb.setMinutes(e.target.value ? Number(e.target.value) : null)}
                >
                  <option value="">{lengthDefaultLabel}</option>
                  {LENGTHS.map((m) => (
                    <option key={m} value={m}>{m} min</option>
                  ))}
                </select>
              </label>
              <button type="button" className="btn primary" onClick={start}>
                {asking ? 'Make what I asked for' : 'Make this podcast'}
              </button>
              <button type="button" className="btn quiet" onClick={() => sb.setStep('pick')}>
                Back to the tools
              </button>
            </div>
            {asking && (
              <p className="later-note">
                Using your own words. Clear the box to use the card instead.
              </p>
            )}
          </>
        )}

        {/* ---------- Making ---------- */}
        {sb.step === 'making' && (
          <section className="card">
            <h2 className="lede">
              {sb.podcast?.requestText
                ? 'Making what you asked for'
                : `Making “${sb.note?.options.find((o) => o.id === sb.picked)?.title ?? 'your podcast'}”`}
            </h2>
            {sb.podcast?.requestText && <p className="asked">“{sb.podcast.requestText}”</p>}
            <ol className="stages">
              {MAKING.map((s, i) => (
                <StageRow
                  key={s.status}
                  state={
                    failed ? (i === stageIndex ? 'active' : 'pending')
                      : stageIndex < 0 ? (i === 0 ? 'active' : 'pending')
                      : i < stageIndex ? 'done'
                      : i === stageIndex ? 'active'
                      : 'pending'
                  }
                  label={s.label}
                  detail={s.detail}
                />
              ))}
            </ol>
            {failed && (
              <>
                <div className="notice" role="alert">
                  <span>{sb.podcast?.error ?? 'The podcast could not be finished.'}</span>
                </div>
                <div className="row">
                  <button type="button" className="btn primary" onClick={() => void sb.retry()}>
                    <RefreshIcon /> Try again
                  </button>
                  <button type="button" className="btn quiet" onClick={sb.backToPick}>
                    Pick a different podcast
                  </button>
                </div>
              </>
            )}
            {!failed && (
              <p className="notice calm">
                This takes a few minutes. The free model tier allows only a few requests a minute,
                so each step waits its turn rather than failing.
              </p>
            )}
          </section>
        )}

        {/* ---------- 3 · Listen ---------- */}
        {sb.step === 'ready' && sb.podcast && (
          <ListenPanel
            podcast={sb.podcast}
            onPickAnother={sb.backToPick}
            onStartOver={sb.reset}
            onStudy={() => void sb.startReview()}
            replayLine={sb.replayLine}
            onReplayed={sb.clearReplay}
          />
        )}

        {/* ---------- 4 · Study: review, quiz, cards ---------- */}
        {sb.step === 'review' && (
          <ReviewStep
            review={sb.review}
            onStartQuiz={() => sb.setStep('quiz')}
            onBack={() => sb.setStep('ready')}
          />
        )}
        {sb.step === 'quiz' && sb.review && (
          <QuizStep
            review={sb.review}
            answers={sb.answers}
            onAnswer={sb.answer}
            onSubmit={() => void sb.submitQuiz()}
            onBack={() => sb.setStep('review')}
          />
        )}
        {sb.step === 'marks' && sb.marks && (
          <MarksStep
            marks={sb.marks}
            onRetake={sb.retakeQuiz}
            onBackToPodcast={() => sb.setStep('ready')}
            onStartOver={sb.reset}
            onReplay={sb.podcast?.chapters?.length ? sb.requestReplay : undefined}
          />
        )}
      </main>
      </div>
    </>
  );
}
