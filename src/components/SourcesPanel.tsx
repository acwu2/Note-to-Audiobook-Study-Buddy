import { useRef, useState } from 'react';
import type { Source, SourceTab } from '../types';
import { CameraIcon, ChevronLeftIcon, PlayIcon } from './Icons';

interface Props {
  sources: Source[];
  openSourceId: string | null;
  onOpen: (id: string) => void;
  onClose: () => void;
  onToggle: (id: string) => void;
  onToggleAll: (enabled: boolean) => void;
  onListen: () => void;
}

const statusLabel = (s: Source) =>
  s.status === 'reading'
    ? 'Reading handwriting…'
    : s.status === 'unclear'
      ? `${s.unclearCount} unclear word${s.unclearCount === 1 ? '' : 's'}`
      : 'Transcribed';

const tabs: { id: SourceTab; label: string; hint: string }[] = [
  { id: 'photo', label: 'Photo', hint: 'The page exactly as you photographed it.' },
  { id: 'transcript', label: 'Transcript', hint: 'What the vision model read. Edit anything it got wrong.' },
  { id: 'spoken', label: 'Read-aloud', hint: 'Rewritten for the ear: symbols and shorthand spelled out, every fact kept.' },
];

export default function SourcesPanel(props: Props) {
  const { sources, openSourceId } = props;
  const current = sources.find((s) => s.id === openSourceId);
  return (
    <section className="panel panel-sources" aria-label="Sources">
      {current ? <SourceViewer source={current} {...props} /> : <SourceList {...props} />}
    </section>
  );
}

function SourceList({ sources, onOpen, onToggle, onToggleAll }: Props) {
  const fileInput = useRef<HTMLInputElement>(null);
  const allOn = sources.every((s) => s.enabled);

  return (
    <>
      <div className="panel-head">
        <h2>Sources</h2>
        <span className="muted">{sources.length} pages</span>
      </div>
      <div className="dropzone-wrap">
        {/* TODO: send chosen files to api.transcribe() */}
        <input ref={fileInput} type="file" accept="image/*,application/pdf" multiple hidden />
        <button type="button" className="dropzone" onClick={() => fileInput.current?.click()}>
          <CameraIcon size={24} className="accent" />
          <strong>Add a photo of your notes</strong>
          <span className="muted">Drop images or PDFs, or snap one with your phone</span>
        </button>
      </div>
      <label className="toggle-all">
        Use all sources in answers
        <input type="checkbox" checked={allOn} onChange={() => onToggleAll(!allOn)} />
      </label>
      <ul className="source-list">
        {sources.map((s) => (
          <li key={s.id} className="source-row">
            <button type="button" className="source-open" onClick={() => onOpen(s.id)}>
              <span className="paper-thumb" aria-hidden="true" />
              <span className="source-meta">
                <span className="source-name">{s.name}</span>
                <span className={`chip chip-${s.status}`}>{statusLabel(s)}</span>
              </span>
            </button>
            <input
              type="checkbox"
              checked={s.enabled}
              onChange={() => onToggle(s.id)}
              aria-label={`Use ${s.name} in answers`}
            />
          </li>
        ))}
      </ul>
    </>
  );
}

function SourceViewer({ source, onClose, onListen }: Props & { source: Source }) {
  const [tab, setTab] = useState<SourceTab>('transcript');
  const hint = tabs.find((t) => t.id === tab)?.hint;
  const reading = source.status === 'reading';

  return (
    <>
      <div className="panel-head panel-head-back">
        <button type="button" className="icon-btn" onClick={onClose} aria-label="Back to sources">
          <ChevronLeftIcon size={20} />
        </button>
        <h2 className="truncate">{source.name}</h2>
      </div>
      <div className="segmented" role="tablist" aria-label="Source view">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            className={tab === t.id ? 'is-active' : ''}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <p className="tab-hint">{hint}</p>
      <div className="panel-body">
        {reading ? (
          <p className="muted">Still reading this page.</p>
        ) : tab === 'photo' ? (
          source.photoUrl ? (
            <img className="photo" src={source.photoUrl} alt={`Photo of ${source.name}`} />
          ) : (
            <div className="paper">
              <p>{source.transcript}</p>
            </div>
          )
        ) : tab === 'transcript' ? (
          <>
            <p className="prose">{source.transcript}</p>
            {source.unclearCount > 0 && (
              <div className="callout">
                <strong>{source.unclearCount} word marked [unclear].</strong> Check it against the photo and fix it
                here before you listen.
              </div>
            )}
          </>
        ) : (
          <>
            <p className="prose">{source.spoken}</p>
            <button type="button" className="btn btn-dark" onClick={onListen}>
              <PlayIcon size={16} className="accent-bright" />
              Listen to this page
            </button>
          </>
        )}
      </div>
    </>
  );
}
