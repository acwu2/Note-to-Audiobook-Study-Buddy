import { studyTools, voices } from '../data/sampleNotebook';
import { formatTime, type AudiobookPlayer } from '../lib/useAudiobookPlayer';
import { BackIcon, DownloadIcon, ForwardIcon, HeadphonesIcon, PauseIcon, PlayIcon, RefreshIcon } from './Icons';

interface Props {
  pageCount: number;
  player: AudiobookPlayer;
  onRunTool: (prompt: string) => void;
}

const SPEEDS = [0.75, 1, 1.25, 1.5];

export default function StudioPanel({ pageCount, player, onRunTool }: Props) {
  const pct = Math.round((player.position / player.totalSeconds) * 100);

  return (
    <section className="panel panel-studio" aria-label="Studio">
      <div className="panel-head">
        <h2>Studio</h2>
      </div>
      <div className="panel-body studio-body">
        <div className="player">
          <div className="player-head">
            <span className="player-art" aria-hidden="true">
              <HeadphonesIcon size={26} />
            </span>
            <div>
              <div className="eyebrow eyebrow-bright">Audiobook</div>
              <div className="player-title">Cellular respiration</div>
              <div className="player-sub">
                {pageCount} pages · {formatTime(player.totalSeconds)}
              </div>
            </div>
          </div>

          <div>
            <div
              className="progress"
              role="progressbar"
              aria-label="Playback position"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={pct}
            >
              <div className="progress-fill" style={{ width: `${pct}%` }} />
            </div>
            <div className="progress-times">
              <span>{formatTime(player.position)}</span>
              <span>{formatTime(player.totalSeconds)}</span>
            </div>
          </div>

          <div className="transport">
            <button type="button" className="icon-btn icon-btn-light" onClick={() => player.skip(-15)} aria-label="Back 15 seconds">
              <BackIcon size={22} />
            </button>
            <button
              type="button"
              className="play-btn"
              onClick={player.toggle}
              aria-label={player.playing ? 'Pause audiobook' : 'Play audiobook'}
            >
              {player.playing ? <PauseIcon size={22} /> : <PlayIcon size={22} />}
            </button>
            <button type="button" className="icon-btn icon-btn-light" onClick={() => player.skip(15)} aria-label="Forward 15 seconds">
              <ForwardIcon size={22} />
            </button>
          </div>

          <div className="speeds" role="group" aria-label="Playback speed">
            {SPEEDS.map((v) => (
              <button
                key={v}
                type="button"
                aria-pressed={player.speed === v}
                className={player.speed === v ? 'is-active' : ''}
                onClick={() => player.setSpeed(v)}
              >
                {v}×
              </button>
            ))}
          </div>

          <label className="voice">
            Voice
            <select value={player.voice} onChange={(e) => player.setVoice(e.target.value)}>
              {voices.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.label}
                </option>
              ))}
            </select>
          </label>

          <div className="row">
            <button type="button" className="btn btn-light grow">
              <DownloadIcon size={16} />
              Download MP3
            </button>
            <button type="button" className="round-btn round-btn-ghost-light" aria-label="Regenerate audiobook">
              <RefreshIcon size={18} />
            </button>
          </div>
        </div>

        <div>
          <h3 className="section-label">Study tools</h3>
          <div className="tool-grid">
            {studyTools.map((t) => (
              <button key={t.name} type="button" className="tool" onClick={() => onRunTool(t.prompt)}>
                <strong>{t.name}</strong>
                <span className="muted small">{t.desc}</span>
              </button>
            ))}
          </div>
        </div>

        <div>
          <h3 className="section-label">Saved notes</h3>
          <div className="saved-note">
            <strong>Krebs cycle, explained simply</strong>
            <span className="muted small">Saved from chat</span>
          </div>
          <button type="button" className="btn btn-outline full">
            Add note
          </button>
        </div>
      </div>
    </section>
  );
}
