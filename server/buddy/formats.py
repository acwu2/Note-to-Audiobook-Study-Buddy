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

WORDS_PER_MINUTE = 150
