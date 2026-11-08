import { useEffect, useRef, useState } from 'react';

/**
 * Simulated player so the UI can be built before real audio exists.
 * When step 3 returns an MP3 URL, back this with an <audio> element:
 * position → audio.currentTime, speed → audio.playbackRate.
 */
export function useAudiobookPlayer(totalSeconds: number) {
  const [playing, setPlaying] = useState(false);
  const [position, setPosition] = useState(128);
  const [speed, setSpeed] = useState(1);
  const [voice, setVoice] = useState('af_heart');
  const speedRef = useRef(speed);
  speedRef.current = speed;

  useEffect(() => {
    if (!playing) return;
    const t = setInterval(() => {
      setPosition((p) => {
        const next = p + speedRef.current;
        if (next >= totalSeconds) {
          setPlaying(false);
          return totalSeconds;
        }
        return next;
      });
    }, 1000);
    return () => clearInterval(t);
  }, [playing, totalSeconds]);

  const clamp = (s: number) => Math.min(totalSeconds, Math.max(0, s));

  return {
    playing,
    position,
    totalSeconds,
    speed,
    voice,
    toggle: () => setPlaying((p) => !p),
    skip: (delta: number) => setPosition((p) => clamp(p + delta)),
    setSpeed,
    setVoice,
  };
}

export type AudiobookPlayer = ReturnType<typeof useAudiobookPlayer>;

export function formatTime(s: number) {
  const m = Math.floor(s / 60);
  const r = Math.floor(s % 60);
  return `${m}:${r < 10 ? '0' : ''}${r}`;
}
