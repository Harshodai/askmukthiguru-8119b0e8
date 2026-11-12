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

- Counts below are at head `fb5cab0f` (verified 2026-11-06). Counts at `c9b42d3e` are in brackets. Source: `FINAL_PENDING_WORK_REGISTER.md` §1.
- P0: 2 open (IP-001, X-06), both waiting on D-01 and D-02. Not changed.
- P1: 47 in the index: 11 closed [11], 12 partial [10], 5 open [6], 8 need an owner decision [8], 10 need a human [11], 1 needs live infrastructure [1].
- P2: 81: 15 closed [14], 22 partial [12], 8 open [19], 28 need a decision [28], 7 need a human [7], 1 live [1].
- P3: 22: 9 closed [8], 3 partial [0], 2 open [5], 7 need a decision [8], 1 human [1].
- All defects: 152: 35 closed [33], 37 partial [22], 15 open [30], 45 need a decision [46], 18 need a human [19], 2 live [2]. 117 are not closed.
- New defects found in this pass and not yet indexed: see `FINAL_AUDIT_GAP_ANALYSIS.md` §2 (DATA-20 to DATA-27, Railway, alerting, answer honesty, harness, MEM-007 to MEM-012).

- Added by the final verification pass and registered in `findings-index.md` (2026-11-05/06): 103 findings: 0 P0, 35 P1, 57 P2, 11 P3 (first pass 75, second pass 22, third pass 6). All open. Details: register §10, §10.1, §10.2.

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
| `FINAL_USAGE_AND_VERIFICATION_LOG_APPENDIX_FILES.md` | Exact list of repository files read and changed, and web sources used, extracted from the tool-call logs (added 2026-11-06) |
| `FINAL_AUDIT_DOCUMENT_INVENTORY.md` | Part 3 inventory of every audit document: complete, evidence, links, conflicts, missing sections, implementable, needs update (added 2026-11-06) |

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
| Extra (2026-11-06) | `MOBILE_APPS_REVIEW_AND_RELEASE_SPEC.md` | Review: 15 findings (6 P1); not submission-ready; Gate C |
| Extra (2026-11-06) | `K8S_MANIFESTS_REVIEW.md` | Review: manifests are not a live path; 9 findings (1 P1, committed default passwords); D-PK8S1 |
| Extra (2026-11-06) | `LOVABLE_SYNC_PATH_REVIEW.md` | Lovable bot self-merges to `main`; 8 findings (3 P1); D-24 proposal: PR-only with required checks |
| Extra (2026-11-06) | `LOAD_AND_COST_MODEL.md` | Model, not a measurement: cost per useful answer about $0.002 to $0.08 [INF]; about 7 concurrent requests per 4-vCPU replica [INF]; Locust staging plan for B8; SYS-014 budget-cap finding |
| Extra (2026-11-06) | `ACCESSIBILITY_AUDIT_AND_REQUIREMENTS.md` | WCAG 2.2 AA audit with axe runtime run on 4 pages; 17 findings (7 P1); C7 not met |

## 5. Reading order

| Reader | Order |
|---|---|
| Owner (decisions, 30 min) | This file -> `FINAL_DECISION_AND_RISK_REGISTER.md` §2.1 -> `FINAL_QDRANT_LIVE_VALIDATION_CHECKLIST.md` -> `FINAL_RAILWAY_STAGING_READINESS.md` Gate A |
| Coding agent | `FINAL_CODING_AGENT_EXECUTION_PACKAGE.md` §1 -> the spec named by the task |
| Next two sessions (2026-11-06) | Opus: `NEXT_SESSION_PROMPT_OPUS.md` (safety, honesty, security, data integrity, review of T7-02). Sonnet: `NEXT_SESSION_PROMPT_SONNET.md` (Railway, operations, configuration, accessibility, k8s, Lovable, guards, docs). Disjoint file ownership; both can run in parallel. |
| Reviewer of this pass | `FINAL_AUDIT_GAP_ANALYSIS.md` -> `FINAL_USAGE_AND_VERIFICATION_LOG.md` |

## 6. Other files changed by this pass

- `lessons.md`: new lessons at the top (insert only).
- `findings-index.md`: one dated pointer line to the pending register.
- `docs/DEVELOPER_GUIDE.md`, `docs/RAG_RUNTIME_DAG.md`, `docs/architecture/README.md`: small corrections; each is in the change log of `FINAL_LESSONS_AND_DOCUMENTATION_REVIEW.md` §7.
- `docs/plans/PROD_READINESS_TASK_LIST_2026-10-11.md`: dated pointer to the pending register.
- `README.md` (this package), `IMPLEMENTATION-AGENT-PROMPT.md` §0u, `unresolved-questions.md`: pointers to this package.

## 7. Commits that landed after the verification head (re-verify before relying on a status)

This package was verified against `c9b42d3e`. On 2026-11-06 the 21 later commits were checked: the "Verified result" column gives the outcome. Before it was committed, 21 commits landed on the branch (`2edee1c4` to `a7be7e65`, batches 9 to 13). The first verification pass did not cover them. Their commit messages claim the work below. The register now holds the verified statuses.

| Commit | Claimed work | Findings named in the message | Parts of this package that may now be stale | Verified result (2026-11-06, head `fb5cab0f`) |
|---|---|---|---|---|
| `2edee1c4`, `addeef77` | T6-02 memory signals for clip diversity; batch 9 record (T4-05, T1-18, T6-02) | MEM-002, UX-005 (T1-18) | Memory spec §2; coding package phase 9 and task 5 of the register's next-15 list | MEM-002 Partial. The live path cannot supply seen-clip ids (`MessagePayload` has no citations). UX-005 Closed at `43b6c6fd`. See register. |
| `649ea2c3` | T6-03 user-stated preferences replace the LLM persona | MEM-004 | Memory spec; register next-15 task 12 | MEM-004 Partial. An LLM still writes the persona; `compile_user_preferences` has no call site. |
| `2a91817f` | T6-10 honest product copy | PRD-010, UX-009, UX-011 | Register | PRD-010, UX-009, UX-011 Partial. Landing copy and pre-limit quota display unchanged. |
| `2318a368` | T7-03 one LLM gateway | SYS-003, CQ-002, AI-005, CQ-014 | Harness spec §2 (provider inventory); D-17; register (SYS-003 was reserved under T7-02: check what T7-03 actually closes) | SYS-003 untouched (stays Open). AI-005 and CQ-002 unchanged (D-17). CQ-014 Partial (alias kept). Only renames and gateway methods changed. |
| `a12ea273` | T7-04 cache key versioning | CQ-003 | Register next-15 task 14 | CQ-003 Partial. Versioned keys and a teaching guard added; no cache mechanism removed. |
| `924419df` | T7-05 exception and import ratchets | CQ-006, CQ-007 | Register next-15 task 13 | CQ-006, CQ-007 Partial. Ratchets pin the current counts; counts not reduced. |
| `1503e5f2` | T8-01 teacher registry extensibility and literal-name guard | GURU-010, CQ-009 | Guru spec §2 (hard-coded literal table, ADR-013 status); gap analysis §2 GURU row; RK-13 | GURU-010 Partial. The guard checks registry schema, not literals, and nothing calls it. CQ-009: no documentation change in this commit. |
| `49c92325` | T1-14 pin Memgraph and Autoheal images | SEC-006 | Harness spec task 12 and gap analysis §2 (`memgraph:latest`) | SEC-006 stays Partial. Compose tags pinned (tag existence unchecked); `Dockerfile.railway` not pinned. |
| `2c81a2d1` | T1-15 doc-versus-code check of pipeline order | CQ-009 | Gap analysis §5 item 10; RK-10; lesson L-DOC-PROSE-HAS-NO-PIN-TEST-1 (update note added) | CQ-009 Partial. Guard covers root `CLAUDE.md` only; `backend/CLAUDE.md` order still old. |
| `4af5e711`, `4c1c3993` | Memory plane inventory (ADV-06); batch 12 record (T1-14, T1-15, T6-01) | ADV-06 | Memory spec §2 | ADV-06 Closed at `4af5e711` (documentation fix). |
| `5db34855` | T4-07 verified helplines and freshness window | SAFE-004 | Register (SAFE-004 listed as human-only) | SAFE-004 Partial. Filter applied at 2 of about 10 helpline call sites; calls by the owner still needed. |
| `a33d6b8d` | T6-04 clip issue reporting and saved answers API | PRD-006, FR-SAVE-01, FR-CORR-01 | Memory spec saved-wisdom tasks; FR/NFR matrix rows FR-SAVE-01, FR-CORR-01; answer contract D-PQ7 (check whether a clip id now reaches the client) | PRD-006 Partial. Control and categories exist; no clip id on the wire, so reports name a video. FR-SAVE-01 and FR-CORR-01 Partial (saved answers stored in a local JSONL file). |
| `4eb04ae8` | T3-07 canonical teacher IDs | DATA-13, GURU-013 | Data-quality spec; guru spec; register | DATA-13, GURU-013 Partial. Query filters normalised; stored values not checked or migrated. |
| `7f63fe4c` | Guard fix: exception handling in feedback; settings collection-name lookup | — | Reliability spec §2 citations into `backend/app/api/feedback.py` (line numbers may have moved) | Correct as claimed. Also fixes a wrong setting name in `a12ea273` code. Clip-report route moved to `feedback.py:386` and list to `:478`. |
| `a7be7e65`, `9d0dce53`, `a4b0aca8`, `19ad9533` | Scorecard and batch records | — | `00` scorecard is newer than this package's gate summary | Documentation only. Not evidence of code behaviour. |

Line numbers cited in this package refer to `c9b42d3e`. Files changed by these commits may have shifted.
