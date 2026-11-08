"""Every model call: fixed prompts, JSON out, temperature 0, retry on rate limits."""

import logging
import os
import re
import time
from enum import Enum

from pydantic import BaseModel, ValidationError

from . import config, fake
from .formats import FORMATS, WORDS_PER_MINUTE, PipelineError, word_budget

log = logging.getLogger("buddy.llm")

# ---- Prompts (fixed; bump config.PIPELINE_VERSION when you change one) ----

TRANSCRIBE_PROMPT = """Transcribe the handwritten notes in this file exactly, in reading order.
Rules:
- Plain text only. No markdown, no commentary.
- Keep the line breaks as they are on the page.
- If you cannot read a word, write [unclear] in its place. Never guess.
- Return one entry per page. A photo is one page."""

OPTIONS_PROMPT = """These are a student's transcribed notes. Say what they are about, and title three podcast episodes made only from them.
- topic: what the notes cover, in at most 6 words.
- full_episode_title: an episode covering everything in the notes, at most 8 words.
- quick_recap_title: a short recap of the key facts, at most 8 words.
- deep_dive_topic: the one sub-topic the notes cover in the most detail, in at most 6 words.
- deep_dive_title: an episode about only that sub-topic, at most 8 words.
- suggestions: three things this student could ask for, written as they would type
  them, at most 14 words each. Make them specific to these notes and different from
  each other in shape, not just in topic: one asking for a particular sub-topic, one
  asking to be tested, one asking for a length or a difficulty. Name real things from
  the notes. No quotation marks, no trailing full stop.
Use only what the notes say. Ignore anything marked [unclear]. Plain words, no quotation marks.

Notes:
{notes}"""

SCRIPT_PROMPT = """Write a two-host audio lesson from a student's notes.
Hosts: Heart and Michael. They take turns, and Heart speaks first.
Lesson: {label}. {brief}
Length: about {words} words in total, and never fewer than {floor}. That is the length
the student asked for, so it is a target to hit, not a ceiling to stay under. Expect
roughly {lines_hint} lines.

Short notes do not mean a short lesson. They mean teaching the same material more
thoroughly: build each idea up in smaller steps, work through an example, say why a
fact matters, and check understanding more often. A page of notes that takes thirty
seconds to read aloud is still a full lesson's worth of teaching.

Padding means repeating yourself, restating the same idea in new words, or filling
with waffle, and that is never allowed. Teaching the notes properly for the full
length is not padding.

This is a lesson someone studies from, not an episode they listen to. The test is
whether a student knows the material better at the end than at the start. Reading
the notes aloud in a friendly voice fails that test.

Every line has a role, and the lesson must have a shape:
- "hook": why this matters, or where it sits in the bigger picture. Open with one.
- "teach": the explanation itself. One idea per line. Build in the order that makes
  the ideas easiest to learn, not necessarily the order they were written down.
- "check": a question put straight to the student, who is given silence to answer
  out loud before the lesson continues. Ask about something already taught. Ask real
  questions with real answers, never "does that make sense?".
- "answer": the answer to the check immediately before it. Confirm, then move on.
- "recap": pull the thread together at the end. Finish with one.

Rules for the shape:
- Every "check" is followed immediately by its "answer".
- Space the checks out. Teach something before you test it.
- A lesson of more than about six lines has at least two checks.
- Never two "hook" lines in a row, and never open with a check.

Every line says where its content came from, and the student is shown those labels.
Be strict about this; it is the whole promise of the product.
- source "notes": every fact, name, number and relationship in the line is in the notes
  below. This is the student's own material, read back to them.
- source "added": the line brings in something the notes do not say — context, an
  analogy, a worked example, why a fact matters, or the meaning of a term the notes
  use without explaining.

Rules:
- Prefer "notes" lines: the student's own material leads, and every fact in the notes
  gets taught. Use "added" lines for what a student genuinely needs in order to follow
  them — an analogy, a worked example, why a fact matters, a term the notes use without
  explaining. Reaching the target length by teaching the notes more carefully is right;
  reaching it with background the student did not need is not.
- Never let an unsourced fact sit inside a "notes" line. If a line would mix the two,
  split it into one of each.
- Everything in an "added" line must be true and must never contradict the notes.
- Skip anything marked [unclear]. Do not guess what it says.
- Write for the ear: spell out symbols and abbreviations ("→" becomes "leads to", "e.g." becomes "for example", "~50%" becomes "about fifty percent", "2×" becomes "twice").
- Plain spoken sentences. No stage directions, sound effects, emoji or markdown.
- Each line is one or two sentences.

Also divide the lesson into chapters the listener can jump between.
- Between two and seven chapters, in order, the first starting at line 0.
- A chapter starts where a new idea begins: on the line that starts teaching it.
  Never in the middle of an idea, never on a check, and never on an answer —
  someone jumping there would land on a question with no idea what it is about,
  or on a reply to a question they never heard.
- Title each chapter by its subject, in two to five words, using the notes' own
  vocabulary: "Why leaves look green", "Splitting water". Never name the move
  instead of the subject — no "Check 1", "Question 2", "Introduction", "Recap".
  A student scanning the list should be able to find the bit they want.

Finally, give the lesson a title: what it covers, at most eight words, in the notes'
own vocabulary. Name the subject, not the request — "The Krebs cycle, step by step",
never "Your five minute overview".

Notes:
{notes}"""


# ---- Response shapes ----


class Page(BaseModel):
    text: str


class Transcription(BaseModel):
    pages: list[Page]


class Options(BaseModel):
    topic: str
    full_episode_title: str
    quick_recap_title: str
    deep_dive_topic: str
    deep_dive_title: str
    suggestions: list[str] = []


class Host(str, Enum):
    HEART = "Heart"
    MICHAEL = "Michael"


class Source(str, Enum):
    """Where a line's content came from. Shown to the student."""

    NOTES = "notes"
    ADDED = "added"


class Role(str, Enum):
    """What a line is doing in the lesson. Drives pacing and the transcript view."""

    HOOK = "hook"      # why this matters, where it sits
    TEACH = "teach"    # the explanation itself
    CHECK = "check"    # a question put to the student; silence follows
    ANSWER = "answer"  # the answer, after the pause
    RECAP = "recap"    # consolidation at the end


class Line(BaseModel):
    host: Host
    text: str
    source: Source = Source.NOTES
    role: Role = Role.TEACH


class ChapterPlan(BaseModel):
    title: str
    startLine: int


class Script(BaseModel):
    lines: list[Line]
    chapters: list[ChapterPlan] = []
    title: str = ""


# ---- Calls ----

_client = None
_RETRY_CODES = {429, 500, 502, 503, 504}


def _gemini():
    global _client
    if _client is None:
        if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
            raise PipelineError(
                "The server has no Gemini API key. Add GEMINI_API_KEY to server/.env, "
                "or start it with FAKE_AI=1 to test without one."
            )
        from google import genai

        _client = genai.Client()
    return _client


def _generate(contents, schema: type[BaseModel]) -> BaseModel:
    from google.genai import errors, types

    cfg = types.GenerateContentConfig(
        temperature=0,
        seed=0,
        response_mime_type="application/json",
        response_schema=schema,
    )
    delay = 2.0
    for attempt in range(6):
        try:
            resp = _gemini().models.generate_content(
                model=config.GEMINI_MODEL, contents=contents, config=cfg
            )
        except errors.APIError as e:
            if e.code in _RETRY_CODES and attempt < 5:
                log.warning("Gemini returned %s; retrying in %.0fs", e.code, delay)
                time.sleep(delay)
                delay = min(delay * 2, 30)
                continue
            if e.code == 429:
                raise PipelineError(
                    "The free Gemini tier is busy right now. Wait a minute and try again."
                ) from e
            if e.code in (401, 403):
                raise PipelineError("The server's Gemini API key was rejected.") from e
            raise PipelineError("The AI service couldn't handle this request.") from e
        if isinstance(resp.parsed, schema):
            return resp.parsed
        try:
            return schema.model_validate_json(resp.text or "")
        except ValidationError as e:
            raise PipelineError("The AI's answer came back in the wrong shape.") from e
    raise PipelineError("The AI service didn't answer. Try again in a minute.")


def transcribe(data: bytes, mime: str) -> list[str]:
    """One uploaded file → the text of each page on it."""
    if config.FAKE_AI:
        return fake.transcribe(data, mime)
    from google.genai import types

    part = types.Part.from_bytes(data=data, mime_type=mime)
    result = _generate([part, TRANSCRIBE_PROMPT], Transcription)
    return [p.text.strip() for p in result.pages]


def _notes_block(transcripts: list[str]) -> str:
    return "\n\n".join(f"[Page {i + 1}]\n{t}" for i, t in enumerate(transcripts))


def name_options(transcripts: list[str]) -> Options:
    if config.FAKE_AI:
        return Options(**fake.OPTIONS)
    return _generate(OPTIONS_PROMPT.format(notes=_notes_block(transcripts)), Options)


MINUTES = re.compile(r"(\d{1,3})\s*(?:-|\s)?\s*(?:minute|minutes|min|mins)\b", re.I)


def minutes_in(request: str, default: int = 5) -> int:
    """Pull a length out of the student's own words: '5 minute overview' -> 5."""
    m = MINUTES.search(request or "")
    if not m:
        return default
    return max(1, min(20, int(m.group(1))))


def _word_count(lines: list[Line]) -> int:
    """Spoken words in a script — what decides how long the audio actually runs."""
    return sum(len(line.text.split()) for line in lines)


def write_script(
    transcripts: list[str],
    format_id: str | None,
    topic: str | None,
    request: str = "",
    minutes: float | None = None,
) -> tuple[list[Line], list[ChapterPlan], str]:
    """Write the lesson from a preset format, or from the student's own request."""
    if request.strip():
        label = "Your request"
        brief = (
            "The student asked for this in their own words, so follow it as closely as "
            "the notes allow:\n\n"
            f'"{request.strip()}"\n\n'
            "Honour what they asked for in shape as well as in content. If they asked "
            "for an overview, do not go deep on one part. If they named a topic, stay "
            "on it. If the notes cannot support part of the request, cover what they do "
            "support and do not invent the rest."
        )
        minutes = minutes if minutes else minutes_in(request)
    else:
        fmt = FORMATS[format_id]
        label = fmt.label
        minutes = minutes or fmt.minutes
        brief = fmt.brief.format(topic=topic or "the main topic")

    if config.FAKE_AI:
        # A custom request has no canned script, so it plays the full episode.
        # Title it after what is actually spoken rather than echoing the request
        # back — otherwise fake mode shows a title the audio does not match.
        key = format_id if format_id in fake.SCRIPTS else "full_episode"
        lines = _repair_arc([Line(**line) for line in fake.SCRIPTS[key]])
        return lines, _fake_chapters(lines), fake.OPTIONS.get(f"{key}_title", "")

    target = minutes * WORDS_PER_MINUTE
    prompt = SCRIPT_PROMPT.format(
        label=label,
        brief=brief,
        words=target,
        floor=int(target * 0.8),
        lines_hint=max(8, round(target / 35)),
        notes=_notes_block(transcripts),
    )
    script = _generate(prompt, Script)
    lines = [line for line in script.lines if line.text.strip()][:200]
    if not lines:
        raise PipelineError("The AI wrote an empty script. Try a clearer photo.")

    # Models undershoot a length target badly on short notes, and a "five minute
    # lesson" that runs fifteen seconds is the one failure a student notices
    # immediately. Ask once for the full length before giving up on it.
    spoken = _word_count(lines)
    if spoken < target * 0.6:
        log.info("script came back at %d words against a %d target; expanding", spoken, target)
        longer = (
            f"{prompt}\n\nAn earlier attempt came back at only {spoken} words. That is far "
            f"too short for the {minutes} minute lesson the student asked for. Write it "
            f"again at the full {target} words: keep everything you had, then teach each "
            "idea in more steps, work through examples, and add more checks with their "
            "answers. Do not repeat yourself, and do not invent facts about the subject — "
            "go deeper on what the notes already say."
        )
        try:
            retry = _generate(longer, Script)
            retry_lines = [line for line in retry.lines if line.text.strip()][:200]
            if _word_count(retry_lines) > spoken:
                script, lines = retry, retry_lines
        except PipelineError:
            pass  # a short lesson beats a failed one

    lines = _repair_arc(lines)
    title = re.sub(r"\s+", " ", script.title or "").strip()[:80]
    return lines, _clean_chapters(script.chapters, lines), title


def _section_start(lines: list[Line], i: int) -> int:
    """Walk back to the first line of the teaching run that leads into line i.

    A chapter that opens on a question drops the listener into a check with no
    idea what it is checking — a milder version of why a chapter never opens on
    an answer. The teaching that sets the question up is the real section start.
    """
    j = i
    while j > 0 and lines[j - 1].role in (Role.TEACH, Role.HOOK):
        j -= 1
    return j


def _fake_chapters(lines: list[Line]) -> list[ChapterPlan]:
    """FAKE_AI gets no chapters.

    A chapter title has to name what that stretch is about, which is a language
    task — the model does it as part of writing the lesson. Faking it from the
    text mechanically produces either a label about the line's role ("Check 1")
    or a mid-sentence fragment ("It makes N A D"), and both are worse than no
    chapter list at all: a student scanning them learns nothing and clicks into
    the wrong place. So the fake path returns nothing and the UI hides the list.
    """
    return []


def _clean_chapters(plan: list[ChapterPlan], lines: list[Line]) -> list[ChapterPlan]:
    """Keep a chapter list only if it is sound. A wrong chapter is worse than none.

    Must ascend, not repeat, stay in range, start at 0, and never split a check
    from its answer — landing there would drop the listener into an answer to a
    question they never heard.
    """
    out: list[ChapterPlan] = []
    for ch in plan or []:
        title = re.sub(r"\s+", " ", str(ch.title or "")).strip()[:64]
        start = int(ch.startLine)
        if not title or not (0 <= start < len(lines)):
            continue
        if lines[start].role is Role.ANSWER:
            continue
        # A chapter that opens on a question is disorienting in the same way, so
        # move it back to the teaching that sets the question up.
        if lines[start].role is Role.CHECK:
            start = _section_start(lines, start)
        if out and start <= out[-1].startLine:
            continue
        out.append(ChapterPlan(title=title, startLine=start))
    if len(out) < 2:
        return []
    out[0] = ChapterPlan(title=out[0].title, startLine=0)
    return out[:7]


def _repair_arc(lines: list[Line]) -> list[Line]:
    """Keep the lesson shape sound even when the model drifts from the brief.

    Only fixes what would actually mislead a listener: a question with no answer
    after it, or an answer with no question before it. Both leave the student
    sitting in silence waiting for something that never comes.
    """
    # Order matters: each pass can create work for the next, so they run from the
    # start of the lesson outwards.

    # 1. A lesson never opens on a question.
    if lines and lines[0].role is Role.CHECK:
        lines[0] = lines[0].model_copy(update={"role": Role.HOOK})

    # 2. An ANSWER only makes sense directly after a CHECK.
    for i, line in enumerate(lines):
        if line.role is Role.ANSWER and (i == 0 or lines[i - 1].role is not Role.CHECK):
            lines[i] = line.model_copy(update={"role": Role.TEACH})

    # 3. A CHECK must be answered. If the model forgot, the question still works as
    #    teaching, and the student is not left hanging in a 3.5 second silence.
    for i, line in enumerate(lines):
        if line.role is Role.CHECK:
            answered = i + 1 < len(lines) and lines[i + 1].role is Role.ANSWER
            if not answered:
                lines[i] = line.model_copy(update={"role": Role.TEACH})

    return lines


# ================= Review -> Quiz -> Flashcards =================
#
# These three are one loop, not three features. The quiz can only be fair if it
# asks about what the review actually taught, and the flashcards can only help
# if they drill what this student personally got wrong. So every quiz question
# names the review point it tests, and a card is only ever made from a point the
# student missed. The pointId is the thread that ties them together.

REVIEW_PROMPT = """Write a study review of a student's notes: the page they read before being tested.

It is read, not heard, so it can use structure the spoken lesson cannot. It must
be worth reading on its own, and it must be made of discrete points, because each
one will be tested separately afterwards.

- Between four and nine points. One idea each — never two facts welded together,
  since a question about a double point cannot be marked fairly.
- heading: what the point is about, two to six words, the notes' own vocabulary.
- body: one to three sentences teaching it. Say what it is and why it matters.
- source "notes" when every fact in the body is in the notes; "added" when the
  body brings in context, an analogy or a definition the notes do not give.
- exam: true only where the notes themselves flag it as examinable ("on the exam",
  starred, underlined). Never guess at what an examiner wants.
- Order them so an earlier point never depends on a later one.
- Skip anything marked [unclear]. Do not guess at it.

Also give the review a title of at most eight words, naming the subject.

Notes:
{notes}"""

QUIZ_PROMPT = """Write quiz questions on a review a student has just read.

Each question tests exactly one point of the review, and says which by its id.
A student who read and understood that point answers correctly; a student who
skimmed does not. So do not ask what the point's heading already states.

- One question per point, in the review's order, for the points listed below.
- pointId: the id of the point the question tests. Use the ids exactly as given.
- q: the question. Ask about what the point actually says, not around it.
- options: exactly four, one correct. Wrong options must be plausible to someone
  who half-remembers — a near-miss number, a neighbouring term, the right idea
  attached to the wrong thing. Never filler nobody would pick.
- answer: the index, 0 to 3, of the correct option.
- why: one sentence on why it is right, in the review's own words.

Use only what the review says. Do not test outside knowledge, and do not test an
"added" point any harder than a "notes" one.

Review:
{review}"""

CARDS_PROMPT = """Write flashcards for a student who has just got some quiz questions wrong.

Below are only the review points they missed. They have already read the review
and failed to retain these, so a card that merely restates the point will fail the
same way. Come at each from a different angle than the review did.

- One or two cards per missed point. Two only where the point genuinely holds two
  things worth recalling separately.
- front: a question or a prompt, short enough to read at a glance.
- back: the answer, in the fewest words that are still complete.
- pointId: the point this card drills. Use the ids exactly as given.
- Where the student picked a particular wrong answer, aim the card at that
  confusion specifically rather than at the topic in general.
- Stay inside what the review says. No new facts.

Missed points:
{points}"""


class ReviewPoint(BaseModel):
    id: str
    heading: str
    body: str
    source: Source = Source.NOTES
    exam: bool = False


class ReviewDoc(BaseModel):
    title: str = ""
    points: list[ReviewPoint]


class QuizQuestion(BaseModel):
    pointId: str
    q: str
    options: list[str]
    answer: int
    why: str = ""


class QuizDoc(BaseModel):
    questions: list[QuizQuestion]


class Card(BaseModel):
    pointId: str
    front: str
    back: str


class CardsDoc(BaseModel):
    cards: list[Card]


def _point_id(i: int) -> str:
    return f"p{i + 1}"


def write_review(transcripts: list[str]) -> ReviewDoc:
    """The page the student reads before being tested on it."""
    if config.FAKE_AI:
        return ReviewDoc(**fake.REVIEW)
    doc = _generate(REVIEW_PROMPT.format(notes=_notes_block(transcripts)), ReviewDoc)
    points = []
    for i, p in enumerate(doc.points):
        heading = re.sub(r"\s+", " ", p.heading or "").strip()
        body = re.sub(r"\s+", " ", p.body or "").strip()
        if not heading or not body:
            continue
        # Ids are assigned here, not by the model, so the quiz can rely on them.
        points.append(p.model_copy(update={"id": _point_id(len(points)), "heading": heading, "body": body}))
    if not points:
        raise PipelineError("A review could not be built from these notes. Try a clearer photo.")
    title = re.sub(r"\s+", " ", doc.title or "").strip()[:80]
    return ReviewDoc(title=title, points=points[:9])


def _review_block(review: ReviewDoc) -> str:
    out = []
    for p in review.points:
        flag = " [flagged as examinable]" if p.exam else ""
        out.append(f"[{p.id}] {p.heading}{flag}\n{p.body}")
    return "\n\n".join(out)


def write_quiz(review: ReviewDoc) -> QuizDoc:
    """One question per review point, each naming the point it tests."""
    if config.FAKE_AI:
        qs = [QuizQuestion(**q) for q in fake.QUIZ]
        return QuizDoc(questions=_clean_quiz(qs, review))
    doc = _generate(QUIZ_PROMPT.format(review=_review_block(review)), QuizDoc)
    questions = _clean_quiz(doc.questions, review)
    if not questions:
        raise PipelineError("A quiz could not be written from this review.")
    return QuizDoc(questions=questions)


def _clean_quiz(questions: list[QuizQuestion], review: ReviewDoc) -> list[QuizQuestion]:
    """Drop anything that breaks the chain or cannot be marked.

    A question whose pointId names no real point is unmarkable and unusable for
    flashcards afterwards, so it goes. So does one without exactly four distinct
    options, or whose answer index is out of range.
    """
    valid = {p.id for p in review.points}
    order = {p.id: i for i, p in enumerate(review.points)}
    seen: set[str] = set()
    out: list[QuizQuestion] = []
    for q in questions:
        opts = [re.sub(r"\s+", " ", str(o)).strip() for o in (q.options or [])]
        if q.pointId not in valid or q.pointId in seen:
            continue
        if len(opts) != 4 or len(set(opts)) != 4 or not all(opts):
            continue
        if not isinstance(q.answer, int) or not (0 <= q.answer < 4):
            continue
        if not str(q.q or "").strip():
            continue
        seen.add(q.pointId)
        out.append(q.model_copy(update={"options": opts, "q": q.q.strip()}))
    out.sort(key=lambda q: order[q.pointId])
    return out


def write_cards(review: ReviewDoc, missed: list[str], chosen: dict[str, str] | None = None) -> CardsDoc:
    """Cards for the points this student actually got wrong. Nothing else."""
    wanted = [p for p in review.points if p.id in set(missed)]
    if not wanted:
        return CardsDoc(cards=[])
    if config.FAKE_AI:
        cards = [Card(**c) for c in fake.CARDS if c["pointId"] in {p.id for p in wanted}]
        return CardsDoc(cards=cards)
    blocks = []
    for p in wanted:
        wrong = (chosen or {}).get(p.id)
        note = f"\nThey answered: {wrong}" if wrong else ""
        blocks.append(f"[{p.id}] {p.heading}\n{p.body}{note}")
    doc = _generate(CARDS_PROMPT.format(points="\n\n".join(blocks)), CardsDoc)
    valid = {p.id for p in wanted}
    cards = [
        c.model_copy(update={"front": c.front.strip(), "back": c.back.strip()})
        for c in doc.cards
        if c.pointId in valid and str(c.front or "").strip() and str(c.back or "").strip()
    ]
    return CardsDoc(cards=cards[: 2 * len(wanted)])
