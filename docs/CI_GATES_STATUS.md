# CI / quality-gates status — checkpoint §5 task #2

Written incrementally, after every gate landed, per explicit owner instruction
(predecessor was killed by a rate limit and left no status doc). If this
session is also killed, resume from here — do not re-verify what is marked
CONFIRMED below from scratch, but do re-run `make quality` / `npm test`
before trusting any number, since 5 agents are editing concurrently.

## Scope

`.github/workflows/**`, `Makefile`, lint+type config (`backend/pyproject.toml`),
`scripts/ops/loop_validate.sh`, guard test files (`test_wiring_invariants.py`,
`test_settings_guards.py`, `test_metrics_reachability.py`).

## Findings: most of this task was already done before this instance started

A prior instance (killed mid-edit per the checkpoint doc) had already landed
most of the deliverables, uncommitted, on disk. This instance's job was to
**verify each one empirically** (not just read the code) and fill genuine gaps.

| Deliverable | Status | Evidence |
| :--- | :--- | :--- |
| F-GATE-1 (`loop_validate.sh` cannot fail) | **ALREADY FIXED, RE-VERIFIED EMPIRICALLY** | See below — the ECC audit's F-GATE-1 finding was a **false positive**. |
| Coverage floor (backend) | **ALREADY DONE** | `backend/pyproject.toml` `[tool.coverage.report] fail_under = 59`, ratcheted below the measured 61.38% baseline (documented in the file's own comment). |
| mypy ratchet | **ALREADY DONE** | `backend/tests/test_type_check_baseline.py` (new file, untracked before this session) — shells out to mypy, baseline 1335 errors, `strict=false` unchanged, fails only on regression. Wired into `pytest` (no separate CI step needed) and into `make type-check` / `make quality`. |
| Lint enforced in CI | **ALREADY DONE** | `.github/workflows/lint-test.yml`: `ruff check .`, `ruff format --check .`, `bandit ...`, `eslint .` all run as plain steps with no `|| true` — a failure fails the job. |
| Perf-regression guard | **ALREADY DONE** | `backend/tests/test_performance_budgets.py` (new file, untracked before this session) — deterministic wall-clock budget on `_fuse_docs` / `stable_document_key` (hot retrieval-fusion path), budgets ~30-50x measured baseline. Runs as a normal pytest test, no live services. |
| `make quality` | **ALREADY DONE** (backend) | `Makefile` `quality` target: ruff lint, ruff format check, bandit, JWT-backdoor guard, then pytest with coverage (which also runs the mypy ratchet and perf-budget tests as part of the suite). |
| Vitest coverage thresholds | **DONE THIS SESSION** | Was genuinely absent. Added `test.coverage` block to `vitest.config.ts` (v8 provider, thresholds a few points below the measured 2026-09-16 baseline: statements 52/branches 42/functions 42/lines 54, measured 54.57/44.5/44.8/57.14) and changed `package.json`'s `test` script to `vitest run --coverage` so `npm test` — what CI, `loop_validate.sh`, and every local dev already run — enforces it without a separate script or workflow edit. |
| Class-7 generic guard (test that re-implements the logic it guards) | **DELIBERATELY NOT BUILT — see below** | Attempted an AST-based generic guard, measured 21% false-positive rate (285/1339 test functions) against real, legitimate tests. Not shipped. |

## F-GATE-1 — re-verified empirically, confirmed a false positive

The task brief (and the ECC audit) claimed `run_gate`/`run_shell_gate` in
`scripts/ops/loop_validate.sh` end in `return 0` under `set +e`, making the
script "mechanically incapable of failing." **This is not true of the whole
script.** `return 0` in those two helper functions only tells the *matrix
runner* to keep going after one gate fails — the real verdict is an `awk`
aggregation at the bottom of the file that turns any non-zero row in
`$SUMMARY` into `LOOP_RESULT=FAIL` + `exit 1`. That aggregation already
existed at `HEAD` (before any of today's edits — verified via
`git show HEAD:scripts/ops/loop_validate.sh`).

A prior instance had already re-audited this (see the comment block at the
top of the file, "re-audited 2026-09-16, filed twice as a swallowed-exit-code
bug and twice wrongly") and hardened the two things that WERE real gaps:
a missing backend `.venv` silently recording as `SKIP` instead of a hard
failure, and an empty `$SUMMARY` (zero gates ran) not being treated as a
failure.

**Verified empirically in this session** (not asserted from reading), per the
task's own acceptance criterion:

1. Introduced a real ruff violation (`backend/app/_gate_test_violation.py`
   with unused imports + unused local — 5 real ruff errors).
2. Ran `LOOP_EVIDENCE_DIR=/tmp/gate_test_run bash scripts/ops/loop_validate.sh`.
3. Result: `backend_ruff` row recorded exit code `1`; final output
   `LOOP_RESULT=FAIL`, script exit code `1`.
4. Deleted the test file afterward (not part of the deliverable).

Full gate summary from that run (some pre-existing failures are from the 5
concurrent agents editing this repo right now, not from my test file):

```
repository_state    0
json_settings        0
diff_check            0
frontend_unit        0
frontend_lint        1   (pre-existing)
frontend_typecheck   2   (pre-existing)
frontend_build       0
bundle_budget         0
backend_focused       4   (pre-existing)
backend_ruff          1   (MY test violation)
backend_bandit        1   (pre-existing)
regex_safety           0
backend_compile        0
backend_full          SKIP (opt-in, FULL_BACKEND not set)
LOOP_RESULT=FAIL
```

**Conclusion: no code change was needed for F-GATE-1.** The finding should be
marked resolved / false-positive in `docs/RUTHLESS_PLAN_10_10.md`'s Phase 0
list, not re-fixed.

## Class-7 generic guard — investigated, not shipped

The task asked for a guard covering "a test that re-implements the logic it
guards and would pass with the module deleted" (defect class 7 from the
session checkpoint), on top of the two known concrete instances already fixed
by the prod-hardening agent (`test_onnx_reranker_thread_bound.py`,
`test_healthz_grace_masking.py` — both now assert against the real imported
module rather than a recomputed formula).

Tried a static AST heuristic: for every `backend/tests/test_*.py` file that
imports symbols from a production package (`app`, `rag`, `domain`, `services`,
`routers`, `ingest`, `schemas`, `tasks`, `guardrails`), flag any `test_*`
function containing an `assert` that never references any of those imported
symbols by name.

**Measured result: 285 of 1339 scanned test functions flagged (~21%).**
Sampled the output — the overwhelming majority are legitimate FastAPI
integration tests that exercise production code through
`TestClient.post(url, ...)` (an HTTP call by string route, not a direct
Python symbol reference), e.g. `test_admin_api.py::test_promote_admin_success`.
A generic name-reference heuristic cannot distinguish "recomputed the formula
locally" from "called the real code through an HTTP client" — the two look
identical in an AST that only sees names.

Per this task's own instruction ("a guard of its own if you can write one
that is not itself noise") and the ponytail rule against shipping noisy
scaffolding: **not adding this guard.** The two concrete instances found this
week already have targeted, low-noise regression tests (asserting against the
real module, documented inline as guarding exactly this failure class); a
third instance would get the same targeted treatment rather than a blanket
static sweep.

## Vitest coverage thresholds — verified empirically

1. Ran `npm test` (now `vitest run --coverage`) clean: exit 0, measured
   54.58/44.51/44.76/57.15 (statements/branches/functions/lines) against
   floors 52/42/42/54. Passes.
2. Temporarily bumped the `statements` floor to 99 in `vitest.config.ts`,
   re-ran: exit 1, `ERROR: Coverage for statements (54.57%) does not meet
   global threshold (99%)`. Reverted immediately (`git diff vitest.config.ts`
   confirmed clean revert to `statements: 52`).

## Verification run — `backend/.venv/bin/python -m pytest -q`

Ran from `backend/`. Real result: **6 failed, 4452 passed, 12 skipped, 3
warnings in 450.80s**. Attributed, not fixed (all outside this task's file
boundary or caused by concurrent agents, per the coordinator's explicit
instruction not to absorb or hide these):

| Failure | Cause | Mine to fix? |
| :--- | :--- | :--- |
| `test_settings_guards.py::test_getattr_names_are_declared` — new undeclared `getattr(settings, 'citation_span_overlap_floor', ...)` | Another agent added a new setting read via `getattr` without declaring it on `Settings`, almost certainly in `rag/nodes/citation_extractor.py` (explicitly off-limits to this task) | No — file boundary. This IS the class-6/settings guard working correctly, catching real concurrent drift. |
| `test_redis_rate_limiter.py` x4 (`test_lua_retry_after_preserves_fraction`, `test_redis_key_names_are_digested`, `test_concurrent_calls_never_exceed_max_requests`, `test_async_live_redis_uses_asyncio_client`) | Live-Redis integration tests for the Lua-script rate limiter; failures look like real behavior regressions (e.g. `test_concurrent_calls_never_exceed_max_requests` got 24 successes instead of 5 — an atomicity break), not flake. Not this task's scope (`app/core/limiter.py` / auth rate limiting, not CI-gate config) and not touched by this session. | No — another agent's in-flight edit, most likely to the rate-limiter's Lua script or Redis wiring. |
| `test_lint_baseline.py::test_ruff_format_debt_does_not_regress` — 322 > baseline 318 at the moment pytest ran | Ratchet on `ruff format` debt; count moves as 5 concurrent agents touch files without reformatting. **Partially addressed**: reformatted the 3 files in this task's own scope that were unformatted (`tests/test_wiring_invariants.py`, `tests/test_type_check_baseline.py`, `tests/test_metrics_reachability.py` — the latter two are new files from the prior instance). Repo-wide count dropped to 316/1013 immediately after (re-measured via `ruff format --check .`), which is back under the 318 baseline, but this is inherently racy while 5 agents edit concurrently — do not chase it further; whoever lands last should re-run `pytest tests/test_lint_baseline.py` before merge. | Partially — fixed my own scope's contribution; did not mass-reformat the other ~313 files (outside scope, would collide with in-flight edits from other agents). |

## Verification run — `make quality`

Ran from repo root. **Result: FAILED at step [1/5] Ruff lint, exit 2 — 678
errors across 35 files** (mostly `F401` unused-import and `I001`
unsorted-import, the shape of mid-refactor debris, not a systemic defect).

This is a real, correctly-reported failure and — bonus verification — proves
`make quality` also does not silently pass: it stopped at step 1 rather than
running the remaining 4 steps (format check, bandit, JWT-backdoor guard,
pytest+coverage).

**None of the 35 flagged files are in this task's scope or were touched by
this session.** Checked file-by-file against my own edits and the guard
files this task owns (`test_wiring_invariants.py`, `test_settings_guards.py`,
`test_metrics_reachability.py`, `test_type_check_baseline.py`,
`test_performance_budgets.py`, `loop_validate.sh`) — zero overlap. The 35
files cluster in `services/canonical_memory/**`, `tests/security/**`
(canonical-memory canary/cost/migration/shadow/red-team tests), and a spread
of unrelated test files (`test_railway_cleanup.py`, `test_feedback.py`,
`test_llm_budget_guard.py`, etc.) — none of which this task's boundary
covers. These belong to the other agents/workstreams editing this tree
concurrently (per the checkpoint doc's §5 item 1 "unified benchmarks" and
other unnamed in-flight work).

`ruff check .` has **no debt-ratchet baseline** the way `ruff format`
(`test_lint_baseline.py`) and `mypy` (`test_type_check_baseline.py`) do — it
is a hard "zero lint errors" gate, matching CI's `lint-test.yml` step (also a
plain `ruff check . --output-format=github` with no baseline). That is by
design for actual lint errors (unused imports, undefined names) — those
should never accumulate as tolerated debt the way format-only whitespace
does. The correct fix is on whoever owns those 35 files, not a new baseline
carve-out; adding one would silently permit unused-import debt in exactly
the files that most need import hygiene.

**Not fixed by this session** — out of file-boundary, and 5 agents mid-edit
in exactly those files makes a drive-by fix likely to collide with in-flight
work. Flagging for the owning workstream instead of absorbing the fix.

## Summary

All 7 explicit DELIVER items were verified; 6 were already done by a prior
instance (F-GATE-1 found to be a false positive on re-verification, coverage
floor, mypy ratchet, perf guard, lint-in-CI, `make quality` backend battery).
This session's own contribution: Vitest coverage thresholds (genuinely
absent, now added and empirically verified to both pass at baseline and fail
above it), reformatted this task's own 3 guard/CI files that had drifted out
of `ruff format`, and a measured, documented decision NOT to ship a
class-7 generic guard (21% false-positive rate against the real suite).

Both final verification runs (`pytest -q`, `make quality`) surfaced real
failures — all attributed to the other 4 concurrent agents' in-flight edits,
none inside this task's scope, none fixed by this session per the explicit
file-boundary and non-absorption instructions.
