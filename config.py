"""
Settings for The Unofficial Guide.

Everything you're likely to change lives here, at the top, on purpose.
You'll edit THRESHOLD in Milestone 4 and the chunking numbers in Milestone 3.

Anything you set in your .env file wins over the defaults here.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")


# ─── The corpus you're working with ──────────────────────────────────────────
# Change this to switch corpora, or pass --corpus on the command line.
# Options are the folder names inside corpora/. See corpora/README.md.

CORPUS = os.getenv("AI201_CORPUS", "campus_life")


# ─── Ingestion ───────────────────────────────────────────────────────────────
# ingest.clean_text always strips web chrome (nav, ads, cookie banners, footers,
# HTML). This switch also drops sentences where a writer only introduces
# themselves ("Second-year here.", "I lived here my sophomore year.").
# Re-run `python app.py index` after changing it.

STRIP_AUTHOR_FRAMING = True


# ─── Chunking (Milestone 3) ──────────────────────────────────────────────────
# These are deliberately plain, generic numbers. Milestone 3 is where you
# replace them with numbers that fit the documents you actually read.

# The generic numbers below are what `fallback_split` uses, and what any
# corpus without an entry in CORPUS_SETTINGS gets (e.g. one you bring yourself).

CHUNK_SIZE = 800        # characters per chunk
CHUNK_OVERLAP = 120     # characters shared between neighbouring chunks

# Per-corpus chunking and retrieval. Each corpus has a different shape (see
# corpora/README.md), so each gets its own strategy and numbers:
#
#   strategy   how `chunker.split_documents` finds the natural units
#                "paragraphs" — blank-line paragraphs, headed by the post title
#                "replies"    — one chunk per thread reply, headed by the question
#                "sections"   — one chunk per `##` section, headed by guide + section
#                "fixed"      — the original fixed-size character windows
#   max_chars  a natural unit longer than this is cut into sentence windows
#   min_chars  paragraphs shorter than this are glued onto a neighbour
#   overlap    characters (whole sentences) repeated between the windows of a
#              unit that had to be cut — a unit that fits is never overlapped
#   top_k      how many chunks retrieval pulls back per question
CORPUS_SETTINGS = {
    # Short posts; overview posts pack several topics into separate paragraphs.
    # Paragraphs never exceed max_chars here, so there is nothing to overlap.
    "campus_life": {
        "strategy": "paragraphs", "max_chars": 450, "min_chars": 80,
        "overlap": 0, "top_k": 5,
    },
    # Each reply is one person's answer (71–198 chars). Answers are spread
    # across replies, so pull back more of them.
    "advice_threads": {
        "strategy": "replies", "max_chars": 450, "min_chars": 0,
        "overlap": 0, "top_k": 6,
    },
    # Long guides with ~7 `##` sections each; one section usually holds the
    # answer, so fewer, larger chunks. Over-long sections get split with overlap.
    "city_guides": {
        "strategy": "sections", "max_chars": 600, "min_chars": 0,
        "overlap": 150, "top_k": 4,
    },
    # Mostly one-paragraph posts, plus four long guides with plain-text headings.
    "practice": {
        "strategy": "paragraphs", "max_chars": 600, "min_chars": 80,
        "overlap": 100, "top_k": 5,
    },
}


# ─── Retrieval (Milestone 4) ─────────────────────────────────────────────────

TOP_K = 5               # default chunks per question, for corpora not listed above

# The relevance gate. If the best chunk is further away than this, the system
# refuses to answer instead of handing the model thin material.
#
# LOWER IS BETTER: 0.3 is a close match, 0.9 is unrelated.
#
# 0.6 is a reasonable starting point, not a right answer. Milestone 4 has you
# measure your own two groups of distances and put the cutoff in the gap.
# Most corpora land somewhere between 0.45 and 0.75.
THRESHOLD = 0.6


# ─── Models ──────────────────────────────────────────────────────────────────
# Embeddings run on your own machine and cost no API quota.
# Only generation calls out to a service.

# This is the model Chroma bundles, and leaving it alone is the fast path: it
# downloads about 80 MB from Chroma's own CDN and needs nothing else installed.
#
# Setting it to any other name — unit 2's "try a second embedding model"
# stretch option — switches to loading that model from Hugging Face instead,
# which needs `pip install 'sentence-transformers>=3.4,<3.5'` first. store.py
# says so with a real error message rather than a stack trace if you forget.
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
MODEL = os.getenv("AI201_MODEL", "gemini-3.5-flash-lite")


# ─── Rate limiting and quota guards ──────────────────────────────────────────
# You should not need to touch these. They exist so that a runaway loop costs
# you a warning instead of your whole day's allowance.

REQUESTS_PER_MINUTE = 30       # outgoing calls the limiter will allow per minute
SESSION_REQUEST_BUDGET = 300   # stop and warn rather than draining the daily quota
MAX_RETRIES = 4                # on 429 / resource-exhausted, with backoff

CACHE_ENABLED = os.getenv("AI201_CACHE", "1") != "0"
CACHE_DIR = ROOT / ".cache"


# ─── Paths ───────────────────────────────────────────────────────────────────

CORPORA_DIR = ROOT / "corpora"
CHROMA_DIR = ROOT / "chroma_db"
RESULTS_DIR = ROOT / "results"


def corpus_path(name: str | None = None) -> Path:
    """Folder holding the documents for a corpus."""
    return CORPORA_DIR / (name or CORPUS) / "documents"


def collection_name(name: str | None = None, variant: str = "default") -> str:
    """
    Name of the vector-store collection for a corpus.

    `variant` lets you index the same corpus two different ways and query both
    without deleting anything — you'll want that in unit 2 when you compare
    chunking strategies.

    Chroma is fussy about collection names: 3 to 63 characters, starting and
    ending with a letter or digit, and nothing but letters, digits, underscores
    and hyphens in between. If you bring your own corpus and name the folder
    something Chroma won't accept, this cleans it up rather than failing.
    """
    import re

    raw = f"{name or CORPUS}__{variant}"
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "-", raw)
    cleaned = cleaned.strip("_-")          # must start and end alphanumeric
    if not cleaned or not cleaned[0].isalnum():
        cleaned = f"c{cleaned}"
    if not cleaned[-1].isalnum():
        cleaned = f"{cleaned}0"
    return cleaned[:63].rstrip("_-") or "collection"


def chunk_settings(name: str | None = None) -> dict:
    """Chunking and retrieval settings for a corpus.

    Corpora without an entry in CORPUS_SETTINGS get the original fixed-size
    behaviour, so a corpus you bring yourself still works unchanged.
    """
    default = {
        "strategy": "fixed",
        "max_chars": CHUNK_SIZE,
        "min_chars": 0,
        "overlap": CHUNK_OVERLAP,
        "top_k": TOP_K,
    }
    return {**default, **CORPUS_SETTINGS.get(name or CORPUS, {})}


def top_k_for(name: str | None = None) -> int:
    """How many chunks retrieval pulls back for a corpus."""
    return chunk_settings(name)["top_k"]
