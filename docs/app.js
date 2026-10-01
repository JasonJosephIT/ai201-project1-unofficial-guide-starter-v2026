// The Unofficial Guide — static front end for serve.py.
//
// This page does no retrieval or generation itself. It calls two routes on the
// backend (serve.py): GET /health to see which corpora are indexed, and
// POST /ask to run a question through app.py::ask_pipeline. Everything it
// shows — answer, gate decision, sources, chunks — comes back in that reply.

(() => {
  "use strict";

  const DEFAULT_API = "http://localhost:5000";
  const STORE = { api: "ug.api", corpus: "ug.corpus" };

  // A few questions per corpus to start from. campus_life's are the ones in
  // questions.py; the last one in each list is deliberately out of scope, so
  // you can watch the gate refuse.
  const EXAMPLES = {
    campus_life: [
      "How much does an official transcript cost?",
      "What time does Halden Hall close?",
      "Which courses drop your lowest midterm?",
      "Is the housing lottery random?",
      "What is the capital of Mongolia?",
    ],
    advice_threads: [
      "Which meal plan tier should I get?",
      "Is a parking permit worth it?",
      "How much RAM do I need for CS courses?",
      "Who won the 1994 World Cup?",
    ],
    city_guides: [
      "How do I get to Brightwater by train?",
      "Which towns are hard to get around with limited mobility?",
      "When is the best time to visit Brightwater?",
      "How do I write a for loop in Rust?",
    ],
    practice: [
      "How does scoring work in Harbourmaster?",
      "What does the market row cost?",
      "Can five people play?",
    ],
  };

  const $ = (sel) => document.querySelector(sel);
  const els = {
    status: $("#status"),
    statusText: $("#status-text"),
    settings: $("#settings"),
    settingsForm: $("#settings-form"),
    apiUrl: $("#api-url"),
    healthDetail: $("#health-detail"),
    corpora: $("#corpora"),
    askForm: $("#ask-form"),
    question: $("#question"),
    askBtn: $("#ask-btn"),
    examples: $("#examples"),
    thread: $("#thread"),
    empty: $("#empty"),
    template: $("#turn-template"),
  };

  const state = {
    api: DEFAULT_API,
    corpora: [],
    corpus: null,
    threshold: null,
    connected: false,
    busy: false,
  };

  // ─── Storage (may be unavailable in private windows) ─────────────────────

  function load(key) {
    try { return localStorage.getItem(key); } catch { return null; }
  }
  function save(key, value) {
    try { localStorage.setItem(key, value); } catch { /* not fatal */ }
  }

  function normaliseApi(url) {
    return (url || "").trim().replace(/\/+$/, "");
  }

  function initialApi() {
    const fromQuery = new URLSearchParams(location.search).get("api");
    return normaliseApi(fromQuery || load(STORE.api) || DEFAULT_API);
  }

  // ─── Network ─────────────────────────────────────────────────────────────

  async function request(path, options = {}, timeoutMs = 60000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetch(state.api + path, { ...options, signal: controller.signal });
      let body = null;
      try { body = await res.json(); } catch { /* non-JSON reply */ }
      if (!res.ok) {
        const message = (body && body.error) || `The backend replied ${res.status} ${res.statusText}.`;
        throw Object.assign(new Error(message), { kind: "http" });
      }
      return body;
    } catch (err) {
      if (err.kind === "http") throw err;
      const reason = err.name === "AbortError" ? "timed out" : "could not be reached";
      throw Object.assign(
        new Error(`The backend at ${state.api} ${reason}. Is \`python serve.py\` running, and is the URL right?`),
        { kind: "network" }
      );
    } finally {
      clearTimeout(timer);
    }
  }

  // ─── Health and corpora ──────────────────────────────────────────────────

  function setStatus(kind, text) {
    els.status.dataset.state = kind;
    els.statusText.textContent = text;
  }

  function toggleSettings(open) {
    const show = open ?? els.settings.hidden;
    els.settings.hidden = !show;
    els.status.setAttribute("aria-expanded", String(show));
    if (show) els.apiUrl.focus();
  }

  async function checkHealth() {
    setStatus("", "Connecting…");
    els.healthDetail.textContent = "";
    try {
      const health = await request("/health", {}, 8000);
      state.connected = true;
      state.threshold = health.threshold ?? null;
      state.corpora = health.corpora && health.corpora.length
        ? health.corpora
        : [{ name: health.corpus, blurb: "", index_ready: health.index_ready }];

      const saved = load(STORE.corpus);
      const pick = [saved, health.corpus].find(
        (name) => state.corpora.some((c) => c.name === name && c.index_ready)
      ) || (state.corpora.find((c) => c.index_ready) || state.corpora[0]).name;
      state.corpus = pick;

      renderCorpora();
      updateReadiness();
      els.healthDetail.textContent = `Connected to ${state.api}.`;
    } catch (err) {
      state.connected = false;
      state.corpora = [];
      renderCorpora();
      setStatus("down", "Backend offline");
      els.healthDetail.textContent = err.message;
      toggleSettings(true);
    }
    updateAskButton();
  }

  function updateReadiness() {
    const current = state.corpora.find((c) => c.name === state.corpus);
    if (!current) return;
    if (current.index_ready) {
      setStatus("ok", `Connected · ${current.name}`);
    } else {
      setStatus("warn", `${current.name} not indexed`);
      els.healthDetail.textContent =
        `No index for ${current.name} yet. Run: python app.py index --corpus ${current.name}`;
    }
  }

  function renderCorpora() {
    els.corpora.replaceChildren();
    if (!state.corpora.length) {
      const p = document.createElement("p");
      p.className = "hint";
      p.textContent = "Connect to the backend to load corpora.";
      els.corpora.append(p);
      renderExamples();
      return;
    }
    for (const c of state.corpora) {
      const label = document.createElement("label");
      label.className = "corpus";
      label.dataset.ready = String(Boolean(c.index_ready));

      const input = document.createElement("input");
      input.type = "radio";
      input.name = "corpus";
      input.value = c.name;
      input.checked = c.name === state.corpus;
      input.disabled = !c.index_ready;
      input.addEventListener("change", () => {
        state.corpus = c.name;
        save(STORE.corpus, c.name);
        updateReadiness();
        renderExamples();
      });

      const name = document.createElement("span");
      name.className = "corpus-name";
      name.textContent = c.name;

      const meta = document.createElement("span");
      meta.className = "corpus-meta";
      const parts = [];
      if (c.strategy) parts.push(`${c.strategy} chunks`);
      if (c.top_k) parts.push(`top-${c.top_k}`);
      parts.push(c.index_ready ? "indexed" : "not indexed");
      meta.textContent = parts.join(" · ");
      if (c.blurb) label.title = c.blurb;

      label.append(input, name, meta);
      els.corpora.append(label);
    }
    renderExamples();
  }

  function renderExamples() {
    els.examples.replaceChildren();
    for (const q of EXAMPLES[state.corpus] || []) {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "chip";
      chip.textContent = q;
      chip.addEventListener("click", () => {
        els.question.value = q;
        els.question.focus();
      });
      els.examples.append(chip);
    }
  }

  function updateAskButton() {
    const current = state.corpora.find((c) => c.name === state.corpus);
    els.askBtn.disabled = state.busy || !state.connected || !(current && current.index_ready);
    els.askBtn.textContent = state.busy ? "Asking…" : "Ask";
  }

  // ─── Asking ──────────────────────────────────────────────────────────────

  function newTurn(question, corpus) {
    const node = els.template.content.firstElementChild.cloneNode(true);
    node.querySelector(".turn-question").textContent = question;
    node.querySelector(".corpus-tag").textContent = corpus;
    const badge = node.querySelector(".badge");
    badge.dataset.kind = "loading";
    badge.textContent = "Searching";
    const answer = node.querySelector(".answer");
    answer.classList.add("muted", "loading-dots");
    answer.textContent = "Retrieving chunks and checking the gate";
    node.querySelector(".gate").hidden = true;
    node.querySelector(".sources").hidden = true;
    node.querySelector(".chunks").hidden = true;
    els.empty.hidden = true;
    els.thread.prepend(node);
    return node;
  }

  function renderResult(node, data) {
    const refused = Boolean(data.refused);
    const badge = node.querySelector(".badge");
    badge.dataset.kind = refused ? "refused" : "answered";
    badge.textContent = refused ? "Refused" : "Answered";

    const answer = node.querySelector(".answer");
    answer.classList.remove("loading-dots");
    answer.classList.toggle("muted", refused);
    answer.classList.add("rendered");
    answer.replaceChildren(...renderMarkdown(data.answer || ""));

    renderGate(node.querySelector(".gate"), data);
    renderSources(node.querySelector(".sources"), data.sources || [], refused);
    renderChunks(node.querySelector(".chunks"), data);
  }

  // The model often answers in light markdown. Render **bold**, *italic*,
  // `code` and "- " lists by building DOM nodes — never innerHTML, so nothing
  // in an answer can inject markup into the page.
  function renderInline(text) {
    const out = [];
    const re = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)/g;
    let last = 0;
    for (const m of text.matchAll(re)) {
      if (m.index > last) out.push(document.createTextNode(text.slice(last, m.index)));
      const tok = m[0];
      const el = document.createElement(
        tok.startsWith("**") ? "strong" : tok.startsWith("`") ? "code" : "em"
      );
      el.textContent = tok.startsWith("**") ? tok.slice(2, -2) : tok.slice(1, -1);
      out.push(el);
      last = m.index + tok.length;
    }
    if (last < text.length) out.push(document.createTextNode(text.slice(last)));
    return out;
  }

  function renderMarkdown(text) {
    const blocks = [];
    for (const para of text.trim().split(/\n\s*\n/)) {
      const lines = para.split("\n");
      if (lines.every((l) => /^\s*(?:[-*•]|\d+[.)])\s+/.test(l))) {
        const ordered = /^\s*\d/.test(lines[0]);
        const list = document.createElement(ordered ? "ol" : "ul");
        for (const l of lines) {
          const li = document.createElement("li");
          li.append(...renderInline(l.replace(/^\s*(?:[-*•]|\d+[.)])\s+/, "")));
          list.append(li);
        }
        blocks.push(list);
      } else {
        const p = document.createElement("p");
        lines.forEach((l, i) => {
          if (i) p.append(document.createElement("br"));
          p.append(...renderInline(l));
        });
        blocks.push(p);
      }
    }
    return blocks;
  }

  function renderGate(gate, data) {
    const best = Number(data.best_distance);
    const cutoff = Number(data.threshold);
    if (!Number.isFinite(best) || !Number.isFinite(cutoff)) { gate.hidden = true; return; }
    gate.hidden = false;
    const passed = !data.refused;
    gate.dataset.passed = String(passed);
    const pct = (v) => `${Math.max(0, Math.min(1, v)) * 100}%`;
    gate.querySelector(".gate-pass").style.width = pct(cutoff);
    gate.querySelector(".gate-cutoff").style.left = pct(cutoff);
    gate.querySelector(".gate-marker").style.left = pct(best);
    gate.querySelector(".gate-numbers").textContent =
      `closest ${best.toFixed(3)} ${passed ? "≤" : ">"} cutoff ${cutoff} · ${passed ? "passed" : "refused"}`;
  }

  function renderSources(box, sources, refused) {
    box.replaceChildren();
    if (refused || !sources.length) { box.hidden = true; return; }
    box.hidden = false;
    const label = document.createElement("span");
    label.className = "sources-label";
    label.textContent = "Sources";
    box.append(label);
    for (const s of sources) {
      const tag = document.createElement("span");
      tag.className = "source";
      tag.textContent = s;
      box.append(tag);
    }
  }

  function renderChunks(details, data) {
    const chunks = data.chunks || [];
    if (!chunks.length) { details.hidden = true; return; }
    details.hidden = false;
    const cutoff = Number(data.threshold);
    details.querySelector("summary").textContent =
      `Retrieved chunks (${chunks.length}${data.top_k ? ` · top-${data.top_k}` : ""})` +
      (data.refused ? " — none close enough to answer from" : "");
    const list = details.querySelector(".chunk-list");
    list.replaceChildren();
    for (const c of chunks) {
      const li = document.createElement("li");
      li.className = "chunk";

      const head = document.createElement("div");
      head.className = "chunk-head";
      const label = document.createElement("span");
      label.className = "chunk-label";
      label.textContent = c.label || c.source;
      const dist = document.createElement("span");
      dist.className = "chunk-dist";
      const d = Number(c.distance);
      dist.dataset.within = String(Number.isFinite(cutoff) ? d <= cutoff : true);
      dist.textContent = `distance ${Number.isFinite(d) ? d.toFixed(3) : "?"}`;
      head.append(label, dist);

      const bar = document.createElement("div");
      bar.className = "chunk-bar";
      bar.setAttribute("aria-hidden", "true");
      const fill = document.createElement("span");
      fill.style.width = `${Math.max(0, Math.min(1, 1 - d)) * 100}%`;
      bar.append(fill);

      const text = document.createElement("p");
      text.className = "chunk-text";
      text.textContent = c.text;

      li.append(head, bar, text);
      list.append(li);
    }
  }

  function renderError(node, err) {
    const badge = node.querySelector(".badge");
    badge.dataset.kind = "error";
    badge.textContent = "Error";
    const answer = node.querySelector(".answer");
    answer.classList.remove("loading-dots");
    answer.classList.add("muted");
    let message = err.message;
    if (/No index called/i.test(message)) {
      message += `\n\nBuild it with: python app.py index --corpus ${node.querySelector(".corpus-tag").textContent}`;
    }
    answer.textContent = message;
  }

  async function ask(question) {
    if (state.busy) return;
    state.busy = true;
    updateAskButton();
    const corpus = state.corpus;
    const node = newTurn(question, corpus);
    try {
      const data = await request("/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, corpus }),
      });
      renderResult(node, data);
    } catch (err) {
      renderError(node, err);
      if (err.kind === "network") {
        state.connected = false;
        setStatus("down", "Backend offline");
      }
    } finally {
      state.busy = false;
      updateAskButton();
    }
  }

  // ─── Wiring ──────────────────────────────────────────────────────────────

  els.status.addEventListener("click", () => toggleSettings());

  els.settingsForm.addEventListener("submit", (e) => {
    e.preventDefault();
    state.api = normaliseApi(els.apiUrl.value);
    save(STORE.api, state.api);
    checkHealth();
  });

  els.askForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const q = els.question.value.trim();
    if (!q) return;
    ask(q);
  });

  els.question.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      els.askForm.requestSubmit();
    }
  });

  state.api = initialApi();
  els.apiUrl.value = state.api;
  renderCorpora();
  updateAskButton();
  checkHealth();
})();
