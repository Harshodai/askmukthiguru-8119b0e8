# AskMukthiGuru Free-to-User Product Inventory

**Evidence classes:** `VERIFIED IN REPOSITORY` unless otherwise stated. This is an implementation inventory, not a claim that every surface is runtime-proven.

## Product surface map

| Surface | User entry point | Main implementation | External/deferred work | Free-user cost exposure | Current status / risk |
|---|---|---|---|---|---|
| Anonymous chat | `/chat` | React chat page; `/api/chat`, `/api/chat/v2`, `/api/chat/stream` | OpenRouter/LLM, Qdrant, Redis, graph/retrieval, optional translation | High per substantive turn | Core value surface; quota and concurrency gates exist, but provider cost remains the main exposure |
| Queued chat | Chat fallback/request queue | `job_queue`, queue router, polling/SSE projection | Redis Streams, worker, LLM/RAG | High plus queue/Redis overhead | Separate transport contract; must be measured independently from direct streaming |
| Greeting fast path | Chat composer | `routing_primitives`, pipeline glue/cache stage | None for pure supported greeting | Near-zero | Strong cost/latency opportunity; only pure greeting regex may short-circuit |
| Distress/safety | Chat | input/output guardrails and distress routing | No provider call for deterministic acute cases where matched | Low for deterministic path; high if uncertain/provider fallback | Safety-critical; never optimize by broadening allowlists or weakening detection |
| Retrieval and citations | Chat answer / References UI | Qdrant, LightRAG/Neo4j, reranker, citation formatter | Embeddings, reranking, optional planner/generation | High compute/provider exposure | Primary quality moat candidate; current long-tail latency and grounded-partial states require held-out evidence |
| Practice and meditation | `/practices`, `/practices/:slug`, Serene Mind flows | Practice pages/components and chat integration | Potential TTS/voice, LLM guidance | Medium | Value surface; verify real versus demo data and consented auto-open behavior |
| Guides and notebooks | `/guides/*`, `/notebooks` | Static/React pages, study notebook | Backend APIs for notebook/SRS where used | Low to medium | Likely low marginal cost; measure activation/value before adding paid infrastructure |
| Knowledge graph | `/knowledge-graph`, `/wisdom-map` redirect | `KnowledgeGraphPage`, KG API | Neo4j / graph endpoints; demo fallback documented | Medium idle and request cost | Demo fallback must not be mistaken for live graph proof |
| Second Brain / memory | `/second-brain`, `/reflections` redirect, `/profile` | memory routes, encrypted Postgres notes, Qdrant vectors | Supabase/Postgres, Qdrant, encryption/key lifecycle | High storage and retrieval cost per active user | High trust value, but expensive; writes/deletion/tenant isolation need strict measurement |
| Attachments/multimodal | Chat upload | `/api/chat/upload`, bounded extractors/OCR/transcription | OCR, Whisper/local compute, storage/bandwidth | High and abuse-sensitive | Limits and ephemeral evidence rules exist; malware scanning/page/frame citations/resumable jobs remain audit gaps |
| Speech | Voice controls / native | Web Speech API and Capacitor speech plugin | Browser/device speech or backend TTS | Low to high depending provider | Verify browser/platform coverage and whether any fallback calls a paid provider |
| Authentication/MFA | `/auth`, `/auth/mfa`, reset flow | Supabase auth, MFA/AAL2 routes | Supabase email/OAuth | Low per user, operationally important | Authenticated-only surfaces should not be required for core free chat |
| Healing course | Profile/practice surfaces | healing-course API/service | Database persistence, notifications where enabled | Medium background/storage cost | Must prove user value and avoid unsolicited automation |
| Push notifications | Auth/profile settings | Capacitor push and backend settings | Push provider/device services | Potential background cost | Feature flag exists; validate consent, delivery, and opt-out |
| Feedback/support/waitlist | Profile/public | feedback, support, waitlist routes | SMTP or file fallback, storage | Low | Waitlist currently disabled by configuration; support fallback should be bounded and privacy-safe |
| Admin analytics | `/admin/*` | admin pages, KPI/metrics/cost/eval APIs | Supabase, telemetry, optional admin LLM assistant | Internal cost, not end-user value | Admin LLM question-answering is an avoidable cost center; prefer deterministic dashboards for routine analytics |
| Ingestion | Admin/ops and worker | ingestion APIs/scripts, Celery worker | YouTube/transcription/LLM/embedding/graph/vector writes | Very high background cost | Worker is profile/ops-controlled; ingestion must remain explicit, rights-aware, and gated |
| Observability | Admin/ops | Prometheus, Grafana, Jaeger, telemetry DB | Storage and scrape overhead | Low per request, non-zero idle cost | Keep only signals that drive reliability/quality/cost decisions; bound retention and cardinality |

## Cost-control evidence

The anonymous quota is enforced at chat admission through `AnonQuotaService.check_and_record`, with a default of **5 messages per 24-hour anonymous session**, Redis-first storage, and a conservative degraded limit of **3** when Redis cannot be used. Reservations are claimed on successful completion and released on failure/cancellation. This is a real free-user control, not merely a dashboard setting.

Chat admission also has a per-replica `max_concurrent_chat` default of **20**, rejecting an exhausted semaphore with HTTP 503 and `Retry-After` rather than allowing unlimited in-process work. The LLM queue separately defaults to **5** concurrent operations and a maximum queue size of **50**. These controls reduce overload risk but are not a direct spend cap.

Token usage is recorded asynchronously to Supabase through `TokenAccumulator` and `CostTracker`. The tracker records model, provider, input/output tokens, cost, endpoint, tenant, user, and session and runs a soft hourly budget check. The current provider cost table contains fixed assumptions for Ollama, Sarvam, Krutrim, and OpenAI; OpenRouter usage must be verified to ensure provider/model cost accounting is not silently mapped to a zero or stale rate. The code explicitly labels provider-reported cost separately from estimated cost, which is correct, but current budget alerts are not hard admission enforcement.

OpenRouter settings include a **$0.25 daily** and **$6 monthly** provider budget plus a **$0.03 maximum request cost** and an optional budget guard that is currently disabled by default. The application also has a broader **$36 monthly operating-envelope alert**, documented as a soft alert rather than a hard cap. For a free-to-user product, the highest-priority cost question is whether these limits are enforced before provider calls or only observed after spend occurs.

## Initial free-to-user findings

| Finding | Evidence class | Priority | Why it matters |
|---|---|---|---|
| Core anonymous chat is free-access but has a bounded quota | VERIFIED IN REPOSITORY | P0 control | Prevents unbounded abuse and makes free access operationally possible |
| Spend budgets are partly observational and budget guard is disabled by default | VERIFIED IN REPOSITORY | P0/P1 | A soft alert cannot prevent a provider bill from exceeding the free-product envelope |
| OpenRouter cost-rate coverage needs reconciliation with actual provider/model billing | VERIFIED IN REPOSITORY + UNKNOWN | P0 | Incorrect zero/stale rates can make unit economics look safe while real spend grows |
| Deterministic greetings and acute distress routes are low-cost | MEASURED / VERIFIED IN REPOSITORY | P1 | Good candidates for high-volume free access, but only within strict safety/phrase boundaries |
| Admin LLM analytics is internal functionality with direct provider cost | VERIFIED IN REPOSITORY | P1 | Replace routine questions with deterministic aggregations or rate-limit/admin budget it |
| Attachments, memory, ingestion, reranking, translation, and graph work are high-cost optional paths | INFERRED from architecture; must be MEASURED | P1 | They need per-workflow cost attribution and admission limits before broad free access |
| Local Docker memory cannot be converted into hosting dollars | VERIFIED IN REPOSITORY / lesson | P0 evidence rule | Railway/provider billing must come from service-level usage data, not local resource display |

## Inventory limitations

This file inventories code and configuration. It does not prove every page, API, provider, worker, or external dependency works end-to-end. Runtime verification, real-provider cost reconciliation, security tests, and first-party product analytics remain separate phases. SimilarWeb/no-data results and failed external skill lookup cannot support demand, traffic, or commercial claims.
