# Revalidation — 2026-11-05

Scope: `audit-output-2026-11-04/25-phase-specific-coding-prompts.md` §1 for branch
`feature/audit-strengthen-rag-qdrant`, head `717296f9e0ef033a3ded7ac913a9809f38460db0`
(`docs(audits): reserve high-risk tasks for a supervised stronger model`). Read-only except where
stated. This session was named by the owner for **T7-01 only** (`IMPLEMENTATION-AGENT-PROMPT.md` §0j),
so no other task was started.

## 1. Head and CI

| Item | Result |
|---|---|
| Branch head at start | `717296f9` (local `9e17370d` was 43 commits behind; fast-forwarded, no rewrite) |
| `Lint & Test` | **completed / success** |
| `Production Readiness` | **completed / success** |
| `Main Hard Gates` | completed / success |
| `Security Audit` | completed / success |
| `CodeQL Analysis` | completed / success |
| `Benchmark Gate (Golden Eval)` | completed / success |
| `Eval Gate (RAGAS Faithfulness + Context Metrics)` | completed / success |
| `Migration Revert Block Check` | completed / success |
| `Golden-25 First-Person Attribution Gate` | completed / success |
| `Pre-launch gate` | **completed / failure** — `UI device matrix (firefox)`, `(Mobile Safari)`, `(webkit)` |

The Pre-launch failure is **not a regression from this branch**. `main@46b808fb` fails the same
three device-matrix jobs, and so did the two earlier `main` runs (`99d09c14`, `9e50fe56`). This is
the red e2e matrix already recorded in `01` §10 and `22a` §7 ("The e2e matrix is red today on
Firefox, WebKit and Mobile Safari"). Nothing in this session touched `src/`, e2e specs or CI config.

No test was edited, skipped or re-baselined to reach these results.

## 2. T7-01 preconditions (the task this session is named for)

`IMPLEMENTATION-AGENT-PROMPT.md` §0j requires "golden-output snapshots recorded for the frozen bank
and the PR suite before any change". Checked on the head:

| Named harness | State on `717296f9` |
|---|---|
| `evals/pr_suite/` (T2-01) | **absent** |
| `evals/retrieval_bank/` (T2-02) | **absent** |
| Frozen-bank runner | `scripts/run_first_person_benchmark.py` — POSTs to `http://localhost:8000/api/first-person/query`; needs the live stack, the served collection and LLM spend |

So the literal precondition could not be met. Owner decision **Q-T7-01-A** (2026-11-05,
`decision-log.md` §3) replaces it with an offline characterization matrix recorded on the pre-split
code: `backend/tests/test_first_person_pipeline_golden.py` plus
`backend/tests/golden/first_person_pipeline/*.json`. It is stated in the module docstring and in the
commit body that this is **not** the frozen bank. Q-T7-01-B/C/D settle the PR shape, the route and
field coverage, and the Step 2c scope.

## 3. Symbols named by the audit, re-located in code

| Audit claim | Verified | State |
|---|---|---|
| CQ-001: `execute` is 2,145 lines | `def execute(` at `backend/services/first_person_pipeline.py:3523`, `return res` at `:5668` | **STILL TRUE** (2,146 lines incl. both ends) |
| 15 step comments inside `execute` | steps 1, 1b, 1c, 2, 2b, 2c, 3, 4, 4b–4d, 5, 6, then the assembly tail | STILL TRUE |
| 5 request-local closures | `_answerability_withheld_result`, `_search`, `is_mock`, `_build_citation`, `_abstain_unverified` | STILL TRUE |
| T7-01 acceptance: "golden-output snapshot identical before and after" | `20-ordered-engineering-roadmap.md:155` | STILL TRUE — the gate now exists (T7-01a) |
| T7-02 depends on T7-01 | `20-...roadmap.md:156`, `21` T7-02 | STILL TRUE — not started (reserved, and it needs T7-01 merged) |

## 4. Baseline test state (local, `.venv`, before any change)

```
backend/tests/test_first_person_pipeline.py            89 passed in 4.01s
tests/test_first_person_pipeline_golden.py            18 passed (after T7-01a)
five first-person files combined                     194 passed, 1 skipped in 3.82s
```

## 5. What this session changed

- `T7-01a` — the offline characterization matrix and its recording script (tests only; no
  application code touched). Findings closed: none (it is the precondition for CQ-001).
- Decision log and unresolved-question register updated with Q-T7-01-A/B/C/D.

## 6. Not done (and why)

- No other task from §0i group A or B was started: the owner named this session for T7-01 only.
- T7-02 is reserved and additionally requires T7-01 to be merged.
- No Qdrant/Supabase/Memgraph/OKF write, no deploy, no live benchmark, no repository setting
  changed. D-01, D-02 and the rest of §0i group B remain open and unanswered for the tasks they
  block.
