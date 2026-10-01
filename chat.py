"""
An interactive session for asking questions and reviewing chunking.

    python app.py chat
    python app.py --corpus city_guides chat

Type a question and it runs through `app.ask_pipeline`, the same function
`python app.py ask` and serve.py use. Every answer is followed by the
documents its chunks came from, the corpus's chunking strategy (from
config.CORPUS_SETTINGS) and the chunks retrieval handed over, with distances.

Commands start with a slash. `/help` lists them. The review commands —
/chunking, /doc, /chunk — cut the documents with `chunker.split_documents`
on the spot, so after you change the chunker they show the new chunks
straight away (run /index before asking again, so retrieval sees them too).
"""

import shutil
import statistics
import textwrap
from types import SimpleNamespace

import config

HELP = """\
Type a question to ask it. Commands:

  /search QUESTION   retrieval and the gate only, no model call (costs nothing)
  /chunks            the last answer's retrieved chunks, in full
  /chunk LABEL       one chunk in full, e.g. /chunk dining_halden_hall.txt#1
  /doc NAME          every chunk cut from one document, to review the chunking
  /chunking          the corpus's strategy, settings and chunk-size stats
  /corpus [NAME]     list the corpora, or switch to one
  /index             rebuild this corpus's index (after changing the chunker)
  /prompt on|off     also print the exact prompt sent to the model
  /help              this list
  /quit              leave (Ctrl-D works too)
"""


class Session:
    def __init__(self, corpus: str, variant: str = "default"):
        self.corpus = corpus
        self.variant = variant
        self.show_prompt = False
        self.last = None            # the last result shown, for /chunks
        self._chunk_cache = {}      # corpus -> chunks, for the review commands

    # ─── Output ──────────────────────────────────────────────────────────────

    @property
    def width(self) -> int:
        return max(60, min(shutil.get_terminal_size((100, 24)).columns, 110))

    def rule(self, title: str = "") -> None:
        title = f" {title} " if title else ""
        print(f"\n──{title}" + "─" * max(0, self.width - len(title) - 2))

    def wrap(self, text: str, indent: str = "") -> None:
        for line in text.splitlines() or [""]:
            if not line.strip():
                print()
                continue
            print(textwrap.fill(line, self.width, initial_indent=indent,
                                subsequent_indent=indent))

    # ─── Dispatch ────────────────────────────────────────────────────────────

    def handle(self, line: str) -> bool:
        """Run one line of input. Returns False when the session should end."""
        if not line.startswith("/"):
            self.ask(line)
            return True

        command, _, rest = line[1:].partition(" ")
        command, rest = command.lower(), rest.strip()
        if command in {"quit", "exit", "q"}:
            return False
        handlers = {
            "help": lambda: print("\n" + HELP),
            "search": lambda: self.search(rest),
            "retrieve": lambda: self.search(rest),
            "chunks": self.show_last_chunks,
            "chunk": lambda: self.show_chunk(rest),
            "doc": lambda: self.show_doc(rest),
            "chunking": self.show_chunking,
            "corpus": lambda: self.switch_corpus(rest),
            "corpora": lambda: self.switch_corpus(""),
            "index": self.reindex,
            "prompt": lambda: self.set_prompt(rest),
        }
        if command not in handlers:
            print(f"Unknown command /{command}. Type /help for the list.")
        else:
            handlers[command]()
        return True

    # ─── Asking ──────────────────────────────────────────────────────────────

    def ask(self, question: str) -> None:
        from app import ask_pipeline

        try:
            outcome = ask_pipeline(
                question,
                corpus=self.corpus,
                variant=self.variant,
                on_prompt=self._print_prompt if self.show_prompt else None,
            )
            error = None
        except Exception as exc:  # noqa: BLE001 — usually a missing key or quota
            # Retrieval and the gate ran before the model call failed, and
            # they're worth seeing on their own, so run them again to show.
            outcome = self._retrieve(question)
            outcome["answer"] = None
            error = f"{type(exc).__name__}: {exc}"

        self.show_result(outcome, error=error)

    def search(self, question: str) -> None:
        if not question:
            print("Usage: /search QUESTION")
            return
        self.show_result(self._retrieve(question), retrieval_only=True)

    def _retrieve(self, question: str) -> dict:
        """Retrieval and the gate, shaped like ask_pipeline's outcome."""
        import gate
        from store import search

        top_k = config.top_k_for(self.corpus)
        results = search(question, top_k=top_k, corpus=self.corpus, variant=self.variant)
        decision = gate.check(results)
        return {
            "question": question,
            "refused": not decision.passed,
            "best_distance": decision.best_distance,
            "threshold": decision.threshold,
            "sources": [],
            "top_k": top_k,
            "chunks": [
                {"label": r.label, "source": r.source, "distance": r.distance, "text": r.text}
                for r in results
            ],
            "answer": gate.REFUSAL if not decision.passed else None,
        }

    def _print_prompt(self, prompt: str) -> None:
        from generate import GROUNDING_INSTRUCTION

        self.rule("system instruction")
        print(GROUNDING_INSTRUCTION)
        self.rule("prompt, exactly as sent")
        print(prompt)

    # ─── One result: answer, then sources, chunking and chunks ───────────────

    def show_result(self, outcome: dict, error: str | None = None,
                    retrieval_only: bool = False) -> None:
        self.last = outcome
        refused = outcome["refused"]
        best, cutoff = outcome["best_distance"], outcome["threshold"]

        if refused:
            status = "REFUSED"
        elif retrieval_only:
            status = "RETRIEVAL ONLY — no model call"
        elif error:
            status = "NOT ANSWERED — the model call failed"
        else:
            status = "ANSWERED"
        self.rule(f"{status} · {self.corpus}")

        if outcome.get("answer"):
            self.wrap(outcome["answer"])
        if error:
            self.wrap(error)
        if retrieval_only and not refused:
            print("Passed the gate. Ask it without /search to get an answer.")
        relation = "under" if not refused else "not under"
        print(f"\nGate: best distance {best:.3f} is {relation} the {cutoff} cutoff.")

        chunks = outcome["chunks"]
        self._print_sources(chunks, sent=not refused and not retrieval_only and not error)
        self._print_chunking()
        self._print_chunk_previews(chunks, outcome.get("top_k"), cutoff)

    def _print_sources(self, chunks: list[dict], sent: bool) -> None:
        docs = {}
        for c in chunks:
            count, closest = docs.get(c["source"], (0, 1.0))
            docs[c["source"]] = (count + 1, min(closest, c["distance"]))
        note = "all sent to the model" if sent else "none sent to the model"
        print(f"\nSource documents ({note})")
        name_width = max((len(name) for name in docs), default=0)
        for name, (count, closest) in docs.items():
            plural = "" if count == 1 else "s"
            print(f"  {name:<{name_width}}   {count} chunk{plural}, closest {closest:.3f}")

    def _print_chunking(self) -> None:
        from corpus_info import chunking

        c = chunking(self.corpus)
        print(f"\nChunking strategy: {c['strategy']}")
        if c["description"]:
            self.wrap(c["description"], indent="  ")
        print(
            f"  max {c['max_chars']} chars · min {c['min_chars']} · overlap "
            f"{c['overlap']} · top-k {c['top_k']} · {c['produced_by']}"
        )

    def _print_chunk_previews(self, chunks: list[dict], top_k, cutoff: float) -> None:
        print(f"\nRetrieved chunks (top-{top_k or len(chunks)}; ✓ = under the cutoff)")
        room = self.width - 9
        for i, c in enumerate(chunks, 1):
            mark = "✓" if c["distance"] < cutoff else "✗"
            print(f"  {i}. {c['distance']:.3f} {mark}  {c['label']}")
            preview = " / ".join(line.strip() for line in c["text"].splitlines() if line.strip())
            if len(preview) > room:
                preview = preview[: room - 1] + "…"
            print(f"       {preview}")
        print("\n(/chunks prints these in full; /doc NAME shows how a document was cut.)")

    def show_last_chunks(self) -> None:
        if not self.last:
            print("Ask something first.")
            return
        cutoff = self.last["threshold"]
        self.rule(f"retrieved chunks for: {self.last['question']}")
        for i, c in enumerate(self.last["chunks"], 1):
            mark = "✓" if c["distance"] < cutoff else "✗"
            print(f"\n{i}. {c['label']}   distance {c['distance']:.3f} {mark}   "
                  f"{len(c['text'])} chars")
            self.wrap(c["text"], indent="   ")

    # ─── Reviewing the chunking ──────────────────────────────────────────────

    def chunks(self):
        if self.corpus not in self._chunk_cache:
            from chunker import split_documents
            from ingest import load_documents

            self._chunk_cache[self.corpus] = split_documents(
                load_documents(self.corpus), corpus=self.corpus
            )
        return self._chunk_cache[self.corpus]

    def show_chunking(self) -> None:
        chunks = self.chunks()
        lengths = [len(c.text) for c in chunks]
        per_doc = {}
        for c in chunks:
            per_doc[c.source] = per_doc.get(c.source, 0) + 1

        self.rule(f"chunking · {self.corpus}")
        self._print_chunking()
        shortest = min(chunks, key=lambda c: len(c.text))
        longest = max(chunks, key=lambda c: len(c.text))
        print(
            f"\n  {len(per_doc)} documents → {len(chunks)} chunks "
            f"({len(chunks) / len(per_doc):.1f} per document)\n"
            f"  chunk length: average {sum(lengths) // len(lengths)}, median "
            f"{int(statistics.median(lengths))} chars\n"
            f"  shortest {len(shortest.text)} chars: {shortest.label}\n"
            f"  longest  {len(longest.text)} chars: {longest.label}"
        )
        most = sorted(per_doc.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
        print("\n  Most chunks:")
        for name, count in most:
            print(f"    {count:>3}  {name}")
        single = sum(1 for n in per_doc.values() if n == 1)
        print(f"\n  {single} document(s) became a single chunk.")
        print("\n(/doc NAME prints every chunk of a document; /chunk LABEL prints one.)")

    def show_doc(self, name: str) -> None:
        if not name:
            print("Usage: /doc NAME   (part of a filename is enough)")
            return
        from app import _chunks_from_doc
        from ingest import load_documents

        try:
            picked = _chunks_from_doc(self.chunks(), name)
        except SystemExit as exc:  # its "no match" / "be more specific" message
            print(exc)
            return
        source = picked[0].source
        doc = next((d for d in load_documents(self.corpus) if d.source == source), None)
        size = f"{len(doc.text)} chars of cleaned text → " if doc else ""
        self.rule(f"{source} · {self.corpus}")
        print(f"{size}{len(picked)} chunk(s) by {picked[0].produced_by} "
              f"({config.chunk_settings(self.corpus)['strategy']})")
        for c in picked:
            print(f"\n#{c.index}   {len(c.text)} chars")
            self.wrap(c.text, indent="   ")

    def show_chunk(self, label: str) -> None:
        if not label:
            print("Usage: /chunk LABEL   e.g. /chunk dining_halden_hall.txt#1")
            return
        match = next((c for c in self.chunks() if c.label.lower() == label.lower()), None)
        if not match:
            print(f"No chunk labelled {label} in {self.corpus}. Labels look like "
                  f"{self.chunks()[0].label}; /doc NAME lists a document's chunks.")
            return
        self.rule(f"{match.label} · {len(match.text)} chars · {match.produced_by}")
        self.wrap(match.text)

    # ─── Corpus, index, settings ─────────────────────────────────────────────

    def switch_corpus(self, name: str) -> None:
        from corpus_info import list_corpora
        from store import index_exists

        names = [n for n, _ in list_corpora()]
        if not name:
            print()
            for n in names:
                marker = "*" if n == self.corpus else " "
                status = "indexed" if index_exists(n, self.variant) else "not indexed"
                strategy = config.chunk_settings(n)["strategy"]
                print(f"{marker} {n:<16} {strategy:<11} {status}")
            print("\n/corpus NAME switches.")
            return
        if name not in names:
            print(f"No corpus called {name}. Choose from: {', '.join(names)}")
            return
        self.corpus = name
        self.last = None
        self._announce()

    def reindex(self) -> None:
        from app import cmd_index

        cmd_index(SimpleNamespace(corpus=self.corpus, variant=self.variant))
        self._chunk_cache.pop(self.corpus, None)

    def set_prompt(self, value: str) -> None:
        if value.lower() not in {"on", "off"}:
            print(f"/prompt on|off (it is {'on' if self.show_prompt else 'off'})")
            return
        self.show_prompt = value.lower() == "on"
        print(f"Prompt printing {'on' if self.show_prompt else 'off'}.")

    def _announce(self) -> None:
        from store import index_exists

        s = config.chunk_settings(self.corpus)
        print(f"\nCorpus: {self.corpus} · {s['strategy']} chunks · top-{s['top_k']} · "
              f"cutoff {config.THRESHOLD}")
        if not index_exists(self.corpus, self.variant):
            print("No index for this corpus yet. Type /index to build it.")


def run(corpus: str, variant: str = "default") -> None:
    try:
        import readline  # noqa: F401 — arrow keys and history at the prompt
    except ImportError:
        pass
    import generate

    session = Session(corpus, variant)
    print("The Unofficial Guide — ask questions and review the chunking.")
    print("Type a question, or /help for commands.")
    session._announce()
    try:
        while True:
            try:
                line = input(f"\n[{session.corpus}] > ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not line:
                continue
            try:
                if not session.handle(line):
                    break
            except KeyboardInterrupt:
                print("\n(stopped)")
            except Exception as exc:  # noqa: BLE001 — keep the session alive
                print(f"\n{type(exc).__name__}: {exc}")
    finally:
        print(generate.usage())
