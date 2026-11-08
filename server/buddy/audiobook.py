"""Shape a finished lesson like a real audiobook.

A lesson that starts talking and never says where it is reads as a podcast clip.
An audiobook has an opening that names the work, a contents list, each chapter
announced with a beat of silence around it, an ending, and chapter markers inside
the file so Apple Books, Overcast or VLC can show and jump between them.

Announcements are audio-only. The script the UI shows is untouched, so every line
index the rest of the system uses (chapter startLine, review lineRefs) still means
what it did; only the offsets in seconds move, and those come out of the mixer.
"""

from __future__ import annotations

import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

from . import audio, config
from .formats import PipelineError

NARRATOR = "Heart"
ARTIST = "Study Buddy"
_NUMBERS = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen twenty"
).split()

_m4b_lock = threading.Lock()


def _say(n: int) -> str:
    return _NUMBERS[n] if 0 <= n < len(_NUMBERS) else str(n)


@dataclass
class Built:
    seconds: float
    line_starts: list[float]  # seconds into the file where each script line begins
    chapters: list[dict]  # the plan's chapters, each with startSeconds
    ffmeta: Path  # chapter and tag sidecar, reused for the m4b


def plan(title: str, lines: list[dict], chapters: list[dict]) -> tuple[list[tuple], list[tuple]]:
    """Render items for the whole audiobook, and a tag for each saying what it is."""
    items: list[tuple] = []
    tags: list[tuple] = []

    def add(host: str, text: str, role: str, tag: tuple) -> None:
        items.append((host, text, role))
        tags.append(tag)

    add(NARRATOR, f"{title}. A lesson made from your notes.", "front", ("front",))
    if len(chapters) >= 2:
        listing = " ".join(f"{_say(i + 1).capitalize()}, {c['title']}." for i, c in enumerate(chapters))
        add(NARRATOR, f"This lesson has {_say(len(chapters))} chapters. {listing}", "front", ("front",))

    chapter_at = {c["startLine"]: i for i, c in enumerate(chapters)}
    for i, line in enumerate(lines):
        if i in chapter_at:
            ci = chapter_at[i]
            add(NARRATOR, f"Chapter {_say(ci + 1)}. {chapters[ci]['title']}.", "chapter", ("chapter", ci))
        add(line["host"], line["text"], line.get("role", "teach"), ("line", i))
    add(NARRATOR, "End of lesson.", "end", ("end",))
    return items, tags


def _esc(value: str) -> str:
    out = str(value)
    for ch in ("\\", "=", ";", "#", "\n"):
        out = out.replace(ch, "\\" + ch)
    return out


def _write_ffmeta(path: Path, title: str, topic: str, marks: list[tuple[str, float]], total: float) -> None:
    out = [
        ";FFMETADATA1",
        f"title={_esc(title)}",
        f"artist={_esc(ARTIST)}",
        f"album={_esc(topic or title)}",
        "genre=Audiobook",
    ]
    for i, (name, start) in enumerate(marks):
        end = marks[i + 1][1] if i + 1 < len(marks) else total
        out += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={int(start * 1000)}", f"END={max(int(end * 1000), int(start * 1000) + 1)}", f"title={_esc(name)}"]
    path.write_text("\n".join(out) + "\n")


def _tag(mp3: Path, ffmeta: Path) -> None:
    """Embed the tags and chapters. A stream copy, so no second generation of loss."""
    tmp = mp3.with_name(mp3.stem + ".tagged.mp3")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3), "-i", str(ffmeta),
             "-map", "0:a", "-map_metadata", "1", "-map_chapters", "1",
             "-c", "copy", "-id3v2_version", "3", "-write_id3v2", "1", str(tmp)],
            check=True,
        )
        tmp.replace(mp3)
    except subprocess.CalledProcessError as e:
        tmp.unlink(missing_ok=True)
        raise PipelineError("Adding the chapters to the audio failed.") from e


def produce(out_mp3: Path, title: str, topic: str, lines: list[dict], chapters: list[dict], on_mixing=None) -> Built:
    valid = [c for c in chapters if 0 <= int(c.get("startLine", -1)) < len(lines)]
    items, tags = plan(title, lines, valid)
    rendered = audio.render(items, out_mp3, on_mixing)

    line_starts = [0.0] * len(lines)
    chapter_starts: dict[int, float] = {}
    end_start = rendered.seconds
    for tag, start in zip(tags, rendered.line_starts):
        if tag[0] == "line":
            line_starts[tag[1]] = start
        elif tag[0] == "chapter":
            chapter_starts[tag[1]] = start
        elif tag[0] == "end":
            end_start = start

    # The file's own chapter list, the way an audiobook has one: opening first,
    # then each chapter at its announcement, then the ending.
    marks = [("Opening", 0.0)] + [
        (f"{ci + 1}. {valid[ci]['title']}", chapter_starts[ci]) for ci in range(len(valid)) if ci in chapter_starts
    ] + [("End of lesson", end_start)]
    ffmeta = out_mp3.with_suffix(".ffmeta")
    _write_ffmeta(ffmeta, title, topic, marks, rendered.seconds)
    _tag(out_mp3, ffmeta)

    return Built(
        seconds=rendered.seconds,
        line_starts=line_starts,
        chapters=[{**c, "startSeconds": chapter_starts.get(i, 0.0)} for i, c in enumerate(valid)],
        ffmeta=ffmeta,
    )


def m4b_path(out_mp3: Path) -> Path:
    return out_mp3.with_suffix(".m4b")


def ensure_m4b(out_mp3: Path) -> Path:
    """The same audiobook as an .m4b, the format audiobook apps expect. Built once, on demand."""
    path = m4b_path(out_mp3)
    ffmeta = out_mp3.with_suffix(".ffmeta")
    if path.exists():
        return path
    if not shutil.which("ffmpeg") or not out_mp3.exists() or not ffmeta.exists():
        raise PipelineError("This audiobook isn't ready to download yet.")
    with _m4b_lock:
        if not path.exists():
            tmp = path.with_name(path.stem + ".tmp.m4b")
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-loglevel", "error", "-i", str(out_mp3), "-i", str(ffmeta),
                     "-map", "0:a", "-map_metadata", "1", "-map_chapters", "1",
                     "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", "-f", "ipod", str(tmp)],
                    check=True,
                )
                tmp.replace(path)
            except subprocess.CalledProcessError as e:
                tmp.unlink(missing_ok=True)
                raise PipelineError("Making the audiobook file failed.") from e
    return path
