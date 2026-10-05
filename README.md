# The Unofficial Guide

<!-- Replace this line with your name and which corpus you picked. -->

> **This file is your submission.** Fill it in as you go — most sections get
> written during the milestone that produces them, not at the end.
>
> How the starter works, and every command you'll need, is in `RUNNING.md`.
> Leave that file alone.
>
> **Paste everything as text.** No screenshots, no video. A typed table gets
> full credit; a picture of the same table gets none.
>
> Delete these instruction blocks as you replace them. The `<!-- -->` comments
> are notes to you and don't show up when the page renders — you can leave them
> or remove them.

---

# Unit 1

## What This Does

<!-- Three or four sentences. Which corpus you picked, and the kinds of
     questions your system answers. Write it for someone who has never seen
     this repo.

     Milestone 5. -->

## Chunking Strategy

**Chunk size:** one paragraph per chunk, capped at 450 characters, with paragraphs under 80 characters glued to a neighbour (`campus_life` in `config.CORPUS_SETTINGS`)
**Overlap:** 0

`campus_life` is 88 short student posts, one to three paragraphs each (307
characters on average, 526 at most). The useful fact in a post usually sits in
a single sentence, and the overview posts put each topic in its own paragraph:
`dining_halden_hall_followup.txt` has one paragraph on wait times and another
that says the hall closes at 7:00pm.

The starter's chunker cut fixed 800-character windows with 120 characters of
overlap. No post is longer than 800 characters, so it made exactly 88 chunks,
one per post, and the overlap never came into play. A post that covered two
topics became one vector that matched neither topic well.

`chunker.py::split_documents` now cuts `campus_life` by paragraph instead:

- **One paragraph per chunk**, so each topic gets its own vector. This gives
  150 chunks, averaging 191 characters (median 180, shortest 102, longest 396).
  33 posts are short enough to stay a single chunk.
- **The post's title starts every chunk** (for example `Laundry in Morrow House`
  or `CS 340 Databases — assessment`). A paragraph like "One midterm and a final,
  both open-book" then still says which course it is about when it is
  retrieved on its own.
- **Paragraphs under 80 characters are joined to a neighbour**, and a short
  heading line always stays with the text under it. Without this, a one-line
  paragraph would become a chunk with almost nothing to match on.
- **450 characters is a safety cap, not a target.** The longest paragraph in
  the corpus is 373 characters, so the cap never cuts anything here. If a
  longer post is added, it is split at sentence boundaries, never
  mid-sentence.
- **Overlap is 0**, because no paragraph gets cut. Overlap only matters when a
  unit is split, and here it would just repeat text between unrelated
  paragraphs.

At ingestion, `ingest.clean_text` also strips self-introduction sentences such
as "Second-year here." (`STRIP_AUTHOR_FRAMING` in `config.py`). They carry no
facts and would pull every chunk that contains one towards the same
meaningless match.

**What changed, measured.** Best distance with the starter's chunks compared
with the paragraph chunks (lower is closer):

| Question | Starter (800/120) | Paragraphs |
|---|---|---|
| What time does Halden Hall close? | 0.261 (`dining_halden_hall.txt#0`) | 0.210 (`dining_halden_hall_followup.txt#1`) |
| Is the housing lottery random? | 0.254 | 0.254 |
| How much does an official transcript cost? | 0.185 | 0.185 |
| What is the capital of Mongolia? (out of scope) | 0.825 | 0.825 |

The gain appears only where a post mixes topics. The Halden Hall closing time
now has a chunk to itself. Single-paragraph posts score the same because they
were already one chunk, and the out-of-scope question is just as far away as
before, so the relevance gate is unaffected.

The other corpora are cut to their own shape: `advice_threads` gets one chunk
per reply, headed by the thread's question (75 chunks, top-6), and
`city_guides` gets one chunk per `##` section, headed by guide and section name.
`city_guides` sections can run long, so they are capped at 600 characters with
150 characters of overlap (96 chunks, top-4).

<!-- What about YOUR documents made you pick these numbers? Short posts and
     long sectioned guides don't want the same chunking, and "800 seemed
     reasonable" earns nothing. Point at something you noticed when you read
     the documents in Milestone 1.

     If you changed your mind partway through, say so and say why. That's worth
     more than pretending you got it right first time.

     Milestone 3. -->

## Sample Chunks

<!-- Five chunks, pasted as text. Label each one and name the file it came from
     AND the function that produced it — the grader checks your code against
     what you claim here.

     `python app.py chunks -n 5` prints all three for you. Copy them straight
     across.

     Milestone 3. -->

From `python app.py --corpus campus_life chunks -n 5`: 150 chunks in total, five
taken at even spacing across the corpus.

**Chunk 1** — source: `admin_add_drop_deadline.txt#0` — produced by: `chunker.py::split_documents`

```
On the add/drop deadline
You can add a course through the end of the second week. Dropping is a longer window — through the end of week six — but a drop after week two shows as a W on your transcript. Nothing anywhere on the registrar's site says this plainly, and students find out from each other.
```

**Chunk 2** — source: `course_cs_340_exams.txt#0` — produced by: `chunker.py::split_documents`

```
CS 340 Databases — assessment
One midterm and a final, both open-book. Lightly curved, usually two or three points.
```

**Chunk 3** — source: `course_stat_150.txt#1` — produced by: `chunker.py::split_documents`

```
STAT 150 Applied Statistics
The one piece of advice: the dropped midterm makes the first one low-stakes; use it to learn the format.
```

**Chunk 4** — source: `health_center.txt#0` — produced by: `chunker.py::split_documents`

```
The health centre
Walk-in hours are 8am to 11am; everything after that is by appointment and appointments run about a week out. If something is urgent, go at 8am and wait rather than booking.
```

**Chunk 5** — source: `housing_morrow_house_laundry.txt#1` — produced by: `chunker.py::split_documents`

```
Laundry in Morrow House
Best time to do laundry here is Tuesday or Wednesday morning. Sunday after 6pm you will wait.
```

## Sample Answer

<!-- One complete question and answer, pasted as text, with the source line
     visible. Milestone 4. -->

**Question:**

**Answer:**

```
```

**My relevance cutoff:**

<!-- The number you set in config.py, and how you got there.

     You ran five questions your corpus covers and the five in OUT_OF_SCOPE
     that it clearly doesn't, and wrote down the best distance for each. What
     did those two groups look like? Where was the gap? Put the actual numbers
     here — the table below wants all ten rows.

     Milestone 4. -->

| Question | In corpus? | Best distance |
|---|---|---|
|  |  |  |

## How I Used AI

<!-- Two specific moments. For each: what you asked for, what came back, and
     what you changed about it.

     "I asked Claude to write the chunking function from my notes. It ignored
     the overlap, so I added that myself" is the level of detail we're after.
     "I used AI to help me code" is not.

     Milestone 5. -->

**1.**

**2.**

<!-- ── Stretch features ─────────────────────────────────────────────────────
     Doing one? Say so here BEFORE you start. A feature this README never
     claims earns nothing.
     ───────────────────────────────────────────────────────────────────────── -->

---

# Unit 2

<!-- These sections get ADDED to what's already above. Don't delete or rewrite
     unit 1 — the point is that someone can see what you said before you knew
     how it went. -->

## Run Log — Before

<!-- Your five criteria, three runs each. `python run_eval.py --label before`
     runs the questions, puts the OUT_OF_SCOPE ones through the gate, and
     writes it all into results/ for you. Targets come from criteria.md; the
     verdict column is your call.

     Criterion 3 is measured in one deterministic pass rather than three, so
     the same number goes in all three run columns. That's correct, not lazy.

     Milestone 1. -->

| Criterion | Target | Run 1 | Run 2 | Run 3 | Verdict |
|---|---|---|---|---|---|
| 1. Retrieved chunk contains the answer | 4 of 5 |  |  |  |  |
| 2. Every answer names a source | 5 of 5 |  |  |  |  |
| 3. Gate stops out-of-corpus questions | 4 of 5 |  |  |  |  |
| 4. | | | | | |
| 5. | | | | | |

<!-- Underneath, paste the REAL output for each criterion from one of your
     runs — the actual text your system produced, not a description of it.
     Name the file and function that produced it. -->

## Verdicts

<!-- MET or MISSED for each of the five, against the target you wrote last
     unit — not a new one. Plus a sentence on how you decided. That sentence
     matters most where it was close.

     If your target said 4 of 5 and your runs came out 4, 3, 4, that's a MISS.
     The target has to hold, not show up occasionally.

     Milestone 2. -->

| # | Criterion | Verdict | How I decided |
|---|---|---|---|
| 1 |  |  |  |
| 2 |  |  |  |
| 3 |  |  |  |
| 4 |  |  |  |
| 5 |  |  |  |

## Diagnoses

<!-- For each miss: which stage caused it, and how. The stage alone isn't
     enough — you need the mechanism.

     Not a diagnosis: "Question 3 didn't work."
     A diagnosis:     "Question 3 asks about laundry costs. The answer is in
                       one sentence that got split across two chunks, so
                       neither chunk on its own contains it."

     The five stages: loading → chunking → embedding → retrieval → generation.

     Look for a pattern. If three misses all ask about numbers, that's one
     problem, not three.

     Missed nothing? Say so, then say honestly whether your targets were set
     low, and which one you'd tighten and to what.

     Milestone 3. -->

## The Improvement

**What I changed:**

**Why I picked it:**

<!-- Connect it to a specific diagnosis above in one sentence. If you can't,
     you picked a fix because it sounded impressive. -->

### Run Log — After

<!-- Same format, same five criteria, three runs each.
     `python run_eval.py --label after` -->

| Criterion | Target | Run 1 | Run 2 | Run 3 | Verdict |
|---|---|---|---|---|---|
| 1. Retrieved chunk contains the answer | 4 of 5 |  |  |  |  |
| 2. Every answer names a source | 5 of 5 |  |  |  |  |
| 3. Gate stops out-of-corpus questions | 4 of 5 |  |  |  |  |
| 4. | | | | | |
| 5. | | | | | |

**Did it help?**

<!-- Say plainly whether it did, and how you know. If it made things worse,
     say that — a change that backfired, honestly reported, earns full credit
     and is more interesting than one that worked. What matters is that you can
     tell.

     Milestone 4. -->

## What's Still Broken

<!-- For each criterion still missed after your fix: what you'd do about it,
     and why you stopped where you did.

     "I ran out of time" is fine if it's true. Pretending nothing is left is
     not.

     Milestone 5. -->

## What I'd Do Differently

<!-- Knowing what you know now — which of your five criteria would you write
     differently, and why?

     Milestone 5. -->
