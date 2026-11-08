import { useState, type FormEvent } from 'react';
import type { ChatMessage, Source } from '../types';
import { notebookGuide, suggestedQuestions } from '../data/sampleNotebook';
import { ArrowUpIcon, BookmarkIcon, MicIcon, PlayIcon, ShieldIcon, VolumeIcon } from './Icons';

interface Props {
  messages: ChatMessage[];
  sources: Source[];
  onAsk: (q: string) => void;
  onOpenSource: (id: string) => void;
  onListen: () => void;
}

export default function ChatPanel({ messages, sources, onAsk, onOpenSource, onListen }: Props) {
  const [draft, setDraft] = useState('');
  const activeCount = sources.filter((s) => s.enabled).length;
  const nameOf = (id: string) => sources.find((s) => s.id === id)?.name ?? id;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    onAsk(draft);
    setDraft('');
  };

  return (
    <section className="panel panel-chat" aria-label="Ask your notes">
      <div className="panel-head">
        <h2>Ask your notes</h2>
        <span className="muted with-icon">
          <ShieldIcon size={14} />
          Answers come only from your notes
        </span>
      </div>

      <div className="chat-scroll">
        <div className="chat-column">
          <div className="guide">
            <div className="eyebrow">Notebook guide</div>
            <h3 className="display">{notebookGuide.title}</h3>
            <p className="guide-summary">{notebookGuide.summary}</p>
            <div className="row-wrap">
              <button type="button" className="btn btn-dark" onClick={onListen}>
                <PlayIcon size={14} className="accent-bright" />
                Listen to the audiobook
              </button>
              <button type="button" className="btn btn-outline">
                Save as note
              </button>
            </div>
          </div>

          {messages.map((m) =>
            m.role === 'user' ? (
              <div key={m.id} className="bubble-user">
                {m.text}
              </div>
            ) : m.role === 'pending' ? (
              <div key={m.id} className="bubble-pending">
                {m.text}
              </div>
            ) : (
              <div key={m.id} className="answer">
                <p className="prose">{m.text}</p>
                <div className="answer-actions">
                  {m.citations?.map((id, i) => (
                    <button
                      key={id}
                      type="button"
                      className="cite"
                      aria-label={`Open source: ${nameOf(id)}`}
                      onClick={() => onOpenSource(id)}
                    >
                      {i + 1}
                    </button>
                  ))}
                  <span className="spacer" />
                  <button type="button" className="btn btn-ghost" onClick={onListen}>
                    <VolumeIcon size={16} />
                    Read aloud
                  </button>
                  <button type="button" className="btn btn-ghost">
                    <BookmarkIcon size={16} />
                    Save to note
                  </button>
                </div>
              </div>
            ),
          )}
        </div>
      </div>

      <div className="composer-wrap">
        <div className="chat-column">
          <div className="suggestions">
            {suggestedQuestions.map((q) => (
              <button key={q} type="button" className="pill" onClick={() => onAsk(q)}>
                {q}
              </button>
            ))}
          </div>
          <form className="composer" onSubmit={submit}>
            <label htmlFor="ask" className="sr-only">
              Ask a question about your notes
            </label>
            <textarea
              id="ask"
              rows={1}
              value={draft}
              placeholder="Ask anything about your notes…"
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) submit(e);
              }}
            />
            <span className="muted small nowrap">{activeCount} sources</span>
            {/* TODO: record a question and transcribe it */}
            <button type="button" className="round-btn round-btn-outline" aria-label="Ask by voice">
              <MicIcon size={18} />
            </button>
            <button type="submit" className="round-btn round-btn-dark" aria-label="Send question">
              <ArrowUpIcon size={18} />
            </button>
          </form>
        </div>
      </div>
    </section>
  );
}
