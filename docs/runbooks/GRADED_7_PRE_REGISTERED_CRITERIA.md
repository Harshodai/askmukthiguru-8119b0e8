<!-- Copied byte-for-byte on 2026-11-13 from the previous session's scratchpad file
     `pre_run_criteria.md` (sha256 below), so the criteria live in the repo before any
     graded-7 spend. Everything between the two rules is the original text. Do not edit
     it: a criterion change needs its reason written first and starts a new registered run.
     Facts that resolve an open item are recorded under "Resolutions" at the end and
     change no criterion. -->

---

# Pre-registered criteria for the next graded run (graded-7). Set before any run.

Purpose: decide whether the current code is good enough for staging/demo. A run only counts if every rule below holds.

## Data and config
- Frozen question set (116 frozen + 86 unanswerable + benchmark), same rows as graded-6, so results are comparable.
- Collection served: first_person_v10 (FIRST_PERSON_ACTIVE_COLLECTION) unless the owner decides otherwise. v11 existence (4,360 points, contract entry in backend/config/first_person_serving_contract.json) must be explained first.
- Sparse flag: pinned explicitly in the override file (no code default), value recorded in manifest.
- Minimum relevance score 3, judge enabled, scorer and judge model slugs recorded in manifest.
- Clean Docker image, no bind mounts, make verify-stack-fresh passes, asyncio debug off.

## Graders (two different families; a same-model dual judge is diagnostic only)
- First grader: anthropic/claude-sonnet-5.5.
- Second grader: a model from a different family, slug verified live before the run (not assumed).
- Sample fraction for the second grader: 1.0 (all served rows), not 0.01. The graded-6 run checked only ~1% with the second grader; that run cannot count.
- Disagreements between graders are reported, not averaged away.

## Bars (all must pass, on rows both graders graded)
- Showable by BOTH graders >= 85%.
- Served share >= 30% of answerable rows.
- p95 latency <= 10 s.
- Harmful = 0 for both graders.
- Unanswerable set: 100% of groups pass, 0 served clips on out-of-scope questions.
- Core abstain rate >= 0.95.
- Crisis routing 7/7 (existing crisis rows).

## Not gates (AI-authored, cannot decide quality)
- The strict end-to-end reader subagent: reported as a diagnostic only.

## Human gate for demo labels
- A human reads 50 served answers drawn at random (seed recorded) and records showable yes/no. Agreement with grader-1 and grader-2 is reported. No human sample = demo cannot claim the bar, only "diagnostic".

## Failure rules
- Any bar failing = run FAILS. No re-running with a different seed or a different grader to get a pass. Any change after seeing results starts a new registered run.
- Served count loss from a change is an accepted cost only if the bars above still pass.

## Stop rules before spend
- Opus pre-run review returns no blocking item.
- Full backend suite green on the exact commit being graded.
- Owner approves graded spend against these criteria.

## Amendments (2026-11-13, after Opus pre-run review ae6a9ce1, verdict RUN AFTER ITEMS 1-6)

### Reproducibility (must hold before spend)
- Sparse flag and judge model pinned in backend/docker-compose.graded.yml (done 2026-11-13). The manifest must record the resolved values, not defaults.
- The answerability-gate setting for the graded run must be read from the graded-6 manifest or logs and recorded. Opus says graded-6 ran with it OFF; config default is ON and the graded compose does not pin it. Unresolved; do not claim either.
- Fingerprint of the served collection (point count, schema, sha of ids) recorded before and after the run.

### Statistics (n matters)
- Showable bar applies to the Wilson 95% LOWER bound, not the point estimate. At n=43 the 95% interval for 85% is roughly 71% to 93%, so a 43-row run cannot show the bar is met. The run needs enough answerable rows for the lower bound to clear the bar, or the result is labelled inconclusive.
- Bars at graded-6 size (n=43): report point estimate and interval; the run is INCONCLUSIVE, not a pass, unless the lower bound clears the bar.

### Definitions
- "Core" = the 116 frozen tuning rows only. The unanswerable and benchmark sets are reported separately.
- "Groups" = scoring groups as named in the unanswerable set file (expected, scoring_group).
- Hub clip metric: the share of served answers that reuse the most-served clip. Fail if any single clip serves more than 3 distinct questions within a run.

### Invalid-run rules
- Any change to code, config, data or prompt after the run starts invalidates it.
- Any missing grader verdict, or any row graded by only one family, makes the run INVALID.
- A run whose manifest lacks any pinned value above is INVALID.

### AI-stage bar (owner request: AI must say very good before human review)
- Both graders >= 90% showable on served rows, lower bound >= 85%.
- Strict reader ANSWERS >= 85%: reported honestly. With one verbatim clip per answer on the current corpus this is not reachable without corpus or selection changes; it is a real gate, so the AI stage will FAIL until it is.
- Second grader is a different model family; the slug must be verified live before the run.

### Not changed
- Human sample of 50 for demo labels stays a separate stage after the AI stage passes.

---

## Resolutions (facts only; no criterion changed)

- **Answerability-gate setting of graded-6 (amendment "Reproducibility", second bullet): resolved 2026-11-13.**
  `~/mukthiguru_attribution_data/graded_runs/20261112-graded-6/manifest.json` records
  `flags.FIRST_PERSON_ANSWERABILITY_CHECK_ENABLED = false`. Graded-6 ran with the gate OFF.
  The value came from `.env`; no compose file pinned it. For graded-7 it is pinned in
  `backend/docker-compose.graded.yml` to the same value so the two runs stay comparable
  (on or off for the product is owner decision T-E1).
- **Source file sha256** (the scratchpad `pre_run_criteria.md` copied above):
  `b8a0504ee5bcf2f33284150e5adf4810e0700c840d89fa71ce9a690ce86baea2`.

## Registration of graded-7 (written 2026-11-14, before the run; changes no criterion)

- **Commit graded:** the `HEAD` of local `main` when the stack is built, recorded as `sha` in the
  run manifest. It is this registration's commit or a docs-only commit on top of it (the planned
  spend row); no code changes after the commit that adds this section. It is **not pushed**
  (owner instruction of 2026-11-13: commit locally, never push), which replaces the runbook's
  "committed and pushed" for this run only.
- **Stack:** `backend/docker-compose.yml` + `backend/docker-compose.graded.yml` from that commit,
  image built from the clean tree, no code bind mounts.
- **Pinned serving values the manifest must show:** `FIRST_PERSON_ACTIVE_COLLECTION=first_person_v10`;
  `FIRST_PERSON_CONTEXT_USE_SPARSE=false`; `FIRST_PERSON_JUDGE_ENABLED=true`;
  `FIRST_PERSON_JUDGE_MODEL=anthropic/claude-haiku-5.5`; `FIRST_PERSON_RELEVANCE_MODEL=anthropic/claude-haiku-5.5`;
  `FIRST_PERSON_RELEVANCE_MIN_SCORE=3`; `FIRST_PERSON_RELEVANCE_TIMEOUT_S=12`;
  `FIRST_PERSON_ANSWERABILITY_CHECK_ENABLED=false` (as in graded-6);
  `FIRST_PERSON_COMPARATIVE_JUDGE_ENABLED=false`; `INTENT_ROUTER_AMBIGUOUS_DOMAIN_ENABLED=false`.
- **Data:** the frozen 116 and the 86-row unanswerable set, the same rows as graded-6. No benchmarks.
- **Graders:** first `anthropic/claude-sonnet-5.5`, second `google/gemini-3.6-flash`, sample fraction 1.0,
  `--allow-shared-judge` not set. If the second grader cannot grade, the run is INVALID; no substitute.
- **Report:** `backend/scripts/ops/graded_registered_report.py` on the run directory. Each bar is
  reported as met, failed or not measured with its point estimate and Wilson 95% interval.
- **Collection fingerprint before the run:** `first_person_v10`, 4,224 points, status green,
  sha256 over the sorted point ids `c96200d7d6104b5c86aaaac7a965813ad4ec6c56443161ec4080b07ad9231835`
  (read 2026-11-13T18:29:08Z). The capture manifest cannot record it (no Qdrant client), so it is
  read again by hand after the run and both values go in the report.
- **What differs from graded-6 in served behaviour:** the standalone-gate changes already on `main`
  (three anaphoric openers, the resumptive "So" rule). Everything added on 2026-11-13/14 is either
  off (comparative judge), inert for single-turn questions (follow-up hint, follow-up cache bypass),
  measurement only (call timing), or routing-neutral (the ambiguous router never completed before).
- **What this run can show (stated before the run):** with about 40 served rows the 85% lower-bound
  bar needs all but one row showable by both graders, so bar 1 is expected to come out FAILED or
  INCONCLUSIVE, and bar 10 (strict reader) is NOT MEASURED because the harness has no such verdict.
  The run is still worth its cost for three things graded-6 could not give: a valid two-family
  grading of the current code, the hub rule after the gate changes, and where the slow judge calls
  spend their time (the new timing line).
- **Spend plan:** capture up to 12 (the preflight's estimate; graded-6 moved the ledger by 2.63),
  grading up to 8. Stop if the run's total passes 25. Ledger rows: `docs/operations/SPEND_LOG_2026.md`.
- **Not in this run:** the comparative judge. It needs its negative-control measurement
  (`scripts/ops/run_negative_controls.py`, 232 calls, worst-case reservation 6.96) and, only if
  that abstains on at least 0.95 of the pairs, a separate registered run.
- **No re-run to pass.** Any change after the capture starts begins a new registered run.
