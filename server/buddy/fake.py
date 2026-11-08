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
    "suggestions": [
        "explain the Krebs cycle like I have never seen it",
        "quiz me on the three stages until I get them right",
        "a five minute version I can listen to on the walk in",
    ],
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


# A review, a quiz that tests it point by point, and cards for the points a
# student is most likely to miss. Keyed by pointId, same as the real path.
REVIEW = {
    "title": "Cellular respiration, the three stages",
    "points": [
        {"id": "p1", "heading": "What respiration is for",
         "body": "Cellular respiration is how a cell turns glucose into ATP, the form of energy it can actually spend. Every stage below exists to serve that one job.",
         "source": "added", "exam": False},
        {"id": "p2", "heading": "Glycolysis, in the cytoplasm",
         "body": "The first stage is glycolysis, and it happens in the cytoplasm. It is the only stage that takes place outside the mitochondria.",
         "source": "notes", "exam": False},
        {"id": "p3", "heading": "The Krebs cycle",
         "body": "The second stage is the Krebs cycle, also called the citric acid cycle. It runs twice for every glucose molecule.",
         "source": "notes", "exam": False},
        {"id": "p4", "heading": "The electron transport chain",
         "body": "The third stage is the electron transport chain, and it makes most of the ATP: about thirty-four of them.",
         "source": "notes", "exam": True},
        {"id": "p5", "heading": "What the Krebs cycle hands on",
         "body": "The Krebs cycle produces NADH and FADH2, and those feed the electron transport chain. That handover is why the stages must run in order.",
         "source": "notes", "exam": False},
    ],
}

QUIZ = [
    {"pointId": "p1", "q": "What is the point of cellular respiration?",
     "options": ["To turn glucose into ATP the cell can spend",
                 "To turn ATP back into glucose for storage",
                 "To move oxygen from the blood into the cell",
                 "To build proteins out of amino acids"],
     "answer": 0, "why": "Respiration converts glucose into ATP, the form of energy a cell can actually use."},
    {"pointId": "p2", "q": "Where does glycolysis take place?",
     "options": ["In the cytoplasm", "In the mitochondria",
                 "On the inner mitochondrial membrane", "In the nucleus"],
     "answer": 0, "why": "Glycolysis is the one stage outside the mitochondria: it happens in the cytoplasm."},
    {"pointId": "p3", "q": "How many times does the Krebs cycle run per glucose molecule?",
     "options": ["Twice", "Once", "Four times", "Thirty-four times"],
     "answer": 0, "why": "The review states the Krebs cycle runs twice for every glucose molecule."},
    {"pointId": "p4", "q": "Which stage makes most of the ATP, and roughly how much?",
     "options": ["The electron transport chain, about thirty-four",
                 "Glycolysis, about thirty-four",
                 "The Krebs cycle, about thirty-four",
                 "The electron transport chain, about two"],
     "answer": 0, "why": "The electron transport chain is the third stage and produces about thirty-four ATP."},
    {"pointId": "p5", "q": "What does the Krebs cycle hand on, and to what?",
     "options": ["NADH and FADH2, to the electron transport chain",
                 "ATP and oxygen, to the cytoplasm",
                 "Glucose and NADH, to glycolysis",
                 "NADH and FADH2, to the Krebs cycle again"],
     "answer": 0, "why": "The Krebs cycle produces NADH and FADH2, which feed the electron transport chain."},
]

CARDS = [
    {"pointId": "p1", "front": "ATP is to a cell what ___ is to you", "back": "spendable money — the form of energy it can actually use"},
    {"pointId": "p2", "front": "The one stage outside the mitochondria", "back": "Glycolysis, in the cytoplasm"},
    {"pointId": "p3", "front": "Krebs cycle: how many turns per glucose?", "back": "Two"},
    {"pointId": "p3", "front": "Another name for the Krebs cycle", "back": "The citric acid cycle"},
    {"pointId": "p4", "front": "Where do the ~34 ATP come from?", "back": "The electron transport chain, the third stage"},
    {"pointId": "p5", "front": "NADH and FADH2 are made by ___ and used by ___", "back": "made by the Krebs cycle, used by the electron transport chain"},
]
