import { useEffect } from 'react';
import { podcastAudioUrl } from '../lib/api';
import { formatTime, useAudioPlayer } from '../lib/useAudioPlayer';
import type { Chapter, Podcast } from '../types';
import { BackIcon, DownloadIcon, ForwardIcon, PauseIcon, PlayIcon } from './Icons';

const SPEEDS = [0.75, 1, 1.25, 1.5, 2];

const squash = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();

/** True when the title is just the request (often truncated), so showing both repeats it. */
function sameAsTitle(request: string, title: string) {
  const r = squash(request);
  const t = squash(title).replace(/\s*\.\.\.$|\s*…$/, '');
  return t.length > 0 && (r.startsWith(t) || t.startsWith(r.slice(0, 24)));
}

/** Step 3 · Listen: the finished MP3, the download, and the script. */
export default function ListenPanel({
  podcast,
  onPickAnother,
  onStartOver,
  onStudy,
  replayLine,
  onReplayed,
}: {
  podcast: Podcast;
  onPickAnother: () => void;
  onStartOver: () => void;
  onStudy: () => void;
  /** A lesson line the student asked to hear again, from a missed question. */
  replayLine?: number | null;
  onReplayed?: () => void;
}) {
  const player = useAudioPlayer();
  const src = podcast.audioUrl ?? podcastAudioUrl(podcast.id);
  // Trust the server's length until the file's own metadata loads.
  const total = player.duration || podcast.seconds || 0;

  // The server drops the list unless it has two or more sound chapters, so an
  // array that is present is always worth showing.
  const chapters = podcast.chapters ?? [];
  const here = chapters.reduce((at, c, i) => (player.position + 0.25 >= c.startSeconds ? i : at), -1);

  const playAt = (seconds: number) => {
    player.seek(seconds);
    void player.play();
  };

  // "Heard it" means reached the end, not merely pressed play.
  const heard = total > 0 && player.position >= total - 2;

  // Coming back from a missed question: seek to the chapter that covers that
  // line. Waits for metadata, because seeking before it lands is ignored.
  const ready = player.duration > 0;
  useEffect(() => {
    if (replayLine == null || !ready) return;
    const c = chapters.reduce<Chapter | null>(
      (best, ch) => (ch.startLine <= replayLine ? ch : best),
      null,
    );
    if (c) {
      player.seek(c.startSeconds);
      void player.play();
    }
    onReplayed?.();
    // player identity changes every render; the line and readiness are the trigger
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [replayLine, ready]);

  const asked = podcast.askedMinutes;
  const runtime = podcast.seconds ?? player.duration;
  const missedLength =
    !!asked && !!runtime && Math.abs(runtime - asked * 60) / (asked * 60) > 0.15;

  return (
    <>
      <div className="listen-grid">
      {chapters.length > 0 && (
        <section className="card chapters-card">
          <h3 className="eyebrow">Chapters</h3>
          <ol className="chapters">
            {chapters.map((c, i) => (
              <li key={i} className={'chapter' + (i === here ? ' is-here' : '')}>
                <button type="button" onClick={() => playAt(c.startSeconds)}>
                  <span className="ch-n">{i + 1}</span>
                  <span className="ch-title">{c.title}</span>
                  <span className="ch-at">{formatTime(c.startSeconds)}</span>
                </button>
              </li>
            ))}
          </ol>
          <p className="later-note">Chapters come from the headings in your notes. Tap one to jump there.</p>
        </section>
      )}
      <section className="player">
        <div>
          <div className="p-format">{podcast.format}</div>
          <h2 className="p-title">{podcast.title}</h2>
          <p className="p-hosts">Two hosts · Heart and Michael</p>
          {/* Some episodes cached before the server titled lessons properly are
              titled with the request itself; echoing it then says the same
              thing twice. Keyed on the two matching, so it stops applying on
              its own as those age out. */}
          {podcast.requestText && !sameAsTitle(podcast.requestText, podcast.title) && (
            <p className="p-asked">You asked for “{podcast.requestText}”</p>
          )}
          {/* A generated script lands within a few percent of its budget, so a
              small miss is normal and saying so every time would read as broken.
              Only speak up when the gap is big enough to notice. */}
          {missedLength && (
            <p className="p-asked">
              You asked for {podcast.askedMinutes} minutes; this one runs {formatTime(total)}.
            </p>
          )}
        </div>

        <audio {...player.bind} src={src} />

        <div className="scrub">
          <span className="t">{formatTime(player.position)}</span>
          <input
            type="range"
            min={0}
            max={total || 1}
            step={1}
            value={Math.min(player.position, total || 1)}
            onChange={(e) => player.seek(Number(e.target.value))}
            aria-label="Position in the episode"
          />
          <span className="t">{formatTime(total)}</span>
        </div>

        <div className="transport">
          <button type="button" className="icon-btn" onClick={() => player.skip(-15)} aria-label="Back 15 seconds">
            <BackIcon />
          </button>
          <button
            type="button"
            className="icon-btn big"
            onClick={player.toggle}
            aria-label={player.playing ? 'Pause' : 'Play'}
          >
            {player.playing ? <PauseIcon /> : <PlayIcon />}
          </button>
          <button type="button" className="icon-btn" onClick={() => player.skip(15)} aria-label="Forward 15 seconds">
            <ForwardIcon />
          </button>
          <select
            className="speed"
            value={player.speed}
            onChange={(e) => player.setSpeed(Number(e.target.value))}
            aria-label="Playback speed"
          >
            {SPEEDS.map((s) => (
              <option key={s} value={s}>
                {s}×
              </option>
            ))}
          </select>
        </div>
      </section>
      </div>

      {/* Once they have heard it, testing themselves is the point — so it
          becomes the loud action. Before that it is still reachable, just quiet. */}
      {heard ? (
        <section className="card next-up">
          <div>
            <h3 className="next-title">Now see what stuck</h3>
            <p className="sub">
              A short review of these notes, then a few questions on it. Whatever you miss turns into cards.
            </p>
          </div>
          <button type="button" className="btn primary" onClick={onStudy}>
            Review and quiz me
          </button>
        </section>
      ) : null}

      <div className="row">
        {!heard && (
          <button type="button" className="btn" onClick={onStudy}>
            Review and quiz me
          </button>
        )}
        <a className="dl" href={podcastAudioUrl(podcast.id, true)} download>
          <DownloadIcon />
          Download MP3
        </a>
        <button type="button" className="btn quiet" onClick={onPickAnother}>
          Pick a different podcast
        </button>
        <button type="button" className="btn quiet" onClick={onStartOver}>
          Start over with new notes
        </button>
      </div>

      {podcast.script && podcast.script.length > 0 && (
        <section className="card">
          <div className="script-head">
            <h3 className="eyebrow">Script</h3>
            {podcast.script.some((l) => l.source === 'added') && (
              <p className="script-key">
                <span className="added-tag">added</span>
                marks a line the narrator added to teach the topic. Everything else is from your pages.
              </p>
            )}
          </div>
          <div className="script">
            {podcast.script.map((line, i) => (
              // Older podcasts have no label; those lines are all from the notes.
              <p className="line" key={i} data-source={line.source ?? 'notes'} data-role={line.role ?? 'teach'}>
                <span className="host">{line.host}</span>
                <span className="said">
                  {line.text}
                  {line.source === 'added' && <span className="added-tag" title="Added by the narrator, not from your notes">added</span>}
                  {line.role === 'check' && (
                    <span className="your-turn">then a pause, so you can answer out loud</span>
                  )}
                </span>
              </p>
            ))}
          </div>
        </section>
      )}
    </>
  );
}
