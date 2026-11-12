# Ask Mukti Guru — architecture and product audit (2026-11-04)

Read-only audit of `origin/main@46b808fb`. No application file was changed. Rules, evidence labels and the finding format: `CONVENTIONS.md`.

> **Location.** This package lives at `audits/audit-output-2026-11-04/` (owner decision D-27, 2026-11-04). It was written as `audit-output/` at the repository root. Read every `audit-output/` path inside these documents as this folder.

## Final verification package (2026-11-05)

Start at `FINAL_READINESS_AND_GAP_ANALYSIS.md`: the release decision for staging, production and public release, and an index of the 10 `FINAL_*` files and the 12 files in `specifications/`. The status of every finding at `c9b42d3e` is in `FINAL_PENDING_WORK_REGISTER.md`. The coding agent starts at `FINAL_CODING_AGENT_EXECUTION_PACKAGE.md` §1.

## Start here

| If you are… | Read |
|---|---|
| The owner (30 min) | `00` → `16` §1–§3 → `unresolved-questions.md` → `20` §3 P0 |
| An implementation agent | `24` → `25` §1 (revalidate first) → `20` → `21` |
| A teacher's representative or guru reviewer | `23` → `14c` → `10` §5 → `11` |
| An engineer reviewing the architecture | `05` → `17` → `08` → `09` → `15` |
| Checking the audit itself | `26` → `27` |

## Documents

| # | File | Content | Author |
|---|---|---|---|
| 00 | `00-executive-overview-and-scorecard.md` | Verdict, six-pillar scorecard, top risks, what to do this week | Lead |
| 01 | `01-repository-git-history-and-pr-investigation.md` | Branches, history, PR #76 and #86, CI state of `main` | Lead |
| 02 | `02-spiritual-user-research-personas-jtbd.md` | External research, personas, jobs to be done, user-study proposal | S4 |
| 03 | `03-product-journeys-functional-requirements.md` | Journeys, UI→API→store traceability map, 32 FRs with status | S4 |
| 04 | `04-non-functional-requirements-slos-and-benchmarks.md` | NFRs with baselines and targets, SLOs, benchmark usage | Lead |
| 05 | `05-current-architecture-and-request-flow.md` | Live request lifecycle, stages, LLM calls, flags, inventory | S1 |
| 06 | `06-data-ingestion-quality-lineage.md` | Every datastore, lineage, cross-store consistency matrix | S2 |
| 07 | `07-video-audio-multisource-synthesis.md` | ASR, speaker attribution, segmentation, multi-video design | S2 |
| 08 | `08-qdrant-graph-retrieval.md` | Hybrid retrieval, rerankers, graph value, retrieval failures | S2 |
| 09 | `09-ai-harness-agents-prompts-context.md` | Every LLM call site, prompt inventory, routing, context | S3 |
| 10 | `10-spiritual-answer-quality-expected-behavior.md` | Anxiety trace, question taxonomy, response modes, voice layers | S3 |
| 11 | `11-krishnaji-preethaji-future-guru-extensibility.md` | Teacher identity, hardcoding, registry, onboarding a teacher | S4 |
| 12 | `12-personal-mentor-memory-ethical-retention.md` | Memory and personalisation architecture | S3 |
| 12b | `12b-ethical-retention-and-mentor-ux.md` | Retention features, north star, ethical hooks | S4 |
| 13 | `13-code-quality-architectural-debt.md` | Remove / refactor / keep registers | S1 |
| 14 | `14-security-safety-privacy-permissions.md` | Security, auth, RLS, privacy, erasure | S1 |
| 14b | `14b-safety-crisis-and-spiritual-trust.md` | Crisis detection, helplines, misattribution, dependency | S3 |
| 14c | `14c-content-permissions-and-ip-register.md` | Rights, public exposure, voice use, permissions register | S4 |
| 15 | `15-reliability-performance-cost-observability.md` | Timeouts, latency, cost per useful answer, observability | S1 |
| 16 | `16-root-cause-and-failure-register.md` | Nine root causes, P0 records, severity reconciliation, failure modes | Lead |
| 17 | `17-target-architecture-and-decision-register.md` | Target architecture, 13 diagrams, component decisions, ADR-001…015 | Lead |
| 18 | `18-golden-eval-dataset-and-testing-spec.md` | Eval asset audit, gold-label verification, benchmarks, golden-set spec | S3 |
| 19 | `19-build-redesign-consolidate-remove-avoid.md` | The short decision list | Lead |
| 20 | `20-ordered-engineering-roadmap.md` | 85 PR-sized tasks in 11 phases, critical path, file-conflict order, phase summaries | Lead |
| 21 | `21-file-level-implementation-specifications.md` | File-level specs for every P0/P1 task | Lead |
| 22 | `22-qdrant-graph-deferred-validation-runbook.md` | Read-only Qdrant and Memgraph checks to run later | S2 |
| 22b | `22b-railway-deployment-readiness-runbook.md` | Railway readiness, env vars, smoke, rollback | S1 |
| 23 | `23-guru-review-and-release-readiness-package.md` | Guru-review package, review question set, gate verification, scorecard | S4 + Lead |
| 24 | `24-coding-agent-master-handoff.md` | Self-contained handoff and master prompt | Lead |
| 25 | `25-phase-specific-coding-prompts.md` | First-task revalidation, phase prompts, final verification | Lead |
| 26 | `26-independent-adversarial-review-and-residual-risks.md` | Independent verification of critical claims; residual risks | Reviewer + Lead |
| 27 | `27-execution-log-coverage-and-usage.md` | What was done, coverage, what was not read, usage | Lead |
| 02b | `02b-competitive-analysis-and-product-opportunities.md` | Competitor analysis; long-term opportunity register | Journey/competitive pass |
| 14d | `14d-user-journey-and-frontend-walkthrough.md` | 14-step seeker journey through the real frontend and API, including error recovery and stream interruption | Journey/competitive pass |
| 22a | `22a-acceptance-criteria-and-testing-plan.md` | Test layers, metric definitions, per-PR verification checklist, regression protection | Lead |
| — | `IMPLEMENTATION-AGENT-PROMPT.md` | **Copy-ready, self-contained prompt for the implementation agent** | Lead |
| — | `findings-index.md` | All findings, stable IDs, reconciled severity, closing task | Lead |
| — | `traceability-matrix.md` | Objective → need → FR → component → data → API → test → metric | Lead |
| — | `decision-log.md` | Audit-method decisions, ADR status, owner decisions | Lead |
| — | `unresolved-questions.md` | Owner decisions D-01…D-27, live-infra unknowns, human gates | Lead |

S1 = backend/stability/security/cost; S2 = data/Qdrant/retrieval; S3 = AI harness/answers/safety/evals; S4 = product/users/guru/rights. All specialists ran read-only.

## Name mapping for the second mission brief (28 required documents)

The second brief asked for different file names. To avoid duplicated conclusions, each required name maps to the file(s) that hold the content.

| Required name | Content lives in |
|---|---|
| `00-executive-diagnosis.md` | `00-executive-overview-and-scorecard.md` |
| `01-repository-and-pr-inventory.md` | `01-…`, coverage ledger in `27` §3 |
| `02-spiritual-user-research.md` | `02-…` §1–§3, §8; competitors in `02b` |
| `03-user-personas-and-jobs-to-be-done.md` | `02-…` §4–§7 |
| `04-current-system-architecture.md` | `05`, current-state diagrams in `17` §2b, lineage in `06` |
| `05-target-system-architecture.md` | `17` |
| `06-backend-and-api-audit.md` | `05` (routes, stages, lifecycle), `14`, `15` |
| `07-data-ingestion-and-data-quality-audit.md` | `06`, `07` |
| `08-qdrant-and-knowledge-graph-audit.md` | `08`, `06` §datastores |
| `09-retrieval-and-rag-audit.md` | `08` |
| `10-ai-harness-and-agent-audit.md` | `09` |
| `11-context-memory-and-personalization-audit.md` | `12`, `12b`, `09` §context |
| `12-complete-prompt-inventory-and-audit.md` | `09` §3 (prompt inventory) |
| `13-spiritual-answer-quality-framework.md` | `10` (behaviour specs, voice layers, modes), `18` §6 (rubric), `22a` §3 (metrics) |
| `14-user-journey-and-frontend-audit.md` | `14d`, `03` |
| `15-security-safety-and-privacy-audit.md` | `14`, `14b`, `14c` |
| `16-reliability-performance-and-cost-audit.md` | `15` |
| `17-root-cause-and-failure-register.md` | `16` (§7 is the full-field failure register) |
| `18-golden-evaluation-dataset.md` | `18` |
| `19-features-to-build-remove-and-avoid.md` | `19` (§6 is the do-not-build register) |
| `20-ordered-engineering-roadmap.md` | `20` |
| `21-file-level-implementation-specifications.md` | `21` |
| `22-acceptance-criteria-and-testing-plan.md` | `22a` |
| `23-railway-and-qdrant-verification-runbook.md` | `22` (Qdrant, graph), `22b` (Railway) |
| `24-coding-agent-master-handoff.md` | `24`, `IMPLEMENTATION-AGENT-PROMPT.md` |
| `25-phase-specific-coding-prompts.md` | `25` |
| `26-final-adversarial-review.md` | `26` |
| `27-execution-and-usage-log.md` | `27` |

## How to check this audit

1. Every material claim carries a label: `[V-STATIC]`, `[V-GIT]`, `[V-WEB]`, `[DOC-CLAIM]`, `[INF]`, `[LIVE-Q]`, `[LIVE-R]`, `[LIVE-L]`, `[HUMAN]`.
2. Re-run the revalidation prompt (`25` §1) against the current `main`.
3. Spot-check the claims verified independently in `26` §2.
