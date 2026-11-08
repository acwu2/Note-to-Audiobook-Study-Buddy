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
        {"host": "Heart", "text": "Cellular respiration is how your cells get usable energy out of food. Everything else in these notes hangs off that one job.", "source": "added", "role": "hook"},
        {"host": "Michael", "text": "Your notes split it into three stages. The first is glycolysis, in the cytoplasm.", "source": "notes", "role": "teach"},
        {"host": "Heart", "text": "The second is the Krebs cycle, in the mitochondria. The third is the electron transport chain.", "source": "notes", "role": "teach"},
        {"host": "Michael", "text": "So before we go on: which of the three stages happens in the cytoplasm?", "source": "notes", "role": "check"},
        {"host": "Heart", "text": "Glycolysis. That is the only one outside the mitochondria, which is worth hanging on to.", "source": "notes", "role": "answer"},
        {"host": "Michael", "text": "The last stage makes most of the A T P. About thirty-four, according to your notes.", "source": "notes", "role": "teach"},
        {"host": "Heart", "text": "And where does most of that A T P come from?", "source": "notes", "role": "check"},
        {"host": "Michael", "text": "The electron transport chain, the third stage. Thirty-four of them.", "source": "notes", "role": "answer"},
        {"host": "Heart", "text": "Three stages, in order: glycolysis, the Krebs cycle, the electron transport chain, with the energy stacked at the end.", "source": "notes", "role": "recap"},
    ],
    "quick_recap": [
        {"host": "Heart", "text": "You have studied this already, so let us find out what stuck. Three questions.", "source": "added", "role": "hook"},
        {"host": "Michael", "text": "Name the three stages of cellular respiration, in order.", "source": "notes", "role": "check"},
        {"host": "Heart", "text": "Glycolysis, the Krebs cycle, then the electron transport chain.", "source": "notes", "role": "answer"},
        {"host": "Michael", "text": "Which stage makes most of the A T P, and roughly how much?", "source": "notes", "role": "check"},
        {"host": "Heart", "text": "The electron transport chain. About thirty-four.", "source": "notes", "role": "answer"},
        {"host": "Michael", "text": "If those came back quickly, you are ready. If not, the full lesson walks through them.", "source": "added", "role": "recap"},
    ],
    "deep_dive": [
        {"host": "Heart", "text": "The Krebs cycle is the step people lose marks on, because it is the middle of a chain and easy to isolate.", "source": "added", "role": "hook"},
        {"host": "Michael", "text": "Your notes also call it the citric acid cycle. Same thing, two names.", "source": "notes", "role": "teach"},
        {"host": "Heart", "text": "Worth knowing, though your notes do not say it: it runs inside the mitochondria.", "source": "added", "role": "teach"},
        {"host": "Michael", "text": "It runs twice for every glucose.", "source": "notes", "role": "teach"},
        {"host": "Heart", "text": "Why twice, do you think, rather than once?", "source": "notes", "role": "check"},
        {"host": "Michael", "text": "Because one glucose is split in two earlier on, so each half goes round. Your notes give the number; the reason is the useful part.", "source": "added", "role": "answer"},
        {"host": "Heart", "text": "It makes N A D H and F A D H 2, and those feed the electron transport chain.", "source": "notes", "role": "teach"},
        {"host": "Michael", "text": "So what does the Krebs cycle hand on, and to what?", "source": "notes", "role": "check"},
        {"host": "Heart", "text": "N A D H and F A D H 2, handed to the electron transport chain.", "source": "notes", "role": "answer"},
        {"host": "Michael", "text": "Two names, twice per glucose, and it feeds the next stage. That is the whole of it.", "source": "notes", "role": "recap"},
    ],
}
