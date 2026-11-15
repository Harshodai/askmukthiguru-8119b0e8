# Graded-7 runbook (prepared 2026-11-13, NOT executed)

Purpose: run the pre-registered graded-7 on committed code, with two graders from different
model families, every served row graded by both. Criteria: the scratchpad file
`pre_run_criteria.md` (session scratchpad) and the amendments in it. Do not re-run to pass.

Markers: **[PAID]** calls a paid model. **[WRITE]** writes to Qdrant or the repo. **[READ]** no spend, no write.

## 0. Preconditions (owner)
- [ ] Owner approves graded-7 spend. Owner approves the second grader spend. (Both are owner decisions; see handoff.)
- [ ] Owner decides the sparse default for the run. The graded config is pinned to sparse OFF (`backend/docker-compose.graded.yml`).
- [ ] The commit to grade is named: `<COMMIT>`. It must be committed and pushed. Do not grade uncommitted code.
- [ ] Full backend suite is green on `<COMMIT>`.

## 1. Model slugs [READ]
Verified live on 2026-11-13 by listing OpenRouter models (no completions):
- `anthropic/claude-sonnet-5.5` (first grader)
- `google/gemini-3.6-flash` (second grader, different family)
- `anthropic/claude-haiku-5.5` (relevance scorer and judge, pinned in graded compose)

Re-check before the run:
```bash
KEY=$(grep -E "^OPENROUTER_API_KEY=" backend/.env | head -1 | cut -d= -f2-)
curl -s -m 20 -H "Authorization: Bearer $KEY" https://openrouter.ai/api/v1/models | python3 -c "import sys,json; ids={m['id'] for m in json.load(sys.stdin)['data']}; print([s for s in ['anthropic/claude-sonnet-5.5','google/gemini-3.6-flash','anthropic/claude-haiku-5.5'] if s not in ids] or 'all listed')"
unset KEY
```

## 2. Clean image from `<COMMIT>` [READ, no spend]
Build from a clean checkout, not the working tree (no bind mounts for code).
```bash
git worktree add /tmp/graded7-<COMMIT> <COMMIT>   # use a path outside the repo
cd /tmp/graded7-<COMMIT>/backend
docker compose -f docker-compose.yml -f docker-compose.graded.yml build --no-cache backend
docker compose -f docker-compose.yml -f docker-compose.graded.yml up -d --force-recreate --no-deps backend
```
Then from the repo root: `make flush-cache && make verify-cache-empty && make verify-stack-fresh`.
Preflight: `cd backend && .venv/bin/python -m scripts.ops.graded_run_preflight --check-logs`.
Confirm the resolved values in the container: `FIRST_PERSON_CONTEXT_USE_SPARSE=false`, `FIRST_PERSON_JUDGE_MODEL=anthropic/claude-haiku-5.5`, `FIRST_PERSON_RELEVANCE_MIN_SCORE=3`, `FIRST_PERSON_ACTIVE_COLLECTION=first_person_v10`. Record the answerability-gate setting too (unresolved; see handoff).

## 3. Collection fingerprint [READ]
Record point count and `ids_sha256` of `first_person_v10` before the run:
```bash
python3 scripts/ops/collection_fingerprint.py --collection first_person_v10   # prints {points, ids_sha256, collection}
```
Save that output. Do not touch `first_person_v11` or create any collection.

**The fingerprint must also be IN the manifest, or the run is invalid.** `graded_capture.py`
writes `collection_fingerprint: None`, and `graded_registered_report.py` marks any run with a
null fingerprint `run valid: False`. With no producer, no run could ever be a verdict — that is
why `20261114-graded-7` is neither a PASS nor a FAIL (`docs/analysis/ENGINEERING_READINESS_AUDIT_2026-11-13.md` §8.3, F-10).
So immediately after step 4 and before any grading:
```bash
python3 scripts/ops/collection_fingerprint.py --collection first_person_v10 \
    --run-dir ~/mukthiguru_attribution_data/graded_runs/<run-id> --write
```
The post-capture value must **equal** the pre-run value. If it does not, something wrote to the
collection during the run and the capture is not reproducible — record that and stop.
The tool refuses `--write` once `registered_report.json` exists, so a finished run cannot be
retro-fitted into validity; a run found invalid must be re-run.

## 4. Capture [PAID]
```bash
cd backend && .venv/bin/python -m scripts.ops.graded_capture --run-id 20261113-graded-7
```
Writes the capture to `~/mukthiguru_attribution_data/graded_runs/20261113-graded-7/`. Serving calls use OpenRouter (scorer, judge, answerability). Cost is per row.

## 5. Grade [PAID]
Grade both slots on every served row:
```bash
R=~/mukthiguru_attribution_data/graded_runs/20261113-graded-7
cd backend
.venv/bin/python -m scripts.ops.grade_served_answers --rows $R/rows.jsonl --out $R/unanswerable.json --unanswerable
.venv/bin/python -m scripts.ops.grade_served_answers --rows $R/rows.jsonl --out $R/grades.json \
  --pass-bar ../evals/first_person/grading_pass_bar.json --unanswerable-scores $R/unanswerable.json \
  --first-model anthropic/claude-sonnet-5.5 --second-model google/gemini-3.6-flash \
  --sample-fraction 1.0
```
`--allow-shared-judge` must NOT be set. If the second grader is unavailable, the run is INVALID; do not substitute.

## 6. Report [READ]
Report each pre-registered bar as met, failed, or not measured, with the point estimate and the Wilson 95% lower bound. With 116 frozen rows, state whether the run is INCONCLUSIVE for the 85% bar. Report disagreements between graders, not averages.

Add to lessons.md only after the numbers exist.

## 7. Cleanup [READ]
```bash
git worktree remove /tmp/graded7-<COMMIT>   # only if clean; never force-remove
```

## Not part of this runbook
- Qdrant writes, including v11/v12 builds [WRITE]: owner decision.
- Merge to main: owner decision after the numbers.
- Railway resume: owner only.
