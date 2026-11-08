"""Listen, then prove it: a quiz on the lesson, and flashcards for what you missed.

The point of the loop is the last step. A quiz that only scores you tells you that
you are weak without telling you where, and a deck built by replaying the questions
you failed drills the question rather than the gap behind it.

So every question declares the concept it tests and the lesson lines it came from.
Grading maps a wrong answer to that concept, and the deck is written against those
concepts — with the wrong option the student actually chose passed in, so a card can
speak to the specific confusion rather than restating the fact.

Grounding carries over from the lesson: questions and cards come from the lesson,
which is itself grounded in the notes. Nothing new is introduced here.
"""

from __future__ import annotations

import hashlib
import re
import uuid

from pydantic import BaseModel

from . import config, llm, store
from .formats import PipelineError

MAX_QUESTIONS = 8
MAX_CARDS = 10


# ---- Shapes -----------------------------------------------------------------


class QuizQuestion(BaseModel):
    id: str = ""
    q: str
    options: list[str]
    answer: int
    why: str
    concept: str
    lineRefs: list[int] = []


class QuizDraft(BaseModel):
    """What the model returns."""

    questions: list[QuizQuestion]


class Flashcard(BaseModel):
    front: str
    back: str
    concept: str
    # Why this card is in the deck: the mistake it answers. Shown to the student,
    # because a card you know the reason for is a card you take seriously.
    because: str = ""


class DeckDraft(BaseModel):
    cards: list[Flashcard]


# ---- Prompts ----------------------------------------------------------------

QUIZ_PROMPT = """Write quiz questions on the audio lesson below. The student has just
listened to it, and this is where they find out what actually stuck.

Rules:
- Ask only about things the lesson actually taught. Never test outside knowledge, and
  never ask about something the lesson only mentioned in passing.
- {count} questions, four options each, exactly one correct.
- Wrong options must be plausible to someone who half-remembers the lesson: a near-miss,
  a swapped pair, the right answer to a different question. Never filler, never absurd.
- Spread the questions across the lesson rather than clustering on one part.
- "why" explains in one sentence why the right answer is right, in the lesson's own terms.

Two fields do the real work, so take them seriously:
- "concept": the single idea this question tests, in two to five words, in the lesson's
  own vocabulary. Getting this question wrong should mean not knowing this concept.
  Two questions testing the same idea share the same concept, spelled identically.
- "lineRefs": the numbers of the lesson lines the question comes from.

Reply as JSON only.

--- THE LESSON ---
{lesson}"""

DECK_PROMPT = """A student listened to a lesson, took a quiz, and got these things wrong.
Write flashcards that fix the specific gaps below — nothing else.

For each gap you are told the concept, what the student was asked, the answer they chose,
and the right answer. The wrong answer they picked is the most useful part: it shows the
shape of the misunderstanding. A card that only restates the right fact will not correct
a student who confidently believed something else.

Rules:
- One or two cards per gap, at most {max_cards} in total. Fewer, sharper cards beat more.
- Front is a question or a term, short enough to hold in your head. Back is the answer in
  the lesson's own words, one or two sentences.
- Where the chosen wrong answer shows a specific confusion, write the card to separate the
  two things being confused. Name both.
- Use only what the lesson says. Never add facts it does not contain.
- "because" is one short clause naming the mistake, addressed to the student, e.g.
  "you picked the cytoplasm for this one". No blame, no praise.
- "concept" repeats the gap's concept, spelled exactly as given.

Reply as JSON only.

--- THE LESSON ---
{lesson}

--- WHAT THEY GOT WRONG ---
{gaps}"""


# ---- Helpers ----------------------------------------------------------------


def _lesson_block(lines: list[dict]) -> str:
    """The lesson as numbered lines, so questions can point back at them."""
    out = []
    for i, line in enumerate(lines):
        tag = line.get("source", "notes")
        out.append(f"[{i}] ({tag}) {line.get('host', '')}: {line.get('text', '')}")
    return "\n".join(out)


def quiz_id_for(podcast_id: str) -> str:
    key = f"{store._mode()}|quiz|{podcast_id}".encode()
    return "q_" + hashlib.sha256(key).hexdigest()[:12]


def _dir(kind: str, ident: str):
    return config.DATA_DIR / kind / ident


def _save(kind: str, ident: str, value: dict) -> None:
    store._write_json(_dir(kind, ident) / "data.json", value)


def _load(kind: str, ident: str) -> dict | None:
    return store._read_json(_dir(kind, ident) / "data.json")


def _clean(questions: list[QuizQuestion], line_count: int) -> list[QuizQuestion]:
    """Drop anything unusable rather than show a broken question."""
    out: list[QuizQuestion] = []
    seen_q: set[str] = set()
    for item in questions:
        text = re.sub(r"\s+", " ", item.q or "").strip()
        options = [re.sub(r"\s+", " ", o or "").strip() for o in (item.options or [])]
        concept = re.sub(r"\s+", " ", item.concept or "").strip()[:60]
        if not text or not concept or len(options) != 4:
            continue
        if any(not o for o in options) or len(set(options)) != 4:
            continue  # a duplicated option makes the question unanswerable
        if not (0 <= item.answer < 4):
            continue
        key = text.lower()
        if key in seen_q:
            continue
        seen_q.add(key)
        refs = [n for n in (item.lineRefs or []) if isinstance(n, int) and 0 <= n < line_count]
        out.append(
            QuizQuestion(
                id=f"qq{len(out) + 1}",
                q=text,
                options=options,
                answer=int(item.answer),
                why=re.sub(r"\s+", " ", item.why or "").strip(),
                concept=concept,
                lineRefs=refs[:4],
            )
        )
    return out[:MAX_QUESTIONS]


# ---- Quiz -------------------------------------------------------------------


def build_quiz(podcast_id: str, lines: list[dict], count: int = 5) -> dict:
    """The quiz for a lesson. Same lesson, same quiz — it is cached like everything else."""
    quiz_id = quiz_id_for(podcast_id)
    cached = _load("quizzes", quiz_id)
    if cached:
        return cached

    count = max(3, min(MAX_QUESTIONS, count))
    if config.FAKE_AI:
        questions = _fake_questions(lines, count)
    else:
        draft = llm._generate(
            QUIZ_PROMPT.format(count=count, lesson=_lesson_block(lines)), QuizDraft
        )
        questions = _clean(draft.questions, len(lines))

    if len(questions) < 3:
        raise PipelineError("Not enough of this lesson could be turned into questions.")

    quiz = {
        "id": quiz_id,
        "podcastId": podcast_id,
        "questions": [q.model_dump() for q in questions],
    }
    _save("quizzes", quiz_id, quiz)
    return quiz


def public_quiz(quiz: dict) -> dict:
    """The quiz as the student may see it: no answers, no explanations.

    Grading happens on the server. Not because a study tool needs anti-cheat, but
    because the answer sitting in the page is the answer sitting in the page.
    """
    return {
        "id": quiz["id"],
        "podcastId": quiz["podcastId"],
        "questions": [
            {"id": q["id"], "q": q["q"], "options": q["options"]} for q in quiz["questions"]
        ],
    }


def load_quiz(quiz_id: str) -> dict | None:
    return _load("quizzes", quiz_id) if re.match(r"^q_[0-9a-f]{12}$", quiz_id) else None


# ---- Grading ----------------------------------------------------------------


def grade(quiz: dict, answers: dict[str, int]) -> dict:
    """Score an attempt and name the gaps it exposes.

    A question left unanswered counts as wrong — not knowing and not saying are the
    same thing for revision purposes — but it is recorded as skipped so the deck can
    tell the difference between a guess and a blank.
    """
    results = []
    score = 0
    gaps: dict[str, dict] = {}

    for q in quiz["questions"]:
        chosen = answers.get(q["id"])
        chosen = int(chosen) if isinstance(chosen, int) and 0 <= chosen < 4 else None
        correct = chosen == q["answer"]
        score += 1 if correct else 0
        results.append(
            {
                "questionId": q["id"],
                "q": q["q"],
                "options": q["options"],
                "chosen": chosen,
                "answer": q["answer"],
                "correct": correct,
                "why": q["why"],
                "concept": q["concept"],
            }
        )
        if not correct:
            # One gap per concept: two misses on the same idea is one weakness,
            # not two, and should not produce two sets of cards.
            gap = gaps.setdefault(
                q["concept"], {"concept": q["concept"], "misses": [], "lineRefs": []}
            )
            gap["misses"].append(
                {
                    "q": q["q"],
                    "chose": q["options"][chosen] if chosen is not None else None,
                    "right": q["options"][q["answer"]],
                    "skipped": chosen is None,
                }
            )
            for n in q.get("lineRefs", []):
                if n not in gap["lineRefs"]:
                    gap["lineRefs"].append(n)

    total = len(quiz["questions"])
    return {
        "id": "a_" + uuid.uuid4().hex[:12],
        "quizId": quiz["id"],
        "podcastId": quiz["podcastId"],
        "score": score,
        "total": total,
        "results": results,
        "gaps": list(gaps.values()),
    }


def save_attempt(attempt: dict) -> None:
    _save("attempts", attempt["id"], attempt)


def load_attempt(attempt_id: str) -> dict | None:
    return _load("attempts", attempt_id) if re.match(r"^a_[0-9a-f]{12}$", attempt_id) else None


# ---- Deck -------------------------------------------------------------------


def _gaps_block(gaps: list[dict]) -> str:
    out = []
    for gap in gaps:
        out.append(f"Concept: {gap['concept']}")
        for miss in gap["misses"]:
            if miss["skipped"]:
                out.append(f'  - Asked "{miss["q"]}" — left blank. Correct: {miss["right"]}')
            else:
                out.append(
                    f'  - Asked "{miss["q"]}" — chose "{miss["chose"]}". '
                    f'Correct: "{miss["right"]}"'
                )
    return "\n".join(out)


def build_deck(attempt: dict, lines: list[dict]) -> dict:
    """Cards for the gaps this attempt exposed, and nothing else.

    A clean sweep gets no deck. There is nothing to drill, and inventing cards to
    fill the screen would teach the student that the deck is decoration.
    """
    gaps = attempt.get("gaps", [])
    deck = {"id": "d_" + uuid.uuid4().hex[:12], "attemptId": attempt["id"], "cards": []}
    if not gaps:
        _save("decks", deck["id"], deck)
        return deck

    if config.FAKE_AI:
        cards = _fake_cards(gaps)
    else:
        draft = llm._generate(
            DECK_PROMPT.format(
                max_cards=MAX_CARDS, lesson=_lesson_block(lines), gaps=_gaps_block(gaps)
            ),
            DeckDraft,
        )
        wanted = {g["concept"] for g in gaps}
        cards = []
        for c in draft.cards:
            front = re.sub(r"\s+", " ", c.front or "").strip()
            back = re.sub(r"\s+", " ", c.back or "").strip()
            concept = re.sub(r"\s+", " ", c.concept or "").strip()
            # A card about something they got right is not a weak point.
            if not front or not back or concept not in wanted:
                continue
            cards.append(
                Flashcard(
                    front=front,
                    back=back,
                    concept=concept,
                    because=re.sub(r"\s+", " ", c.because or "").strip(),
                )
            )
        cards = cards[:MAX_CARDS]

    deck["cards"] = [c.model_dump() for c in cards]
    _save("decks", deck["id"], deck)
    return deck


def load_deck(deck_id: str) -> dict | None:
    return _load("decks", deck_id) if re.match(r"^d_[0-9a-f]{12}$", deck_id) else None


# ---- Fakes ------------------------------------------------------------------


def _fake_questions(lines: list[dict], count: int) -> list[QuizQuestion]:
    """Enough structure to exercise the flow without a key.

    The content is nonsense on purpose: a fake that reads like a real quiz invites
    someone to judge quality from it, and quality is exactly what the fake cannot
    show. See benchmark/README.md for the same argument about chapters.
    """
    teach = [i for i, line in enumerate(lines) if line.get("role") in (None, "teach", "hook")]
    out = []
    for n in range(min(count, max(3, len(teach)))):
        i = teach[n % len(teach)] if teach else 0
        out.append(
            QuizQuestion(
                id=f"qq{n + 1}",
                q=f"[sample question {n + 1} — needs a GEMINI_API_KEY for real ones]",
                options=[f"Option {k}" for k in "ABCD"],
                answer=n % 4,
                why="Sample explanation.",
                concept=f"Sample concept {n % 3 + 1}",
                lineRefs=[i],
            )
        )
    return out


def _fake_cards(gaps: list[dict]) -> list[Flashcard]:
    cards = []
    for gap in gaps[:MAX_CARDS]:
        miss = gap["misses"][0]
        because = (
            "you left this one blank"
            if miss["skipped"]
            else f'you picked "{miss["chose"]}"'
        )
        cards.append(
            Flashcard(
                front=f"[sample card for: {gap['concept']}]",
                back=f'The lesson\'s answer was "{miss["right"]}".',
                concept=gap["concept"],
                because=because,
            )
        )
    return cards
