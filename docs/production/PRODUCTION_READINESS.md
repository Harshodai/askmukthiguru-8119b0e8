# AskMukthiGuru Production Readiness Matrix

**Assessment date:** 2026-08-22  
**Current repository head:** `0bb0782`
**Current backend deployment:** `f1d6d75e-2e83-48f6-b269-2a940f7bff91`
**Production backend:** `https://askmukthiguru-8119b0e8-production.up.railway.app`

## Verdict

# NOT READY FOR PRODUCTION

The service is healthy for controlled traffic and the latest backend release passed its focused Railway regression suite, but the Master Mission’s strict release rule remains decisive: unresolved cost/memory, grounded-retrieval quality, latency-tail, browser-publication, authenticated-observability, artifact-packaging, and recovery gates cannot be hidden by successful smoke tests. No corpus files were modified, staged, or uploaded.

## Matrix

| Category | Requirement | Status | Evidence | Test / verification | Owner | Remaining risk |
|---|---|---|---|---|---|---|
| Core chat | Grounded answers for representative queries | PARTIAL | Post-retrieval-fix Hindi peace probe: `5/5` HTTP 200, `5/5` grounded, faithfulness `0.80`, response length `243–507` chars; Telugu: `5/5` HTTP 200, `4/5` grounded and `1/5` honest abstention, response length `240–346` chars | Live production probes and focused Railway tests | Backend + QA | Narrow held prompts improved; multilingual held-out quality and authoritative teaching coverage remain open |
| Safety | Distress requests receive safe redirect | VERIFIED FOR SMOKE | Sequential production control returned `blocked=true`, `grounding_state=safety_redirect`, faithfulness `1.0` | Signed anonymous-session production smoke | Security + QA | Full multilingual and adversarial matrix remains open |
| Cost | Current and forecast spend remain within controlled envelope | FAIL | Latest recorded Railway snapshot: `$29.6933` current usage against `$30` hard limit; forecast `$55.2651`; memory `94%` of spend | Railway billing snapshot and service metrics | FinOps + Performance | Current trajectory leaves negligible headroom for broad traffic |
| Provider accounting | Actual, estimated, and unknown AI costs are separated | VERIFIED IN CODE / PARTIAL LIVE | Commit `34c98a5` distinguishes provider-reported cost, configured fallback estimate, and unknown cost; cache read/write counters added | Static/deployment evidence; authenticated aggregation still open | FinOps + Backend | Live dashboard and alert proof incomplete |
| Memory | Backend resident memory is attributed and optimized | PARTIAL IMPROVEMENT, GATE OPEN | FlagEmbedding-only cleanup removed the unused BGE-M3 ONNX snapshot; cache moved from approximately `4.4G` to `2.3–2.7G`; post-release RSS observed around `2.78–3.02 GiB`, cgroup current around `4.26–4.40 GB` | Live SSH footprint snapshots; no sustained billing reduction proven | Performance + DevOps | Reranker is not baked; true RSS attribution and a fixed measurement window remain open |
| Retrieval | Ranking and citation correctness hold across protected classes | PARTIAL | Retrieval final-return `NameError` was repaired to return `all_docs`; Hindi post-fix probe was `5/5` grounded at `0.80`; Telugu was `4/5` grounded and `1/5` honest abstention | Live metadata probes, regression suite, and retrieval source review | Database + QA | Held-out NDCG, citation correctness, source-quality filtering, and grounded teaching coverage remain open |
| Graph | Parallel graph work improves useful cost/latency | NOT VERIFIED | Graph/Neo4j health is available, but no valid held-out graph-on/off comparison has been run | Read-only audit and bounded source inspection | Architecture + Performance | Do not activate broader graph concurrency or fusion changes without evidence |
| Database | Constraints/indexes and mutations are safe | VERIFIED READ-ONLY / MUTATION GATED | Three remote uniqueness constraints were previously confirmed ONLINE and populated; no schema mutation was run in this pass | Remote read-only checks | Database | Mutation lock, snapshot, rollback, and restore drill remain open |
| Browser UX | Critical journeys pass in real browser at required breakpoints | PARTIAL | Lovable homepage and `/chat` rendered; visible thinking, controls, privacy notices, and harmless submission worked. Repository now emits/consumes authoritative `event: final`, but Lovable-hosted bundle republish is not proven | Public browser capture plus direct production SSE contract evidence | UX + QA | Fresh post-publish conversation, mobile/tablet, auth, Second Brain, source panel, and custom-domain checks remain open |
| Authentication | Auth, authorization, AAL2, and tenant isolation are independently verified live | PARTIAL | Prior repository/RLS evidence exists; fresh independent live red-team pass is incomplete | CI/static evidence and prior vault evidence | Security + Privacy | BOLA/IDOR and authenticated user-flow proof remain open |
| Uploads | Bounded multimodal extraction is safe and understandable | PARTIAL | Size, semaphore, and SSRF controls exist; full browser and malformed-media failure matrix is incomplete | Static review only in this cycle | Backend + Red Team | Expensive or malformed uploads may still stress the service |
| Observability | Failures, cost spikes, and token anomalies are diagnosable | PARTIAL | Health, Prometheus metrics, startup logs, provider counters, and direct SSE trace evidence exist; protected `/api/metrics` aggregation was not authenticated in this pass | Health/log/SSE checks; authenticated counter visibility open | SRE + Observability | Alert routing and operational dashboard proof remain incomplete |
| SLOs | Latency, availability, queue, and useful-answer SLOs have error budgets | PARTIAL | Post-fix Hindi internal latency `2.925–6.470s` and wall `3.994–7.917s`; Telugu internal `2.768–5.746s` and wall `3.991–6.945s`; prior concurrent tests showed tail amplification up to roughly `10s+` and comparative/provenance tails above `12s` | Controlled production probes, not a broad load test | SRE + Performance | Stable route-level p95/p99, session overhead, and concurrency behavior remain open |
| Backups | Important data can be restored | PARTIAL | Backup/restore runbook exists | Non-destructive restore proof remains open | DevOps + Data | Recovery may fail under incident pressure until drilled |
| Deployment | Reproducible and rollback-aware release | VERIFIED FOR DEPLOYMENT | Clean archive deployment `f1d6d75e-2e83-48f6-b269-2a940f7bff91` reached `SUCCESS`; health reached `ready=true`, `status=healthy`, embedding dimension `1024`; scoped suite completed `83 passed, 2 skipped` | Railway deployment polling, health checks, live source inspection, SSH pytest | DevOps | Rollback drill and worker parity for later backend-only changes remain incomplete |
| Data integrity | Corpus and user-memory boundaries are preserved | PARTIAL | Guard checks passed; immutable corpus remained untouched; no ONNX activation, RRF/DBSF change, Neo4j schema mutation, global Redis flush, or transcript upload occurred | Git path guard and deployment archive inspection | Data + Privacy | Full authenticated Second Brain E2E and restore proof remain open |
| Runtime artifacts | Reviewed OKF and doctrine lexicon artifacts are available | FAIL / GATED | Serving logs still warn that curated OKF/doctrine artifacts are absent; no empty placeholders were manufactured | Startup logs and image inspection | Data + Backend | Rebuild must use approved audited ingestion/ops flow and review gate |

## Evidence interpretation

The cache result is a **measured footprint reduction**, not a claimed invoice reduction. The cleanup is guarded to run only for the FlagEmbedding backend, preserves required PyTorch weights, and is disabled for ONNX mode; no retrieval semantics were intentionally changed. A sustained billing comparison requires a fixed observation window after the release.

The Hindi result is a **narrow held-prompt improvement after repairing the retrieval return contract**, not proof of multilingual retrieval quality. The Telugu result remains mixed: one of five runs used the explicitly non-doctrinal, citation-free fallback. Neither result closes the underlying retrieval contamination, source coverage, or held-out multilingual evidence gate.

The authoritative SSE final-answer change is proven at the backend contract and parser regression level. It is not yet proven in the Lovable-hosted frontend bundle because a fresh post-publish browser conversation or asset-revision check is still missing.

## Scoring rule

No numerical score overrides the verdict. A future score must report the numerator, denominator, source, window, and evidence class for every category. Any unresolved P0, uncontrolled cost risk, critical user-journey failure, data-loss risk, or severe security issue automatically produces **NOT READY FOR PRODUCTION**.

## Closure requirements

The final verdict may change only after the shared issue register is updated with independent verification for `COST-001`, `QUAL-001`, `PERF-001`, `MEM-001`, `DATA-001`, `E2E-001`, and `OPS-001`. Required proof includes a staging/blue-green memory experiment, sustained post-prune billing window, held-out graph/retrieval matrix, real-browser critical journeys after Lovable publication, adversarial authorization and cost-abuse testing, authenticated telemetry validation, reviewed runtime artifacts, and a non-destructive backup/restore drill. The retrieval return-contract fix and exact Hindi UX regression are mitigations, not grounds to change the verdict.
