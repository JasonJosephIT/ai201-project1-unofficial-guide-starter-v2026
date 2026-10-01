"""
One-line descriptions of the provided corpora, for `python app.py corpora`.

The full descriptions — which you should read before picking, in Milestone 1 —
are in corpora/README.md.
"""

from pathlib import Path

import config

BLURBS = {
    "campus_life": (
        "Short posts about student life. ~88 documents of 1–3 paragraphs. "
        "Useful information usually sits in a single sentence."
    ),
    "advice_threads": (
        "Question-and-answer threads with several people replying and "
        "disagreeing. Uneven lengths; answers spread across replies."
    ),
    "city_guides": (
        "Long travel guides divided into labelled sections — nine towns and "
        "five guides that cut across them. Information is organised by heading "
        "and spread across paragraphs."
    ),
    "practice": (
        "Not for your project — the small corpus used for the in-class "
        "follow-along."
    ),
}


def list_corpora() -> list[tuple[str, str]]:
    """Every corpus folder that actually exists, with its description."""
    found = []
    if not config.CORPORA_DIR.exists():
        return found

    for path in sorted(config.CORPORA_DIR.iterdir()):
        if not path.is_dir() or not (path / "documents").exists():
            continue
        count = len(
            [
                f
                for f in (path / "documents").iterdir()
                if f.suffix.lower() in {".txt", ".md"}
            ]
        )
        blurb = BLURBS.get(path.name, "Your own corpus.")
        found.append((path.name, f"{blurb} ({count} documents)"))
    return found


# What each chunking strategy in config.CORPUS_SETTINGS does, in one line.
STRATEGIES = {
    "paragraphs": "One chunk per paragraph, headed by the post's title. Short "
                  "paragraphs are glued to a neighbour; a plain-text heading "
                  "starts a new chunk.",
    "replies": "One chunk per thread reply, headed by the thread's question and "
               "the reply's vote line.",
    "sections": "One chunk per `##` section, headed by \"<guide> — <section>\".",
    "fixed": "Fixed-size character windows with overlap (the starter's original).",
}


def chunking(name: str | None = None) -> dict:
    """How a corpus is chunked and retrieved: config.chunk_settings, plus a
    one-line description and the function that produces the chunks.
    `python app.py chat` prints this next to every answer."""
    settings = config.chunk_settings(name)
    strategy = settings["strategy"]
    return {
        **settings,
        "description": STRATEGIES.get(strategy, ""),
        "produced_by": (
            "chunker.py::fallback_split" if strategy == "fixed"
            else "chunker.py::split_documents"
        ),
    }
