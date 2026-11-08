"""The fixed menu. The model never invents a format; it only titles these."""

from dataclasses import dataclass


class PipelineError(Exception):
    """A failure the student should see, in plain words."""


@dataclass(frozen=True)
class Format:
    id: str
    label: str
    minutes: int
    description: str  # may contain {topic}
    brief: str  # what the script should do; may contain {topic}


FORMATS: dict[str, Format] = {
    "full_episode": Format(
        id="full_episode",
        label="Full lesson",
        minutes=8,
        description="The whole thing taught properly, start to finish.",
        brief=(
            "Teach everything in the notes as one lesson. Open by saying what this "
            "is for and how the pieces fit together, then take the ideas in the order "
            "that makes them easiest to learn, which is not always the order they were "
            "written down. Check the listener after each idea, and recap at the end."
        ),
    ),
    "quick_recap": Format(
        id="quick_recap",
        label="Quick recap",
        minutes=3,
        description="Drill yourself on the key facts, right before class.",
        brief=(
            "This listener has studied already and wants to find out what has stuck. "
            "Lead with the questions, not the answers: ask, leave the pause, then "
            "confirm briefly. Cover only the facts most likely to be examined. "
            "Keep teaching to a minimum — this is retrieval practice, not a first pass."
        ),
    ),
    "deep_dive": Format(
        id="deep_dive",
        label="Deep dive",
        minutes=5,
        description="{topic}, taught from scratch until it clicks.",
        brief=(
            "Teach only {topic}, to someone who has not understood it yet. Build it up "
            "one step at a time and do not move on until each step stands on its own. "
            "Say why it matters before you say what it is. Check understanding more "
            "often than the other formats, and recap the chain of steps at the end."
        ),
    ),
}

FORMAT_ORDER = ["full_episode", "quick_recap", "deep_dive"]

# Host name → Kokoro voice id. Both are American English (lang_code "a").
HOSTS: dict[str, str] = {"Heart": "af_heart", "Michael": "am_michael"}

# Measured from Kokoro on the sample lessons: 172-200 wpm depending on the text,
# averaging 184. This is the speaking rate only — it says nothing about pauses.
SPEAKING_WPM = 184

# Typical seconds of speech in one line, used to guess how many lines a budget
# buys, and so how many gaps there will be. Measured at 5.3s across the samples.
SECONDS_PER_LINE = 5.3

# Roughly how often a lesson stops to ask something. More checks means more
# silence, which is why a flat words-per-minute figure drifts: a recap full of
# questions runs far longer than its word count suggests.
CHECKS_PER_MINUTE = 1.2

# Kept for anything still importing it. It is a finished-audio figure, not a
# speaking rate, and word_budget() supersedes it.
WORDS_PER_MINUTE = 150


def word_budget(minutes: float, think_seconds: float, turn_seconds: float) -> int:
    """How many words fit in `minutes` of finished audio, pauses included.

    A length request is about the file, not about the script: someone asking for
    five minutes wants a five minute file. Silence is part of that, and this
    lesson format has a lot of it — every check is followed by several seconds
    for the student to answer in. Budgeting words alone overshoots.

    Solved by one fixed-point pass: guess the speech time, see how many lines and
    checks that buys, subtract their silence, and re-solve.
    """
    total = max(0.5, float(minutes)) * 60.0
    checks = max(1.0, round(minutes * CHECKS_PER_MINUTE))
    speech = total * 0.85  # first guess
    for _ in range(3):
        lines = max(1.0, speech / SECONDS_PER_LINE)
        silence = checks * think_seconds + max(0.0, lines - checks) * turn_seconds
        speech = max(total * 0.3, total - silence)
    return max(40, int(speech / 60.0 * SPEAKING_WPM))
