"""Turn the transcribed notes into flashcards with Gemini.

Reads text/notes.txt (made by transcribe.py) and writes output/flashcards.json:

    [
      {"front": "What do rubrics let you say that win rates don't?",
       "back": "How good a model is on specific criteria, not just whether it beats another model."},
      ...
    ]

    python flashcards.py                    # as many cards as the notes support
    python flashcards.py --max 15           # at most 15 cards
    python flashcards.py --input other.txt  # use a different text file
"""

import argparse
import json
import sys
import time
from pathlib import Path

from google.genai import types
from pydantic import BaseModel

from gemini import HERE, MODEL, generate, make_client

DEFAULT_INPUT = HERE / "text" / "notes.txt"
OUTPUT_DIR = HERE / "output"
OUT_FILE = OUTPUT_DIR / "flashcards.json"


class Flashcard(BaseModel):
    front: str
    back: str


PROMPT = """You are an expert educational designer specializing in spaced repetition and active recall.
Your task is to analyze the study notes below and generate high-yield, conceptual flashcards.

Rules:
1. Active Recall: Each front must be a direct question, a short scenario, or a fill-in-the-blank statement that requires retrieval. Never a yes/no question.
2. Atomic Principle: Each card tests exactly one clear concept or relationship. Never combine several questions on one card.
3. Concise Back: The back states the core answer only, optionally followed by one sentence of context or rationale from the notes.
4. Grounded: Use ONLY information explicitly stated in the notes. Do not invent facts, examples, numbers or explanations, and do not add outside knowledge.
5. Prioritize: Prefer definitions, distinctions, purposes, and named examples over trivia such as dates or the note's title.
6. No duplicates: Do not test the same fact twice with different wording.
7. {count_rule}

About the notes:
- They were transcribed from handwriting. Lines like "--- page 2: photo.jpg ---" only mark page breaks; they are not content.
- [unclear] marks a word that could not be read. Never build a card whose answer depends on an [unclear] word, and never guess what it was.
- Lines starting with "Margin note:" are the writer's own side comments on the nearby text; you may use them.
- The writer uses shorthand (e.g. "w/" = with, "eg" = for example, "ctx" = context). Write cards in clear, complete wording, spelling out shorthand only where its meaning is certain.

Notes:
\"\"\"
{notes}
\"\"\""""


def clean(cards):
    """Drop empty cards and repeated fronts, and trim whitespace."""
    seen = set()
    kept = []
    for card in cards:
        front, back = card.front.strip(), card.back.strip()
        key = front.lower()
        if not front or not back or key in seen:
            continue
        seen.add(key)
        kept.append({"front": front, "back": back})
    return kept


def main():
    parser = argparse.ArgumentParser(description="Generate flashcards (JSON) from the transcribed notes.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="text file to read (default text/notes.txt)")
    parser.add_argument("--max", type=int, help="maximum number of cards (default: as many as the notes support)")
    args = parser.parse_args()

    if not args.input.exists():
        sys.exit(f"{args.input} not found. Run transcribe.py first.")
    notes = args.input.read_text(encoding="utf-8").strip()
    if not notes:
        sys.exit(f"{args.input} is empty.")
    if "[page not transcribed" in notes:
        print("warning: some pages failed to transcribe; their content won't be in the cards.")

    count_rule = (
        f"Quantity: Make at most {args.max} cards. Cover the most important ideas first."
        if args.max
        else "Quantity: Make as many cards as the notes genuinely support, and no more. Do not pad with weak cards."
    )
    prompt = PROMPT.format(count_rule=count_rule, notes=notes)

    client = make_client()
    print(f"make  flashcards from {args.input.name} with {MODEL}", flush=True)
    reply = generate(
        client,
        prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=list[Flashcard],
        ),
        started=time.monotonic(),
        what="asking Gemini for flashcards",
    )

    cards = reply.parsed
    if cards is None:  # fall back to parsing the raw JSON text
        cards = [Flashcard(**c) for c in json.loads(reply.text)]
    cards = clean(cards)
    if args.max:
        cards = cards[: args.max]
    if not cards:
        sys.exit("Gemini returned no usable flashcards.")

    OUTPUT_DIR.mkdir(exist_ok=True)
    OUT_FILE.write_text(json.dumps(cards, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"saved {OUT_FILE.relative_to(HERE)}: {len(cards)} cards")
    print("  Check a few against the notes before trusting the rest:")
    for card in cards[:3]:
        print(f"  Q: {card['front']}")
        print(f"  A: {card['back']}")
        print()


if __name__ == "__main__":
    main()
