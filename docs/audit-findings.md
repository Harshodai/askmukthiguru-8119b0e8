# Master Audit Findings

| ID | Severity | Finding | Status |
|---|---|---|---|
| AM-001 | P1 | Critical `okf_compiled` artifact missing; `/api/health` says `ready=false`. | Open; reproduced. |
| AM-002 | P1 | Qdrant golden labels do not match configured contextual corpus; quality unproven. | Open; strict harness added. |
| AM-003 | P1 | Browser E2E stalled for two 300-second waits. | Open; unavailable. |
| AM-004 | P1 | No restore/RPO/RTO or cross-store recovery proof. | Open. |
| AM-005 | P1 | Redis/Supabase/Neo4j/provider integration tests skipped locally. | Open. |
| AM-006 | P2 | Load harness misclassified 202 queue admissions as failures. | Fixed; 3 regressions pass. |
| AM-007 | P2 | Benchmark had shell/global cache flush blast radius. | Fixed; Bandit/AST gates pass. |
| AM-008 | P2 | Corpus audit URL access lacked strict validation. | Fixed; URL tests pass. |
| AM-009 | P2 | `/guides` and `/support` were hard 404s. | Fixed; 5 route tests pass. |
| AM-010 | P2 | Separate vault/Profile Memory surfaces had ambiguous error wording. | Fixed; source-contract regression passes. |
| AM-011 | P2 | OTEL collector noise contaminated ordinary tests. | Fixed; full loop passes. |
| AM-012 | P2 | `langchain_text_splitters` stub warning remains. | Open. |
| AM-013 | P2 | Gitleaks scope was approximately zero bytes/commits. | Open. |
| AM-014 | P1 | 10x/100x capacity, completion latency, resource, and cost baselines absent. | Open. |
| AM-015 | P2 | Mobile production parity not live-verified. | Open. |

AM-001 through AM-005 and AM-014 keep the release Red. Fixed findings remain subject to final cross-review.
| AM-022 | P2 | The canonical Serene Mind MP3 manifest URL returned HTTP 404 in the local preview journey. Browser-TTS fallback and dedicated meditation fallback tests pass, but canonical audio delivery and asset availability are not proven. | Open; verify rights-approved asset publication and CDN integrity in staging without substituting fabricated media. |

| AM-023 | P1 | Disposable RLS verification exposed missing table privileges for authenticated/service-role access on `meditation_sessions` and `user_profiles`, preventing valid policy-evaluated operations. | Fixed with `20260825000002_restore_user_activity_table_grants.sql`; local reset and all 12 synthetic-user probes pass; staging apply remains unproven. |
| AM-024 | P1 | Synthetic-user RLS verification could previously be pointed at an unspecified remote target, creating avoidable mutation risk. | Fixed; verifier now refuses non-local targets unless `STAGING_ENVIRONMENT=staging` and `ALLOW_STAGING_SYNTHETIC_USERS=1`. |
| AM-025 | P2 | Retrieval baseline regression test rewrote the checked-in baseline as a side effect of evaluation. | Fixed; baseline updates now require explicit `UPDATE_QDRANT_BASELINE=1`; staging wrapper verifies read-only integrity. |
| AM-026 | P2 | No single staging command path combined migration rollback, runtime, RLS, HTTP red-team, and strict retrieval checks. | Fixed; staging scripts, environment-protected workflow, evidence contract, and runbook added. |
| AM-027 | P2 | Root frontend lint scanned independent nested Git worktrees and failed on stale copies outside the active checkout. | Fixed; `.claude/worktrees/**` is excluded from the root ESLint scope; active checkout lint passes with existing warnings only. |

The new staging automation improves verification maturity but does not close AM-001, AM-002, AM-004, AM-005, AM-014, or AM-015. The release verdict remains Red until environment-specific runtime artifacts, retrieval corpus quality, recovery, provider/worker resilience, capacity/cost, and native mobile parity are proven.
