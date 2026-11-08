"""Point the quiz engine at a review instead of a lesson.

Two sessions built a quiz loop at the same time. The engine in quiz.py is the
better one — it collapses gaps by concept so two misses on one idea are one
weakness, it keeps the answers off the client and marks on the server, it tells
a guess apart from a blank, and it records why each card is in the deck. None of
that was in the version I wrote.

What it did not have is the step Dante actually asked for: a review to read
before being tested. That lives in llm.write_review.

So this module is the join. It adapts review points into the shape quiz.py
already consumes and reuses its generation, validation, grading and deck
building unchanged. quiz.py is not modified — a review point is simply another
kind of source line.
"""

from __future__ import annotations

import hashlib

from . import quiz, store


def points_as_lines(points: list[dict]) -> list[dict]:
    """A review point in the shape quiz.py expects of a lesson line.

    Index matters: quiz.py validates lineRefs against the list length and stores
    them per question, so a question's refs come back as indices into this list,
    which is the review's own point order.
    """
    return [
        {
            "host": "",
            "text": f"{p.get('heading', '')}. {p.get('body', '')}".strip(". ").strip(),
            "source": p.get("source", "notes"),
        }
        for p in points
    ]


def quiz_id_for(review_id: str) -> str:
    key = f"{store._mode()}|reviewquiz|{review_id}".encode()
    return "q_" + hashlib.sha256(key).hexdigest()[:12]


def build(review_id: str, points: list[dict], count: int = 5) -> dict:
    """The quiz for a review. Same review, same quiz: cached like everything else."""
    quiz_id = quiz_id_for(review_id)
    cached = quiz._load("quizzes", quiz_id)
    if cached:
        return cached

    lines = points_as_lines(points)
    count = max(3, min(quiz.MAX_QUESTIONS, min(count, len(lines))))

    if quiz.config.FAKE_AI:
        questions = quiz._fake_questions(lines, count)
    else:
        draft = quiz.llm._generate(
            quiz.QUIZ_PROMPT.format(count=count, lesson=quiz._lesson_block(lines)),
            quiz.QuizDraft,
        )
        questions = quiz._clean(draft.questions, len(lines))

    if len(questions) < 3:
        raise quiz.PipelineError("Not enough of this review could be turned into questions.")

    built = {
        "id": quiz_id,
        # quiz.grade() and quiz.public_quiz() both read podcastId, so it carries
        # the review id here. reviewId is the honest name; both are written so
        # the engine stays untouched and callers need not care which they got.
        "podcastId": review_id,
        "reviewId": review_id,
        "questions": [q.model_dump() for q in questions],
    }
    quiz._save("quizzes", quiz_id, built)
    return built


def deck_for(attempt: dict, points: list[dict]) -> dict:
    """Cards for the gaps this attempt exposed, drawn from the review."""
    return quiz.build_deck(attempt, points_as_lines(points))
