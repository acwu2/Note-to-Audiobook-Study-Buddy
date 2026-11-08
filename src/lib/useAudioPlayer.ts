import { useRef, useState } from 'react';

/** State for one <audio> element. Spread `bind` onto the element. */
export function useAudioPlayer() {
  const ref = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [position, setPosition] = useState(0);
  const [duration, setDuration] = useState(0);
  const [speed, setSpeedState] = useState(1);

  const bind = {
    ref,
    preload: 'metadata' as const,
    onPlay: () => setPlaying(true),
    onPause: () => setPlaying(false),
    onEnded: () => setPlaying(false),
    onTimeUpdate: () => setPosition(ref.current?.currentTime ?? 0),
    onLoadedMetadata: () => {
      setDuration(ref.current?.duration ?? 0);
      if (ref.current) ref.current.playbackRate = speed;
    },
  };

  return {
    bind,
    playing,
    position,
    duration,
    speed,
    toggle: () => {
      const a = ref.current;
      if (!a) return;
      if (a.paused) void a.play();
      else a.pause();
    },
    /** Start playing, whatever the current state — used when seeking to a chapter. */
    play: async () => {
      try {
        await ref.current?.play();
      } catch {
        /* a browser may refuse until the student interacts; the controls still work */
      }
    },
    seek: (seconds: number) => {
      if (ref.current) ref.current.currentTime = seconds;
      setPosition(seconds);
    },
    skip: (delta: number) => {
      const a = ref.current;
      if (!a) return;
      a.currentTime = Math.min(a.duration || 0, Math.max(0, a.currentTime + delta));
    },
    setSpeed: (s: number) => {
      if (ref.current) ref.current.playbackRate = s;
      setSpeedState(s);
    },
  };
}

export function formatTime(s: number) {
  if (!Number.isFinite(s)) return '0:00';
  const m = Math.floor(s / 60);
  const r = Math.floor(s % 60);
  return `${m}:${r < 10 ? '0' : ''}${r}`;
}
