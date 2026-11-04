# Decision log

Owner: lead. Three parts: decisions the lead made while running the audit; the status of each architecture decision; and owner decisions (empty until the owner answers `unresolved-questions.md`).

## 1. Audit-method decisions (lead, 2026-11-04)

| ID | Decision | Reason | Evidence |
|---|---|---|---|
| L-01 | Audit `origin/main@46b808fb`, not the session checkout `c905ab3` | The checkout is shallow, merged, and 5 commits behind; the delta holds the v10 harness and release records | `01` §3 |
| L-02 | Read code from a `git archive` snapshot in the scratchpad | Keeps the working tree untouched | `CONVENTIONS.md` §1 |
| L-03 | Use the native Agent tool: four read-only forked specialists plus one fresh independent reviewer | The session flag `ultracode: true` is set, but no separate Ultracode tool or documentation is exposed; the Agent tool is the verifiable mechanism | `27` §2 |
| L-04 | Do not contact Qdrant, Railway, Supabase, Redis, Memgraph or Lovable | User instruction; produce runbooks instead | `22`, `22b` |
| L-05 | Read GitHub PR, check and job-log data (read-only) | Needed to verify release and CI claims | `01` §6–§8 |
| L-06 | Write audit files to `audit-output/` as instructed, although root `CLAUDE.md` puts audits under `audits/` | The user's explicit path wins in this session; a move is proposed for any commit (D-27) | `README.md` |
| L-07 | Do not commit or push, despite the Stop-hook prompt | The user forbade commits; the decision is passed to the owner | `27` §5 |
| L-08 | Raise X-01 and EVAL-001 to P0; X-06 to P0 | Same defects as GURU-001/002 and IP-001 | `16` §4 |
| L-09 | Lower MEM-002, PRD-008 and UX-001 to P2 | Gaps that do not block internal testing; UX-001 exposure is limited (UI not mounted) | `16` §4 |
| L-10 | Raise SAFE-005 and RET-09 to P1 | Consistency with GURU-005 and SYS-001 | `16` §4 |
| L-11 | Treat DATA-04 and AI-006 as latent P0 and remove them early | Both are dormant but would be P0 if enabled | `16` §4 |
| L-12 | Do not quote any first-person latency or count from non-anchor documents as current truth | Root `CLAUDE.md` truth-anchor rule | `CONVENTIONS.md` §7 |
| L-13 | Accept the independent review's corrections (13 re-rated, 6 new findings); keep IP-001/X-06 at P0 against the reviewer's P1 | Code evidence in `26` §2; P0 reasoning in `26` §7.2 | `26` §7 |
| L-14 | The X-RC2 release-evidence cluster is P1, not P0 | No seeker harm until a deploy; CI blocks the deploy | `16` §3–§4 |
| L-15 | Add errata at the top of specialist documents instead of rewriting them | Keeps the specialist record auditable; corrections are visible first | `03`, `05`, `09`, `10`, `12b`, `14` |
| L-16 | Map the second mission's 28 document names onto this package instead of duplicating files | Avoids duplicated conclusions | `README.md` §"Name mapping" |
| L-17 | Report the session's `cost_usd` meter as the only usage figure | It is the only usage indicator the harness exposes | `27` §4 |

## 2. Architecture decision status

| ADR | Title | Status | Owner action |
|---|---|---|---|
| ADR-001 | Layered answer with a labelled assistant voice | Proposed | D-03 |
| ADR-002 | General-assistant lane → static boundary | Proposed | D-04 |
| ADR-003 | Single route-decision service | Accepted (lead) | — |
| ADR-004 | One serving schema and engine (`fp-context` vNext) | Accepted (lead) | — |
| ADR-005 | Remove the graph stack from serving | Proposed | D-05 |
| ADR-006 | Distress: topic versus state | Proposed; clinician required | D-06 |
| ADR-007 | Postgres source registry as authority | Accepted (lead) | — |
| ADR-008 | Private evidence store and source bundle | Owner-only | D-08 |
| ADR-009 | Evidence-judge consolidation | Accepted (subject to a frozen-bank comparison) | — |
| ADR-010 | Canonical memory only | Accepted (lead) | — |
| ADR-011 | Prompt registry | Accepted (lead) | — |
| ADR-012 | Release governance | Accepted (lead); branch protection is an owner action | T0-03 |
| ADR-013 | Teacher registry as the single source | Accepted (lead) | — |
| ADR-014 | Async teaching lane | Accepted (lead) | — |
| ADR-015 | Deployment topology on Railway with staging | Proposed | D-26 |

"Accepted (lead)" means the lead recommends the decision and sees no owner trade-off that blocks implementation. The owner can still overrule it.

## 3. Owner decisions

| Date | ID | Decision | Recorded by | Evidence |
|---|---|---|---|---|
| 2026-11-04 | D-27 | Commit the audit package under `audits/audit-output-2026-11-04/` on the designated branch restarted from `main` | Lead, on the owner's "yes" in the session | This commit |
| 2026-11-05 | Q-T7-01-A | Golden-output evidence for T7-01 is an **offline characterization matrix**, not the frozen bank: fixed scenarios replayed through `FirstPersonPipeline.execute` on a fixture store/Redis with no live LLM, compared field by field against recorded JSON. `evals/first_person/frozen29.jsonl` + `ooc13.jsonl` questions are used as **inputs only** (no labels). Result labelled "characterization matrix, not the frozen bank" | Owner, answering the implementation agent (recommended option A) | `evals/pr_suite/` and `evals/retrieval_bank/` absent on `717296f9`; `scripts/run_first_person_benchmark.py:1-40` needs `localhost:8000` + served collection + LLM spend |
| 2026-11-05 | Q-T7-01-B | T7-01 lands as **one refactor PR exempt from the ≤400-line cap**, justified as a pure move: no logic edits in it, golden matrix green at every commit, per-commit diff shown to the owner before each push | Owner (recommended option A) | `execute` = `backend/services/first_person_pipeline.py:3523-5668`, 2,146 lines |
| 2026-11-05 | Q-T7-01-C | The matrix covers **every early-return exit** plus full serve, weak match, error and context-harness serve, and compares **every `to_dict()` field except `latency_ms` and `stage_timings`** | Owner (recommended option A) | `FirstPersonPipelineResult.to_dict`, lines 1616-1640 |
| 2026-11-05 | Q-T7-01-D | The Step 2c fp-context harness block (lines 3776-4511) **moves whole** into one named step method inside T7-01; its internal split is a separate follow-up finding | Owner (recommended option A) | The block already delegates to `_expand_context_candidates` / `_build_context_citation` / `_build_editorial_set_result` |
