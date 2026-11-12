# Same-clip defect: analysis (2026-11-13)

Status: analysis only. No scorer, judge, or serve-rule change was made in this step.
Evidence source: graded-6 rows (20261112-graded-6, sparse off, min 3, judge on).

## What was measured
- 43 served answers use **31 distinct clips**.
- **9 clips** serve **21 answers** (more than one question each). Top clip (`46f3f516062a`) serves 4 questions; `509877630aa0` serves 3.
- The strict end-to-end reader marked 7 of 43 as answering the question; the automated judge marked 34 showable. Both are AI readers.

Example reuse: "There is this understanding that if you're not suffering…" is served for chronic-stress, sickness, Ayurveda and inner-state questions. "We feel if we get more wealthier…" is served for wealth, relationship and lasting-success questions.

## Where the decision is made (code, current line numbers)
1. **Judge path (the graded config).** `FIRST_PERSON_JUDGE_ENABLED=true`. `services/first_person_judge.py::judge_select_async` (line 318) scores one clip per call. `select_index` (line 263) serves the highest-relevance clip that passes `answers`, `relevance >= minimum`, safety, completeness and standalone flags.
2. **Harness fan-out.** `services/first_person_pipeline.py` (~line 4725 `_eval_ctx_worker`, ~line 5071 `asyncio.gather`): every retrieved context is judged separately, in parallel. The first passing context in retrieval order is served. Each judge call sees one clip, so it cannot see that another clip fits better.
3. **Relevance scorer path** (`_relevance_select_scored_async`, line 1309): same one-clip-per-call shape.

## Root cause
The judge and scorer decide "does this clip answer this question?" in isolation, one clip at a time, with no comparison and no notion of "this clip is reused". A clip that is loosely on-topic (stress, health, wealth) gets a passing score for many questions. Retrieval order then picks it whenever it ranks first.

Re-ordering by score alone does not fix this: the scores are the defect. The `select_index` tie rule cannot change any row, because the judge already returns at most one clip per call.

## Candidate fixes
| # | Fix | Change | Cost | Proof |
|---|-----|--------|------|-------|
| A | **Comparative judge.** One judge call sees all passing candidates for the question and picks the best, or abstains if none answers. | New prompt and parser; harness passes all candidates into one call instead of N parallel calls. | +1 judge call per request; changes latency profile; changes served answers. | Negative-control set (`evals/first_person/negative_controls.jsonl`) abstains on nearly all pairs; graded re-run on frozen116. |
| B | **Reuse-aware abstain.** Refuse a clip that the same answer set would serve for a different question. | Needs a cross-request record or an offline precomputed clip-to-question map. | Requires state or an offline map; new Qdrant-side or file-side data. | Hub metric on graded rows (no clip serves >3 questions). |
| C | **Scorer rubric tightened to a stricter 3.** A 3 must mean "answers this question", not "on topic". | Rubric and anchor examples; keep min 3. | Changes scorer prompt, so every past run is incomparable. | Negative-control abstain rate before and after; graded re-run. |

Recommendation: **A first**, measured on the negative-control set before any graded spend. It addresses the mechanism (no comparison). C is needed too, because A still depends on the rubric. B is a later data project.

## Tests that would prove a fix
- Negative-control pairs: abstain rate >= 0.95 (pre-registered bar, not yet measured).
- Hub metric: no clip serves more than 3 distinct questions in a run.
- Frozen116 positive set: served share stays >= 30% of answerable rows.
- Unit tests for the new select rule: the comparative call abstains when no candidate answers; it never serves a candidate that failed the standalone or safety flags.

## Not decided here (owner)
- Whether a comparative judge (A) is acceptable as the same grader family as the rest of the judge path.
- Whether the demo may serve fewer answers in exchange for fewer wrong ones.
