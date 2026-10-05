# Acceptance criteria — The Unofficial Guide

Five criteria that say what "working" means for this system, written in unit 1
**before** any results existed.

An acceptance criterion names a target: a number, a count, a rate, or something
a person could plainly observe. *"Retrieval works"* is an opinion. *"For at
least 4 of my 5 test questions, the top results include a chunk containing the
answer"* is a criterion.

Under each one, write a sentence or two on **why that target** and not a
stricter or looser one. A reason that says something about your corpus or your
pipeline earns credit; *"80% seemed reasonable"* does not.

> Missing your own targets next unit costs you nothing. Setting a target so
> easy you can't miss it does.

---

## 1. Retrieved chunks contain the answer

For at least 4 of my 5 test questions, the retrieved chunks include one that
contains the answer.

**Why this target:**
Four of my questions each have one post that states the answer in a single
sentence. The fifth, "Which courses drop your lowest midterm?", has its answer
split across two course posts (STAT 150 and PHYS 130). It also shares the
word "drop" with admin posts about the add/drop deadline and the pass/fail
option. Those posts compete for the five retrieval slots, and when I checked,
they pushed PHYS 130 out of the top five. I expect four of five, with the
midterm question as the likely miss.

---

## 2. Every answer names a source

Every answer the system produces names at least one source document.

**Why this target:**
The pipeline asks for a citation twice. `generate.build_prompt` labels every
chunk `[from <filename>]`, and `GROUNDING_INSTRUCTION` tells the model to name
the file it used. Refused questions never reach the model. I count only the
model's own answer text here, not the "Sources retrieved" line that `app.py`
prints, so a miss means Gemini ignored a direct instruction. All five is the
right bar for that.

---

## 3. The relevance gate stops out-of-corpus questions

When I ask a question my documents clearly don't cover, the relevance gate
stops it and the system returns "I don't have enough information about that" —
in at least 4 of 5 tries.

<!-- The five questions are the ones in `OUT_OF_SCOPE` at the bottom of
     `questions.py`, and `run_eval.py` puts them through the gate and writes
     what happened into your run log. Swap them for your own if you'd rather —
     just keep five of them, or the "4 of 5" above has nothing to be 4 of. -->

**Why this target:**
When I set the cutoff, my five in-corpus questions scored 0.170 to 0.510 and
the five out-of-scope questions scored 0.825 to 0.923. That is a clean gap
with 0.6 inside it, and all five out-of-scope questions were refused. I kept
the target at four of five because the gap narrows for questions that borrow
a campus name. "How do I get from Kestrelford to Halden Bay by train?" asks
about something the corpus doesn't cover, yet it scored 0.594 against the
Kestrel Commons post and got through.

---

## 4. Something about your chunks

<!-- YOU WRITE THIS ONE.

     How would you know if your chunks were the right size? Name something
     countable or observable.

     Examples of the right shape — don't copy these, they should come from
     what you actually saw in Milestone 3:
       - "At least 4 of 5 sampled chunks read as a complete thought, with no
          sentence cut in half at either end."
       - "No chunk is shorter than 200 characters, since anything below that
          in my corpus turned out to be a heading with no content under it." -->

Every `campus_life` chunk starts with its post's title, and no chunk is shorter
than 100 characters. Checked by running `chunker.split_documents` over the
corpus and counting.

**Why this target:**
Many `campus_life` paragraphs never name their subject. "One midterm and a
final, both open-book" could describe any course until the title "CS 340
Databases — assessment" sits above it. A chunk without its title can be
retrieved for the wrong course and cited for the wrong one. The corpus also
has short lines, such as post titles and one-sentence asides, that carry
nothing to answer from on their own. A chunk under 100 characters means the
80-character join rule let one through.

---

## 5. Your choice

<!-- YOU WRITE THIS ONE TOO.

     Pick something you actually care about getting right. It could be about
     speed, about refusals, about a particular kind of question your corpus
     handles badly, about source attribution being correct rather than merely
     present — anything, as long as it names a number or an observable
     outcome. -->

For at least 4 of my 5 test questions, a file that the answer names contains
the answer: the `expects` phrase from `questions.py` appears in that file.

**Why this target:**
Criterion 2 only checks that a filename appears. The prompt carries all five
retrieved chunks, including neighbours from other posts. The Halden Hall
answer had `dining_pellew_dining_hall.txt` in its prompt alongside the two
Halden Hall posts, so the model could cite a file that is present but wrong.
I want the cited file to be the right one. I expect four of five because the
midterm answer lives in two files, and the model may cite a course post that
mentions midterms without dropping one.

---

<!-- ─────────────────────────────────────────────────────────────────────────
     UNIT 2 — read this before you change anything above.

     If a criterion turns out to be BROKEN rather than merely unmet, you can
     revise it, and that earns credit. But never delete or edit the original
     line. Add the revision underneath it, like this:

         ## 1. Retrieved chunks contain the answer

         For at least 4 of my 5 test questions, the retrieved chunks include
         one that contains the answer.

         **Why this target:** ...

         > **Revised in unit 2:** For at least 4 of 5 questions, the top three
         > results contain the answer.
         >
         > **Why revised:** I couldn't judge "the chunks include one that
         > contains the answer" the same way twice — I scored two questions
         > differently on Monday than on Wednesday. The new version is
         > something I can actually check.

     That's a revision because the criterion couldn't be MEASURED.

     Lowering a target because you missed it is not a revision, and it costs
     you the point:

         ✗ "I said 4 of 5 but got 2 of 5, so 2 of 5 is more realistic."

     A number you missed stays where it is, gets diagnosed, and gets a fix
     attempted. That's where the points are.

     The whole reason the originals stay visible is so someone can see what you
     said before you knew the answer.
     ───────────────────────────────────────────────────────────────────────── -->
