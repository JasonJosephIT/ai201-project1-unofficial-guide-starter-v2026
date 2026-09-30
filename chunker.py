"""
Stage 2 of the pipeline: splitting documents into chunks.

⚠️ THIS IS THE FILE YOU CHANGE IN MILESTONE 3.

Milestone 3 change: `split_documents` now picks a strategy per corpus from
`config.CORPUS_SETTINGS` — paragraphs for campus_life and practice, one chunk
per reply for advice_threads, one chunk per `##` section for city_guides — and
starts every chunk with its document's title (or thread question, or guide and
section name) so a chunk read on its own still says what it is about.

The starter's version cut every document into fixed-size pieces with a fixed
overlap. On `campus_life` that gave 88 documents and 88 chunks, because almost
nothing reaches 800 characters; the paragraph strategy gives 158, splitting
multi-topic overview posts into one chunk per topic.

If you get stuck for 30 minutes, `fallback_split` is the original. Switch back
to it, write down what you saw, and move on. That's a real observation about
your pipeline, not giving up.
"""

import re
from dataclasses import dataclass

import config
from ingest import Document


@dataclass
class Chunk:
    """One piece of one document."""

    text: str
    source: str        # which file it came from
    index: int         # which chunk within that file, starting at 0
    produced_by: str   # the function that made it — cite this in your README

    @property
    def label(self) -> str:
        return f"{self.source}#{self.index}"


def fallback_split(
    documents: list[Document],
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[Chunk]:
    """
    The starter's original chunker. Fixed-size character windows with overlap.

    Keep this function. Milestone 3's stop rule points back at it, and having
    something to compare your own strategy against is useful in unit 2.
    """
    chunk_size = chunk_size or config.CHUNK_SIZE
    overlap = overlap or config.CHUNK_OVERLAP

    if overlap >= chunk_size:
        raise ValueError("overlap has to be smaller than chunk_size")

    chunks: list[Chunk] = []
    for doc in documents:
        start = 0
        index = 0
        while start < len(doc.text):
            piece = doc.text[start : start + chunk_size].strip()
            if piece:
                chunks.append(
                    Chunk(
                        text=piece,
                        source=doc.source,
                        index=index,
                        produced_by="chunker.py::fallback_split",
                    )
                )
                index += 1
            start += chunk_size - overlap

    return chunks


PRODUCED_BY = "chunker.py::split_documents"


def split_documents(documents: list[Document], corpus: str | None = None) -> list[Chunk]:
    """
    Split documents into chunks, using the strategy that fits the corpus.

    Each corpus has its own shape, so `config.CORPUS_SETTINGS` picks a strategy
    and numbers per corpus (`corpus` defaults to `config.CORPUS`):

      paragraphs  campus_life, practice. One chunk per paragraph, with short
                  lines glued to a neighbour and a plain-text heading starting
                  a new chunk. Every chunk starts with the post's title, so a
                  paragraph like "The bad: the heating is uneven" still says
                  which building it is about.
      replies     advice_threads. One chunk per reply, starting with the
                  thread's question and the reply's vote line.
      sections    city_guides. One chunk per `##` section (plus the intro),
                  starting with "<guide> — <section heading>".
      fixed       anything else: the original `fallback_split` windows.

    Any unit longer than `max_chars` is cut into sentence windows that share
    `overlap` characters of whole sentences, so no cut lands mid-sentence.
    """
    settings = config.chunk_settings(corpus)
    strategy = settings["strategy"]

    if strategy == "fixed":
        return fallback_split(documents, settings["max_chars"], settings["overlap"])

    unit_finders = {
        "paragraphs": _paragraph_units,
        "replies": _reply_units,
        "sections": _section_units,
    }
    if strategy not in unit_finders:
        raise ValueError(
            f"Unknown chunking strategy '{strategy}' in config.CORPUS_SETTINGS. "
            f"Use one of: fixed, {', '.join(unit_finders)}."
        )
    find_units = unit_finders[strategy]

    chunks: list[Chunk] = []
    for doc in documents:
        index = 0
        for header, body in find_units(doc.text, settings):
            for window in _windows(body, settings["max_chars"], settings["overlap"]):
                text = f"{header}\n{window}" if header else window
                chunks.append(
                    Chunk(text=text, source=doc.source, index=index, produced_by=PRODUCED_BY)
                )
                index += 1
    return chunks


# ─── Finding the natural units ───────────────────────────────────────────────
# Each finder returns (header, body) pairs. The header is repeated at the top
# of every chunk cut from that body, so a chunk read on its own still says
# what it is about.


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _looks_like_heading(paragraph: str) -> bool:
    """A short single line with no closing punctuation, e.g. 'Crew variants'."""
    return (
        "\n" not in paragraph
        and len(paragraph) <= 60
        and not paragraph.rstrip().endswith((".", "!", "?", ":", ";", ","))
    )


def _paragraph_units(text: str, settings: dict) -> list[tuple[str, str]]:
    paragraphs = _paragraphs(text)
    title = ""
    if paragraphs and _looks_like_heading(paragraphs[0]):
        title = paragraphs.pop(0)

    min_chars, max_chars = settings["min_chars"], settings["max_chars"]
    units: list[str] = []
    buffer = ""
    for para in paragraphs:
        if _looks_like_heading(para):
            # A heading always starts a new unit and stays with what follows it.
            if buffer:
                units.append(buffer)
            buffer = para
            continue
        joined = f"{buffer}\n\n{para}" if buffer else para
        if buffer and _looks_like_heading(buffer):
            buffer = joined  # a heading never stands alone
            continue
        short = len(para) < min_chars or len(buffer) < min_chars
        if buffer and short and len(joined) <= max_chars:
            buffer = joined
        else:
            if buffer:
                units.append(buffer)
            buffer = para
    if buffer:
        units.append(buffer)

    # A trailing unit that is still tiny joins the one before it.
    if len(units) > 1 and len(units[-1]) < min_chars:
        tail = units.pop()
        units[-1] = f"{units[-1]}\n\n{tail}"

    if not units and title:
        return [("", title)]
    return [(title, unit) for unit in units]


_REPLY_MARKER = re.compile(r"^--- reply .*---\s*$", re.MULTILINE)


def _reply_units(text: str, settings: dict) -> list[tuple[str, str]]:
    markers = list(_REPLY_MARKER.finditer(text))
    if not markers:  # not a thread after all: treat it as paragraphs
        return _paragraph_units(text, settings)

    question = text[: markers[0].start()].strip()
    units = []
    for i, marker in enumerate(markers):
        end = markers[i + 1].start() if i + 1 < len(markers) else len(text)
        body = text[marker.end():end].strip()
        if body:
            header = f"{question}\n{marker.group(0).strip()}" if question else marker.group(0).strip()
            units.append((header, body))
    return units


_SECTION_HEADING = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)


def _section_units(text: str, settings: dict) -> list[tuple[str, str]]:
    headings = list(_SECTION_HEADING.finditer(text))
    if not headings:  # no markdown headings: fall back to paragraphs
        return _paragraph_units(text, settings)

    title = ""
    first = headings[0]
    if len(first.group(1)) == 1:  # a single '#' is the guide's own title
        title = first.group(2).strip()

    units = []
    intro = text[: first.start()].strip()
    if intro:
        units.append((title, intro))
    for i, heading in enumerate(headings):
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        body = text[heading.end():end].strip()
        if not body:
            continue
        if heading is first and title:
            units.append((title, body))  # the intro under the '#' title
        else:
            name = heading.group(2).strip()
            units.append((f"{title} — {name}" if title else name, body))
    return units


# ─── Cutting a unit that is too long ─────────────────────────────────────────


def _windows(body: str, max_chars: int, overlap: int) -> list[str]:
    """
    Return `body` whole if it fits. Otherwise cut it into windows of whole
    sentences, each at most `max_chars` (unless one sentence alone is longer),
    with each window repeating about `overlap` characters of sentences from the
    end of the one before.
    """
    if len(body) <= max_chars:
        return [body]

    # Each piece is one sentence plus the whitespace after it, so joining pieces
    # back together keeps the original line and paragraph breaks.
    sentences = [s for s in re.findall(r".*?(?:[.!?](?=\s)|$)\s*", body, re.DOTALL) if s.strip()]
    windows: list[str] = []
    start = 0
    while start < len(sentences):
        end = start
        size = 0
        while end < len(sentences) and (end == start or size + len(sentences[end]) <= max_chars):
            size += len(sentences[end])
            end += 1
        windows.append("".join(sentences[start:end]).strip())
        if end >= len(sentences):
            break
        # Step back over whole sentences until about `overlap` chars are repeated,
        # but always move forward at least one sentence.
        back, carried = end, 0
        while back - 1 > start and carried + len(sentences[back - 1]) <= overlap:
            back -= 1
            carried += len(sentences[back])
        start = back
    return windows


def describe(chunks: list[Chunk]) -> str:
    """A one-line summary, printed after indexing."""
    if not chunks:
        return "0 chunks"
    lengths = [len(c.text) for c in chunks]
    return (
        f"{len(chunks)} chunks, "
        f"{sum(lengths) // len(lengths)} characters on average "
        f"(shortest {min(lengths)}, longest {max(lengths)}), "
        f"produced by {chunks[0].produced_by}"
    )


if __name__ == "__main__":
    import sys

    from ingest import load_documents

    name = sys.argv[1] if len(sys.argv) > 1 else config.CORPUS
    chunks = split_documents(load_documents(name), corpus=name)
    print(f"{name} ({config.chunk_settings(name)['strategy']}): {describe(chunks)}")
