// Study Buddy frontend <-> Flask backend (app.py)
// Endpoints: POST /api/note (photo), POST /api/ask, POST /api/speak, GET /audio/<name>
(() => {
  const $ = (id) => document.getElementById(id);
  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  };
  const store = {
    get(k, d) { try { const v = localStorage.getItem("sb:" + k); return v ? JSON.parse(v) : d; } catch { return d; } },
    set(k, v) { try { localStorage.setItem("sb:" + k, JSON.stringify(v)); } catch {} },
  };

  // ---------- state ----------
  // source: {id, name, status: 'reading'|'done'|'error', text, spoken, audio, photo, use, error}
  let sources = store.get("sources", []).filter((s) => s.status === "done");
  let notes = store.get("notes", []);
  let book = store.get("book", null); // {audio, key, voice}
  let busy = false;
  const queue = [];
  const save = () => {
    store.set("sources", sources.filter((s) => s.status === "done").map(({ photo, file, ...s }) => s));
    store.set("notes", notes);
    store.set("book", book);
  };

  async function api(path, opts) {
    const res = await fetch(path, opts);
    let data = null;
    try { data = await res.json(); } catch {}
    if (!res.ok) throw new Error((data && data.error) || `Server error ${res.status}`);
    return data;
  }
  const postJSON = (path, body) =>
    api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

  function toast(msg) {
    const t = el("div", "toast", msg);
    t.setAttribute("role", "status");
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 2200);
  }

  const used = () => sources.filter((s) => s.status === "done" && s.use);
  const unclearCount = (t) => (t.match(/\[unclear\]/gi) || []).length;
  const notesText = () => used().map((s, i) => `[Source ${i + 1}: ${s.name}]\n${s.text}`).join("\n\n");

  // ---------- mobile tabs ----------
  function showTab(tab) {
    $("panels").dataset.mobileTab = tab;
    document.querySelectorAll(".mobile-tabs button").forEach((b) => {
      const on = b.dataset.tab === tab;
      b.classList.toggle("is-active", on);
      b.setAttribute("aria-pressed", on);
    });
  }
  document.querySelectorAll(".mobile-tabs button").forEach((b) => (b.onclick = () => showTab(b.dataset.tab)));

  // ---------- sources ----------
  function renderSources() {
    const list = $("sourceList");
    list.textContent = "";
    if (!sources.length) list.appendChild(el("li", "empty", "No pages yet. Add a photo of your handwritten notes to begin."));
    sources.forEach((s) => {
      const li = el("li", "source-row");
      const open = el("button", "source-open");
      open.type = "button";
      open.disabled = s.status !== "done";
      open.onclick = () => openSource(s);
      const thumb = el("span", "paper-thumb");
      thumb.setAttribute("aria-hidden", "true");
      if (s.photo) Object.assign(thumb.style, { background: `center/cover url(${s.photo})` });
      const meta = el("span", "source-meta");
      meta.appendChild(el("span", "source-name", s.name));
      let chip;
      if (s.status === "reading") chip = el("span", "chip chip-reading", s.queued ? "Waiting…" : "Reading handwriting…");
      else if (s.status === "error") chip = el("span", "chip chip-error", "Could not read");
      else {
        const n = unclearCount(s.text);
        chip = n ? el("span", "chip chip-unclear", `${n} unclear word${n > 1 ? "s" : ""}`) : el("span", "chip chip-transcribed", "Transcribed");
      }
      if (s.error) chip.title = s.error;
      meta.appendChild(chip);
      open.append(thumb, meta);
      li.appendChild(open);
      if (s.status === "done") {
        const cb = el("input");
        cb.type = "checkbox";
        cb.checked = s.use;
        cb.setAttribute("aria-label", `Use ${s.name} in answers`);
        cb.onchange = () => { s.use = cb.checked; save(); renderAll(); };
        li.appendChild(cb);
      }
      if (s.status === "error" && s.file) {
        const retry = el("button", "btn btn-ghost", "Try again");
        retry.type = "button";
        retry.setAttribute("aria-label", `Try reading ${s.name} again`);
        retry.onclick = () => {
          Object.assign(s, { status: "reading", queued: true, error: null });
          queue.push({ s, file: s.file });
          renderAll();
          pump();
        };
        li.appendChild(retry);
      }
      if (s.status !== "reading") {
        const rm = el("button", "remove");
        rm.type = "button";
        rm.setAttribute("aria-label", `Remove ${s.name}`);
        rm.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>';
        rm.onclick = () => { sources = sources.filter((x) => x !== s); save(); renderAll(); };
        li.appendChild(rm);
      }
      list.appendChild(li);
    });
    const done = sources.filter((s) => s.status === "done").length;
    $("sourceCount").textContent = `${done} page${done === 1 ? "" : "s"}`;
    $("toggleAll").checked = done > 0 && used().length === done;
  }
  $("toggleAll").onchange = (e) => {
    sources.forEach((s) => { if (s.status === "done") s.use = e.target.checked; });
    save(); renderAll();
  };

  let detailSource = null;
  function openSource(s) {
    detailSource = s;
    $("detailName").textContent = s.name;
    $("sourcesList").hidden = true;
    $("sourceDetail").hidden = false;
    setDetailView("text");
  }
  function setDetailView(v) {
    const s = detailSource;
    document.querySelectorAll("#sourceDetail .segmented button").forEach((b) => {
      const on = b.dataset.view === v;
      b.classList.toggle("is-active", on);
      b.setAttribute("aria-pressed", on);
      if (b.dataset.view === "photo") b.disabled = !s.photo;
    });
    $("detailPaper").hidden = v === "photo";
    $("detailPhoto").hidden = v !== "photo";
    if (v === "photo") { $("detailPhoto").src = s.photo; $("detailPhoto").alt = `Photo of ${s.name}`; }
    $("detailText").textContent = v === "spoken" ? s.spoken : s.text;
    $("detailHint").textContent = v === "spoken"
      ? "This is the rewritten version the audiobook reads, with symbols and shorthand spelled out."
      : v === "photo" ? "The photo you added." : "Check this against your page. Words the AI could not read are marked [unclear].";
    const n = unclearCount(s.text);
    $("detailCallout").hidden = !(v === "text" && n);
    $("detailCallout").textContent = `${n} word${n > 1 ? "s" : ""} could not be read. Answers will not use them, so check them against your page.`;
  }
  document.querySelectorAll("#sourceDetail .segmented button").forEach((b) => (b.onclick = () => setDetailView(b.dataset.view)));
  $("detailBack").onclick = () => { $("sourceDetail").hidden = true; $("sourcesList").hidden = false; };

  // upload
  const pick = () => { showTab("sources"); $("fileInput").click(); };
  $("dropzone").onclick = pick;
  $("guideAdd").onclick = pick;
  $("fileInput").onchange = (e) => { addFiles(e.target.files); e.target.value = ""; };
  const dz = $("dropzone");
  ["dragenter", "dragover"].forEach((t) => dz.addEventListener(t, (e) => { e.preventDefault(); dz.classList.add("is-over"); }));
  ["dragleave", "drop"].forEach((t) => dz.addEventListener(t, () => dz.classList.remove("is-over")));
  dz.addEventListener("drop", (e) => { e.preventDefault(); addFiles(e.dataTransfer.files); });

  function addFiles(files) {
    [...files].filter((f) => f.type.startsWith("image/")).forEach((file) => {
      const s = {
        id: Math.random().toString(36).slice(2),
        name: file.name.replace(/\.[^.]+$/, ""),
        status: "reading", queued: true, use: true, text: "", spoken: "",
        photo: URL.createObjectURL(file),
      };
      sources.push(s);
      queue.push({ s, file });
    });
    renderAll();
    pump();
  }

  // One photo at a time, so the free Gemini tier is not hammered.
  let pumping = false;
  async function pump() {
    if (pumping) return;
    pumping = true;
    while (queue.length) {
      const { s, file } = queue.shift();
      s.queued = false;
      renderSources();
      const fd = new FormData();
      fd.append("photo", file);
      fd.append("voice", $("voice").value);
      try {
        const data = await api("/api/note", { method: "POST", body: fd });
        Object.assign(s, { status: "done", text: data.text, spoken: data.spoken, audio: data.audio });
        // The audiobook covers every page in use; with a single page we already have its audio.
        if (used().length === 1 && used()[0] === s) book = { audio: data.audio, key: bookKey(), voice: $("voice").value };
      } catch (err) {
        Object.assign(s, { status: "error", error: err.message, file });
        toast(err.message);
      }
      save();
      renderAll();
    }
    pumping = false;
  }

  // ---------- chat ----------
  function scrollChat() { const c = $("chatScroll"); c.scrollTop = c.scrollHeight; }

  async function ask(question, opts = {}) {
    if (busy) return;
    if (!used().length) { toast("Add a photo of your notes first"); return; }
    showTab("chat");
    busy = true; renderComposer();
    const col = $("chatColumn");
    col.appendChild(el("div", "bubble-user", question));
    const pending = el("div", "bubble-pending", "Reading your notes…");
    col.appendChild(pending);
    scrollChat();
    const cited = used();
    try {
      const data = await postJSON("/api/ask", { text: notesText(), question, quiz: !!opts.quiz, speak: false });
      pending.replaceWith(renderAnswer(question, data.answer, cited));
    } catch (err) {
      pending.replaceWith(el("div", "bubble-error", "Something went wrong: " + err.message.slice(0, 200)));
    }
    busy = false; renderComposer();
    scrollChat();
  }

  function renderAnswer(question, answer, cited) {
    const wrap = el("div", "answer");
    wrap.appendChild(el("p", "prose", answer));
    const actions = el("div", "answer-actions");
    cited.forEach((s, i) => {
      const c = el("button", "cite", String(i + 1));
      c.type = "button";
      c.setAttribute("aria-label", `Open source: ${s.name}`);
      c.title = s.name;
      c.onclick = () => { showTab("sources"); openSource(s); };
      actions.appendChild(c);
    });
    actions.appendChild(el("span", "spacer"));

    const read = el("button", "btn btn-ghost");
    read.type = "button";
    read.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11 5L6 9H2v6h4l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14"/></svg><span>Read aloud</span>';
    let audioUrl = null, player = null;
    read.onclick = async () => {
      const label = read.querySelector("span");
      if (player && !player.paused) { player.pause(); label.textContent = "Read aloud"; return; }
      if (!audioUrl) {
        read.disabled = true; label.textContent = "Recording…";
        try { audioUrl = (await postJSON("/api/speak", { text: answer, voice: $("voice").value })).audio; }
        catch (err) { toast("Could not make audio"); read.disabled = false; label.textContent = "Read aloud"; return; }
        read.disabled = false;
        player = new Audio(audioUrl);
        player.onended = () => (label.textContent = "Read aloud");
      }
      $("audio").pause();
      player.playbackRate = rate;
      player.play();
      label.textContent = "Stop";
    };

    const keep = el("button", "btn btn-ghost");
    keep.type = "button";
    keep.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg><span>Save to note</span>';
    keep.onclick = () => {
      addNote(question, answer, "Saved from chat");
      keep.disabled = true; keep.querySelector("span").textContent = "Saved";
    };
    actions.append(read, keep);
    wrap.appendChild(actions);
    return wrap;
  }

  function renderComposer() {
    const n = used().length;
    $("composerCount").textContent = `${n} source${n === 1 ? "" : "s"}`;
    const off = busy || !n;
    $("sendBtn").disabled = off;
    document.querySelectorAll("[data-q],[data-quiz]").forEach((b) => (b.disabled = off));
  }

  $("composer").onsubmit = (e) => {
    e.preventDefault();
    const q = $("ask").value.trim();
    if (!q) return;
    $("ask").value = "";
    ask(q);
  };
  $("ask").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("composer").requestSubmit(); }
  });
  document.querySelectorAll("[data-q]").forEach((b) => (b.onclick = () => ask(b.dataset.q)));
  document.querySelectorAll("[data-quiz]").forEach((b) => (b.onclick = () => ask("Quiz me with three questions.", { quiz: true })));

  // voice input (browser speech recognition, when available)
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { $("micBtn").disabled = true; $("micBtn").title = "Voice input is not supported in this browser"; }
  else {
    let rec = null;
    $("micBtn").onclick = () => {
      if (rec) { rec.stop(); return; }
      rec = new SR();
      rec.lang = "en-US";
      rec.interimResults = true;
      $("micBtn").classList.add("recording");
      $("micBtn").setAttribute("aria-label", "Stop listening");
      rec.onresult = (e) => { $("ask").value = [...e.results].map((r) => r[0].transcript).join(""); };
      rec.onend = () => {
        rec = null;
        $("micBtn").classList.remove("recording");
        $("micBtn").setAttribute("aria-label", "Ask by voice");
        if ($("ask").value.trim()) $("composer").requestSubmit();
      };
      rec.start();
    };
  }

  // ---------- audiobook ----------
  const audio = $("audio");
  let rate = 1;
  const fmt = (t) => (isFinite(t) ? `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}` : "0:00");
  const bookKey = () => used().map((s) => s.id).join(",") + "|" + $("voice").value;

  function renderPlayer() {
    const pages = used();
    const fresh = book && book.key === bookKey();
    $("playerTitle").textContent = pages.length ? (pages.length === 1 ? pages[0].name : "Your notes") : "No audiobook yet";
    $("playBtn").disabled = !fresh;
    $("guideListen").disabled = !fresh;
    $("regenBtn").disabled = !pages.length || making;
    const dl = $("downloadBtn");
    if (fresh) { dl.href = book.audio; dl.removeAttribute("aria-disabled"); dl.style.pointerEvents = ""; dl.style.opacity = ""; }
    else { dl.removeAttribute("href"); dl.setAttribute("aria-disabled", "true"); dl.style.pointerEvents = "none"; dl.style.opacity = ".5"; }
    if (fresh && !audio.src.endsWith(book.audio)) audio.src = book.audio;
    if (!fresh && !audio.paused) audio.pause();
    $("playerSub").textContent = !pages.length ? "Add a photo to make one"
      : `${pages.length} page${pages.length > 1 ? "s" : ""}` + (fresh && audio.duration ? ` · ${fmt(audio.duration)}` : "");
    if (!making) $("playerStatus").textContent = pages.length && !fresh ? "Press the regenerate button to record these pages with this voice." : "";
  }

  let making = false;
  $("regenBtn").onclick = async () => {
    const pages = used();
    if (!pages.length || making) return;
    making = true; renderPlayer();
    $("playerStatus").textContent = "Recording the audiobook… this can take a minute.";
    const key = bookKey();
    try {
      const data = await postJSON("/api/speak", { text: pages.map((s) => s.spoken).join("\n\n"), voice: $("voice").value });
      book = { audio: data.audio, key, voice: $("voice").value };
      save();
    } catch (err) { toast("Could not record the audiobook"); }
    making = false; renderPlayer();
  };
  $("voice").onchange = () => { store.set("voice", $("voice").value); renderPlayer(); };

  function setPlaying(on) {
    $("playBtn").setAttribute("aria-label", on ? "Pause audiobook" : "Play audiobook");
    $("playIcon").innerHTML = on ? '<path d="M6 4h4v16H6zM14 4h4v16h-4z"/>' : '<path d="M7 4l13 8-13 8z"/>';
  }
  $("playBtn").onclick = () => (audio.paused ? audio.play() : audio.pause());
  $("guideListen").onclick = () => { showTab("studio"); audio.play(); };
  $("back15").onclick = () => (audio.currentTime = Math.max(0, audio.currentTime - 15));
  $("fwd15").onclick = () => (audio.currentTime = Math.min(audio.duration || 0, audio.currentTime + 15));
  audio.onplay = () => setPlaying(true);
  audio.onpause = audio.onended = () => setPlaying(false);
  audio.onloadedmetadata = () => { $("timeTotal").textContent = fmt(audio.duration); audio.playbackRate = rate; renderPlayer(); };
  audio.ontimeupdate = () => {
    const pct = audio.duration ? (audio.currentTime / audio.duration) * 100 : 0;
    $("progressFill").style.width = pct + "%";
    $("progress").setAttribute("aria-valuenow", Math.round(pct));
    $("timeNow").textContent = fmt(audio.currentTime);
  };
  $("progress").onclick = (e) => {
    if (!audio.duration) return;
    const r = e.currentTarget.getBoundingClientRect();
    audio.currentTime = ((e.clientX - r.left) / r.width) * audio.duration;
  };
  document.querySelectorAll("#speeds button").forEach((b) => (b.onclick = () => {
    rate = +b.dataset.rate;
    audio.playbackRate = rate;
    document.querySelectorAll("#speeds button").forEach((x) => {
      x.classList.toggle("is-active", x === b);
      x.setAttribute("aria-pressed", x === b);
    });
  }));

  // ---------- saved notes ----------
  function addNote(title, body, origin) {
    notes.unshift({ id: Date.now(), title: title.slice(0, 80), body, origin });
    save(); renderNotes();
    toast("Saved to notes");
  }
  function renderNotes() {
    const list = $("savedList");
    list.textContent = "";
    if (!notes.length) list.appendChild(el("div", "muted small", "Answers you save show up here."));
    notes.forEach((n) => {
      const card = el("div", "saved-note");
      card.append(el("strong", null, n.title), el("p", null, n.body), el("span", "muted small", n.origin));
      const row = el("div", "row");
      const del = el("button", "btn btn-ghost", "Delete");
      del.type = "button";
      del.setAttribute("aria-label", `Delete note ${n.title}`);
      del.onclick = () => { notes = notes.filter((x) => x !== n); save(); renderNotes(); };
      row.appendChild(del);
      card.appendChild(row);
      list.appendChild(card);
    });
  }
  $("addNoteBtn").onclick = () => { $("noteForm").hidden = false; $("addNoteBtn").hidden = true; $("noteText").focus(); };
  $("noteCancel").onclick = () => { $("noteForm").hidden = true; $("addNoteBtn").hidden = false; $("noteText").value = ""; };
  $("noteForm").onsubmit = (e) => {
    e.preventDefault();
    const t = $("noteText").value.trim();
    if (!t) return;
    addNote(t.split("\n")[0], t, "Written by you");
    $("noteCancel").onclick();
  };

  // ---------- header / guide ----------
  $("shareBtn").onclick = async () => {
    try { await navigator.clipboard.writeText(location.href); toast("Link copied"); }
    catch { toast(location.href); }
  };
  function renderGuide() {
    const pages = used();
    const title = pages.length === 1 ? pages[0].name : pages.length ? "Your notes" : "Start with a photo";
    $("guideTitle").textContent = title;
    $("notebookTitle").textContent = pages.length ? title : "My notes";
    $("guideSummary").textContent = pages.length
      ? `${pages.length} page${pages.length > 1 ? "s" : ""} ready. Ask anything below, or try a study tool. Answers come only from what is written on your pages.`
      : "Add a photo of a handwritten page. Study Buddy reads it, turns it into an audiobook, and answers questions using only what is on your page.";
  }

  function renderAll() { renderSources(); renderComposer(); renderPlayer(); renderGuide(); }

  const v = store.get("voice", null);
  if (v) $("voice").value = v;
  renderAll();
  renderNotes();
})();
