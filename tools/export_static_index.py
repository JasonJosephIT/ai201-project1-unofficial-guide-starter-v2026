"""
Export the index as static JSON, so the GitHub Pages site can search it.

GitHub Pages serves files and nothing else: no Python, no Chroma, no secrets.
So this runs the real pipeline at build time — ingest, chunk, embed — and
writes what the browser needs to do the rest itself:

    docs/data/<corpus>.json    every chunk, with its vector
    docs/data/manifest.json    the cutoff, the refusal, the grounding
                               instruction, the prompt template, the corpora

Everything the browser decides with (threshold, top_k, refusal text, prompt)
comes from here rather than being typed into docs/app.js a second time. A
second copy is a second cutoff you'd have to keep in step, and it would drift.

Vectors are the same bundled all-MiniLM-L6-v2 that Chroma uses (store.embed),
L2-normalised and stored as base64 float32. With unit-length vectors, the
browser's `1 - dot(q, v)` is exactly Chroma's cosine distance, so the 0.6
cutoff means the same thing online as it does in `python app.py ask`.

    python tools/export_static_index.py              # writes docs/data/
    python tools/export_static_index.py --out /tmp/x # somewhere else

docs/data/ is a build output: GitHub Actions regenerates it on every deploy
(.github/workflows/pages.yml), and .gitignore keeps it out of commits.
"""

import argparse
import base64
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import chunker  # noqa: E402
import config  # noqa: E402
import corpus_info  # noqa: E402
import gate  # noqa: E402
import generate  # noqa: E402
import ingest  # noqa: E402
import store  # noqa: E402

# The instructor's follow-along corpus. Not part of anyone's project.
SKIP = {"practice"}

# The Transformers.js build of the same model. docs/app.js loads this one.
BROWSER_MODEL = "Xenova/all-MiniLM-L6-v2"

# generate.build_prompt, as a template the browser can fill in. Placeholders
# are filled in one pass (see `_fill`), so a chunk that happens to contain
# "{question}" is left alone. `_check_prompt_template` proves this renders
# byte-for-byte what build_prompt does, and stops the export if it ever doesn't.
PROMPT_TEMPLATE = {
    "chunk": "[from {source}]\n{text}",
    "separator": "\n\n",
    "prompt": (
        "Documents:\n\n{context}\n\n"
        "---\n\nQuestion: {question}\n\n"
        "Answer using only the documents above, and name the file you used."
    ),
}


def _fill(template: str, values: dict) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), m.group(0)), template)


def render_prompt(question: str, results) -> str:
    context = PROMPT_TEMPLATE["separator"].join(
        _fill(PROMPT_TEMPLATE["chunk"], {"source": r.source, "text": r.text})
        for r in results
    )
    return _fill(PROMPT_TEMPLATE["prompt"], {"context": context, "question": question})


def _check_prompt_template(chunks) -> None:
    """Fail loudly if PROMPT_TEMPLATE no longer matches generate.build_prompt."""
    sample = [
        store.Result(text=c.text, source=c.source, label=c.label, distance=0.0,
                     produced_by=c.produced_by)
        for c in chunks[:3]
    ]
    question = "What time does {question} Halden Hall close?"
    if render_prompt(question, sample) != generate.build_prompt(question, sample):
        sys.exit(
            "PROMPT_TEMPLATE in tools/export_static_index.py no longer matches "
            "generate.build_prompt. Update the template so the browser sends the "
            "same prompt the Python pipeline does."
        )


def _pack(vectors) -> tuple[list[str], int]:
    """L2-normalise and base64-encode each vector as little-endian float32."""
    matrix = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    matrix = matrix / np.where(norms == 0, 1, norms)
    matrix = matrix.astype("<f4")
    return [base64.b64encode(row.tobytes()).decode("ascii") for row in matrix], matrix.shape[1]


def export_corpus(name: str, out_dir: Path) -> dict:
    settings = config.chunk_settings(name)
    documents = ingest.load_documents(name)
    chunks = chunker.split_documents(documents, corpus=name)
    if not chunks:
        sys.exit(f"{name}: no chunks — is corpora/{name}/documents empty?")

    _check_prompt_template(chunks)
    chunking = corpus_info.chunking(name)
    made_by = {c.produced_by for c in chunks}
    if made_by != {chunking["produced_by"]}:
        sys.exit(f"{name}: chunks came from {made_by}, not {chunking['produced_by']}.")
    packed, dim = _pack(store.embed([c.text for c in chunks]))

    payload = {
        "corpus": name,
        "model": config.EMBEDDING_MODEL,
        "strategy": settings["strategy"],
        "top_k": settings["top_k"],
        "chunking": chunking,
        "dim": dim,
        "chunks": [
            {"label": c.label, "source": c.source, "text": c.text, "v": v}
            for c, v in zip(chunks, packed)
        ],
    }
    path = out_dir / f"{name}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"  {name:<16} {len(chunks):>4} chunks  {path.stat().st_size / 1024:>6.0f} KB  -> {path}")
    return {"documents": len(documents), "chunks": len(chunks), "strategy": settings["strategy"],
            "top_k": settings["top_k"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=config.ROOT / "docs" / "data")
    args = parser.parse_args()

    if os.getenv("AI201_FAKE_EMBEDDINGS") == "1":
        sys.exit("AI201_FAKE_EMBEDDINGS=1 is set. Refusing to publish stand-in vectors.")
    if config.EMBEDDING_MODEL != store.BUNDLED_MODEL:
        sys.exit(
            f"config.EMBEDDING_MODEL is {config.EMBEDDING_MODEL!r}, but the browser "
            f"embeds questions with {BROWSER_MODEL}. Export only works with "
            f"{store.BUNDLED_MODEL!r}, or online distances would mean nothing."
        )

    blurbs = dict(corpus_info.list_corpora())
    names = [n for n in config.CORPUS_SETTINGS if n not in SKIP and n in blurbs]
    if not names:
        sys.exit("No corpora to export. Check config.CORPUS_SETTINGS and corpora/.")

    args.out.mkdir(parents=True, exist_ok=True)
    print(f"Exporting {len(names)} corpora with {config.EMBEDDING_MODEL}:")

    corpora = []
    for name in names:
        info = export_corpus(name, args.out)
        corpora.append({"name": name, "blurb": blurbs[name], "file": f"{name}.json", **info})

    manifest = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": os.getenv("GITHUB_SHA", ""),
        "threshold": config.THRESHOLD,
        "model": config.MODEL,
        "embedding_model": config.EMBEDDING_MODEL,
        "browser_embedding_model": BROWSER_MODEL,
        "grounding_instruction": generate.GROUNDING_INSTRUCTION,
        "refusal": gate.REFUSAL,
        "prompt_template": PROMPT_TEMPLATE,
        "default_corpus": config.CORPUS if config.CORPUS in names else names[0],
        "corpora": corpora,
    }
    path = args.out / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  manifest -> {path}")


if __name__ == "__main__":
    main()
