"""Simple web app around the study buddy. Run: python app.py, then open http://127.0.0.1:5000"""

import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory
from werkzeug.exceptions import HTTPException

import study_buddy as sb

OUT = Path(__file__).parent / "output"
OUT.mkdir(exist_ok=True)

VOICES = {"af_heart", "af_bella", "am_michael", "bf_emma"}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB per photo


def pick_voice(value):
    return value if value in VOICES else sb.VOICE


@app.errorhandler(Exception)
def on_error(e):
    """Send errors back as JSON so the page can show them."""
    if isinstance(e, HTTPException):
        return jsonify(error=e.description), e.code
    app.logger.exception(e)
    code = getattr(e, "code", None)
    if code == 429 or (isinstance(code, int) and code >= 500):
        return jsonify(error="Gemini is busy right now. Wait a minute and try again."), 503
    return jsonify(error=str(e) or e.__class__.__name__), 500


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/simple")
def simple():
    """The original one-column page, kept for reference."""
    return render_template("simple.html")


@app.post("/api/note")
def note():
    file = request.files.get("photo")
    if not file or not file.filename:
        return jsonify(error="No photo was sent."), 400
    voice = pick_voice(request.form.get("voice"))
    job = uuid.uuid4().hex[:8]
    img = OUT / f"{job}{Path(file.filename).suffix.lower() or '.jpg'}"
    file.save(img)

    text = sb.read_note(img)
    spoken = sb.prepare_for_ear(text)
    mp3 = sb.speak(spoken, OUT / f"{job}.mp3", voice=voice)
    return jsonify(text=text, spoken=spoken, audio=f"/audio/{mp3.name}")


@app.post("/api/ask")
def ask():
    data = request.get_json(force=True)
    if not (data.get("text") or "").strip():
        return jsonify(error="Add a note first."), 400
    if data.get("quiz"):
        answer = sb.quiz(data["text"])
    else:
        if not (data.get("question") or "").strip():
            return jsonify(error="Type a question."), 400
        answer = sb.ask(data["text"], data["question"])
    result = {"answer": answer}
    # speak defaults to True so the old page keeps working; the new page asks for audio on demand.
    if data.get("speak", True):
        mp3 = sb.speak(answer, OUT / f"answer_{uuid.uuid4().hex[:8]}.mp3", voice=pick_voice(data.get("voice")))
        result["audio"] = f"/audio/{mp3.name}"
    return jsonify(result)


@app.post("/api/speak")
def speak():
    """Record any text (an answer, or several pages joined into one audiobook)."""
    data = request.get_json(force=True)
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify(error="Nothing to read."), 400
    mp3 = sb.speak(text, OUT / f"speak_{uuid.uuid4().hex[:8]}.mp3", voice=pick_voice(data.get("voice")))
    return jsonify(audio=f"/audio/{mp3.name}")


@app.get("/audio/<name>")
def audio(name):
    return send_from_directory(OUT, name)


if __name__ == "__main__":
    app.run(debug=True)
