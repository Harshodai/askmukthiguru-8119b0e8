# AskMukthiGuru Ruthless Audit — Fresh Rerun

**Audit date:** 24 August 2026
**Repository:** `Harshodai/askmukthiguru-8119b0e8`
**Audited revision:** `0d30fad238a4d63b95e39de296ad590fdb2bd6db` at the start of this rerun; subsequent dependency-remediation edits were present in the working tree and are called out separately.
**Method:** Original `pasted_content.txt` brief, 16 parallel forensic tracks, fresh frontend/backend/browser/runtime checks, fresh competitor research, and a master reconciliation pass.
**Deployment:** No production deployment or destructive external operation was performed.

## 1. Executive summary

> **Verdict: READY FOR STAGING VERIFICATION; NOT READY FOR UNRESTRICTED PUBLIC PRODUCTION.**

The repository is substantially stronger than the previous audit baseline. The prior browser transport defect is no longer the only story: the current local stack now issues signed anonymous-session tokens, returns correct `422` validation errors, returns a queued distress job whose terminal result is explicitly blocked with `intent=DISTRESS` and `grounding_state=safety_redirect`, serves healthy Qdrant/Redis/Neo4j/LLM/embedding/graph dependencies, passes the fresh bounded validation loop, and completes a full dependency-equipped backend suite at **2,378 passed, 30 skipped, and 1 warning in 221.38 seconds**. Frontend unit tests, typecheck, lint, production build, prerender, bundle budget, mobile-targeted build, focused backend security/RAG/memory tests, Compose validation, and the Chromium static-browser matrix also pass. [1] [2]

The decisive blocker is now visible at runtime: `/api/health` returns HTTP 200 but `ready=false`, `status=unhealthy`, with `runtime_artifacts.missing_required=["okf_compiled"]`. A live browser chat request begins the streaming/progress path and then ends with `ERR_UNKNOWN` / `Failed to fetch`, with no final answer or citations. That is not a cosmetic failure; it is a production-serving failure in the exact flagship journey. The distress path is materially better and completed safely through the queue, but benign grounded teaching cannot be declared production-proven while the curated artifact gate is red and the local contextual collection contains only a tiny development corpus. [3] [4]

Dependency work also advanced. The current requirements file explicitly upgrades Starlette, LangChain/LangGraph families, cryptography, Pillow, pypdf, pydantic-settings, and related packages, while pinning `dspy-ai==3.2.1` to prevent a silent resolver downgrade. However, the current working-tree handoff still records unresolved findings for the `transformers`/`json-repair`/`llm-guard` compatibility chain and gptcache/diskcache, and the fresh `pip-audit` attempt stalled while installing its isolated environment. Dependency closure therefore remains **unverified**, not solved by assertion.

## 2. Current repository reality

| Reality check | Fresh result | Classification |
|---|---|---|
| Repository revision and remote | Previous committed `HEAD` was synchronized with `origin/main`; this rerun also found new working-tree changes in `backend/requirements.txt`, `docs/operations/prod-readiness-remediation-2026-08-24.md`, and `memory/qdrant_quality_baseline.json`. | Confirmed |
| Local Docker | Docker recovered and reported server version `29.7.2`; five core containers were up and healthy: backend, frontend, Neo4j, Qdrant, and Redis. | Confirmed |
| Compose config | `docker compose -f backend/docker-compose.yml config --quiet` passed. | Confirmed |
| Liveness | `GET /api/healthz` returned HTTP 200 and `{ "ok": true, "status": "alive" }`. | Confirmed |
| Deep readiness | `GET /api/health` returned HTTP 200, `ready=false`, `status=unhealthy`; required `okf_compiled` was missing. | Confirmed |
| Anonymous session | `POST /api/auth/anon-session` returned HTTP 200 with a signed token and `anon:` session identifier. | Confirmed |
| Malformed request | `POST /api/chat` with an invalid body returned HTTP 422 with a structured validation response. | Confirmed |
| Distress request | Queued as HTTP 202, then polled as HTTP 200 with `blocked=true`, `intent=DISTRESS`, zero citations, and `grounding_state=safety_redirect`. | Confirmed |
| Benign browser chat | UI rendered and began progress/search streaming, then ended in `ERR_UNKNOWN` / `Failed to fetch`; no completed answer or sources. | Confirmed failure |
| Curated corpus | Runtime reported `okf_compiled` missing; prior fresh extraction evidence found only eight local contextual chunks, including development/test fixture content. | Confirmed blocker |
| Full backend suite | 2,378 passed, 30 skipped, 1 warning; Jaeger export was unavailable but did not block tests. | Confirmed |

The distinction matters: process liveness, dependency health, and test passing are not equivalent to answer-serving readiness. The application is currently a healthy-looking process with a deliberately red serving gate.

## 3. Production-readiness scorecard

These are evidence-weighted engineering scores, not benchmark measurements. They are used to show where the risk is concentrated and do not override the P0 gate.

| Dimension | Score / 10 | Rationale |
|---|---:|---|
| Product | 7.0 | Clear spiritual companion, practices, memory, graph, attachments, and admin surfaces; value is undermined by unreliable benign answer completion and incomplete corpus proof. |
| Frontend / UX | 7.8 | Strong navigation, responsive primitives, accessibility improvements, clear reflective-guidance labeling, and good static journey coverage; live chat failure remains severe. |
| Backend / API | 7.4 | Strong validation, signed anonymous sessions, queue ownership checks, explicit status semantics, and broad tests; live dependency/artifact behavior is not fully closed. |
| RAG | 5.2 | Many implemented layers and safety-aware fallbacks, but current local evidence cannot prove that the full curated retrieval path serves approved doctrine reliably. |
| AI quality | 4.8 | Safety redirect evidence is good; held-out answer quality, citation correctness, hallucination rate, and model/provider parity remain insufficiently proven. |
| Source faithfulness | 4.5 | The system distinguishes grounded teaching from reflective guidance and can abstain; missing approved runtime artifacts prevents a trustworthy corpus-serving claim. |
| Security | 7.4 | Strong static scanning, authz regressions, upload guards, rate limits, and prompt/data-boundary work; production credentials and hosted penetration evidence remain open. |
| Privacy | 6.7 | Encrypted vault design, scoped caches, retention, forget endpoints, and deletion tests exist; cross-store production deletion and RLS drills remain unverified. |
| Database / RLS | 6.2 | Extensive migrations and policy tests exist; fresh local Supabase replay fails at `realtime.messages` ownership, so clean-room rebuildability is not proven. |
| Reliability | 6.1 | Queue, backpressure, health, and fallback mechanisms are present; benign chat fails locally and direct-stream reconnect remains unproven. |
| Observability | 6.0 | Correlation IDs, metrics, traces, and dashboards exist; Jaeger availability and production alert/SLO evidence remain incomplete. |
| Performance | 5.7 | Warmup, caching, coalescing, concurrency limits, and bundle gates exist; historical long-tail latency and full RAG stage budgets remain open. |
| Cost control | 5.6 | Quotas, cache layers, routing, and token/cost telemetry exist; 100/1,000/10,000/100,000 DAU cost envelopes are not evidenced by load tests. |
| Mobile | 6.1 | Capacitor configuration and mobile build pass; native OAuth, push, audio, lifecycle, poor-network, and store-device evidence are incomplete. |
| Testing | 7.8 | Broad unit/security/E2E coverage and full backend suite now pass; several important live/hosted tests are explicit skips. |
| DevOps / release | 6.0 | Compose, image, health, and release documentation exist; dependency scan, artifact packaging, staging deployment, rollback, and restore gates remain open. |
| Documentation | 7.6 | AGENTS, lessons, reports, runbooks, and loop scripts are unusually rich; instruction-file sprawl and stale dated claims still create agent ambiguity. |
| Agent readiness | 7.2 | Strong invariants and reproducible gates; agent still cannot infer corpus rights, hosted project credentials, artifact ownership, or migration decision authority. |

## 4. Product health and feature map

| ID | Capability | Entry point / implementation | State | Evidence and failure mode | Priority |
|---|---|---|---|---|---:|
| F-01 | Anonymous spiritual chat | `src/components/chat/ChatInterface.tsx`; `backend/app/api/chat.py`; signed `/api/auth/anon-session` | **FUNCTIONAL / BLOCKED IN RUNTIME** | Anonymous session issuance and malformed validation pass. Browser benign chat starts but ends in `Failed to fetch`; deep readiness is red. | P0 |
| F-02 | Authenticated chat and history | Supabase auth, chat routes, conversation storage | **FUNCTIONAL** | Static and focused auth tests pass; live OAuth and full authenticated staging proof remain open. | P1 |
| F-03 | Grounded teaching | runtime OKF, Qdrant, citation/provenance pipeline | **PARTIAL** | Missing `okf_compiled`; reflective guidance is correctly labelled when grounding is absent. | P0 |
| F-04 | Reflective guidance fallback | generation/formatting and UI labels | **FUNCTIONAL** | UI explicitly says “No grounded teaching was found”; must not be marketed as corpus teaching. | P1 |
| F-05 | Distress safety routing | `distress_stage.py`, queued jobs, safety guardrails | **FUNCTIONAL / NEEDS HOSTED PROOF** | Fresh queued result was blocked, `intent=DISTRESS`, `grounding_state=safety_redirect`, zero citations, 1.145s latency. | P1 |
| F-06 | Streaming chat | direct and queued SSE, Nginx, frontend parser | **PARTIAL** | Proxy semantics and pre-token JSON fallback are implemented; live benign turn still fails before final answer. Direct reconnect/resume remains unproven. | P0 |
| F-07 | Practices and meditation | `/practices`, `/practices/*`, meditation flow | **FUNCTIONAL STATICALLY** | Static page/prelaunch and accessibility suites pass; live audio/CDN and mobile tests remain open. | P1 |
| F-08 | Second Brain / memory | `backend/services/second_brain`, Qdrant vault, Postgres encrypted nodes | **FUNCTIONAL / ENVIRONMENT-UNVERIFIED** | Focused memory/vault tests pass; cross-store forget and tenant isolation require staging. | P1 |
| F-09 | Knowledge graph | Neo4j, graph stages, `/knowledge-graph` | **FUNCTIONAL / QUALITY-UNPROVEN** | Container is healthy and graph UI mounts; retrieval improvement over vector-only baseline is not demonstrated. | P1 |
| F-10 | Attachments | upload route, extraction/OCR, source policy | **FUNCTIONAL WITH SECURITY BOUNDARIES** | Focused upload/RAG/security tests pass; adversarial corpus, decompression/OCR stress, and production storage lifecycle remain open. | P1 |
| F-11 | Multilingual support | i18n locales, translation path, language selector | **PARTIAL** | Supported locale UI exists; translation-key completeness and live multilingual faithfulness remain open. | P1 |
| F-12 | Admin operations | admin pages, MFA/AAL2, OKF/staging queue | **FUNCTIONAL STATICALLY** | Protected route and component suites pass; hosted AAL2 identity and editorial approval workflow remain unproven. | P1 |
| F-13 | Metrics and dashboards | `/api/metrics`, telemetry, Sentry/OTel paths | **FUNCTIONAL / OPERATIONS-INCOMPLETE** | Code and schemas exist; Jaeger was unavailable during full tests and alert/SLO validation is incomplete. | P1 |
| F-14 | Mobile app | Capacitor iOS/Android build paths | **BUILDABLE / NOT DEVICE-PROVEN** | `npm run build:mobile` passes; native-device and store callback evidence is missing. | P1 |

## 5. User journey audit

| Journey | Trace result | Verdict |
|---|---|---|
| Anonymous visitor | Landing/static routes → chat page → signed anonymous session path | Static UI works; live benign answer completion is blocked by runtime readiness/transport. |
| First-time seeker | Onboarding/pre-practice gate → composer → streaming/progress UI | Browser reaches the composer and progress state; final answer can fail with `ERR_UNKNOWN`. |
| Authenticated user | Supabase session → protected routes → memory/history | Static and focused contracts pass; real OAuth, session expiry, and hosted provider proof remain open. |
| Returning user | Sidebar conversations → history and memory controls | UI renders and local history is visible; cross-device consistency and stale-cache behavior require staging. |
| Memory-enabled user | Chat → memory stage → encrypted Postgres/Qdrant vault | Focused tests pass; production deletion, cache isolation, and poisoning recovery require two-user staging. |
| Knowledge-graph user | `/knowledge-graph` → graph API/Neo4j → visualization | UI/container path exists; graph quality and retrieval lift are unproven. |
| Attachment user | upload → extraction/OCR → retrieval/provenance → answer | Guards and tests exist; malicious files, parser limits, OCR resource exhaustion, and prompt injection need adversarial staging. |
| Meditation/audio user | practices → meditation flow → audio/TTS | Static route works; CDN-accessible asset, mobile audio, permissions, and network-change behavior remain open. |
| Mobile user | Capacitor WebView → auth, keyboard, audio, push, uploads | Mobile build passes; device lifecycle and deep-link behavior are not production-proven. |
| Admin/editor | admin auth/AAL2 → OKF/staging review → publish | UI/test contracts exist; artifact rights approval and real MFA identities remain external prerequisites. |
| Deletion requester | forget/delete API → Postgres/Qdrant/Redis/queue/cache | Code and focused tests exist; complete hosted deletion proof is missing. |

## 6. Frontend and UX audit

The frontend is the strongest area of the current system. The fresh loop reports 87 frontend test files passing with 509 tests passed and 6 skipped, zero lint errors, successful typecheck, successful production build with 28 prerendered routes, and passing bundle-budget checks. Chromium axe coverage passed 8/8 after a real cookie-consent hover contrast defect was corrected. Static page and prelaunch suites passed 24/24.

The most important UX defect is not visual: a real browser chat turn can show the user a question, a “Thinking” state, a source-search status, and then an `ERR_UNKNOWN` / `Failed to fetch` terminal state with no final answer. The fallback logic reduces some pre-token transport failures, but the user-facing system still needs a fully working live smoke path with the required artifacts loaded. The “Guru is waking up” notice is honest but should be paired with an explicit degraded-mode explanation when readiness is red.

Remaining frontend work is dominated by 31 non-blocking lint warnings, cross-browser validation, tablet stress testing, live audio, and explicit handling of long-running or failed provider requests. The browser test suite itself exposed one 30-second navigation timeout in the Serene Mind regression, although the rerun of that specific test was skipped by its own conditions; it should not be counted as a green live meditation proof.

## 7. Backend and API audit

The backend has strong contract hygiene. Anonymous session issuance is signed, invalid bodies return `422`, queue polling checks ownership and returns `404` on mismatch, API/SSE proxy status is preserved, health JSON is structured, and focused safety/authz/queue tests pass. The full backend suite now completed at 2,378 passed and 30 skipped.

The major backend gap is operational truth. `/api/healthz` is alive, but `/api/health` is red because the required curated artifact is missing. A 200 status on deep health must not be treated as a serving-ready signal; deployment must gate on the `ready` field. The benign chat failure demonstrates that a healthy process can still be unable to produce a usable answer.

The service also emits a Jaeger exporter failure after the full suite: export retries and then fail against `jaeger:4317`. The application tests continue, which is desirable, but production operators must know whether trace loss is acceptable, alerted, sampled, and bounded.

## 8. RAG audit by layer

| Layer | Current implementation | Fresh assessment |
|---|---|---|
| Input safety | Deterministic input guardrails and distress routing | Stronger than prior baseline; fresh distress queue result was correct. |
| Semantic routing | Intent/query routing and bounded shortcuts | Implemented; held-out route-quality metrics are incomplete. |
| Intent classification | Regex/provider stages | Safety failures are fail-closed; provider parity needs staging. |
| Query decomposition | Pipeline/query analysis stages | Present; incremental answer-quality contribution is not isolated. |
| Parent/child/tree navigation | Context graph and retrieval helpers | Present; quality lift not measured against a simple baseline. |
| Hybrid vector + graph | Qdrant plus Neo4j/LightRAG fusion | Wired and container-healthy; current local corpus is too small to prove lift. |
| Reranking | ONNX/ColBERT/FlashRank/RAGatouille paths | Complex and costly; RAGatouille fallback should be removed only after proving the ONNX path is complete. |
| CRAG grading | Grading/rewrite/fallback nodes | Safety invariant exists; graph terminal behavior after rewrite exhaustion remains a key audit point. |
| Guru tone adapter | Prompt/adapter flags and familiarity classification | Implemented but benchmark-gated; do not enable broadly without live quality results. |
| Context-aware generation | Prompt assembly, provenance, source policy | Implemented; no answer-quality benchmark proves the full stack. |
| Chain of Verification | Verification stages and metadata | Implemented; current live benign request did not reach a final answer. |
| Self-RAG/output rail | Output checks/guardrails | Implemented as a safety/quality layer; provider/model variance remains. |

The system should retain safety, deterministic provenance, one grounded evidence path, and one quality gate. It should merge or remove layers only after an ablation report shows no quality regression and a measurable latency/cost benefit. Architectural complexity is currently ahead of demonstrated quality evidence.

## 9. AI quality and source-faithfulness audit

The system has an important honesty feature: it can label a response as reflective guidance when no grounded teaching was found. That is preferable to fabricating a citation. It also supports deterministic grounded partials with bounded excerpts and explicit `verification.method=grounded_partial_evidence`, `partial=true`, and `verification.passed=false`.

However, the repository still lacks a sufficiently authoritative held-out corpus evaluation for answer faithfulness, citation correctness, hallucination rate, refusal correctness, multilingual quality, and provider compatibility. The local Qdrant contextual collection used in the fresh environment contains only eight chunks, including a development/test fixture. Any NDCG computed over that set is not a meaningful production-quality baseline. The current runtime artifact gate is therefore a feature, not an inconvenience: it correctly prevents a thin dev corpus from being represented as a trustworthy doctrine corpus.

Required quantitative evaluation must include Recall@K, Precision@K, MRR/NDCG, context precision/recall, answer faithfulness, citation correctness, hallucination rate, refusal precision, first-token and total latency, token cost, cache hit rate, and provider/model stratification. No unobserved benchmark result is claimed here.

## 10. Knowledge graph / LightRAG audit

Neo4j is running and the repository contains graph ingestion, entity, relationship, traversal, fusion, visualization, and fallback paths. The graph architecture is therefore real in the implementation sense. It is not yet proven to improve user outcomes. The correct experiment is a paired held-out set: vector-only versus graph-only versus hybrid, with identical generation settings and measured retrieval recall, answer faithfulness, citation correctness, latency, token usage, graph failure rate, and stale-node rate.

The graph should remain only if it demonstrates material lift on doctrine/entity questions or enables user-facing exploration that the vector path cannot provide. Otherwise, the graph should be narrowed to an offline enrichment and visualization capability rather than remaining on every latency-sensitive chat request.

## 11. Memory / Second Brain audit

The repository implements session memory, transient chat logs, protected user core memory, encrypted vault nodes, Qdrant user filtering, Redis TTLs, inactive-account cleanup, and forget/delete endpoints. Focused memory, vault, timestamp, cache isolation, and authorization tests passed.

The unresolved question is distributed deletion. A user forget request must be shown to remove or invalidate the corresponding Postgres row, Qdrant vector, Redis exact/semantic cache entries, queued job payloads, derived indexes, and any backups subject to the retention policy. A two-user staging drill must demonstrate that Alice cannot read Bob’s memory before or after deletion and that deleted content cannot reappear through a stale cache or graph projection.

## 12. Security, privacy, auth, RLS, and MFA audit

Static security posture is strong: backend Ruff passes, Bandit reports no medium/high findings, regex safety passes, authz route sweeps pass, upload/RAG safety clusters pass, and the repository contains MFA/AAL2 and RLS verification machinery. The signed anonymous-session behavior is confirmed in the live local backend, and job ownership checks are explicit.

The fresh local Supabase rebuild attempt exposed a real migration portability defect: `20260509180000_secure_realtime.sql` attempts to enable RLS on `realtime.messages` but the migration runner is not the table owner, producing `ERROR: must be owner of table messages`. This may work in hosted Supabase under a different role model, but the repository’s migrations do not currently replay from zero in the disposable local environment. That is a P1 reliability and disaster-recovery risk.

Open environment checks include hosted two-user RLS probes, Google OAuth with dedicated test identities, real password-reset email delivery, service-role boundary validation, secret rotation, backup/restore, and cross-store deletion.

## 13. Attachment and prompt-injection audit

The code contains attachment type/size and extraction controls, safe web retrieval rules, provenance handling, and tests for common security boundaries. The correct security model is that uploaded and retrieved content is **data**, never instructions. The system must not let a PDF, webpage, caption, memory, or graph node override system policy, source restrictions, or user-tenant boundaries.

Production hardening still needs adversarial fixtures: oversized files, decompression bombs, parser edge cases, malicious PDF/HTML metadata, OCR abuse, embedded prompt injection, exfiltration attempts, repeated uploads, storage expiry, and worker resource exhaustion. The “extraction MVP” is suitable for controlled staging, not automatically sufficient for open public uploads.

## 14. Multi-model provider audit

Provider abstraction, timeout, retries, fallback, rate limiting, streaming, embeddings, and bounded web search are implemented. The requirements remediation caught a real package-resolution hazard: changing LangChain versions silently downgraded `dspy-ai` when it was left floating. Pinning `dspy-ai==3.2.1` prevents that specific regression.

The provider system still needs a compatibility matrix across every active model and provider for structured output, citation/provenance fields, distress routing, multilingual translation, streaming framing, timeout, retry, and cost. A provider fallback must not silently change spiritual tone, source policy, refusal behavior, or output schema. Each provider needs a canary and a release gate.

## 15. Mobile audit

The mobile-targeted production build passes, and Capacitor integration exists for iOS and Android. This establishes buildability, not device readiness. The remaining gaps are OAuth deep links, push permissions and delivery, keyboard/back navigation, audio playback, microphone permission failure, attachment uploads, offline/poor-network transitions, background/foreground lifecycle, and store-signing configuration.

Web/mobile parity should be measured as a journey matrix rather than a feature checklist. Anonymous chat, authenticated chat, deletion, distress routing, audio, attachments, and memory should each be tested on a physical or emulator device with network interruption.

## 16. Database, performance, cost, and observability

Database migrations, indexes, retention rules, RLS policies, connection pooling, and deletion paths are extensive. Scale risk is concentrated in chat history queries, memory/vector filtering, graph traversal, attachment extraction, and multi-stage RAG fan-out. The 100,000-user question is not answered by container health: concurrency limits, provider quotas, queue depth, connection pool size, Qdrant payload indexes, Neo4j traversal bounds, Redis memory policy, and storage growth need load evidence.

The most expensive likely paths are full multi-stage RAG, embeddings/reranking, graph traversal, long context generation, attachment OCR/extraction, and trace export. The system already has coalescing, TTL caches, backpressure, quotas, model routing, and cost telemetry; it still needs workload-based cost envelopes at 100, 1,000, 10,000, and 100,000 DAU. No numeric cloud cost estimate is invented here.

Operators can currently see correlation IDs, health state, queue/backpressure indicators, model/provider metadata in the response contract, and various metrics/traces. They still need tested dashboards and alerts for time-to-first-token, total latency, provider error rate, RAG-stage latency, graph latency, cache hit rate, tokens/cost, refusal rate, faithfulness/citation metrics, memory operations, attachment failures, and release/artifact version. Jaeger export failure must be visible but non-blocking.

## 17. Testing and CI/CD audit

The fresh validation loop passed the bounded mandatory matrix: frontend unit, lint, typecheck, build, bundle budget, focused backend tests, Ruff, Bandit medium/high gate, regex safety, JSON hygiene, Compose syntax, and backend compilation. A separate full backend run passed 2,378 tests and skipped 30. Chromium accessibility passed 8/8; the static page/prelaunch suite passed 24/24; the larger Chromium regression/security run passed 43 with 3 skips and 1 flaky navigation timeout.

The explicit skips are not failures, but they are not proof. Live backend assertions, hosted auth identities, cross-browser AAL2, production audio, RLS, restore/rollback, and dependency vulnerability closure remain outside the local green matrix. CI should make these environment requirements explicit rather than silently presenting a static green build as release readiness.

## 18. Documentation and agent infrastructure

The repository has unusually rich `AGENTS.md`, `lessons.md`, `.claude`, `.codex`, `.opencode`, runbooks, reports, and task plans. The strongest useful invariants are the fail-closed artifact rule, signed anonymous-session rule, public SSE metadata allowlist, safety-before-circuit ordering, cache isolation, pinned model revisions, and deployment proxy configuration.

The main documentation risk is sprawl and temporal conflict. There are many dated plans and claims of active corpus sizes or deployed releases that are not equivalent to the current local runtime. The canonical agent operating model should be: `AGENTS.md` for binding invariants and current handoff, `lessons.md` for durable regression lessons, one current production-readiness report, one release runbook, and task files only for active work. Every dated claim should say whether it is current, historical, local-only, or production-proven.

## 19. Competitive research

Headspace’s public Ebb material emphasizes personalized recommendations, memory, privacy, security, safety-by-design, crisis support, expert involvement, pre-release evaluation, post-release monitoring, and explicit disclosure that the AI is not human care or clinical treatment. [5] [6] Waking Up differentiates through a large structured library, teachers, traditions, theory, community, and a clear practice-learning journey. [7] Perplexity sets a useful general answer-engine standard through clickable citations, conversational follow-ups, file upload, and source exploration. [8]

AskMukthiGuru’s genuine opportunity is not to imitate a generic chatbot. Its differentiation should be **source-faithful, culturally responsive spiritual guidance with transparent grounding states**, careful separation of doctrine from reflective guidance, multilingual access, a coherent practice journey, and user-controlled memory. That positioning is only credible when the curated corpus, citations, deletion controls, safety evaluation, and operational monitoring are demonstrably reliable.

## 20. Independent red-team findings

| Scenario | Fresh answer |
|---|---|
| Qdrant down | Code contains degraded/fallback paths and health checks; live behavior is not fully staged. Critical retrieval should fail closed rather than invent doctrine. |
| Neo4j down | Graph is marked non-critical in deep health; vector path should continue, but graph-latency and quality degradation need alerting. |
| Redis down | Fallbacks exist for some rate/cache paths; distributed duplicate prevention, quota, and cache privacy need failure tests. |
| Supabase down | Auth, persistence, and history degrade; the anonymous path must remain bounded and never collapse identities. |
| Provider A fails | Timeouts/retries/fallbacks exist; quality/safety/provider parity remains unproven. |
| Malformed provider output | Structured-output and output-rail tests exist; live provider compatibility remains open. |
| Retrieved content is malicious | Treat-as-data policy exists; adversarial indirect injection fixtures are still needed. |
| Memory is wrong or poisoned | User controls and scoped storage exist; conflict resolution and poisoning recovery are not fully measured. |
| Cross-user memory attack | Static authz and cache tests pass; hosted Alice/Bob proof remains open. |
| 100 concurrent identical requests | Coalescing/backpressure/rate limits exist; load evidence and cost behavior remain open. |
| Malicious 10 MB file | Size/extraction guards exist; parser/OCR/decompression stress needs staging. |
| User asks to ignore teachings | Safety/source hierarchy should dominate; held-out prompt-injection evaluation is incomplete. |
| Network interruption | JSON fallback and queued path exist; direct SSE reconnect/resume is unproven. |
| Deployment/migration failure | Health and rollback docs exist; clean migration replay and rollback drill remain open. |
| Stale cache/account deletion | Cache scopes and deletion contracts exist; full cross-store proof remains open. |

## 21. Confirmed bugs and risks requiring verification

### Confirmed

1. The current local deep readiness endpoint reports `ready=false` because `okf_compiled` is missing.
2. The live local benign browser chat turn fails after progress begins with `ERR_UNKNOWN` / `Failed to fetch` and produces no final answer or citations.
3. The local Supabase migration set fails from zero at `realtime.messages` ownership.
4. The local contextual Qdrant environment is too thin to support a meaningful doctrine NDCG claim.
5. Jaeger trace export is unavailable in the current local Compose environment, although it does not block tests.
6. A larger Chromium regression run contains a flaky 30-second navigation timeout for the Serene Mind flow; the isolated rerun was skipped by test conditions and therefore does not close live meditation proof.

### Requires verification

1. Whether the hosted production Qdrant and Neo4j actually contain the claimed approved corpus and graph state.
2. Whether dependency upgrades are installed in the image actually deployed to Railway.
3. Whether `transformers`, `json-repair`, `llm-guard`, gptcache, diskcache, and their transitive chains are acceptable under the current vulnerability database.
4. Whether OAuth, password reset, AAL2, RLS, deletion, restore, rollback, and device journeys pass with real staging identities.
5. Whether graph retrieval materially improves held-out answer quality.
6. Whether direct SSE can reconnect/resume without duplication or loss.

## 22. Missing features, features to remove, and redesign candidates

The missing production capabilities are not more UI pages. They are an approved corpus/artifact release process, a hosted staging evidence pack, full cross-store deletion proof, migration replay/rollback, complete dependency policy, provider compatibility canaries, held-out RAG/faithfulness evaluation, direct SSE resume, and device-level mobile tests.

The system should consider removing or isolating unused complexity rather than adding more layers. RAGatouille should disappear from the online fallback path once the ONNX-native MaxSim path is proven complete. Graph traversal should be removed from latency-critical requests when it does not beat vector-only retrieval. Experimental guru-voice and advanced optimization paths should remain feature-flagged until benchmark results exceed the documented threshold. Demo data should never be used as a silent substitute for a missing production corpus.

## 23. P0/P1/P2/P3 backlog

| ID | Objective | Current behavior | Desired behavior | Files / systems | Acceptance | Classification |
|---|---|---|---|---|---|---|
| P0-01 | Ship approved curated artifacts | `okf_compiled` absent; readiness red | Versioned, rights-approved, checksummed artifacts are baked into the runtime image | Corpus pipeline, `backend/app/runtime_artifacts.py`, deployment image | Deep health ready; artifact manifest verified; held-out source tests pass | Requires human/editorial approval |
| P0-02 | Close dependency risk | `pip-audit` stalls; documented unresolved chains remain | Vulnerability status is reproducible and accepted/closed by policy | `backend/requirements.txt`, lock/build CI | `pip-audit` complete; no unaccepted P0/P1; full tests and image scan pass | Ready after architecture decision for transformer chain |
| P0-03 | Fix live benign chat | Browser request ends `Failed to fetch` | Benign, distress, comparative, and multilingual staging journeys complete | chat API, queue, SSE, Nginx, runtime artifacts | 20 repeated bounded probes with final answer/grounding/citations and no duplicate turns | Ready for agent after staging access |
| P1-01 | Repair migration replay | Fresh local Supabase fails table-owner check | Disposable local/hosted project replays migrations from zero | `supabase/migrations/20260509180000_secure_realtime.sql` | `supabase db reset` and rollback rehearsal pass | Requires human approval on security migration |
| P1-02 | Prove deletion and isolation | Focused tests only | Alice/Bob and delete/forget proof across all stores | Supabase, Qdrant, Redis, queues, backups | No cross-user reads and no deleted-data resurrection | Requires hosted disposable project |
| P1-03 | Build held-out RAG evaluation | Many tests are mock-heavy or thin-corpus | Retrieval/answer/source metrics are release gates | `scripts/eval`, golden set, production-like Qdrant | Recall/NDCG, faithfulness, citation, refusal, latency, cost thresholds pass | Requires product/source decision |
| P1-04 | Prove mobile and cross-browser parity | Chromium and mobile build pass | Firefox/WebKit/device journeys pass | Playwright projects, Capacitor iOS/Android | Auth, chat, audio, uploads, deletion, responsive and offline tests pass | Ready after device access |
| P1-05 | Make observability actionable | Telemetry code exists; Jaeger unavailable | Operators can diagnose user/provider/RAG/release failures | OTel/Sentry/dashboards/runbooks | Alerts and SLOs fire in a staging drill without blocking requests | Ready after ops decision |
| P2-01 | Reduce online RAG complexity | Multiple graph/reranker/fallback layers | Keep only layers with measured lift | RAG pipeline and feature flags | Ablation report shows quality/latency/cost tradeoffs | Requires architecture decision |
| P2-02 | Close remaining lint warnings | 31 non-blocking warnings | Zero meaningful hook/export warnings | Frontend components/hooks | Lint output has zero warnings or documented exceptions | Ready for agent |
| P3-01 | Cost/load envelope | No scale proof | Publish measured cost/latency envelopes at 4 DAU levels | Load harness, dashboards | p95/p99 and estimated cost targets recorded | Requires workload decision |

## 24. Agent-ready implementation tasks

Every P0/P1 task above is implementable only with its missing environment decision made explicit. An agent can implement P0-02, P1-03 harnesses, P1-05 dashboard instrumentation, P2-01 ablation tooling, and P2-02 warning cleanup immediately. P0-01 requires a human/editorial approval of corpus sources and rights. P1-01 requires a security owner to approve the realtime migration fix. P1-02 requires a disposable hosted Supabase/Qdrant/Redis environment. P0-03 requires staging credentials and approved expected answers. P1-04 requires device/emulator and OAuth test identities.

## 25. Recommended repository structure

Keep `AGENTS.md` as the binding root contract, `lessons.md` as durable engineering memory, `docs/production-readiness/` for current and historical evidence, `docs/operations/` for runbooks and release procedures, `scripts/ops/` for bounded reproducible gates, `scripts/eval/` for evaluation, and `supabase/migrations/` as the single migration source. Do not add more instruction systems. Mark `.claude`/`.codex`/`.opencode` plans as active, historical, or superseded, and provide one canonical current handoff.

## 26. Current and target architecture

### Current architecture

The web and Capacitor clients call a FastAPI backend. Supabase provides Auth, Postgres, RLS, and storage. Redis supports queues, quotas, rate limits, caches, and transient state. Qdrant stores curated context and Second Brain vectors. Neo4j supports graph enrichment and traversal. A multi-stage RAG pipeline performs safety, routing, retrieval, graph fusion, reranking, grading, generation, verification, and citation/provenance assembly. Celery/queue workers handle background tasks, while OpenTelemetry, Sentry, Prometheus, dashboards, and health endpoints provide operations.

### Target architecture

The target should preserve the existing major services but enforce clear planes. The **serving plane** contains API, auth identity resolution, safety, bounded retrieval, generation, verification, and public provenance projection. The **knowledge plane** contains approved corpus ingestion, normalization, metadata, embedding, Qdrant indexing, graph enrichment, manifests, rights, and held-out evaluation. The **memory plane** contains encrypted Postgres source-of-truth records, scoped Qdrant projections, Redis transient state, deletion tombstones, and audit events. The **operations plane** contains health/readiness, metrics, tracing, SLO alerts, release manifests, dependency scans, image scanning, rollback, backup, and restore. The **client plane** contains web and Capacitor journeys with a shared contract test matrix.

No new infrastructure is justified until the existing planes are proven. The first target change is not another model or database: it is a trustworthy artifact release and staging-evidence process.

## 27. RAG target architecture

1. Ingest only approved sources with rights metadata.
2. Normalize documents and preserve canonical source URLs, titles, speakers, dates, language, and version.
3. Chunk with bounded size and source-segment identifiers.
4. Embed with a pinned model and record model revision/dimension.
5. Index Qdrant with explicit tenant/source/version payload indexes.
6. Build graph entities/edges offline with ontology and provenance, not on the hot path by default.
7. Retrieve vector and optionally graph context behind an experiment flag.
8. Rerank only when the held-out evaluation shows material lift for the query class.
9. Assemble context with source rights, freshness, support, and injection boundaries.
10. Generate with a provider contract that preserves safety, citations, language, and schema.
11. Verify claims and source support; abstain or mark reflective guidance when support is inadequate.
12. Project only allowlisted provenance fields to the browser.
13. Record stage latency, token use, retrieval IDs, grounding state, citation correctness, and provider/model in secure telemetry.
14. Gate releases on held-out retrieval, faithfulness, citation, refusal, latency, and cost thresholds.

## 28. Final gap analysis

The most important additional finding from the fresh pass is that the system now has enough health instrumentation to prove its own unreleasability, but the browser still presents a generic fetch failure rather than a product-level “service is warming / curated corpus unavailable” state. The next loop should make the degraded mode explicit while also fixing the underlying artifact and live chat path.

A second overlooked gap is the difference between local dependency state and the container image. The current working-tree requirements improvements are not production proof until both `backend/Dockerfile` and `Dockerfile.railway` are rebuilt and scanned from the same lock/resolution. A third is migration portability: security migrations that succeed only under hosted ownership assumptions are not reproducible disaster-recovery assets.

## 29. The 100,000-user question

If 100,000 real users started tomorrow, the first failures would likely be **answer-serving capacity and trust**, not the landing page. Full multi-stage RAG, provider calls, reranking, graph traversal, attachments, and memory operations would amplify latency, queue depth, token spend, and provider rate-limit pressure. A missing or stale curated artifact would make the service unable to provide trustworthy doctrine even while infrastructure health looked green. Direct-stream interruptions would create repeated or failed user turns. Cross-store caches and memory would become the highest-impact privacy risk if tenant scoping or deletion invalidation failed under concurrency.

The system would detect these through readiness/artifact alerts, p95/p99 latency and time-to-first-token, provider and queue error rates, backpressure, cache hit/miss, token cost, citation/faithfulness evaluation, deletion audit events, and RLS probes. It cannot detect what it does not currently measure: a complete held-out quality baseline, hosted deletion proof, cost envelope, and true graph lift.

## 30. What prevents world-class status today?

AskMukthiGuru is prevented from becoming world-class today by the gap between **architectural ambition and production proof**. It has many of the right components: safety gates, source-aware retrieval, graph enrichment, memory controls, multilingual UI, citations, queues, metrics, and agent instructions. But a world-class spiritual AI platform must make a narrower promise and prove it repeatedly: approved sources, reliable answers, transparent grounding, safe refusals, complete deletion, stable latency, measured cost, and operational recovery.

The immediate path is therefore not to add more intelligence. It is to load and verify the approved corpus, close dependency and migration risks, make the live benign chat path complete, run held-out faithfulness and refusal evaluations, prove tenant isolation/deletion/restore/rollback, and only then widen traffic.

## 31. References and evidence

[1]: ./rerun-2026-08-24/validation/summary.tsv "Fresh bounded loop validation summary"
[2]: ./rerun-2026-08-24/browser-live-chat.txt "Fresh live browser chat evidence"
[3]: ./rerun-2026-08-24/runtime-smoke.txt "Fresh local health and runtime evidence"
[4]: ./rerun-2026-08-24/distress-job-poll.txt "Fresh queued distress terminal result"
[5]: https://www.headspace.com/ai-mental-health-companion "Headspace Ebb AI mental health companion"
[6]: https://www.headspace.com/ai "Headspace AI principles and safety practices"
[7]: https://www.wakingup.com/ "Waking Up meditation and wisdom product"
[8]: https://www.perplexity.ai/hub/blog/getting-started-with-perplexity "Perplexity cited answer-engine product overview"
