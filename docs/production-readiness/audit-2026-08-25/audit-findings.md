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
