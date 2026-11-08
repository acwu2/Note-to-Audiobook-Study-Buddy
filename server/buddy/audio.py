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


def _trim(a: np.ndarray) -> np.ndarray:
    """Strip the dead air Kokoro leaves at both ends of a line.

    It returns roughly 0.3s before the first word and 0.5s after the last. Stack
    that on a gap of our own and every turn sits in about 1.2 seconds of silence,
    which is what makes an alternating script sound stitched together rather than
    spoken. Trim it off and the gap between lines becomes ours to choose.
    """
    loud = np.where(np.abs(a) > config.TRIM_THRESHOLD)[0]
    if len(loud) == 0:
        return a
    keep = int(config.SAMPLE_RATE * config.TRIM_KEEP_SECONDS)
    start = max(0, int(loud[0]) - keep)
    end = min(len(a), int(loud[-1]) + keep)
    return a[start:end]


def _gap_after(role: str, nxt: tuple | None, host: str) -> float:
    """How long to wait before the next line. Pacing is most of what sells a voice.

    A question gets a real pause to answer in. A new section gets a beat. Two
    lines from the same host run on, the way a person finishing a thought does.
    Everything else gets a natural turn-taking gap.
    """
    if role == "check":
        return config.THINK_SECONDS
    if nxt is None:
        return config.TAIL_SECONDS
    next_host = nxt[0]
    next_role = nxt[2] if len(nxt) > 2 else "teach"
    if next_role in ("hook", "recap"):
        return config.SECTION_SECONDS
    if next_host == host:
        return config.SAME_HOST_SECONDS
    return config.TURN_SECONDS


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
    chunks: list[np.ndarray] = []
    line_starts: list[float] = []
    samples = 0
    for i, line in enumerate(lines):
        host, text = line[0], line[1]
        role = line[2] if len(line) > 2 else "teach"
        line_starts.append(round(samples / config.SAMPLE_RATE, 2))
        spoken = _trim(speak_line(text, HOSTS[host]))
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        gap = _silence(_gap_after(role, nxt, host))
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
