// Does the browser retrieve what Python retrieves?
//
// The static site embeds questions in the browser (Transformers.js) and
// searches docs/data/<corpus>.json itself. If its distances drift from
// store.search, the relevance gate behaves differently online than it does
// in `python app.py ask` — so this checks, question by question:
//
//   - the same top-1 chunk label,
//   - |Δ best distance| < 0.01,
//   - the same gate decision (answer vs refuse).
//
// The questions are questions.py's QUESTIONS and OUT_OF_SCOPE plus the
// example chips in docs/app.js. The embedding settings and the Transformers.js
// version are read out of docs/app.js too, so this tests what the page runs.
//
// Setup, once:
//   python tools/export_static_index.py
//   python app.py --corpus campus_life index        (and any other corpus)
//   npm install --prefix tools
// Then:
//   node tools/check_static_parity.mjs              # every exported corpus
//   node tools/check_static_parity.mjs campus_life  # just one
//
// PYTHON=.venv/bin/python picks the interpreter (default: python3).

import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const TOOLS = dirname(fileURLToPath(import.meta.url));
const ROOT = dirname(TOOLS);
const DATA = join(ROOT, "docs", "data");
const MAX_DELTA = 0.01;

// ─── What the page runs ──────────────────────────────────────────────────────

const appJs = readFileSync(join(ROOT, "docs", "app.js"), "utf8");

function constFromAppJs(name) {
  const match = appJs.match(new RegExp(`const ${name} = ([\\s\\S]*?);\\n`));
  if (!match) throw new Error(`Couldn't find \`const ${name}\` in docs/app.js`);
  return new Function(`return (${match[1]});`)();
}

const EMBED = constFromAppJs("EMBED");
const EXAMPLES = constFromAppJs("EXAMPLES");
const pageVersion = constFromAppJs("TRANSFORMERS_VERSION");
const installed = JSON.parse(
  readFileSync(join(TOOLS, "node_modules", "@huggingface", "transformers", "package.json"), "utf8")
).version;
if (installed !== pageVersion) {
  console.error(`docs/app.js loads Transformers.js ${pageVersion}, but tools/ has ${installed}. ` +
    `Make tools/package.json match and re-run npm install --prefix tools.`);
  process.exit(1);
}

const { pipeline } = await import("@huggingface/transformers");

// ─── Browser-side retrieval, same maths as docs/app.js ───────────────────────

function decode(b64) {
  const bytes = Buffer.from(b64, "base64");
  return new Float32Array(bytes.buffer, bytes.byteOffset, bytes.byteLength / 4);
}

function search(index, q) {
  return index.chunks
    .map((c) => {
      let dot = 0;
      for (let i = 0; i < q.length; i++) dot += q[i] * c.vec[i];
      return { label: c.label, distance: 1 - dot };
    })
    .sort((a, b) => a.distance - b.distance)
    .slice(0, index.top_k);
}

// ─── Run ─────────────────────────────────────────────────────────────────────

const manifest = JSON.parse(readFileSync(join(DATA, "manifest.json"), "utf8"));
const wanted = process.argv.slice(2);
const corpora = manifest.corpora.filter((c) => !wanted.length || wanted.includes(c.name));
if (!corpora.length) {
  console.error(`No exported corpus matches ${wanted.join(", ")}.`);
  process.exit(1);
}

console.log(`Transformers.js ${installed} · ${EMBED.model} · dtype ${EMBED.dtype} · ` +
  `pooling ${EMBED.pooling} · normalize ${EMBED.normalize} · cutoff ${manifest.threshold}\n`);
const extractor = await pipeline("feature-extraction", EMBED.model, { dtype: EMBED.dtype });

let failures = 0;
let worst = 0;
for (const corpus of corpora) {
  const index = JSON.parse(readFileSync(join(DATA, corpus.file), "utf8"));
  index.chunks.forEach((c) => { c.vec = decode(c.v); });

  const python = JSON.parse(execFileSync(
    process.env.PYTHON || "python3",
    [join(TOOLS, "parity_reference.py")],
    { cwd: ROOT, input: JSON.stringify({ corpus: corpus.name, questions: EXAMPLES[corpus.name] || [] }),
      stdio: ["pipe", "pipe", "inherit"], maxBuffer: 64 * 1024 * 1024 }
  ));

  console.log(`── ${corpus.name} (top-${index.top_k}, ${index.chunks.length} chunks)`);
  for (const ref of python.results) {
    const out = await extractor(ref.question, { pooling: EMBED.pooling, normalize: EMBED.normalize });
    const hits = search(index, out.data);
    const best = hits[0].distance;
    const passed = best < manifest.threshold;
    const delta = Math.abs(best - ref.best);
    worst = Math.max(worst, delta);

    const problems = [];
    if (hits[0].label !== ref.top[0].label) problems.push(`top-1 ${hits[0].label} vs ${ref.top[0].label}`);
    if (delta >= MAX_DELTA) problems.push(`Δ ${delta.toFixed(4)}`);
    if (passed !== ref.passed) problems.push(`gate ${passed ? "answers" : "refuses"} vs Python ${ref.passed ? "answers" : "refuses"}`);
    if (problems.length) failures++;

    console.log(
      `  ${problems.length ? "FAIL" : "ok  "}  ${best.toFixed(4)} (py ${ref.best.toFixed(4)}, Δ ${delta.toFixed(5)})  ` +
      `${passed ? "answer" : "refuse"}  ${hits[0].label.padEnd(38)} ${ref.question}` +
      (problems.length ? `\n        ${problems.join("; ")}` : "")
    );
  }
  console.log();
}

console.log(`Largest |Δ best distance|: ${worst.toFixed(5)} (limit ${MAX_DELTA})`);
if (failures) {
  console.log(`${failures} question(s) differ. Fix the embedding settings in docs/app.js — not the threshold.`);
  process.exit(1);
}
console.log("Parity holds: same top-1, same gate decision, distances within tolerance.");
