"""
Stage 1 of the pipeline: loading documents off disk and cleaning them up.

The five stages are loading, chunking, embedding, retrieval, and generation.
When something goes wrong in unit 2, your job is to work out which of the five
it happened in. This is the first one.
"""

import html
import re
from dataclasses import dataclass
from pathlib import Path

import config


@dataclass
class Document:
    """One source file, cleaned and ready to be chunked."""

    source: str   # the filename, e.g. "housing_lottery.txt" — this is what gets cited
    text: str


# ─── What isn't real content ─────────────────────────────────────────────────
# Mapped with Jev (TypeSafe) by labelling the role of all 1,322 sentences in the
# four shipped corpora. Result: no navigation, ads or other page chrome at all,
# so the web-chrome rules below change nothing on them — they are there for
# documents you bring yourself, scraped pages especially. The one kind of
# non-content Jev found with confidence is the writer introducing themselves.

# Whole lines that are website furniture rather than writing. Each pattern has
# to match the entire line, so a real sentence that merely starts with "Sign up"
# or mentions cookies is left alone.
_CHROME_LINE = re.compile(
    r"""^\s*(?:
        # a bare UI label, optionally with a count or arrow: "Read more »", "Share (12)"
        (?:skip\ to\ (?:main\ )?content|back\ to\ top|read\ more|see\ more|load\ more
          |advertisement|sponsored(?:\ content)?|related\ (?:posts|articles|links)
          |you\ (?:may|might)\ also\ like|share\ (?:this|on)\b[^.!?]{0,30}|share
          |print\ this\ page|permalink|log\ ?in|sign\ ?in|sign\ up|log\ out|sign\ out)
          [\s\d():»›→|•-]{0,10}
      | (?:subscribe|follow\ us|join\ our\ (?:newsletter|mailing\ list))\b[^\n]{0,120}
      | sign\ up\ for\ (?:our|the)\ (?:newsletter|mailing\ list|emails?|updates)\b[^\n]{0,80}
      | [^\n]{0,40}\b(?:we|this\ site|this\ website|our\ site)\ uses?\ cookies\b[^\n]*
      | [^\n]{0,40}\b(?:accept|manage|reject)\ (?:all\ )?cookies\b[^\n]{0,60}
      | (?:©|\(c\)|copyright\ (?:©\ )?\d{4})[^\n]{0,120}
      | [^\n]{0,80}\ball\ rights\ reserved\b[^\n]{0,40}
      | (?:posted|published|last\ updated|updated|edited)\ (?:by|on|at)\b[^.!?\n]{0,60}
      | (?:https?://|www\.)\S+
    )\s*$""",
    re.IGNORECASE | re.VERBOSE,
)

# Breadcrumbs and nav bars: three or more one-to-three-word items joined by
# | › » > or •, e.g. "Home | Housing | Dining" or "Home › Guides › Brightwater".
# Lines starting with "|" are markdown tables and are kept.
_NAV_ITEM = r"[\w&'’-]+(?:\ [\w&'’-]+){0,2}"
_NAV_LINE = re.compile(
    rf"^\s*(?!\|){_NAV_ITEM}(?:\s*[|›»>•]\s*{_NAV_ITEM}){{2,}}\s*$"
)

# Sentences where the writer only introduces themselves or says why they're
# posting. Jev labelled these "author_framing" with confidence 0.85 or higher.
# Lower-confidence framing is kept on purpose, because those lines carry a
# caveat or a subject name the answer needs — "Transferred in last year, so take
# this with a grain of salt", "None of these are official", "Adding to what
# people have said about The Atrium".
_AUTHOR_FRAMING = re.compile(
    r"""(?:^|(?<=[.!?]\ )|(?<=\n))(?:
        I\ lived\ here\ (?:my|in|for|during)\ [^.!?\n]{1,40}\.
      | I'm\ an?\ (?:freshman|first-year|sophomore|second-year|junior|third-year|senior|fourth-year)
          \ and\ I've\ (?:done|taken|had)\ this\ [^.!?\n]{1,30}\.
      | Took\ this\ (?:last\ |this\ )?(?:spring|summer|fall|autumn|winter|semester|term|year)\.
      | Just\ finished\ a\ (?:year|semester|term)\ in\ this\ [^.!?\n]{1,30}\.
      | (?:First|Second|Third|Fourth|Final)-year\ here\.
      | Asked\ about\ this\ a\ lot\ so\ writing\ it\ down\.
    )[ \t]*""",
    re.VERBOSE,
)


def clean_text(raw: str) -> str:
    """
    Strip the stuff that isn't the real content.

    In order: normalise line endings; remove HTML tags and entities; drop
    whole lines of website furniture (navigation and breadcrumbs, ads, cookie
    banners, share/subscribe/login prompts, copyright footers, "posted by"
    stamps, bare URLs); drop sentences where the writer only introduces
    themselves; then tidy the whitespace that leaves behind.
    """
    text = raw.replace("\r\n", "\n").replace("\r", "\n")

    # HTML left over from a scraped page: tags out, entities decoded.
    if re.search(r"<[a-zA-Z/!][^>]*>", text):
        text = re.sub(r"(?is)<(script|style|nav|header|footer|aside)\b.*?</\1>", "\n", text)
        text = re.sub(r"(?i)<br\s*/?>|</(?:p|div|li|h[1-6])>", "\n", text)
        text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)

    # Whole lines of page chrome.
    lines = [
        line for line in text.split("\n")
        if not (_CHROME_LINE.match(line) or _NAV_LINE.match(line))
    ]
    text = "\n".join(lines)

    # The writer introducing themselves.
    if config.STRIP_AUTHOR_FRAMING:
        text = _AUTHOR_FRAMING.sub("", text)

    # Collapse runs of blank lines down to one.
    text = re.sub(r"\n[ \t]+\n", "\n\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Collapse repeated spaces and tabs, but keep line structure intact.
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"[ \t]+\n", "\n", text)

    return text.strip()


def load_documents(corpus: str | None = None) -> list[Document]:
    """
    Read every .txt and .md file in the corpus folder.

    Returns a list of Documents. Each one keeps its filename, because every
    answer your system produces has to name the document it came from.
    """
    folder = config.corpus_path(corpus)

    if not folder.exists():
        raise FileNotFoundError(
            f"No corpus at {folder}.\n"
            f"Check the corpus name in config.py, or see corpora/README.md "
            f"for what's available."
        )

    documents: list[Document] = []
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() not in {".txt", ".md"}:
            continue
        text = clean_text(path.read_text(encoding="utf-8"))
        if text:
            documents.append(Document(source=path.name, text=text))

    if not documents:
        raise ValueError(f"{folder} has no .txt or .md files in it.")

    return documents


def describe(documents: list[Document]) -> str:
    """A one-line summary, printed after indexing so you can sanity-check it."""
    total = sum(len(d.text) for d in documents)
    avg = total // max(len(documents), 1)
    return (
        f"{len(documents)} documents, "
        f"{total:,} characters, "
        f"~{avg:,} characters per document"
    )


if __name__ == "__main__":
    docs = load_documents()
    print(describe(docs))
    print()
    for doc in docs[:3]:
        preview = doc.text[:200].replace("\n", " ")
        print(f"  {doc.source}: {preview}...")
