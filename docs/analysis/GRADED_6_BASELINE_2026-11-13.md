# Graded-6 baseline against the graded-7 registered bars (2026-11-13)

Computed by `backend/scripts/ops/graded_registered_report.py` from the graded-6 run artifacts
(`manifest.json`, `rows.jsonl`, `grades.json`, `unanswerable.json`). Bars are exactly those in
`docs/runbooks/GRADED_7_PRE_REGISTERED_CRITERIA.md`; none changed. Ids, hashes and numbers only.

**Result: FAIL, and the run is INVALID under the criteria's invalid-run rules.** Graded-6 is a
baseline, not a registered run.

## Bars

| # | Bar | Status | Estimate | n | Wilson 95% |
|---|---|---|---|---|---|
| 1 | Showable by both graders (lower bound >= 0.85) | NOT MEASURED | 1/10 jointly (diagnostic only) | 10 | 0.018-0.404 |
| 2 | Served share of answerable core rows >= 0.30 | met | 0.483 (43/89) | 89 | 0.382-0.586 |
| 3 | p95 latency <= 10 s, served core rows | met | 9,443 ms | 43 | n/a |
| 4 | Harmful = 0, both graders | NOT MEASURED | 0 seen (first 0, second 0) | - | n/a |
| 5 | Unanswerable set: groups pass, 0 served clips | met | 4 of 4 groups 100%; 0 served | 86 | n/a |
| 6 | Core abstain rate >= 0.95 | met | 1.0 (69/69) | 69 | 0.947-1.000 |
| 7 | Crisis routing 7/7 | met | 7/7 | 7 | 0.646-1.000 |
| 8 | Hub rule: no clip serves > 3 questions | **failed** | max 4 | 43 answers | n/a |
| 9 | Grader disagreements | reported | q006 (1 of 10 compared) | 10 | n/a |
| 10 | Strict-reader ANSWERS | NOT MEASURED | no such verdict in the harness (audit H-6) | - | n/a |

Not-measured reasons:
- Bar 1: graded-6 used one model (`anthropic/claude-sonnet-5.5`) in both grader slots (`grades.json`
  `models` and `warnings`), and the second slot saw only 10 of 43 served rows (the 9 non-showable or
  unsure rows plus a 1% sample). The 10-row figure is selection-biased and is shown only as a diagnostic.
  Single-grader showable on all 43 served rows: 34/43 = 0.791 (Wilson 0.648-0.886), below both the
  0.90 point estimate and the 0.85 lower-bound requirement.
- Bar 4: zero harmful verdicts were seen, but the criteria require two independent graders on every row.
- Bar 10: not implemented in the harness.

## Hub rule

43 served answers use 31 distinct clips (keyed on url + start time, short-hashed). The most-reused clip
serves 4 distinct questions; one clip is over the limit of 3: `e90ae47b50`.

## Invalid-run reasons (per the criteria)

- 33 served rows were graded by one grader family only.
- Shared judge: both slots are the same model.
- Manifest lacks the pinned value `FIRST_PERSON_JUDGE_MODEL` (added to the graded compose after graded-6).
- Manifest has no collection fingerprint (the capture script does not write one yet).

## Manifest facts

- Commit `d6962eab862e002484644f420c69026d3d26c596`; image `sha256:fbe8da1c4471...`.
- Collection `first_person_v10` (active, serving and context).
- `FIRST_PERSON_CONTEXT_USE_SPARSE=false`; `FIRST_PERSON_RELEVANCE_MIN_SCORE=3`;
  `FIRST_PERSON_ANSWERABILITY_CHECK_ENABLED=false`; `FIRST_PERSON_JUDGE_ENABLED=true`;
  `FIRST_PERSON_RELEVANCE_GATE_ENABLED=true`; `FIRST_PERSON_LLM_RERANK_ENABLED=false`;
  `FIRST_PERSON_SERVE_WEAK_MATCH=true`; `FIRST_PERSON_LLM_FALLBACK_ENABLED=false`.
- Scorer model `anthropic/claude-haiku-5.5`; judge model not recorded; grader models both
  `anthropic/claude-sonnet-5.5`.
- `INTENT_ROUTER_*` flags not recorded (the prefix was not captured then).
- Spend: day 26.045 to 28.677, month 120.373 to 123.005, delta +2.632 USD for both.

## Method notes

- Sets in `rows.jsonl`: `set == frozen116` with `answerable` true/false (89 and 27); `set == unanswerable86`
  with `expected` and `scoring_group`. No benchmark rows were in this run. Core = `frozen116`.
- Served = the row has at least one citation. Latency is the server-side `latency_ms`. The tool's p95 is
  over served core rows (9,443 ms); the grader's own 8,073 ms is over all 200 rows with a value. Both pass.
- Rule for missing latency: a served row without it never passes (all missing = not measured, some
  missing = failed). Graded-6 had none missing on served core rows.
- Bars 5, 6 and 7 are taken from the grader's `unanswerable.json` (the support-line check for crisis rows
  needs the grader code); served clips on the unanswerable set are recounted from rows (0).

## What this baseline can and cannot show

It shows the retrieval and abstention side is healthy on the frozen tuning set: served share 0.48, p95 under
10 s, 100% abstain on the core draft set, 7/7 crisis routing. It shows one real defect, a hub clip. It
cannot show answer quality: no two-family grading exists, the 85% lower-bound bar is unreachable at n=43
(needs 42 of 43 showable), the 116 are an AI-authored tuning set and the 86 unanswerable rows are an
unreviewed draft. Nothing here is held-out evidence.
