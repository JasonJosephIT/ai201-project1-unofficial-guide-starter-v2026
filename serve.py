#!/usr/bin/env python3
"""
The Unofficial Guide — the same pipeline, over HTTP.

    python serve.py                          run it locally on port 5000
    gunicorn serve:app                       run it the way a host runs it

Nothing new happens in this file. It is a wrapper: a request comes in, it
hands the question to `app.py::ask_pipeline` — the exact function the command
line uses — and hands the answer back as JSON. Retrieval, the relevance gate
and the grounded prompt all still live where they lived. If you change how
your system answers, you change it in those files and this one follows.

Two routes:

    POST /ask       {"question": "...", "corpus": "..."} in, the answer, its
                    sources and the retrieved chunks out (corpus is optional)
    GET  /health    is the service up, and which corpora have an index

The web page in docs/ (served by GitHub Pages) calls these two routes from the
browser. A page on another origin may only read the replies if this service
says so, which is what the CORS headers below are for. Set
AI201_ALLOWED_ORIGINS to a comma-separated list to change who may call it;
the default is your own machine and any *.github.io page.

Why this exists: `app.py` runs once and exits, which is fine on your laptop
and impossible to deploy. A hosted service has to stay up and wait for
requests. This is the smallest thing that does that.

⚠️ There is deliberately no logging, no timing and no metrics in this file.
Unit 9 has you build the structured log yourself — the request line, the
timing field everyone skips, the whole instrument-before-you-deploy exercise.
Shipping a logger here would hand you the answer to that. Add yours in unit 9;
this file stays the bare shell until then.
"""

import fnmatch
import os

from flask import Flask, jsonify, request

import config

app = Flask(__name__)

ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "AI201_ALLOWED_ORIGINS",
        "http://localhost:*,http://127.0.0.1:*,https://*.github.io",
    ).split(",")
    if o.strip()
]


def _origin_allowed(origin: str) -> bool:
    return any(
        fnmatch.fnmatch(origin, pattern) or origin == pattern.replace(":*", "")
        for pattern in ALLOWED_ORIGINS
    )


@app.after_request
def cors(response):
    """Let the GitHub Pages front end (a different origin) read the replies."""
    origin = request.headers.get("Origin", "")
    if origin and _origin_allowed(origin):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        # Chrome asks this extra question before a public https page may call a
        # server on your own machine (http://localhost). Without it, the page
        # on github.io can't reach `python serve.py` running on your laptop.
        if request.headers.get("Access-Control-Request-Private-Network") == "true":
            response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response


@app.route("/ask", methods=["OPTIONS"])
@app.route("/health", methods=["OPTIONS"])
def preflight():
    return ("", 204)


def _corpus_names() -> list[str]:
    from corpus_info import list_corpora

    return [name for name, _ in list_corpora()]


@app.get("/health")
def health():
    """Is the service up, and is there an index to search?

    Two different questions, and the second one is the one that bites. A
    freshly deployed service answers this route happily while every /ask
    returns "no index" — hosts give you no disk that survives a restart, so
    the index has to be built as part of getting the service up. Checking
    here means you find that out in one request instead of five.
    """
    from corpus_info import list_corpora
    from store import index_exists

    ready = index_exists(config.CORPUS)
    return jsonify(
        {
            "status": "ok",
            "corpus": config.CORPUS,
            "index_ready": ready,
            "detail": (
                "ready"
                if ready
                else "no index for this corpus — run `python app.py index`"
            ),
            "threshold": config.THRESHOLD,
            # Every corpus on disk, so a front end can offer a choice. Only the
            # ones with an index can answer; the rest need
            # `python app.py index --corpus NAME` first.
            "corpora": [
                {
                    "name": name,
                    "blurb": blurb,
                    "index_ready": index_exists(name),
                    "strategy": config.chunk_settings(name)["strategy"],
                    "top_k": config.top_k_for(name),
                }
                for name, blurb in list_corpora()
            ],
        }
    )


@app.post("/ask")
def ask():
    """One question in, one grounded answer out.

    A refused question is a 200, not an error. The gate refusing is your
    system working — it is an answer, and the JSON says so with
    `"refused": true` so whatever calls this can tell the two apart.
    """
    from app import ask_pipeline

    payload = request.get_json(silent=True) or {}
    question = (payload.get("question") or "").strip()
    corpus = (payload.get("corpus") or config.CORPUS).strip()

    if not question:
        return (
            jsonify(
                {
                    "error": "Send JSON with a question in it, like "
                    '{"question": "is the housing lottery random?"}'
                }
            ),
            400,
        )

    if corpus not in _corpus_names():
        return jsonify({"error": f"No corpus called '{corpus}'."}), 400

    try:
        outcome = ask_pipeline(question, corpus=corpus)
    except Exception as exc:  # noqa: BLE001 — a reader gets this, not a traceback
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500

    return jsonify(
        {
            "question": question,
            "answer": outcome["answer"],
            "refused": outcome["refused"],
            "sources": outcome["sources"],
            "best_distance": round(outcome["best_distance"], 4),
            "threshold": outcome["threshold"],
            "corpus": corpus,
            "top_k": outcome["top_k"],
            "chunks": [
                {**chunk, "distance": round(chunk["distance"], 4)}
                for chunk in outcome["chunks"]
            ],
        }
    )


def main():
    # Hosts tell you which port to listen on through PORT, and they expect you
    # on 0.0.0.0. Binding 127.0.0.1 instead works perfectly on your laptop and
    # then answers nothing at all once deployed, because the host's router
    # can't reach a socket that only accepts connections from inside the
    # container. It is the single most common way a first deploy "succeeds"
    # and is unreachable.
    port = int(os.getenv("PORT", "5000"))

    # Debug mode reloads on save, which is handy, and prints a console that
    # runs arbitrary code, which is not something to leave switched on where
    # strangers can reach it. Off unless you ask for it.
    debug = os.getenv("AI201_DEBUG", "0") == "1"

    print(f"Serving The Unofficial Guide on http://localhost:{port}")
    print(f"Corpus: {config.CORPUS}    (Ctrl-C to stop)\n")
    print("Try it from another terminal:\n")
    print(f"  curl http://localhost:{port}/health")
    print(
        f"  curl -X POST http://localhost:{port}/ask \\\n"
        f"    -H 'Content-Type: application/json' \\\n"
        f"    -d '{{\"question\": \"is the housing lottery random?\"}}'\n"
    )

    app.run(host="0.0.0.0", port=port, debug=debug)


if __name__ == "__main__":
    main()
