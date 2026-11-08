import type { ReactNode } from 'react';
import { BookIcon, HeadphonesIcon, MicIcon, ShieldIcon, VolumeIcon, BookmarkIcon } from './Icons';

type Tool = {
  id: string;
  title: string;
  blurb: string;
  icon: ReactNode;
  tone: string;
  best?: boolean;
  /** Absent when the tool is not built, which renders it as unavailable. */
  go?: () => void;
  soon?: string;
};

/**
 * The reference's "What do you want to make?" grid. Three of the six are real
 * today; the rest are shown because the grid is the design, but they say so
 * rather than leading somewhere empty.
 */
export default function MakeGrid({
  topic,
  pageCount,
  onAudiobook,
  onQuiz,
  onStudyGuide,
  onBack,
}: {
  topic: string;
  pageCount: number;
  onAudiobook: () => void;
  onQuiz: () => void;
  onStudyGuide: () => void;
  onBack: () => void;
}) {
  const tools: Tool[] = [
    {
      id: 'quiz', title: 'Quiz', tone: 'dark', best: true,
      blurb: 'Questions from your notes, then cards for whatever you miss.',
      icon: <ShieldIcon />, go: onQuiz,
    },
    {
      id: 'flashcards', title: 'Flashcards', tone: 'violet',
      blurb: 'Cards for the things you got wrong.',
      icon: <BookmarkIcon />, soon: 'Comes with the quiz',
    },
    {
      id: 'audiobook', title: 'Audiobook', tone: 'amber',
      blurb: 'Two hosts read your notes, with chapters you can jump between.',
      icon: <HeadphonesIcon />, go: onAudiobook,
    },
    {
      id: 'guide', title: 'Study guide', tone: 'green',
      blurb: 'The points worth knowing, with the exam ones marked.',
      icon: <BookIcon />, go: onStudyGuide,
    },
    {
      id: 'explain', title: 'Explain it simply', tone: 'blue',
      blurb: 'Ask anything and hear it explained from your notes.',
      icon: <MicIcon />, soon: 'Not wired up yet',
    },
    {
      id: 'exam', title: 'Practice exam', tone: 'rose',
      blurb: 'A longer paper under timed conditions.',
      icon: <VolumeIcon />, soon: 'Not built yet',
    },
  ];

  return (
    <>
      <div className="summary-bar">
        <button type="button" className="btn quiet back" onClick={onBack}>‹ Back</button>
        <div className="summary-text">
          <strong>{pageCount} {pageCount === 1 ? 'page' : 'pages'} read · {topic}</strong>
          <span>Handwriting turned into text</span>
        </div>
      </div>

      <section className="card">
        <h1 className="lede">What do you want to make?</h1>
        <p className="sub">Pick one to start. You can come back and make the rest from the same notes.</p>
        <ul className="tiles">
          {tools.map((t) => {
            const live = !!t.go;
            return (
              <li key={t.id}>
                <button
                  type="button"
                  className={`tile tone-${t.tone}` + (t.tone === 'dark' ? ' is-dark' : '') + (live ? '' : ' is-soon')}
                  onClick={t.go}
                  disabled={!live}
                >
                  <span className="tile-top">
                    <span className="tile-icon" aria-hidden="true">{t.icon}</span>
                    {t.best && <span className="tile-badge">Best start</span>}
                    {t.soon && <span className="tile-badge soon">{t.soon}</span>}
                  </span>
                  <span className="tile-title">{t.title}</span>
                  <span className="tile-blurb">{t.blurb}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </section>
    </>
  );
}
