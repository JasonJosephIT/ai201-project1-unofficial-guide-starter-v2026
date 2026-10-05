# The Unofficial Guide

**Jason Joseph** · corpus: `campus_life`

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

The Unofficial Guide answers questions about student life at a university
from `campus_life`, 88 short posts written by students. The posts cover
courses, housing, admin deadlines, dining halls, money, the health centre and
getting around campus. You can ask "What time does Halden Hall close?" or "Is
the housing lottery random?". The system pulls the closest paragraphs, has
Gemini answer from those alone, and names the files it used. A question the
posts don't cover, such as "What is the capital of Mongolia?", gets "I don't
have enough information about that." instead of a guess.

## Chunking Strategy

**Chunk size:** one paragraph per chunk, at most 450 characters. The chunker glues any paragraph under 80 characters to a neighbour (`campus_life` in `config.CORPUS_SETTINGS`).
**Overlap:** 0

`campus_life` holds 88 short student posts of one to three paragraphs each, 307
characters on average and 526 at most. In most posts the useful fact sits in one
sentence, and an overview post gives each topic its own paragraph.
`dining_halden_hall_followup.txt`, for example, spends one paragraph on wait
times and the next on the hall closing at 7:00pm.

The starter's chunker cut fixed 800-character windows with 120 characters of
overlap. No `campus_life` post reaches 800 characters, so the starter made 88
chunks, one per post, with no window boundary for the overlap to bridge. The
Halden Hall follow-up became a single vector that mixed wait times with the
closing time.

`chunker.py::split_documents` cuts `campus_life` by paragraph:

- **One paragraph per chunk.** Each topic gets its own vector: 150 chunks,
  averaging 191 characters (median 180, shortest 102, longest 396). 33 posts
  stay as a single chunk.
- **The post's title opens each chunk**, such as `Laundry in Morrow House` or
  `CS 340 Databases — assessment`. When search returns "One midterm and a final,
  both open-book" on its own, you can see which course it describes.
- **Short paragraphs join a neighbour.** The chunker merges any paragraph under
  80 characters into a neighbouring one and keeps a heading line with the text
  beneath it. The shortest chunk in the corpus runs 102 characters.
- **450 characters works as a safety cap.** The longest paragraph runs 373
  characters, so the cap cuts nothing in this corpus. If you add a longer post,
  the chunker splits it at sentence boundaries.
- **Overlap stays at 0** because the chunker splits no paragraph. Overlap helps
  when a paragraph breaks in two; here it would repeat text between unrelated
  paragraphs.

At ingestion, `ingest.clean_text` strips self-introduction sentences such as
"Second-year here." (`STRIP_AUTHOR_FRAMING` in `config.py`). Those sentences
carry no facts, and leaving them in would pull each chunk that contains one
towards the same empty match.

**Before and after, measured.** Best distance for four questions, starter chunks
against paragraph chunks (lower is closer):

| Question | Starter (800/120) | Paragraphs |
|---|---|---|
| What time does Halden Hall close? | 0.261 (`dining_halden_hall.txt#0`) | 0.210 (`dining_halden_hall_followup.txt#1`) |
| Is the housing lottery random? | 0.254 | 0.254 |
| How much does an official transcript cost? | 0.185 | 0.185 |
| What is the capital of Mongolia? (out of scope) | 0.825 | 0.825 |

Paragraph chunking improved the one question whose answer shares a post with
another topic. Halden Hall's closing time has its own chunk, and its best
distance dropped from 0.261 to 0.210. The housing lottery and transcript posts
score the same, since each one formed a single chunk under both strategies. The
Mongolia question stays at 0.825, so the relevance gate refuses it as before.

The other corpora get cuts that match their shape. `advice_threads` gets one
chunk per reply, each starting with the thread's question (75 chunks, top-6).
`city_guides` gets one chunk per `##` section, each starting with the guide and
section name. Its sections run long, so the chunker caps them at 600 characters
with 150 characters of overlap (96 chunks, top-4).

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

**Question:** What time does Halden Hall close?

**Answer:**

From `python app.py --corpus campus_life ask "What time does Halden Hall close?"`:

```
  (best distance 0.210, cutoff 0.6)

Halden Hall closes at 7:00pm.

Sources: `dining_halden_hall.txt` and `dining_halden_hall_followup.txt`

Sources retrieved: dining_halden_hall.txt, dining_halden_hall_followup.txt, dining_pellew_dining_hall.txt
```

**My relevance cutoff:** 0.6 (`THRESHOLD` in `config.py`)

The five questions the corpus covers came back with best distances between
0.170 and 0.510. The five questions from `OUT_OF_SCOPE` came back between 0.825
and 0.923. That leaves a gap from 0.510 to 0.825, and 0.6 sits inside it, so
the gate answers all five in-corpus questions and refuses all five
out-of-scope ones.

The cutoff sits nearer the in-corpus group on purpose. The weakest in-corpus
match, "Which courses drop your lowest midterm?" at 0.510, has its answer
spread over two documents (STAT 150 and PHYS 130), and a cutoff tighter than
0.51 would refuse it. The out-of-scope questions sit 0.225 above the cutoff at
their closest.

One question shows the cutoff's weak spot. "How do I get from Kestrelford to
Halden Bay by train?" asks about an intercity train, and the corpus's transit
posts cover only walking times and the campus shuttle. Its closest chunk is
the Kestrel Commons dining post (`dining_kestrel_commons.txt#1`), which shares
the word "Kestrel" and nothing useful. It scores 0.594, 0.006 under the
cutoff, so the gate lets it through.

<!-- The number you set in config.py, and how you got there.

     You ran five questions your corpus covers and the five in OUT_OF_SCOPE
     that it clearly doesn't, and wrote down the best distance for each. What
     did those two groups look like? Where was the gap? Put the actual numbers
     here — the table below wants all ten rows.

     Milestone 4. -->

| Question | In corpus? | Best distance |
|---|---|---|
| How much does an official transcript cost? | Yes | 0.185 (`admin_transcript_requests.txt#0`) |
| What time does Halden Hall close? | Yes | 0.210 (`dining_halden_hall_followup.txt#1`) |
| Which courses drop your lowest midterm? | Yes | 0.510 (`course_stat_150.txt#1`) |
| Is the housing lottery random? | Yes | 0.254 (`admin_housing_lottery.txt#0`) |
| What are the health centre's walk-in hours? | Yes | 0.170 (`health_center.txt#0`) |
| What is the capital of Mongolia? | No | 0.825 |
| How do I change the oil in a diesel engine? | No | 0.923 |
| Who won the 1994 World Cup? | No | 0.886 |
| What is the recommended dosage of ibuprofen for a headache? | No | 0.839 |
| How do I write a for loop in Rust? | No | 0.864 |

## How I Used AI

<!-- Two specific moments. For each: what you asked for, what came back, and
     what you changed about it.

     "I asked Claude to write the chunking function from my notes. It ignored
     the overlap, so I added that myself" is the level of detail we're after.
     "I used AI to help me code" is not.

     Milestone 5. -->

**1.** I asked Claude Code to host the system on GitHub Pages, so anyone
could ask it questions without my laptop running `serve.py`. It built a
static site. A GitHub Actions job ran my Python pipeline and exported every
chunk and its vector to JSON. The browser embedded each question with the same
MiniLM model, and a parity script showed that browser distances matched
`store.search` exactly. What I changed: the live URL kept showing this README,
because Pages was still set to deploy from a branch, and a website was more
than I needed to test retrieval. I had it roll back all the web work while
keeping my per-corpus chunking, and build `python app.py chat` instead. That
command shows each answer with its source documents, chunking strategy and
retrieved chunks, and has commands for reviewing how each document was cut.

**2.** I asked Claude Code to fill in the Chunking Strategy section above. It
measured the change instead of describing it: the starter's 800/120 windows
gave one chunk per post, and paragraph chunks moved the Halden Hall question
from 0.261 to 0.210 while the single-paragraph posts stayed the same. Its
first draft read like generated text, full of hedging adverbs and one
"a safety cap, not a target" contrast. What I changed: I had it rewrite the
section under stop-slop rules, with active voice, no hedges and the same
numbers. The rewrite also corrected a claim that short paragraphs merge into
"the next one", since the code joins them to whichever neighbour fits.

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
