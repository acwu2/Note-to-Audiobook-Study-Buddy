"""Canned answers for FAKE_AI=1, so the app runs end to end without a key.

Built from the frontend's sample notes (Bio 101, cellular respiration).
"""

import hashlib

_PAGES = [
    "Cellular respiration → ATP\n3 stages:\n1st glycolysis (cytoplasm)\n"
    "2nd Krebs cycle (mitochondria)\n3rd ETC — most ATP, ~34\n"
    "e.g. glucose + O2 → CO2 + H2O",
    "Krebs cycle = citric acid cycle\nruns 2× per glucose\n"
    "makes NADH + FADH2 → feed ETC\nreleases CO2 [unclear]",
]


def transcribe(data: bytes, mime: str) -> list[str]:
    if mime == "application/pdf":
        return list(_PAGES)
    # The same photo always gets the same sample page.
    return [_PAGES[hashlib.sha256(data).digest()[0] % len(_PAGES)]]


OPTIONS = {
    "topic": "Cellular respiration",
    "full_episode_title": "Cellular respiration, start to finish",
    "quick_recap_title": "The three stages in three minutes",
    "deep_dive_topic": "The Krebs cycle",
    "deep_dive_title": "The Krebs cycle, explained simply",
}

SCRIPTS = {
    "full_episode": [
        {"host": "Heart", "text": "Today we are walking through cellular respiration: how your cells turn glucose into A T P.", "source": "notes"},
        {"host": "Michael", "text": "Your notes split it into three stages. First is glycolysis, which happens in the cytoplasm.", "source": "notes"},
        {"host": "Heart", "text": "Second is the Krebs cycle, inside the mitochondria. Third is the electron transport chain.", "source": "notes"},
        {"host": "Michael", "text": "And that last stage makes most of the A T P. About thirty-four, according to your notes.", "source": "notes"},
    ],
    "quick_recap": [
        {"host": "Heart", "text": "Three stages, three minutes. Ready?", "source": "notes"},
        {"host": "Michael", "text": "One: glycolysis, in the cytoplasm. Two: the Krebs cycle, in the mitochondria.", "source": "notes"},
        {"host": "Heart", "text": "Three: the electron transport chain, which makes most of the A T P.", "source": "notes"},
    ],
    "deep_dive": [
        {"host": "Heart", "text": "Let us slow down on the Krebs cycle. Your notes also call it the citric acid cycle.", "source": "notes"},
        {"host": "Michael", "text": "It runs twice for every glucose.", "source": "notes"},
        {"host": "Michael", "text": "Worth knowing, though your notes do not say it: that happens inside the mitochondria.", "source": "added"},
        {"host": "Heart", "text": "It makes N A D H and F A D H 2, and those feed the electron transport chain.", "source": "notes"},
    ],
}
