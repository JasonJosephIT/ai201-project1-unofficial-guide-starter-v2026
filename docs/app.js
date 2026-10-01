// The Unofficial Guide — front end, in two modes.
//
// Backend mode calls serve.py: GET /health to see which corpora are indexed,
// and POST /ask to run a question through app.py::ask_pipeline.
//
// Static mode needs no server, which is what lets the page run on GitHub
// Pages. GitHub Actions runs the real Python pipeline at build time and writes
// every chunk and its vector to data/ (tools/export_static_index.py). The
// browser then embeds the question with the same MiniLM model, finds the
// nearest chunks, applies the same relevance gate, and either calls Gemini
// with a key the visitor pastes in or shows a retrieval-only answer. The
// cutoff, refusal text, grounding instruction and prompt template all come
// from data/manifest.json, so none of them is typed in here a second time.
//
// Both modes hand renderResult the same shape /ask returns.

(() => {
  "use strict";

  const DEFAULT_API = "http://localhost:5000";
  const STORE = {
    api: "ug.api",
    corpus: "ug.corpus",
    mode: "ug.mode",
    key: "ug.geminiKey",
  };

  // How the browser embeds a question. tools/check_static_parity.mjs reads
  // these two constants out of this file and checks the distances they give
  // against store.search, so change them here and re-run it. fp32, not the
  // default quantised model: quantising moves distances enough to push
  // questions across the cutoff.
  const TRANSFORMERS_VERSION = "3.8.1";
  const EMBED = { model: "Xenova/all-MiniLM-L6-v2", dtype: "fp32", pooling: "mean", normalize: true };

  const GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models";

  // A few questions per corpus to start from. The last one in each list is
  // deliberately out of scope, so you can watch the gate refuse.
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
    modeInputs: document.querySelectorAll('input[name="mode"]'),
    backendSettings: $("#backend-settings"),
    staticSettings: $("#static-settings"),
    settingsForm: $("#settings-form"),
    apiUrl: $("#api-url"),
    useStatic: $("#use-static"),
    keyForm: $("#key-form"),
    keyInput: $("#gemini-key"),
    forgetKey: $("#forget-key"),
    keyStatus: $("#key-status"),
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
    mode: "backend",
    api: DEFAULT_API,
    corpora: [],
    corpus: null,
    threshold: null,
    connected: false,
    busy: false,
    manifest: null,
  };

  // ─── Storage (may be unavailable in private windows) ─────────────────────

  function load(key) {
    try { return localStorage.getItem(key); } catch { return null; }
  }
  function save(key, value) {
    try { localStorage.setItem(key, value); } catch { /* not fatal */ }
  }
  function forget(key) {
    try { localStorage.removeItem(key); } catch { /* not fatal */ }
  }

  function normaliseApi(url) {
    return (url || "").trim().replace(/\/+$/, "");
  }

  function initialApi() {
    const fromQuery = new URLSearchParams(location.search).get("api");
    return normaliseApi(fromQuery || load(STORE.api) || DEFAULT_API);
  }

  // ?api= always means backend. Otherwise a mode chosen earlier in this
  // browser wins, and a first visit to *.github.io starts in static mode.
  function initialMode() {
    const params = new URLSearchParams(location.search);
    if (params.get("api")) return "backend";
    const asked = params.get("mode") || load(STORE.mode);
    if (asked === "static" || asked === "backend") return asked;
    return location.hostname.endsWith(".github.io") ? "static" : "backend";
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

  async function fetchJson(path) {
    const res = await fetch(path, { cache: "no-cache" });
    if (!res.ok) throw new Error(`${path}: ${res.status} ${res.statusText}`);
    return res.json();
  }

  // ─── Status, settings and modes ──────────────────────────────────────────

  function setStatus(kind, text) {
    els.status.dataset.state = kind;
    els.statusText.textContent = text;
  }

  function toggleSettings(open) {
    const show = open ?? els.settings.hidden;
    els.settings.hidden = !show;
    els.status.setAttribute("aria-expanded", String(show));
    if (show) (state.mode === "static" ? els.keyInput : els.apiUrl).focus();
  }

  function setMode(mode) {
    state.mode = mode;
    for (const input of els.modeInputs) input.checked = input.value === mode;
    els.backendSettings.hidden = mode !== "backend";
    els.staticSettings.hidden = mode !== "static";
    els.useStatic.hidden = true;
    connect();
  }

  function connect() {
    return state.mode === "static" ? loadManifest() : checkHealth();
  }

  function pickCorpus(preferred) {
    const saved = load(STORE.corpus);
    return [saved, preferred].find(
      (name) => state.corpora.some((c) => c.name === name && c.index_ready)
    ) || (state.corpora.find((c) => c.index_ready) || state.corpora[0]).name;
  }

  async function checkHealth() {
    setStatus("", "Connecting…");
    els.healthDetail.textContent = "";
    try {
      const health = await request("/health", {}, 8000);
      if (state.mode !== "backend") return;
      state.connected = true;
      state.threshold = health.threshold ?? null;
      state.corpora = health.corpora && health.corpora.length
        ? health.corpora
        : [{ name: health.corpus, blurb: "", index_ready: health.index_ready }];
      state.corpus = pickCorpus(health.corpus);

      renderCorpora();
      updateReadiness();
      els.healthDetail.textContent = `Connected to ${state.api}.`;
    } catch (err) {
      if (state.mode !== "backend") return;
      state.connected = false;
      state.corpora = [];
      renderCorpora();
      setStatus("down", "Backend offline");
      els.healthDetail.textContent = err.message;
      els.useStatic.hidden = false;
      toggleSettings(true);
    }
    updateAskButton();
  }

  async function loadManifest() {
    setStatus("", "Loading index…");
    els.healthDetail.textContent = "";
    try {
      const manifest = state.manifest || await fetchJson("data/manifest.json");
      if (state.mode !== "static") return;
      state.manifest = manifest;
      state.connected = true;
      state.threshold = manifest.threshold;
      state.corpora = manifest.corpora.map((c) => ({ ...c, index_ready: true }));
      state.corpus = pickCorpus(manifest.default_corpus);

      renderCorpora();
      updateReadiness();
      const built = manifest.built_at ? new Date(manifest.built_at).toLocaleString() : "unknown";
      els.healthDetail.textContent =
        `Static index built ${built}${manifest.commit ? ` from ${manifest.commit.slice(0, 7)}` : ""}. ` +
        `Cutoff ${manifest.threshold}, answers from ${manifest.model} when a key is set.`;
    } catch (err) {
      if (state.mode !== "static") return;
      state.connected = false;
      state.corpora = [];
      renderCorpora();
      setStatus("down", "No static index");
      els.healthDetail.textContent =
        `Couldn't load data/manifest.json (${err.message}). Build it with ` +
        "`python tools/export_static_index.py`; GitHub Actions does this on every deploy.";
      toggleSettings(true);
    }
    updateAskButton();
  }

  function updateReadiness() {
    const current = state.corpora.find((c) => c.name === state.corpus);
    if (!current) return;
    if (state.mode === "static") {
      setStatus("ok", `Static · ${current.name}`);
    } else if (current.index_ready) {
      setStatus("ok", `Connected · ${current.name}`);
    } else {
      setStatus("warn", `${current.name} not indexed`);
      els.healthDetail.textContent =
        `No index for ${current.name} yet. Run: python app.py --corpus ${current.name} index`;
    }
  }

  function renderKeyStatus() {
    const saved = Boolean(load(STORE.key));
    els.keyStatus.textContent = saved
      ? "A key is saved in this browser. Answers are written by Gemini from the retrieved chunks."
      : "No key saved. Answers are retrieval-only: the closest passages, quoted.";
    els.forgetKey.disabled = !saved;
    els.keyInput.placeholder = saved ? "Key saved — paste a new one to replace it" : "Paste a Gemini API key (optional)";
  }

  function renderCorpora() {
    els.corpora.replaceChildren();
    if (!state.corpora.length) {
      const p = document.createElement("p");
      p.className = "hint";
      p.textContent = state.mode === "static"
        ? "The static index hasn't loaded."
        : "Connect to the backend to load corpora.";
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
      if (state.mode === "static") {
        if (c.chunks) parts.push(`${c.chunks} chunks`);
      } else {
        parts.push(c.index_ready ? "indexed" : "not indexed");
      }
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

  // ─── Static mode: embedding, retrieval, gate, answer ─────────────────────

  let extractorPromise = null;
  const indexCache = new Map();

  // Loaded on the first question, not on page load: it's ~90 MB the first
  // time, and the browser caches it after that.
  function getExtractor(onProgress) {
    if (!extractorPromise) {
      extractorPromise = (async () => {
        const { pipeline, env } = await import(
          `https://cdn.jsdelivr.net/npm/@huggingface/transformers@${TRANSFORMERS_VERSION}`
        );
        env.allowLocalModels = false;  // there is no /models/ folder on this site
        const files = new Map();
        return pipeline("feature-extraction", EMBED.model, {
          dtype: EMBED.dtype,
          progress_callback: (p) => {
            if (p.status !== "progress" || !p.total) return;
            files.set(p.file, p);
            let loaded = 0, total = 0;
            for (const f of files.values()) { loaded += f.loaded; total += f.total; }
            onProgress(loaded, total);
          },
        });
      })();
      extractorPromise.catch(() => { extractorPromise = null; });  // let a retry try again
    }
    return extractorPromise;
  }

  async function getIndex(corpus) {
    if (!indexCache.has(corpus)) {
      const entry = state.manifest.corpora.find((c) => c.name === corpus);
      const promise = fetchJson(`data/${entry.file}`).then((index) => {
        for (const c of index.chunks) {
          const bytes = Uint8Array.from(atob(c.v), (ch) => ch.charCodeAt(0));
          c.vec = new Float32Array(bytes.buffer);
          delete c.v;
        }
        return index;
      });
      promise.catch(() => indexCache.delete(corpus));
      indexCache.set(corpus, promise);
    }
    return indexCache.get(corpus);
  }

  // Vectors are unit length on both sides, so 1 − dot is Chroma's cosine
  // distance and the cutoff means what it means in Python.
  function searchIndex(index, q) {
    return index.chunks
      .map((c) => {
        let dot = 0;
        for (let i = 0; i < q.length; i++) dot += q[i] * c.vec[i];
        return { label: c.label, source: c.source, text: c.text, distance: 1 - dot };
      })
      .sort((a, b) => a.distance - b.distance)
      .slice(0, index.top_k);
  }

  // Fill {placeholders} in one pass, like tools/export_static_index.py does,
  // so a chunk that happens to contain "{question}" is left alone.
  function fill(template, values) {
    return template.replace(/\{(\w+)\}/g, (m, k) => (k in values ? values[k] : m));
  }

  function buildPrompt(question, chunks) {
    const t = state.manifest.prompt_template;
    const context = chunks.map((c) => fill(t.chunk, { source: c.source, text: c.text })).join(t.separator);
    return fill(t.prompt, { context, question });
  }

  async function askGemini(key, prompt) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 60000);
    try {
      const res = await fetch(
        `${GEMINI_ENDPOINT}/${encodeURIComponent(state.manifest.model)}:generateContent`,
        {
          method: "POST",
          // The key goes in a header, never the URL, and only to Google.
          headers: { "Content-Type": "application/json", "x-goog-api-key": key },
          body: JSON.stringify({
            systemInstruction: { parts: [{ text: state.manifest.grounding_instruction }] },
            contents: [{ role: "user", parts: [{ text: prompt }] }],
          }),
          referrerPolicy: "no-referrer",
          signal: controller.signal,
        }
      );
      let body = null;
      try { body = await res.json(); } catch { /* non-JSON reply */ }
      if (!res.ok) {
        throw new Error((body && body.error && body.error.message) || `Gemini replied ${res.status} ${res.statusText}.`);
      }
      const parts = body?.candidates?.[0]?.content?.parts || [];
      const text = parts.map((p) => p.text || "").join("").trim();
      if (!text) {
        const why = body?.promptFeedback?.blockReason || body?.candidates?.[0]?.finishReason || "no text";
        throw new Error(`Gemini returned no answer (${why}).`);
      }
      return text;
    } catch (err) {
      if (err.name === "AbortError") throw new Error("Gemini timed out after 60 seconds.");
      if (err instanceof TypeError) throw new Error("Couldn't reach Gemini. Check your connection.");
      throw err;
    } finally {
      clearTimeout(timer);
    }
  }

  // No key: quote the closest passages that cleared the cutoff, and say
  // plainly that nothing was generated.
  function retrievalOnly(chunks, threshold) {
    const quoted = chunks.filter((c) => c.distance < threshold).slice(0, 2);
    const answer = quoted
      .map((c) => `From **${c.source}** (distance ${c.distance.toFixed(3)}):\n\n${c.text}`)
      .join("\n\n");
    return { answer, sources: [...new Set(quoted.map((c) => c.source))].sort() };
  }

  async function askStatic(question, corpus, onProgress) {
    const { threshold, refusal } = state.manifest;

    onProgress("Loading the index");
    const index = await getIndex(corpus);

    const extractor = await getExtractor((loaded, total) => {
      const mb = (n) => (n / 1e6).toFixed(0);
      onProgress(`Loading the embedding model, once (${mb(loaded)} of ${mb(total)} MB; cached after this)`);
      setStatus("warn", `Loading model ${Math.round((100 * loaded) / total)}%`);
    });
    updateReadiness();
    onProgress("Retrieving chunks and checking the gate");
    const output = await extractor(question, { pooling: EMBED.pooling, normalize: EMBED.normalize });
    const chunks = searchIndex(index, output.data);

    const best = chunks.length ? chunks[0].distance : 1.0;
    const result = {
      question,
      refused: !(best < threshold),
      best_distance: best,
      threshold,
      top_k: index.top_k,
      chunking: index.chunking,
      sources: [],
      chunks,
    };
    if (result.refused) return { ...result, answer: refusal };

    const key = load(STORE.key);
    if (!key) {
      return {
        ...result,
        mode: "retrieval",
        ...retrievalOnly(chunks, threshold),
        note: "Retrieval-only: no Gemini key is set, so nothing was generated. Add one in settings for a written answer.",
      };
    }

    onProgress(`Asking ${state.manifest.model}`);
    try {
      const answer = await askGemini(key, buildPrompt(question, chunks));
      return { ...result, answer, sources: [...new Set(chunks.map((c) => c.source))].sort() };
    } catch (err) {
      return {
        ...result,
        mode: "retrieval",
        ...retrievalOnly(chunks, threshold),
        note: `Gemini call failed, so this is retrieval-only. ${err.message}`,
      };
    }
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
    node.querySelector(".answer-note").hidden = true;
    node.querySelector(".gate").hidden = true;
    node.querySelector(".sources").hidden = true;
    node.querySelector(".details").hidden = true;
    els.empty.hidden = true;
    els.thread.prepend(node);
    return node;
  }

  function renderResult(node, data) {
    const refused = Boolean(data.refused);
    const retrieval = data.mode === "retrieval";
    const badge = node.querySelector(".badge");
    badge.dataset.kind = refused ? "refused" : retrieval ? "retrieval" : "answered";
    badge.textContent = refused ? "Refused" : retrieval ? "Retrieval-only" : "Answered";

    const answer = node.querySelector(".answer");
    answer.classList.remove("loading-dots");
    answer.classList.toggle("muted", refused);
    answer.classList.add("rendered");
    answer.replaceChildren(...renderMarkdown(data.answer || ""));

    const note = node.querySelector(".answer-note");
    note.hidden = !data.note;
    note.textContent = data.note || "";

    renderGate(node.querySelector(".gate"), data);
    renderSources(node.querySelector(".sources"), data.sources || [], refused);
    renderDetails(node.querySelector(".details"), data);
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
      `closest ${best.toFixed(3)} ${passed ? "<" : "≥"} cutoff ${cutoff} · ${passed ? "passed" : "refused"}`;
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

  // One dropdown per answer: which documents the chunks came from, how the
  // corpus was chunked (config.CORPUS_SETTINGS, via corpus_info.chunking),
  // and every retrieved chunk with its distance.
  function renderDetails(details, data) {
    const chunks = data.chunks || [];
    if (!chunks.length) { details.hidden = true; return; }
    details.hidden = false;
    const cutoff = Number(data.threshold);
    const within = (d) => (Number.isFinite(cutoff) ? d < cutoff : true);
    const docs = new Map();
    for (const c of chunks) {
      const doc = docs.get(c.source) || { count: 0, best: Infinity };
      doc.count += 1;
      doc.best = Math.min(doc.best, Number(c.distance));
      docs.set(c.source, doc);
    }
    details.querySelector("summary").textContent =
      `Sources, chunking and chunks (${docs.size} document${docs.size === 1 ? "" : "s"}, ${chunks.length} chunks)`;

    renderDocs(details, docs, new Set(data.sources || []), data.refused, within);
    renderChunking(details.querySelector(".chunking-desc"), details.querySelector(".chunking-facts"), data);

    details.querySelector(".chunks-title").textContent =
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
      dist.dataset.within = String(within(d));
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

  function renderDocs(details, docs, cited, refused, within) {
    details.querySelector(".docs-title").textContent =
      refused ? "Closest documents (none close enough)" : "Source documents";
    const list = details.querySelector(".doc-list");
    list.replaceChildren();
    for (const [name, doc] of docs) {
      const li = document.createElement("li");
      li.className = "doc";
      const file = document.createElement("span");
      file.className = "doc-name";
      file.textContent = name;
      const meta = document.createElement("span");
      meta.className = "doc-meta";
      meta.dataset.within = String(within(doc.best));
      const role = refused ? "" : cited.has(name) ? " · used for the answer" : "";
      meta.textContent =
        `${doc.count} chunk${doc.count === 1 ? "" : "s"} · closest ${doc.best.toFixed(3)}${role}`;
      li.append(file, meta);
      list.append(li);
    }
  }

  function renderChunking(desc, facts, data) {
    const c = data.chunking;
    facts.replaceChildren();
    if (!c) {
      desc.textContent = "Not reported by this backend. Update serve.py to see the strategy here.";
      return;
    }
    desc.replaceChildren();
    const name = document.createElement("strong");
    name.textContent = c.strategy;
    desc.append(name, document.createTextNode(c.description ? ` — ${c.description}` : ""));
    const rows = [
      ["Max chars", c.max_chars],
      ["Min chars", c.min_chars],
      ["Overlap", c.overlap],
      ["Top-k", c.top_k],
      ["Produced by", c.produced_by],
    ];
    for (const [k, v] of rows) {
      if (v === undefined || v === null || v === "") continue;
      const wrap = document.createElement("div");
      const dt = document.createElement("dt");
      dt.textContent = k;
      const dd = document.createElement("dd");
      dd.textContent = String(v);
      wrap.append(dt, dd);
      facts.append(wrap);
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
      message += `\n\nBuild it with: python app.py --corpus ${node.querySelector(".corpus-tag").textContent} index`;
    }
    answer.textContent = message;
  }

  async function ask(question) {
    if (state.busy) return;
    state.busy = true;
    updateAskButton();
    const corpus = state.corpus;
    const node = newTurn(question, corpus);
    const answer = node.querySelector(".answer");
    try {
      let data;
      if (state.mode === "static") {
        data = await askStatic(question, corpus, (text) => { answer.textContent = text; });
      } else {
        data = await request("/ask", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question, corpus }),
        });
      }
      renderResult(node, data);
    } catch (err) {
      renderError(node, err);
      if (state.mode === "static") {
        updateReadiness();
      } else if (err.kind === "network") {
        state.connected = false;
        setStatus("down", "Backend offline");
        els.useStatic.hidden = false;
      }
    } finally {
      state.busy = false;
      updateAskButton();
    }
  }

  // ─── Wiring ──────────────────────────────────────────────────────────────

  els.status.addEventListener("click", () => toggleSettings());

  for (const input of els.modeInputs) {
    input.addEventListener("change", () => {
      save(STORE.mode, input.value);
      setMode(input.value);
    });
  }

  els.useStatic.addEventListener("click", () => {
    save(STORE.mode, "static");
    setMode("static");
  });

  els.settingsForm.addEventListener("submit", (e) => {
    e.preventDefault();
    state.api = normaliseApi(els.apiUrl.value);
    save(STORE.api, state.api);
    checkHealth();
  });

  els.keyForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const key = els.keyInput.value.trim();
    if (!key) return;
    save(STORE.key, key);
    els.keyInput.value = "";
    renderKeyStatus();
  });

  els.forgetKey.addEventListener("click", () => {
    forget(STORE.key);
    els.keyInput.value = "";
    renderKeyStatus();
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
  renderKeyStatus();
  renderCorpora();
  updateAskButton();
  setMode(initialMode());
})();
