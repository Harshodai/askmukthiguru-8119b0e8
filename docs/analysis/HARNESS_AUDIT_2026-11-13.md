# Evaluation harness audit (graded runs), 2026-11-13

Scope: `backend/scripts/ops/graded_capture.py`, `graded_run_preflight.py`, `grade_served_answers.py`,
`evals/first_person/` (all files), `backend/evaluation/first_person_harness.py`,
`backend/evaluation/gold/calibrator.py`, `backend/docker-compose.graded.yml`, and the graded-6 run
artifacts (`~/mukthiguru_attribution_data/graded_runs/20261112-graded-6/`).

Method and limits: read-only. No Docker, no network, no LLM calls, no `.env` reads, no dataset or code
edits. Run artifacts were read for keys and counts only; no answer or clip text is copied here.
Bash was blocked by an auto-mode hook for part of the session, so grep-based checks were re-run with
simpler commands and Python one-liners. Anything not re-checked is marked UNVERIFIED.

Line numbers are for the files as they stand in the working tree on 2026-11-13 (uncommitted changes
present; see git status in the handoff).

---

## 1. What a graded run does, step by step

Capture (`backend/scripts/ops/graded_capture.py`, `main()` at lines 299-375):

1. Refuses to reuse a run id if `backend.log`, `rows.jsonl` or `manifest.json` already exists (lines 51-55).
2. Runs the preflight (`run_preflight`, `graded_run_preflight.py:301-329`) plus a cache-empty proof
   (`verify_cache_empty.py`, `graded_capture.py:90-110`). Writes `preflight.txt`. Aborts on any FAIL (lines 330-338).
3. Records the commit (`git rev-parse HEAD`, line 340) and container facts from `docker inspect` and
   `docker exec printenv` (`_container_facts`, lines 140-160). Only env keys with prefixes
   `FIRST_PERSON_`, `OPENROUTER_`, `CELERY_TASK`, `LLM_PROVIDER` are recorded (line 45). Keys containing
   key/secret/token/password are redacted.
4. Reads OpenRouter spend from Redis, day and month totals (`read_spend`, line 342).
5. Builds the item list (`_items`, lines 163-265). Default input is the frozen 116
   (`backend/evaluation/datasets/first_person_bakeoff_2026-09-25.json`, set `frozen116`, `split=tuning`)
   plus `evals/first_person/unanswerable60_draft.jsonl` (set `unanswerable86`). Benchmarks
   (frozen29, compound10, ooc13) and the question bank are opt-in flags (lines 311-314, 350-352).
   Default run = **202 rows** (116 + 86). The 116 includes 89 answerable and 27 unanswerable or near-miss.
6. Asks one question at a time (sequential, no concurrency) through `POST /api/chat` on an anonymous
   session, reusing a session for 4 questions (`_ask`, lines 268-296). Polls `/api/jobs/{id}` on HTTP 202,
   up to 110 s.
7. Writes one row per question (`build_row`, lines 62-87; `stamp_row`, lines 58-59). Fields:
   item fields (`id`, `question`, `set`, `split`, `answerable`, or `expected`/`scoring_group`/`lang` for
   the unanswerable set), `http`, `answer`, `route`, `model_used`, `grounding`, `citations`
   (snippet, speaker, speaker_verified, url, t), `notices`, `latency_ms` (server-side), `sec` (wall clock),
   plus `sha`, `container_id`, `run_id`.
8. Saves `docker logs` to `backend.log` (lines 367-370). Runs `validity()` (lines 113-128), which fails the
   run on auth-error or spend-limit lines in the log (`check_log_clean`, `graded_run_preflight.py:168-187`).
9. Writes `manifest.json` (lines 372-373): run id, sha, container id, image, started_at, flags, valid,
   reasons, spend before and after (day and month Redis totals). Exit code 2 if invalid.

Spend is recorded per run only, not per row. Graded-6 spend delta from its manifest: day 26.045 to 28.677
(+2.632 USD), month 120.373 to 123.005 (+2.632 USD), computed from the manifest.

Grading (`backend/scripts/ops/grade_served_answers.py`, `main()` at lines 1361-1562):

1. Loads rows. `require_stamped` refuses rows with no `sha` (lines 882-889, called at 1412-1413).
2. `--unanswerable` mode (lines 1414-1418) scores the unanswerable set by `expected` and `scoring_group`
   (`score_unanswerable`, lines 813-879), with no LLM. Output is `unanswerable.json`.
3. Grading mode: `check_judge_independence` (lines 1299-1324, called at 1435-1438) aborts if a judge equals
   the product relevance scorer, or if the two judges are the same model, unless `--allow-shared-judge`.
4. Grades only served rows (`served_rows or rows`, lines 1342-1343). Each row gets a first verdict from
   `--first-model`, then a second verdict for a selected subset (`grade_rows`, lines 777-794).
5. Both calls go through OpenRouter (`_openrouter_asker`, lines 892-985): temperature 0 (line 917),
   timeout 120 s, up to 8 retries on 429, 402 and 5xx. Retries exhausted raises `GraderAvailabilityError`
   (lines 980-983), which blocks the report unless `--offline-fallback` is passed (lines 1503-1535, 1474-1491).
6. `evaluate_bar` (lines 645-774) computes gates and status. `grades.json` is written at line 1559.

## 2. Preflight: what is verified and what is not

`run_preflight` (`graded_run_preflight.py:301-329`) checks: git clean (line 303), no code bind mounts
(106-115), container started after HEAD (118-133), env equals the graded override (136-145), spend headroom
against `--need-usd 12` (148-165), local review API not live (190-210). Caches empty is checked in
`graded_capture.py`.

The env check compares only keys listed in `docker-compose.graded.yml`, which has **27** keys in
`environment:` (`read_override_pins`, lines 247-253). The graded-6 preflight passed with **25** pins
(`preflight.txt`), so the two later pins (`FIRST_PERSON_CONTEXT_USE_SPARSE`, `FIRST_PERSON_JUDGE_MODEL`)
were added after graded-6 (per the compose comments).

Graded-6 manifest (`manifest.json`) has 55 recorded flags (26 pinned, 28 unpinned, plus the redacted API key). Compared with the graded compose:

- Pinned in compose and in the manifest: 26 of 27 (`FIRST_PERSON_JUDGE_MODEL` is pinned but absent from the
  graded-6 manifest, so graded-6 used its code default).
- In the manifest but **not pinned** by the graded compose: 28 keys. They ride on `.env`, outside-repo
  overrides, or code defaults. The ones that change served answers or grading:

| Flag | Graded-6 value (manifest) | Code default (`backend/app/config.py`) | Pinned in graded compose? |
|---|---|---|---|
| `FIRST_PERSON_ANSWERABILITY_CHECK_ENABLED` | `false` | `true` (line 462) | No. Source of `false` is UNVERIFIED (not in repo, not in `.env` read by me) |
| `FIRST_PERSON_RELEVANCE_MIN_SCORE` | `3` | `2` (line 526) | Yes, `3` (compose line 44). Code default disagrees with CLAUDE.md invariant 24 |
| `FIRST_PERSON_CONTEXT_USE_SPARSE` | `false` | `true` (line 330) | Yes, `false` (compose line 41), added after graded-6 |
| `FIRST_PERSON_JUDGE_ENABLED` | `true` | `false` (line 2716) | Yes, `true` (compose line 35) |
| `FIRST_PERSON_JUDGE_MODEL` | absent (default used) | `anthropic/claude-haiku-5.5` (line 2717) | Yes (compose line 38), added after graded-6 |
| `INTENT_ROUTER_AMBIGUOUS_DOMAIN_ENABLED` | not recorded | `false` (line 2060) | No. Also not recorded: the manifest prefix filter (`graded_capture.py:45`) omits `INTENT_ROUTER_` |

Other manifest flags not pinned (values equal to or chosen by the run): `FIRST_PERSON_CHAT_BRIDGE_ENABLED`,
`FIRST_PERSON_COLLECTION`, `FIRST_PERSON_CONTEXT_COLLECTION`, `FIRST_PERSON_CONTEXT_MAX_SPANS`,
`FIRST_PERSON_CROSS_VIDEO_DIVERSITY_ENABLED`, `FIRST_PERSON_DISTRESS_SERVE_CLIP_ENABLED`,
`FIRST_PERSON_HARNESS_PARALLEL_ENABLED`, `FIRST_PERSON_LLM_RERANK_ENABLED`, `FIRST_PERSON_LOCAL_REVIEW_ROOT`,
`FIRST_PERSON_MAX_CLIP_SECONDS`, `FIRST_PERSON_OKF_EXPANSION_ENABLED`, `FIRST_PERSON_RELEVANCE_FALLBACK_ENABLED`,
`FIRST_PERSON_RELEVANCE_GATE_ENABLED`, `FIRST_PERSON_REQUIRE_SPEAKER_VERIFIED`, `FIRST_PERSON_ROUTE_ENABLED`,
`FIRST_PERSON_SPECULATIVE_PARALLELISM_ENABLED`, `LLM_PROVIDER`, `OPENROUTER_CLASSIFY_MODEL`,
`OPENROUTER_FAST_MODEL`, `OPENROUTER_GENERATION_MODEL`, `OPENROUTER_GENERATION_MODEL_FALLBACK`,
`OPENROUTER_MAX_REQUEST_COST_USD`, `OPENROUTER_PREFERRED_*`, `OPENROUTER_PROVIDER_PARTITION`,
`OPENROUTER_PROVIDER_SORT`, `OPENROUTER_RPM_LIMIT`. Model slugs for generation and classify are on code
defaults, so a rerun gets them only if the defaults stay unchanged.

Not checked by the preflight at all: `INTENT_ROUTER_*`, any flag not in the compose file, the dataset and
draft file hashes, and the grader model slugs (they are passed on the command line, not pinned).

## 3. Grading: slots, sampling, showable, and the requested metrics

- **Slots.** First grader = `--first-model` (default `anthropic/claude-haiku-5.5`, line 1380). Second grader =
  `--second-model`, required (line 1381). Runbook uses sonnet-5.5 first and gemini-3.6-flash second.
- **Selection.** `select_for_second_pass` (lines 557-565): every row whose first verdict is not `showable`
  (not_showable, harmful, unsure) goes to the second grader, plus `max(1, round(passed * fraction))` randomly
  sampled showable rows (seeded `random.Random(seed).sample`, default seed 20261030, line 1401).
  With `--sample-fraction 1.0` (default, line 1397), all rows get both graders. With a smaller fraction,
  showable rows that are not sampled are final on the first grader alone. No check rejects a fraction below 1.
- **`--allow-shared-judge`** (lines 1387-1393). Without it, first == second or first == scorer aborts
  (lines 1318-1323). Graded-6 `grades.json` contains `warnings: ["first and second judge are the same model
  'anthropic/claude-sonnet-5.5'"]` and both `models` fields are sonnet-5.5. That warning is only emitted when the
  allow flag is set, so the flag was used. This conflicts with the runbook rule "must NOT be set".
- **Final verdict.** `final_grades` (lines 583-588): the second verdict overrides the first wherever the second
  graded. Gates use this final verdict only. There is no per-grader gate.
- **Showable.** Verdict `showable` after `parse_grade` (lines 526-554). `harmful=true` forces `not_showable`
  (lines 543-548). Unparseable or empty output becomes `unsure` (lines 460-464), which counts as not showable.
  The rubric is the `RUBRIC` string (lines 466-482). It has no version or hash, and `grades.json` does not
  record one.
- **Showable rate denominator.** `evaluate_bar` divides by `total = len(final)`, which is the number of served rows
  (lines 657-660). The answerable-denominator figure is reported beside it (lines 720-730), not gated.

Requested metrics:

| Requirement | Status | Evidence |
|---|---|---|
| Both graders on every served row | PARTIAL. Done when `--sample-fraction 1.0` is passed. Not enforced: no assertion, no per-grader gate. Graded-6 used one model in both slots. | `grade_served_answers.py:557-565, 583-588, 645-774, 1394-1400` |
| Wilson 95% lower bound | MISSING. No `wilson` text in any of the five ops and eval files (grep exit 1). Gates use point estimates. | `evaluate_bar` 645-774 |
| No clip serves more than 3 distinct questions (hub rule) | MISSING. No `hub`, `distinct` or `Counter` in the grader, capture, preflight or harness code (grep exit 1). Clip identity is never computed in code. | none |

Computed here from graded-6 `rows.jsonl`, keying clips on (`url`, `t`) with no text output: 31 distinct
clips across 43 served rows; the most-reused clip serves **4** questions; 1 clip serves more than 3 questions.
This already fails the hub rule on graded-6. The handoff's "9 clips serve 21 answers" is not re-checked (UNVERIFIED).

Other gates that exist but are not all in the pass decision:

- Crisis route 7/7: computed in `score_unanswerable` (`crisis_route`, lines 866-872) but not a gate in
  `evaluate_bar` (gates at 665-702). The bar file lists it under `hard_gates_checked_elsewhere`.
- "Strict ANSWERS" (the reader checks whether the answer answers the question): not in the grader. The rubric only
  asks showable. The graded-6 strict read was done outside the repo (scratchpad; not reproducible from committed files).
- p95 latency gate (lines 676-683) uses `latency_ms` from the server. Rows with no `latency_ms` are counted in
  `missing` but do not fail the gate (lines 599-623).

## 4. Negative controls: abstain-rate consumer

**MISSING.** `evals/first_person/negative_controls.jsonl` (116 rows, `expected: abstain`) is produced by
`evals/first_person/build_negative_controls.py` only. A search of `backend/scripts`, `backend/evaluation`,
`backend/services`, `scripts` and `evals` found no other file that reads it. `graded_capture._items`
(lines 163-265) does not include it, and `score_unanswerable` only reads `expected` values from
`UNANSWERABLE_EXPECTED` (line 797), which the negative-control schema does not use. The only test is
`backend/tests/test_negative_controls.py` (schema and pairing). The pairing assumption (a question paired
with another question's clip should abstain) is not verified: the handoff notes some clips are on-topic for both.

## 5. Datasets

All hashes are SHA-256 of the file bytes at audit time. Row counts from `wc`-equivalent Python counts.

| File | Rows | Authorship (from file) | Status | SHA-256 |
|---|---|---|---|---|
| `backend/evaluation/datasets/first_person_bakeoff_2026-09-25.json` | 116 questions (89 answerable, 27 unanswerable or near-miss) | AI agent, from transcripts (`_header`) | Frozen, but the bar calls it a TUNING set | acb635fc899dcd850ff0b7c9d2fb4bfddd6826e78baad71f32eecc2af16848c8 |
| `evals/first_person/unanswerable60_draft.jsonl` | 86 (name says 60) | AI-drafted (status field) | DRAFT: `draft_needs_native_review` / `draft_needs_owner_review`. Feeds the core abstain rate | 53f73a02e3dfc1160b0bfacf1b13f674854d4c83f410f0185de9d1dbed670bd5 |
| `evals/first_person/unanswerable38_draft.jsonl` | 38 | AI-drafted | DRAFT (`draft_needs_owner_review`). Not used by the runbook | ed0a506a85938d26f80f7f795f3d83f49c8d9de072d594080611378f290f96ad |
| `evals/first_person/negative_controls.jsonl` | 116 | Script output (seed 20261113, no LLM) | Generated from graded-6 served rows; not reviewed | eb491702baec088064c53d3d22c9ad9be91a3110be809568b7a91fae5cb9fd7f |
| `evals/first_person/build_negative_controls.py` | n/a | Agent-written (docstring) | Code | da27585ecdf8fb458010a73eed49c01696246225c48a7d7672a15aae7c201a5d |
| `evals/first_person/grading_pass_bar.json` | n/a | `approved: true`, `approved_by: Harsha`, 2026-10-31 (file) | Bar; contains unapproved 2026-11-09 proposal (0.95 / 0.45) | 6672d332aad892328d6fcfb9aca8d19b319dab26a2a8e094351a9f8e9c2e9297 |
| `evals/first_person/frozen29.jsonl` | 29 | No author field (UNVERIFIED) | Benchmark, on-topic | 338e7601a1d149f19af3573b44523f30fac49050dcb4dad3b694ea427bfafe3d |
| `evals/first_person/compound10.jsonl` | 10 | No author field (UNVERIFIED) | Benchmark, compound | df3bedb3a71021d72ba7f476022a0e8e6f5f160783ebb2588a4201e88301e14b |
| `evals/first_person/ooc13.jsonl` | 13 | No author field (UNVERIFIED) | Benchmark, out of corpus | 0230716557b0db78a008ea20b3076dbb59c3ab7780ba67d2afaf2b65004d5de8 |
| `evals/first_person/conversation_cases_draft.jsonl` | 25 lines (first line is a metadata header) | AI-authored (`note` field) | DRAFT; not calibration gold | 40d5ddf8426f29cb0bcdc7ec0d5ee06b4ec0b16b11f0354a213e0744dd2bab7b |
| `evals/first_person/native_language_review_sheet.csv` | 11 | Blank review columns for a native speaker (header) | Pending human review | afafb218e07c127222077b3d01d72d71a77e42879aab5a2ef7faf434345f8e49 |
| `evals/README.md` | n/a | Agent-written | Explains the safety harness (`evals/run_safety_scenarios.py`), not the first-person graded run | not hashed |

There is no `README` inside `evals/first_person/`. The frozen 116 is labelled a tuning set in the bar file
("all gate tuning used these 116"). The 116 are not held out.

`backend/evaluation/first_person_harness.py` is a retrieval harness, not the grader. Its key metrics are top-1
hit rate with a video-clustered bootstrap CI (`bootstrap_ci_by_video`), an exact McNemar test (`mcnemar_exact`),
and paraphrase consistency, against time-range answer keys. It does not produce showable verdicts and is not
wired into the graded criteria.

`backend/evaluation/gold/calibrator.py` is a Learn-then-Test selective-risk calibrator (target risk 1%, delta
0.05, Clopper-Pearson). It needs at least 299 zero-error gold items (lines 125-131). No profile exists, so the
graded run does not use it (CLAUDE.md invariant 3).

## 6. Reproducibility gaps

- **Settings outside the repo.** `FIRST_PERSON_ANSWERABILITY_CHECK_ENABLED=false` in graded-6 has no pin, and the
  code default is `true`. A rerun from committed files alone gets `true`, which is a different serving path.
- **Sparse and judge flags.** Graded-6 had sparse off and judge on from outside the compose file (the handoff says
  sparse lived in an override). They are pinned now, but graded-6 cannot be reproduced from the repo as it was.
- **Relevance min score.** Code default 2; graded run pins 3. A non-graded container (for example, a plain
  `docker compose up`) serves at 2, which conflicts with CLAUDE.md invariant 24.
- **Intent router.** `INTENT_ROUTER_AMBIGUOUS_DOMAIN_ENABLED` is not pinned and not recorded in the manifest.
- **Model slugs on defaults.** Generation, classify, fast and fallback slugs are on code defaults. Grader slugs
  are CLI arguments. The runbook verified the slugs are listed, not that a call works under budget policy.
- **Seeds.** Grader sampling seed is fixed (20261030). Answer generation is not seeded; LLM serving calls are not
  deterministic. Two runs of the same commit can differ.
- **Pre-registered criteria.** `pre_run_criteria.md` is in the session scratchpad, not the repo. A rerun cannot
  check the registered bar against a committed file.
- **Input fingerprint.** The manifest records the commit sha and container, but not the sha of the frozen dataset
  or the draft unanswerable file that was run. A changed input would leave no trace in the manifest.
- **Rubric version.** `RUBRIC` and `build_prompt` are not hashed into `grades.json`.
- **Container image.** Image digest is recorded (`sha256:fbe8da...`), but the graded run builds from the working
  tree of the commit, so a dirty tree is blocked only by the git-clean check at run time.

## 7. Statistical limits

Served share: 43 of 89 answerable rows (48.3%). Showable: 35 of 43 served (81.4%). Verdict counts in the final
grades: 35 showable, 6 not_showable, 2 unsure. Graded-6 p95 latency 8,073 ms.

Wilson 95% lower bound, z = 1.96:

    lower = (p + z^2/(2n) - z * sqrt(p(1-p)/n + z^2/(4n^2))) / (1 + z^2/n)

Results at the served n (n = 43):

| Observed showable | k / 43 | Wilson 95% lower bound | Clears 0.85? |
|---|---|---|---|
| 85% | 37 | 0.727 | No |
| 90% | 39 | 0.784 | No |
| 95% | 41 | 0.845 | No |
| 97.7% | 42 | 0.879 | Yes |
| 81.4% (graded-6) | 35 | 0.674 (upper 0.903) | No |

Results if all 89 answerable were served (n = 89), for comparison:

| Observed | k / 89 | Lower bound |
|---|---|---|
| 85% | 76 | 0.766 |
| 90% | 80 | 0.819 |
| 95% | 85 | 0.890 |

Answerable-denominator showable for graded-6: 35 / 89 = 39.3% (Wilson 0.298 to 0.497).

Is the ">= 85% lower bound" bar reachable at n = 43? Only with at least 42 of 43 showable (97.7%). At 90%
observed, the smallest n whose lower bound clears 0.85 is about 200 served rows; at 95% observed it is 60.
At a 48% served share, 200 served rows needs roughly 420 answerable questions. The frozen 116 cannot produce
that. Conclusion: at this n the 85% lower-bound bar is not reachable on the frozen 116 without near-perfect
showability, and any single run is INCONCLUSIVE for that bar. The point-estimate bar (0.85, `grading_pass_bar.json`)
is what the code gates on.

Served share gate (>= 0.30): 0.483 passes. Core abstain gate (>= 0.95): graded-6 1.0 on 69 draft rows, a small
set whose confidence interval is also wide (Wilson lower bound at 69/69 is 69/(69+3.84), about 0.947; the code computes no such bound).

## Gaps

| id | gap | evidence (file:line) | effect on a registered run | owner | suggested smallest fix |
|---|---|---|---|---|---|
| H-1 | No Wilson 95% lower bound computed or gated | `grade_served_answers.py:645-774`; no `wilson` in the five files | Gate passes on point estimate; the pre-registered lower bound is never checked | AGENT | Add `wilson_lower(k, n)` (about 10 lines) and a gate in `evaluate_bar` |
| H-2 | "Both graders on every row" not enforced | `grade_served_answers.py:557-565, 583-588, 645-774` | A run with `--sample-fraction` below 1, or one grader, can pass | AGENT | Refuse a fraction below 1 when a pass bar is set; gate on both verdicts |
| H-3 | Graded-6 used one judge in both slots (`--allow-shared-judge`) | `grade_served_answers.py:1299-1324, 1387-1393, 1543-1546`; `grades.json` warnings | Graded-6 is single-judge evidence, which the runbook forbids | OWNER (record) | Keep the flag off in graded-7; the code already aborts without it |
| H-4 | Hub rule (no clip serves more than 3 questions) not implemented; fails on graded-6 (max 4) | no `hub`/`distinct`/`Counter` in graders; computed on (url, t) | Pre-registered criterion cannot be evaluated; graded-6 already fails it | AGENT | Count questions per (url, t) in `evaluate_bar` and add a gate |
| H-5 | Crisis 7/7 computed but not a gate | `grade_served_answers.py:866-872` vs gates 665-702 | PASS can hide a crisis failure | AGENT | Add `crisis_route` as a gate (missing or failed = FAIL) |
| H-6 | "Strict ANSWERS" verdict does not exist in code | rubric `:466-482` asks showable only | The 85% strict-answer bar cannot be measured by the harness | OWNER (decide the reader) | Decide whether a second rubric is registered; do not reuse showable |
| H-7 | Bar file and pre-registered criteria disagree | `grading_pass_bar.json` (0.85, core abstain 0.95); handoff (both graders 90%, lower bound 85%, abstain 100%) | Two different pass bars; the code uses the file | OWNER | Owner confirms one bar in writing before graded-7 |
| H-8 | Negative-control abstain rate not implemented | `evals/first_person/build_negative_controls.py` is the only file that touches `negative_controls.jsonl`; `graded_capture.py:163-265` does not include it | The >= 0.95 abstain criterion cannot be measured | AGENT (code); OWNER (spend) | Add a set to `_items` and a rate in `score_unanswerable`; scorer spend needs approval |
| H-9 | Negative-control pairing assumption unverified | handoff; builder docstring | Abstain rate could be wrong for on-topic pairs | OWNER | Review a sample of pairs before the abstain rate is trusted |
| H-10 | Core abstain set is a draft with a misleading name | `graded_capture.py:41` loads `unanswerable60_draft.jsonl` (86 rows, draft status) | The 1.0 core abstain rate is on unreviewed items | OWNER | Native and owner review before it counts as a gate |
| H-11 | Frozen 116 is tuning, AI-authored | dataset `_header`; bar note | Any pass on it is not held-out evidence | OWNER | Report as tuning; keep a held-out set for the decision |
| H-12 | Answerability gate flag set to `false` outside the repo; code default `true` | manifest flag; `config.py:462`; not pinned in compose | Graded-7 can differ from graded-6 if `.env` changes | OWNER (decide), AGENT (pin) | Pin it in compose after the owner decides |
| H-13 | Relevance min-score code default 2; graded pin 3 | `config.py:526`; compose line 44 | Non-graded containers serve at a different threshold | OWNER | Owner decides the default; compose pin stays |
| H-14 | Intent-router flag not pinned and not recorded | `config.py:2060`; `graded_capture.py:45` prefix list | Its value is invisible in the manifest and the preflight | AGENT | Add `INTENT_ROUTER_` to the recorded prefixes and to the compose pins |
| H-15 | Preflight checks only compose keys | `graded_run_preflight.py:136-145, 247-253` | 28 manifest flags are unchecked; drift passes preflight | AGENT | Pin the serving flags or add an explicit allow-list check |
| H-16 | Input dataset and draft files not fingerprinted | `graded_capture.py:372` manifest keys | A changed input leaves no trace in the run record | AGENT | Add sha256 of each input file to the manifest |
| H-17 | Per-row spend not recorded | `graded_capture.py:342, 371` (day and month totals only) | Cannot attribute cost to a row or a question | AGENT | Record per-call cost in the row, or accept run-level only |
| H-18 | p95 gate ignores rows with no latency | `grade_served_answers.py:599-623, 679-683` | A run with missing latency rows can pass the p95 gate | AGENT | Fail the gate when `missing > 0` |
| H-19 | Rubric and prompt not versioned in outputs | `RUBRIC` `:466-482`; `grades.json` keys | Grades cannot be tied to the rubric used | AGENT | Hash `RUBRIC` and `build_prompt` into `grades.json` |
| H-20 | Pre-registered criteria live only in session scratchpad | handoff; runbook section 0 | The registered bar is not in the repo, so a rerun cannot check it | OWNER | Commit the criteria file before graded-7 |
| H-21 | Second grader slug not verified to run | runbook section 1 (list check only) | A missing second grader makes the run invalid after spend | OWNER (spend) | One small paid probe only if the owner approves it |
| H-22 | Answer generation not seeded; serving LLM calls not deterministic | `graded_capture.py:268-296`; no seed | A rerun of the same commit can differ | OWNER (accept) | Record the expected variance; do not present one run as exact |
| H-23 | Server-side `latency_ms` is the p95 input; wall clock is not gated | `graded_capture.py:85`; `grade_served_answers.py:599-623` | Latency bar reflects server time only | OWNER (accept) | State this in the report |
| H-24 | Tests do not cover the missing metrics | `backend/tests/test_grade_served_answers.py`, `test_graded_capture.py`, `test_graded_run_preflight.py`, `test_negative_controls.py` (builder schema only) | No test would catch a missing Wilson, hub or abstain gate | AGENT | Add a test per gate when the gate is added |
| H-25 | Frozen benchmarks lack authorship fields | `frozen29.jsonl`, `compound10.jsonl`, `ooc13.jsonl` (no author key) | Provenance UNVERIFIED | OWNER | Record authorship in the file header or a README |

UNVERIFIED items: the source of `FIRST_PERSON_ANSWERABILITY_CHECK_ENABLED=false` (not in the repo and not read
from `.env`); the 9-clips-serve-21-answers figure in the handoff; whether the second grader slug works under
budget policy; the grader's per-row cost; authorship of the three benchmark files.
