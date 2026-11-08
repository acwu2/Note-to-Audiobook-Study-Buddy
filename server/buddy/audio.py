"""Script lines → one MP3: Kokoro per line, short pauses, ffmpeg to encode."""

import shutil
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from . import config
from .formats import HOSTS, PipelineError

_pipeline = None
_pipeline_lock = threading.Lock()


def _kokoro():
    global _pipeline
    with _pipeline_lock:
        if _pipeline is None:
            from kokoro import KPipeline

            # "a" = American English; both hosts' voices use it.
            _pipeline = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
    return _pipeline


def _tone(text: str, voice: str) -> np.ndarray:
    """FAKE_TTS: a quiet tone as long as the line would take to say."""
    seconds = max(1.0, len(text.split()) * 0.35)
    t = np.arange(int(config.SAMPLE_RATE * seconds)) / config.SAMPLE_RATE
    pitch = 220.0 if voice == HOSTS["Heart"] else 165.0
    wave = 0.08 * np.sin(2 * np.pi * pitch * t)
    fade = np.minimum(1.0, np.minimum(t, seconds - t) / 0.05)
    return (wave * fade).astype(np.float32)


def speak_line(text: str, voice: str) -> np.ndarray:
    if config.FAKE_TTS:
        return _tone(text, voice)
    parts = []
    for _, _, audio in _kokoro()(text, voice=voice):
        if audio is None:
            continue
        if hasattr(audio, "detach"):
            audio = audio.detach().cpu().numpy()
        parts.append(np.asarray(audio, dtype=np.float32))
    return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)


def _silence(seconds: float) -> np.ndarray:
    return np.zeros(int(config.SAMPLE_RATE * seconds), dtype=np.float32)


@dataclass(frozen=True)
class Render:
    seconds: float
    line_starts: list[float]
    """Where each line begins in the finished MP3. Exact, because the mixer knows
    every rendered duration before it concatenates — chapter offsets come from
    here rather than from estimating word counts."""


def render(
    lines: list[tuple[str, str]] | list[tuple[str, str, str]],
    out_mp3: Path,
    on_mixing: Callable[[], None] | None = None,
) -> Render:
    """Speak (host, text[, role]) lines in order, write out_mp3, report the timing.

    A line with role "check" is a question put to the student, so it is followed by
    a longer silence: long enough to actually answer out loud before the lesson
    continues. That pause is what makes this studying rather than listening.
    """
    if not shutil.which("ffmpeg"):
        raise PipelineError("The server needs ffmpeg to make MP3s. Install it with: brew install ffmpeg")
    pause = _silence(config.PAUSE_SECONDS)
    think = _silence(config.THINK_SECONDS)
    chunks: list[np.ndarray] = []
    line_starts: list[float] = []
    samples = 0
    for line in lines:
        host, text = line[0], line[1]
        role = line[2] if len(line) > 2 else "teach"
        line_starts.append(round(samples / config.SAMPLE_RATE, 2))
        spoken = speak_line(text, HOSTS[host])
        gap = think if role == "check" else pause
        chunks.append(spoken)
        chunks.append(gap)
        samples += len(spoken) + len(gap)
    if on_mixing:
        on_mixing()
    audio = np.concatenate(chunks) if chunks else pause
    wav = out_mp3.with_suffix(".wav")
    sf.write(wav, audio, config.SAMPLE_RATE)
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav),
             "-b:a", config.MP3_BITRATE, "-map_metadata", "-1", str(out_mp3)],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        raise PipelineError("Encoding the MP3 failed.") from e
    finally:
        wav.unlink(missing_ok=True)
    return Render(round(len(audio) / config.SAMPLE_RATE, 1), line_starts)
