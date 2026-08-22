# AskMukthiGuru Production Readiness Matrix

**Assessment date:** 2026-08-22  
**Current repository head:** `d44b1c4`
**Current backend deployment:** `a88a9362-a256-49c1-b654-6a9a8e314b72`
**Production backend:** `https://askmukthiguru-8119b0e8-production.up.railway.app`

## Verdict

# NOT READY FOR PRODUCTION

The service is healthy for controlled traffic and the latest backend release passed its focused Railway regression suite, but the Master Mission’s strict release rule remains decisive: unresolved cost/memory, grounded-retrieval quality, latency-tail, browser-publication, authenticated-observability, artifact-packaging, and recovery gates cannot be hidden by successful smoke tests. No corpus files were modified, staged, or uploaded.

## Matrix

| Category | Requirement | Status | Evidence | Test / verification | Owner | Remaining risk |
|---|---|---|---|---|---|---|
| Core chat | Grounded answers for representative queries | PARTIAL | Latest Telugu peace probe: `5/5` HTTP 200, `5/5` grounded, faithfulness `0.80`, response length `173–261` chars; stillness has a bounded non-doctrinal fallback but not a proven authoritative grounded teaching answer | Live production probes and focused Railway tests | Backend + QA | Retrieval contamination and insufficient authoritative evidence remain open |
| Safety | Distress requests receive safe redirect | VERIFIED FOR SMOKE | Sequential production control returned `blocked=true`, `grounding_state=safety_redirect`, faithfulness `1.0` | Signed anonymous-session production smoke | Security + QA | Full multilingual and adversarial matrix remains open |
| Cost | Current and forecast spend remain within controlled envelope | FAIL | Latest recorded Railway snapshot: `$29.6933` current usage against `$30` hard limit; forecast `$55.2651`; memory `94%` of spend | Railway billing snapshot and service metrics | FinOps + Performance | Current trajectory leaves negligible headroom for broad traffic |
| Provider accounting | Actual, estimated, and unknown AI costs are separated | VERIFIED IN CODE / PARTIAL LIVE | Commit `34c98a5` distinguishes provider-reported cost, configured fallback estimate, and unknown cost; cache read/write counters added | Static/deployment evidence; authenticated aggregation still open | FinOps + Backend | Live dashboard and alert proof incomplete |
| Memory | Backend resident memory is attributed and optimized | PARTIAL IMPROVEMENT, GATE OPEN | FlagEmbedding-only cleanup removed the unused BGE-M3 ONNX snapshot; cache moved from approximately `4.4G` to `2.3–2.7G`; post-release RSS observed around `2.78–3.02 GiB`, cgroup current around `4.26–4.40 GB` | Live SSH footprint snapshots; no sustained billing reduction proven | Performance + DevOps | Reranker is not baked; true RSS attribution and a fixed measurement window remain open |
| Retrieval | Ranking and citation correctness hold across protected classes | PARTIAL | Telugu smoke is stable after native-language detector fix; stillness provenance previously showed low-score transcript/editing fragments and an `Inner Stillness` entity | Live SSE/provenance evidence and fallback tests | Database + QA | Held-out NDCG, citation correctness, source-quality filtering, and grounded teaching coverage remain open |
| Graph | Parallel graph work improves useful cost/latency | NOT VERIFIED | Graph/Neo4j health is available, but no valid held-out graph-on/off comparison has been run | Read-only audit and bounded source inspection | Architecture + Performance | Do not activate broader graph concurrency or fusion changes without evidence |
| Database | Constraints/indexes and mutations are safe | VERIFIED READ-ONLY / MUTATION GATED | Three remote uniqueness constraints were previously confirmed ONLINE and populated; no schema mutation was run in this pass | Remote read-only checks | Database | Mutation lock, snapshot, rollback, and restore drill remain open |
| Browser UX | Critical journeys pass in real browser at required breakpoints | PARTIAL | Lovable homepage and `/chat` rendered; visible thinking, controls, privacy notices, and harmless submission worked. Repository now emits/consumes authoritative `event: final`, but Lovable-hosted bundle republish is not proven | Public browser capture plus direct production SSE contract evidence | UX + QA | Fresh post-publish conversation, mobile/tablet, auth, Second Brain, source panel, and custom-domain checks remain open |
| Authentication | Auth, authorization, AAL2, and tenant isolation are independently verified live | PARTIAL | Prior repository/RLS evidence exists; fresh independent live red-team pass is incomplete | CI/static evidence and prior vault evidence | Security + Privacy | BOLA/IDOR and authenticated user-flow proof remain open |
| Uploads | Bounded multimodal extraction is safe and understandable | PARTIAL | Size, semaphore, and SSRF controls exist; full browser and malformed-media failure matrix is incomplete | Static review only in this cycle | Backend + Red Team | Expensive or malformed uploads may still stress the service |
| Observability | Failures, cost spikes, and token anomalies are diagnosable | PARTIAL | Health, Prometheus metrics, startup logs, provider counters, and direct SSE trace evidence exist; protected `/api/metrics` aggregation was not authenticated in this pass | Health/log/SSE checks; authenticated counter visibility open | SRE + Observability | Alert routing and operational dashboard proof remain incomplete |
| SLOs | Latency, availability, queue, and useful-answer SLOs have error budgets | PARTIAL | Warm sequential controls: greeting `1.21s`, safety `1.06s`, Hindi `7.84s`, Telugu `5.55s`; post-detector Telugu internal latency median `4.08s`, maximum `4.49s`; earlier concurrent tests showed tail amplification up to roughly `10s+` and comparative/provenance tails above `12s` | Controlled production probes, not a broad load test | SRE + Performance | Session issuance consumes roughly `4–5s`; stable route-level p95/p99 is not closed |
| Backups | Important data can be restored | PARTIAL | Backup/restore runbook exists | Non-destructive restore proof remains open | DevOps + Data | Recovery may fail under incident pressure until drilled |
| Deployment | Reproducible and rollback-aware release | VERIFIED FOR DEPLOYMENT | Clean archive deployment `a88a9362-a256-49c1-b654-6a9a8e314b72` reached `SUCCESS`; health reached `ready=true`, `status=healthy`; focused suite completed `27 passed, 2 skipped` and the preceding full focused set completed `105 passed, 3 skipped` | Railway deployment polling, health checks, SSH pytest | DevOps | Rollback drill and worker parity for later backend-only changes remain incomplete |
| Data integrity | Corpus and user-memory boundaries are preserved | PARTIAL | Guard checks passed; immutable corpus remained untouched; no ONNX activation, RRF/DBSF change, Neo4j schema mutation, global Redis flush, or transcript upload occurred | Git path guard and deployment archive inspection | Data + Privacy | Full authenticated Second Brain E2E and restore proof remain open |
| Runtime artifacts | Reviewed OKF and doctrine lexicon artifacts are available | FAIL / GATED | Serving logs still warn that curated OKF/doctrine artifacts are absent; no empty placeholders were manufactured | Startup logs and image inspection | Data + Backend | Rebuild must use approved audited ingestion/ops flow and review gate |

## Evidence interpretation

The cache result is a **measured footprint reduction**, not a claimed invoice reduction. The cleanup is guarded to run only for the FlagEmbedding backend, preserves required PyTorch weights, and is disabled for ONNX mode; no retrieval semantics were intentionally changed. A sustained billing comparison requires a fixed observation window after the release.

The Telugu result is a **stability improvement for one bounded prompt class**, not proof of multilingual retrieval quality. The fallback is explicitly non-doctrinal and citation-free when evidence is insufficient. It must not be used to claim that the underlying retrieval contamination or missing authoritative source coverage has been solved.

The authoritative SSE final-answer change is proven at the backend contract and parser regression level. It is not yet proven in the Lovable-hosted frontend bundle because a fresh post-publish browser conversation or asset-revision check is still missing.

## Scoring rule

No numerical score overrides the verdict. A future score must report the numerator, denominator, source, window, and evidence class for every category. Any unresolved P0, uncontrolled cost risk, critical user-journey failure, data-loss risk, or severe security issue automatically produces **NOT READY FOR PRODUCTION**.

## Closure requirements

The final verdict may change only after the shared issue register is updated with independent verification for `COST-001`, `QUAL-001`, `PERF-001`, `MEM-001`, `DATA-001`, `E2E-001`, and `OPS-001`. Required proof includes a staging/blue-green memory experiment, sustained post-prune billing window, held-out graph/retrieval matrix, real-browser critical journeys after Lovable publication, adversarial authorization and cost-abuse testing, authenticated telemetry validation, reviewed runtime artifacts, and a non-destructive backup/restore drill.
