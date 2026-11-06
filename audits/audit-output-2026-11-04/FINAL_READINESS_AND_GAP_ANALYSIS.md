# Final package index and release decision (2026-11-05)

Head `c9b42d3e` on `feature/audit-strengthen-rag-qdrant`. This is the entry point for the final verification pass of 2026-11-05. It gives the release decision, then links every file the pass produced. Evidence labels: `CONVENTIONS.md` §3. No application code, configuration, test or migration was changed by this pass.

This file replaces its own first draft, which was written under a budget limit. Corrections to that draft are listed in `FINAL_AUDIT_GAP_ANALYSIS.md` §1.

## 1. Release decision

| Gate | Decision | Why | Full gate |
|---|---|---|---|
| A. Railway staging (closed testers) | **NO (conditional)** | CI fails on `c9b42d3e` (every workflow failed in the GitHub Actions run list the lead checked on 2026-11-05, [V-GIT]). The only corpus copy is on the owner's Mac (DATA-01). Qdrant hosting (D-26) and the serving posture (D-14) are undecided. The IaC declares one service with no worker, beat or Redis. Railway drain time is 0 s, release identity is missing under `railway up`, and Celery modes ignore SIGTERM. A fresh v10 build would serve nothing (DATA-20). | `FINAL_RAILWAY_STAGING_READINESS.md` (A1-A21) |
| B. Production (invited users) | **NO** | Gate A not met. 2 P0 open (IP-001, X-06; D-01). Alerts partly broken (rules read metrics nothing emits). No restore drill. No real-provider load test. A store error can report `verification.passed=True`. | `FINAL_PRODUCTION_RELEASE_READINESS.md` (B1-B18) |
| C. Public release | **NO** | Gate B not met. No clinician sign-off, rights approval, guru review, 299 human gold labels, or native-speaker review. | `FINAL_PRODUCTION_RELEASE_READINESS.md` (C1-C12) |

The conditions that turn Gate A into a yes are, in order: CI passes; the snapshot is copied off the Mac and loaded on the chosen host; D-26, D-14, D-29 and D-30 are decided; Phase 1 to Phase 3 of `FINAL_CODING_AGENT_EXECUTION_PACKAGE.md` land; Gate A A1-A21 pass on Railway.

## 2. Pending work in one line each

- P0: 2 open (IP-001, X-06), both waiting on D-01 and D-02.
- P1: 47 in the index: 11 closed, 10 partial, 6 open, 8 need an owner decision, 11 need a human, 1 needs live infrastructure.
- P2: 81: 14 closed, 12 partial, 19 open, 28 need a decision, 7 need a human, 1 live.
- P3: 22: 8 closed, 5 open, 8 need a decision, 1 human.
- New defects found in this pass and not yet indexed: see `FINAL_AUDIT_GAP_ANALYSIS.md` §2 (DATA-20 to DATA-27, Railway, alerting, answer honesty, harness, MEM-007 to MEM-012).

Source: `FINAL_PENDING_WORK_REGISTER.md`.

## 3. The 10 FINAL files

| File | Purpose |
|---|---|
| `FINAL_AUDIT_GAP_ANALYSIS.md` | What the audit and this pass got wrong or missed; new defects; pillar and A-J coverage; completeness challenge |
| `FINAL_RAILWAY_STAGING_READINESS.md` | Every Railway item classified; Gate A A1-A21 (authoritative IDs) |
| `FINAL_PRODUCTION_RELEASE_READINESS.md` | Gates B and C; quality claims allowed at each gate |
| `FINAL_PENDING_WORK_REGISTER.md` | Status of every finding at `c9b42d3e`, with proof; next tasks; items by decision, human and live system |
| `FINAL_SPECIFICATION_COMPLETENESS_MATRIX.md` | Rating of each specification; cross-spec conflicts; per-task readiness elements |
| `FINAL_LESSONS_AND_DOCUMENTATION_REVIEW.md` | Full `lessons.md` classification (1,468 lessons); recurring failures; guard coverage; documentation contradictions; applied doc edits |
| `FINAL_QDRANT_LIVE_VALIDATION_CHECKLIST.md` | Owner-run, read-only-first Qdrant checks with commands and pass conditions |
| `FINAL_CODING_AGENT_EXECUTION_PACKAGE.md` | First instruction; phase order with task IDs; rules; handoff gaps |
| `FINAL_DECISION_AND_RISK_REGISTER.md` | Every open decision sorted by the gate it blocks; 15 ranked risks |
| `FINAL_USAGE_AND_VERIFICATION_LOG.md` | Usage, agents, files read and changed, verification and independent review |

## 4. The specifications (`specifications/`)

| Requested | File | Status |
|---|---|---|
| 6.1 | `INGESTION_AND_CONTENT_PROCESSING_SPEC.md` | Partial |
| 6.2 | `RETRIEVAL_AND_RAG_SPEC.md` | Partial |
| 6.3 | `MULTI_VIDEO_TEACHING_SYNTHESIS_SPEC.md` | Variant A ready in shadow mode; Variant B decision-blocked (D-03) |
| 6.4 | `DATA_QUALITY_AND_CROSS_STORE_CONSISTENCY_SPEC.md` | Partial (static checks ready) |
| 6.5 | `GURU_KNOWLEDGE_AND_KNOWLEDGE_GRAPH_SPEC.md` | Partial |
| 6.6 | `AI_HARNESS_PROMPT_AND_CONTEXT_SPEC.md` | Partial |
| 6.7 | `SPIRITUAL_ANSWER_QUALITY_AND_RESPONSE_CONTRACT.md` | Partial |
| 6.8 | `PERSONAL_MENTOR_MEMORY_AND_PERSONALIZATION_SPEC.md` | Partial |
| 6.9 | `COMPLETE_FR_NFR_AND_ACCEPTANCE_MATRIX.md` | Complete as a matrix |
| 6.10 | `PRODUCTION_RELIABILITY_SECURITY_AND_COST_SPEC.md` | Partial |
| 6.11 | `RAILWAY_DEPLOYMENT_AND_PRODUCTION_OPERATIONS_RUNBOOK.md` | Specification; nothing run on Railway |
| Extra | `ARCHITECTURE_DECISION_RECORDS_HISTORICAL.md` | 16 historical ADRs; do-not-reintroduce list |

## 5. Reading order

| Reader | Order |
|---|---|
| Owner (decisions, 30 min) | This file -> `FINAL_DECISION_AND_RISK_REGISTER.md` §2.1 -> `FINAL_QDRANT_LIVE_VALIDATION_CHECKLIST.md` -> `FINAL_RAILWAY_STAGING_READINESS.md` Gate A |
| Coding agent | `FINAL_CODING_AGENT_EXECUTION_PACKAGE.md` §1 -> the spec named by the task |
| Reviewer of this pass | `FINAL_AUDIT_GAP_ANALYSIS.md` -> `FINAL_USAGE_AND_VERIFICATION_LOG.md` |

## 6. Other files changed by this pass

- `lessons.md`: new lessons at the top (insert only).
- `findings-index.md`: one dated pointer line to the pending register.
- `docs/DEVELOPER_GUIDE.md`, `docs/RAG_RUNTIME_DAG.md`, `docs/architecture/README.md`: small corrections; each is in the change log of `FINAL_LESSONS_AND_DOCUMENTATION_REVIEW.md` §7.
- `docs/plans/PROD_READINESS_TASK_LIST_2026-10-11.md`: dated pointer to the pending register.
- `README.md` (this package), `IMPLEMENTATION-AGENT-PROMPT.md` §0u, `unresolved-questions.md`: pointers to this package.

## 7. Commits that landed after the verification head (re-verify before relying on a status)

This package was verified against `c9b42d3e`. Before it was committed, 21 commits landed on the branch (`2edee1c4` to `a7be7e65`, batches 9 to 13). This package did not verify them. Their commit messages claim the work below. A coding agent must re-check each named finding against the code at the current head and update `FINAL_PENDING_WORK_REGISTER.md`.

| Commit | Claimed work | Findings named in the message | Parts of this package that may now be stale |
|---|---|---|---|
| `2edee1c4`, `addeef77` | T6-02 memory signals for clip diversity; batch 9 record (T4-05, T1-18, T6-02) | MEM-002, UX-005 (T1-18) | Memory spec §2; coding package phase 9 and task 5 of the register's next-15 list |
| `649ea2c3` | T6-03 user-stated preferences replace the LLM persona | MEM-004 | Memory spec; register next-15 task 12 |
| `2a91817f` | T6-10 honest product copy | PRD-010, UX-009, UX-011 | Register |
| `2318a368` | T7-03 one LLM gateway | SYS-003, CQ-002, AI-005, CQ-014 | Harness spec §2 (provider inventory); D-17; register (SYS-003 was reserved under T7-02: check what T7-03 actually closes) |
| `a12ea273` | T7-04 cache key versioning | CQ-003 | Register next-15 task 14 |
| `924419df` | T7-05 exception and import ratchets | CQ-006, CQ-007 | Register next-15 task 13 |
| `1503e5f2` | T8-01 teacher registry extensibility and literal-name guard | GURU-010, CQ-009 | Guru spec §2 (hard-coded literal table, ADR-013 status); gap analysis §2 GURU row; RK-13 |
| `49c92325` | T1-14 pin Memgraph and Autoheal images | SEC-006 | Harness spec task 12 and gap analysis §2 (`memgraph:latest`) |
| `2c81a2d1` | T1-15 doc-versus-code check of pipeline order | CQ-009 | Gap analysis §5 item 10; RK-10; lesson L-DOC-PROSE-HAS-NO-PIN-TEST-1 (update note added) |
| `4af5e711`, `4c1c3993` | Memory plane inventory (ADV-06); batch 12 record (T1-14, T1-15, T6-01) | ADV-06 | Memory spec §2 |
| `5db34855` | T4-07 verified helplines and freshness window | SAFE-004 | Register (SAFE-004 listed as human-only) |
| `a33d6b8d` | T6-04 clip issue reporting and saved answers API | PRD-006, FR-SAVE-01, FR-CORR-01 | Memory spec saved-wisdom tasks; FR/NFR matrix rows FR-SAVE-01, FR-CORR-01; answer contract D-PQ7 (check whether a clip id now reaches the client) |
| `4eb04ae8` | T3-07 canonical teacher IDs | DATA-13, GURU-013 | Data-quality spec; guru spec; register |
| `7f63fe4c` | Guard fix: exception handling in feedback; settings collection-name lookup | — | Reliability spec §2 citations into `backend/app/api/feedback.py` (line numbers may have moved) |
| `a7be7e65`, `9d0dce53`, `a4b0aca8`, `19ad9533` | Scorecard and batch records | — | `00` scorecard is newer than this package's gate summary |

Line numbers cited in this package refer to `c9b42d3e`. Files changed by these commits may have shifted.
