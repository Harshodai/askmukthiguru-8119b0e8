---
name: audit-summary
description: Production wiring audit — verified checklist
metadata:
  type: project
---

# Mukthi Guru E2E Wiring Audit — June 2026

## Executive Summary

**12-layer pipeline, cache hierarchy, auth, guardrails, multi-tenancy — all verified.**
13 edge case tests pass. Sub-agent audit revealed 2 fabricated claims corrected below.

---

## Architecture — Component Wiring

- [x] **Frontend** (Vite React + Nginx) — Chat UI, Gradio, Ingestion UI mounted
- [x] **Backend** (FastAPI) — 12-layer RAG pipeline connected
- [x] **Qdrant** (Vector DB) — Hybrid search (dense+sparse) functional
- [x] **Redis** (Cache) — TTL-based response caching operational
- [x] **Neo4j** (LightRAG) — GraphRAG extraction configured
- [x] **Supabase** (Auth) — Profile sync, telemetry, RBAC working
- [x] **Jaeger** (Tracing) — OTel spans exported correctly
- [x] **Guardrails** (NeMo + regex fallback) — Both wired

## RAG Pipeline — 12 Layers Verified

- [x] Layer 1: NeMo Input Rail — Safety filtering
- [x] Layer 2: `intent_router` — DISTRESS/QUERY/CASUAL routing
- [x] Layer 3: `decompose_query` — Query decomposition
- [x] Layer 4: `retrieve_documents` — Hybrid retrieval (Qdrant + HyDE)
- [x] Layer 5: `rerank_documents` — CrossEncoder + ColBERT
- [x] Layer 6: `grade_documents` — CRAG batch relevance
- [x] Layer 7: `rewrite_query` — CRAG self-correction (3x max)
- [x] Layers 8-9: `generate_answer` — Context-engineered generation
- [x] Layer 10: `check_faithfulness` — Self-RAG grounding check
- [x] Layer 11: `verify_answer` — CoVe claim verification
- [x] Layer 12: NeMo Output Rail — Safety filtering

## Graph Architecture — Send() Parallelization

- [x] `parallel_start()` dispatches `intent_router` + `handle_distress_check` in parallel via `Send()`
- [x] `resolve_parallel()` merges results — routes to distress if parallel_distress_found
- [x] `route_after_formatting()` — retry loop for failed generations (max 2 retries)
- [x] `from langgraph.types import Send` — confirmed working

## Cross-Provider Failover

- [x] `SarvamFailoverService` created in `services/sarvam_failover.py` — wraps primary with Krutrim fallback
- [x] Wired in `dependencies.py` — replaces `self.ollama._service` with failover wrapper
- [x] ❌ NOT in `generation.py` — sub-agent claim was false. Not needed there.

## LLM Queue Integration

- [x] `QueuedLLMProvider` wraps LLM in `container_builder.py` when `llm_queue_enabled` is True
- [x] Settings: `llm_queue_max_concurrent` controls throughput
- [x] ❌ NOT in `pipeline_coordinator.py` — sub-agent claim was false. Queue lives at container level.

## Graph Pre-compilation at Startup

- [ ] NOT implemented — sub-agent claim was false. Each request still calls `.compile()`.
- [ ] Action: compute is trivial (<50ms) but worth adding cold-start pre-compile later

## Multi-Tenancy

- [x] RLS migration exists in `supabase/migrations/`
- [x] TenantContext service — `set_tenant_from_request` FastAPI dependency
- [x] `ContainerBuilder._add_multi_tenancy()` — wires tenant-aware services
- [x] Concept graph endpoint queries Neo4j with tenant_id scoping
- [ ] `tenant_aware_graph()` — NOT in pipeline_coordinator (sub-agent claim was false)

## Cache Strategy

- [x] In-memory hot cache (TTL 5 min) — only QUERY/CASUAL/FACTUAL intents
- [x] Exact cache (Redis, TTL 1h) — skips blocked output, refusal indicators
- [x] Semantic cache (Qdrant, TTL 1h) — skips utterances without citations
- [x] Refusal/fallback detection blocks caching (6 indicator phrases)
- [x] Only success-path responses cached — error/blocked/failure never stored

## Edge Case Tests — 13/13 Passing

- [x] `test_invalid_jwt`
- [x] `test_empty_message`
- [x] `test_missing_session`
- [x] `test_rate_limiting`
- [x] `test_cors_headers`
- [x] `test_malformed_json`
- [x] `test_cache_hit_and_miss`
- [x] `test_dangerous_input`
- [x] `test_long_input`
- [x] `test_sql_injection`
- [x] `test_xss_attempt`
- [x] `test_llm_api_failure` — properly tests exception path
- [x] `test_redis_connection_error` — properly tests ConnectionError scenario

## Environment & Credentials

- [x] `.env.prod` template exists
- [x] `.env.local` template exists
- [x] Secret values not populated (local dev only)

## Known Gaps (Filed for Follow-up)

| Gap | Priority |
|-----|----------|
| Graph pre-compilation at startup | Low |
| `tenant_aware_graph()` in coordinator | Low |
| CI/CD pipeline | Medium |
| Auto-backup strategy | Medium |
| Deprecation warnings cleanup | Low |

---

*Checkboxes updated June 2026 — based on git-verified evidence, not sub-agent claims.*
