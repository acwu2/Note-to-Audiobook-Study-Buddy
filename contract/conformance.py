#!/usr/bin/env python3
"""Check that a running Study Buddy server satisfies contract/API.md.

Framework-agnostic on purpose: standard library only, no imports from the
project, nothing but HTTP. Point it at a Flask server or a FastAPI server and
it asks the same questions of both, so "which stack shipped" stops being a
thing anyone has to reason about.

    python3 contract/conformance.py http://localhost:8000

Run the server with FAKE_AI=1 FAKE_TTS=1 for a fast, deterministic, free pass.
Exit status is 0 only when every check passes.
"""

import base64
import json
import mimetypes
import sys
import time
import urllib.error
import urllib.request
import uuid

# A real 1x1 PNG. Under FAKE_AI the bytes are never looked at, but the upload
# still has to be a genuine file of an allowed type.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

PASS, FAIL = [], []


def ok(what: str) -> None:
    PASS.append(what)
    print(f"  pass  {what}")


def bad(what: str, detail: str = "") -> None:
    FAIL.append(what)
    print(f"  FAIL  {what}")
    if detail:
        print(f"        {detail}")


def request(base, path, method="GET", body=None, headers=None):
    """Return (status, parsed_json_or_bytes, headers). Never raises on 4xx/5xx."""
    req = urllib.request.Request(base + path, data=body, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, _parse(r.read(), r.headers.get("content-type", "")), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, _parse(e.read(), e.headers.get("content-type", "")), dict(e.headers)
    except urllib.error.URLError as e:
        print(f"\ncannot reach {base}{path}: {e.reason}")
        sys.exit(2)


def _parse(raw: bytes, content_type: str):
    if "json" in content_type:
        try:
            return json.loads(raw)
        except ValueError:
            return raw
    return raw


def multipart(files: list[tuple[str, str, bytes]]) -> tuple[bytes, str]:
    """files: (field, filename, content). Hand-rolled so there are no deps."""
    boundary = "----studybuddy" + uuid.uuid4().hex
    out = bytearray()
    for field, filename, content in files:
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        out += f"--{boundary}\r\n".encode()
        out += f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'.encode()
        out += f"Content-Type: {mime}\r\n\r\n".encode()
        out += content + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"


def expect_detail(status, body, want_status, what):
    """Every error must be {"detail": "<sentence>"} — see API.md."""
    if status != want_status:
        bad(what, f"expected {want_status}, got {status}")
        return
    if not isinstance(body, dict) or not isinstance(body.get("detail"), str) or not body["detail"].strip():
        bad(what, f'expected {{"detail": "<sentence>"}}, got {str(body)[:120]}')
        return
    ok(f"{what} → {want_status} {body['detail'][:48]}")


def main(base: str) -> int:
    base = base.rstrip("/")
    print(f"\nChecking {base} against contract/API.md\n")

    # ---- health ----
    print("GET /api/health")
    status, body, _ = request(base, "/api/health")
    if status == 200 and isinstance(body, dict) and body.get("ok") is True:
        ok("returns ok:true")
        for key in ("fakeAi", "fakeTts"):
            if isinstance(body.get(key), bool):
                ok(f"{key} is a boolean")
            else:
                bad(f"{key} is a boolean", f"got {body.get(key)!r}")
        if body.get("fakeAi") and body.get("model") is not None:
            bad("model is null when fakeAi", f"got {body.get('model')!r}")
        else:
            ok("model agrees with fakeAi")
    else:
        bad("returns ok:true", f"{status} {str(body)[:120]}")
        return report()

    fake = bool(body.get("fakeAi"))
    if not fake:
        print("\n  note: server is not in FAKE_AI mode — this run will call the real model")

    # ---- errors on upload ----
    print("\nPOST /api/notes (error envelope)")
    data, ctype = multipart([])
    status, body, _ = request(base, "/api/notes", "POST", data, {"Content-Type": ctype})
    if status in (400, 422):
        expect_detail(status, body, status, "no files rejected")
    else:
        bad("no files rejected", f"expected 400, got {status}")

    data, ctype = multipart([("photos", "notes.txt", b"not an image")])
    status, body, _ = request(base, "/api/notes", "POST", data, {"Content-Type": ctype})
    expect_detail(status, body, 415, "unsupported type rejected")

    data, ctype = multipart([("photos", "empty.png", b"")])
    status, body, _ = request(base, "/api/notes", "POST", data, {"Content-Type": ctype})
    expect_detail(status, body, 400, "empty file rejected")

    # ---- a real upload ----
    print("\nPOST /api/notes")
    data, ctype = multipart([("photos", "page1.png", PNG)])
    status, note, _ = request(base, "/api/notes", "POST", data, {"Content-Type": ctype})
    if status != 200 or not isinstance(note, dict):
        bad("accepts a photo", f"{status} {str(note)[:160]}")
        return report()
    ok("accepts a photo")

    for key in ("noteId", "topic", "pages", "options"):
        if key in note:
            ok(f"note has {key}")
        else:
            bad(f"note has {key}")
    if isinstance(note.get("pages"), list) and note["pages"]:
        page = note["pages"][0]
        if isinstance(page.get("transcript"), str) and isinstance(page.get("unclearCount"), int):
            ok("page has transcript and unclearCount")
        else:
            bad("page has transcript and unclearCount", str(page)[:120])
    opts = note.get("options") or []
    if len(opts) == 3 and all(o.get("id") and o.get("title") and o.get("label") for o in opts):
        ok("three titled options")
    else:
        bad("three titled options", str(opts)[:160])

    # idempotency: the same bytes must not mint a new note
    data, ctype = multipart([("photos", "page1.png", PNG)])
    status, again, _ = request(base, "/api/notes", "POST", data, {"Content-Type": ctype})
    if isinstance(again, dict) and again.get("noteId") == note["noteId"]:
        ok("same bytes return the same noteId")
    else:
        bad("same bytes return the same noteId",
            f'{note["noteId"]} then {again.get("noteId") if isinstance(again, dict) else again}')

    # ---- create a podcast ----
    print("\nPOST /api/podcasts")
    status, body, _ = request(
        base, "/api/podcasts", "POST",
        json.dumps({"noteId": "n_doesnotexist", "optionId": opts[0]["id"]}).encode(),
        {"Content-Type": "application/json"},
    )
    expect_detail(status, body, 404, "unknown noteId rejected")

    status, body, _ = request(
        base, "/api/podcasts", "POST",
        json.dumps({"noteId": note["noteId"], "optionId": "not_a_format"}).encode(),
        {"Content-Type": "application/json"},
    )
    expect_detail(status, body, 400, "unknown optionId rejected")

    option_id = opts[0]["id"]
    payload = json.dumps({"noteId": note["noteId"], "optionId": option_id}).encode()
    status, body, _ = request(base, "/api/podcasts", "POST", payload, {"Content-Type": "application/json"})
    if status == 202:
        ok("returns 202 for a queued job")
    else:
        bad("returns 202 for a queued job", f"got {status} (200 misreports a queued job as done)")
    if not isinstance(body, dict) or not body.get("id"):
        bad("returns an id", str(body)[:120])
        return report()
    podcast_id = body["id"]
    ok("returns an id")

    status, again, _ = request(base, "/api/podcasts", "POST", payload, {"Content-Type": "application/json"})
    if isinstance(again, dict) and again.get("id") == podcast_id:
        ok("same note and option return the same job id")
    else:
        bad("same note and option return the same job id",
            f"{podcast_id} then {again.get('id') if isinstance(again, dict) else again}")

    # ---- poll ----
    print(f"\nGET /api/podcasts/{podcast_id}")
    status, body, _ = request(base, "/api/podcasts/p_doesnotexist")
    expect_detail(status, body, 404, "unknown podcast id rejected")

    states, deadline, doc = set(), time.time() + (120 if fake else 600), None
    while time.time() < deadline:
        status, doc, _ = request(base, f"/api/podcasts/{podcast_id}")
        if status != 200 or not isinstance(doc, dict):
            bad("status is readable", f"{status} {str(doc)[:120]}")
            return report()
        states.add(doc.get("status"))
        if doc.get("status") in ("ready", "failed"):
            break
        time.sleep(1)

    known = {"queued", "writing", "recording", "mixing", "ready", "failed"}
    if states <= known:
        ok(f"states seen are all known: {', '.join(sorted(states))}")
    else:
        bad("states are from the known set", f"unexpected: {sorted(states - known)}")

    if doc.get("status") == "failed":
        bad("job reached ready", f'failed: {doc.get("error")}')
        return report()
    if doc.get("status") != "ready":
        bad("job reached ready", f'still {doc.get("status")} when time ran out')
        return report()
    ok("job reached ready")

    for key in ("id", "noteId", "optionId", "title", "format", "script", "seconds", "audioUrl"):
        if key in doc:
            ok(f"ready status has {key}")
        else:
            bad(f"ready status has {key}")

    script = doc.get("script") or []
    if script and all(isinstance(l.get("host"), str) and isinstance(l.get("text"), str) for l in script):
        ok(f"{len(script)} script lines with host and text")
    else:
        bad("script lines have host and text", str(script)[:160])
    bad_source = [l.get("source") for l in script if l.get("source") not in (None, "notes", "added")]
    if bad_source:
        bad("source is notes or added", f"got {bad_source}")
    else:
        labelled = sum(1 for l in script if l.get("source"))
        ok(f"source values valid ({labelled}/{len(script)} labelled; missing means notes)")

    if doc.get("audioUrl") == f"/api/podcasts/{podcast_id}/audio.mp3":
        ok("audioUrl matches the documented path")
    else:
        bad("audioUrl matches the documented path", f'got {doc.get("audioUrl")!r}')

    # ---- audio ----
    print(f"\nGET /api/podcasts/{podcast_id}/audio.mp3")
    status, body, headers = request(base, f"/api/podcasts/{podcast_id}/audio.mp3")
    ctype_hdr = (headers.get("Content-Type") or headers.get("content-type") or "").lower()
    if status == 200 and "audio/mpeg" in ctype_hdr:
        ok(f"serves audio/mpeg ({len(body)} bytes)")
    else:
        bad("serves audio/mpeg", f"{status} {ctype_hdr}")
    disp = (headers.get("Content-Disposition") or headers.get("content-disposition") or "").lower()
    if "inline" in disp or not disp:
        ok("plain request is inline")
    else:
        bad("plain request is inline", disp)

    status, _, headers = request(base, f"/api/podcasts/{podcast_id}/audio.mp3?download=true")
    disp = (headers.get("Content-Disposition") or headers.get("content-disposition") or "").lower()
    if status == 200 and "attachment" in disp:
        ok("download=true is an attachment")
    else:
        bad("download=true is an attachment", f"{status} {disp!r}")
    if ".mp3" in disp:
        ok("attachment has an .mp3 filename")
    else:
        bad("attachment has an .mp3 filename", disp or "(no header)")

    status, body, _ = request(base, "/api/podcasts/p_doesnotexist/audio.mp3")
    expect_detail(status, body, 404, "audio for an unknown id rejected")

    return report()


def report() -> int:
    print(f"\n{'=' * 56}")
    print(f"{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print(f"  - {f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"))
