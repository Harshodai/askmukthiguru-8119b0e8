# MukthiGuru — Comprehensive Remediation + Integration Goal

**Scope:** Complete the remaining code-review remediation units, merge all pending worktree changes to `main`, implement the backend integration spec for Custom Assistants & Notes, study and integrate best ideas from `hyper-extract`, and apply retrieval-quality improvements.

**Guiding principle:** Generation quality is a reflection of retrieval quality. Prioritize chunking, metadata filtering, deduplication, smaller-but-better context windows, and preprocessing before model changes.

---

## Phase 1 — Stabilise what we have (DONE)

- [x] Unit 5 — Guardrail allowlist fail-safe
- [x] Unit 6 — CSP + rate limiter hardening
- [x] Unit 7 — Generation node reliability (SarvamCloudService DI, token budget)
- [x] Unit 8 — Service locator cleanup, telemetry deduplication, cache log context
- [x] Unit 9 — Reranking + intent fail-safes
- [x] Merge all Unit 7/8/9 worktree commits into `main`
- [x] Fix merge artefacts and verify regression tests pass

---

## Phase 2 — Backend decomposition (Units 10–14)

- [x] **Unit 10 — Decompose `backend/rag/prompts.py`**
  - Split monolithic prompts.py into `backend/rag/prompts/{guardrails,rag,system}.py` with re-export facade
  - Add `backend/tests/test_prompts_decomposition.py`
  - Merged to main (legacy `backend/rag/prompts.py` removed)

- [x] **Unit 11 — Decompose `backend/services/cache_service.py`**
  - Split into `backend/services/cache/{redis_adapter,semantic_adapter,memory_adapter,factory,exceptions,llm_cache,constants}.py`
  - Fail-closed init behaviour preserved via `CacheInitializationError`
  - Health checks available through `ServiceContainer.health_status()`

- [x] **Unit 12 — Decompose `backend/services/qdrant_service.py`**
  - Split into `backend/services/qdrant/{searcher,indexer,neighbours,raptor,filters,exceptions,utils}.py`
  - Facade in `backend/services/qdrant_service.py` preserves public API
  - Metadata/tag filtering hooks preserved and propagated to all hybrid prefetches

- [x] **Unit 13 — Decompose `backend/app/main.py`**
  - Routes moved into `backend/app/api/{chat,health,ingest,memory,profile,speech,job_routes,cache_metrics}.py`
  - Middleware ordering preserved

- [x] **Unit 14 — Decompose `backend/app/dependencies.py`**
  - `ContainerBuilder` is the active construction path in `get_container()`
  - Legacy `ServiceContainer.__init__` retained but emits `DeprecationWarning` and delegates to builder stages
  - DI health verification at startup via `_di_health_check()`

---

## Phase 3 — Frontend decomposition (Units 15–17) — DONE

- [x] **Unit 15 — Decompose `src/lib/aiService.ts`**
  - Split chat transport, health polling, fallback/placeholder mode, and streaming into `src/lib/chat/`

- [x] **Unit 16 — Decompose admin dashboard pages**
  - Move data fetching into `src/admin/hooks/` and presentational components into `src/admin/components/`

- [x] **Unit 17 — Component boundary cleanup**
  - Extract reusable UI into `src/components/common/ui/`

---

## Phase 4 — Regression test packs (Units 18–19)

- [x] **Unit 18 — Backend regression pack**
  - Contract test for `retrieve_documents`: `backend/tests/test_retrieve_documents_contract.py`
  - Graph strategy wiring tests: `backend/tests/test_graph_strategies.py`
  - Fail-closed guardrails tests: `backend/tests/test_guardrails.py`, `test_guardrails_chain.py`
  - Intent fallback tests: `backend/tests/test_intent_router.py`
  - Retrieval empty-set / cutoff tests: `backend/tests/test_retrieval_quality.py`
  - Hyper-extract adapter tests: `backend/tests/test_hyper_extract_adapter.py`

- [x] **Unit 19 — Frontend regression pack**
  - `src/test/aiService.regression.test.ts` covers health/fallback/streaming paths
  - `src/test/components/{ChatInterface,ChatMessage,LanguageSelector}.test.tsx` cover component behavior

---

## Phase 5 — New integrations

### 5.1 Backend Integration Spec — Custom Assistants & Notes

Source: `docs/BACKEND_INTEGRATION_ASSISTANTS_AND_NOTES.md`

- [x] Add `AssistantContext` optional field to chat request contract (`backend/app/schemas.py`)
- [x] Apply `assistant.system_prompt` override in prompt assembly while preserving safety layers
- [x] Apply `assistant.knowledge_tags` filter in Qdrant retrieval; hard exclude `tags: ["sky"]` unless explicitly requested
- [x] Add `tags text[]` to chunk payload and `kb_sources` telemetry records
- [x] Add `assistant_slug` log to `chat_queries` telemetry sink (`backend/app/telemetry_sink.py`)
- [x] Add `tags` parameter to `IngestionPipeline.ingest_url()` and CLI bulk ingestion scripts (`--tags`)
- [x] Add tag multi-select to ingestion UI (`ingest-ui/index.html` + `app.js`)
- [ ] Non-regression smoke tests: run `backend/benchmarks/smoke_doctrine.py` with/without assistant block
- [ ] Database migration: add `assistant_slug` column to `chat_queries` in Supabase (backend insert already sends the field)

### 5.2 Retrieval-quality improvements

Inspired by the "Biggest improvement to RAG wasn't a better LLM" principles. Status and mapping documented in `docs/PRODUCTION_RAG_OVER_MILLIONS_OF_PDFS.md`.

- [x] **Better chunking strategy (implemented, partly gated)**
  - `RecursiveCharacterTextSplitter` remains default; `backend/ingest/boundary_chunker.py` provides sentence-boundary splitting
  - `backend/ingest/adaptive_chunking.py` ports `ekimetrics/adaptive-chunking` and is wired behind `use_ingest_adaptive_chunker`
  - *Gaps:* set flags default after benchmark validation; add Indic-language sentence splitter

- [x] **Metadata-based filtering (implemented, used in chat)**
  - `source_url`, `title`, `tags`, detected `language`, and `source_type` stored in Qdrant metadata
  - `knowledge_tags` threaded through retrieval from `GraphState` to `qdrant.search()`
  - `kb_sources` telemetry table records source-level tags
  - Assistant-aware tag filtering and hard `sky` exclusion active

- [x] **Removing duplicate content (implemented, opt-in)**
  - Near-duplicate detection at ingestion time via `backend/ingest/deduplication.py`
  - Deduplication pass in retrieval via `rag.nodes.retrieval._apply_retrieval_dedup()`
  - *Gaps:* both flags are off by default; no persisted cross-ingest duplicate index

- [x] **Retrieving fewer but more relevant chunks (implemented, gated)**
  - Score-delta cutoff (`score < 0.5 * top_score`) implemented but gated by `retrieval_score_delta_enabled`
  - MMR diversity reranking and rerank floor already active
  - CRAG relevance grading implemented
  - *Gaps:* score-delta and lowered top-k need benchmark validation before becoming default

- [x] **Improving document preprocessing (implemented, default on)**
  - Clean transcript artifacts (timestamps, filler words, bracketed captions)
  - Normalize spiritual terms using `DOCTRINE_SYNONYMS`
  - LLM transcript correction and auditor gate before indexing
  - Parent-chunk summarization for RAPTOR available when `raptor_parent_summaries_enabled` is set

### 5.3 `hyper-extract` study and integration — DONE

Repo: `https://github.com/yifanfeng97/hyper-extract`

- [x] Fetch and read the repository structure, README, and core modules
- [x] Identify techniques applicable to our pipeline (document structure, atom facts, graph/hypergraph extraction)
- [x] Port/adapt the highest-value extraction logic into `backend/ingest/hyper_extract_adapter.py` without heavy dependencies
- [x] Wire optional enrichment into `IngestionPipeline` behind `use_hyper_extract_enrichment`
- [x] Add unit tests in `backend/tests/test_hyper_extract_adapter.py`
- [x] Document the decision in `docs/HYPER_EXTRACT_INTEGRATION.md`

### 5.4 `ekimetrics/adaptive-chunking` study and integration — DONE

Repo: `https://github.com/ekimetrics/adaptive-chunking`

- [x] Fetch and read the repository structure, README, and core chunking strategy
- [x] Identify how it can improve transcript/PDF ingestion beyond current `RecursiveCharacterTextSplitter`
- [x] Port/adapt a lightweight adaptive chunking module into `backend/ingest/adaptive_chunking.py`
- [x] Wire into `IngestionPipeline` behind `use_ingest_adaptive_chunker` config flag
- [x] Document decision in `docs/ADAPTIVE_CHUNKING_INTEGRATION.md`

---

## Phase 6 — Continuous verification

- [x] Run `backend/tests/` and `src/test/` + `src/tests/` after every unit
- [ ] Run `backend/benchmarks/smoke_doctrine.py` for no-regression after the current batch
- [x] Keep `main` green; commit each unit separately
- [ ] Push `main` to origin after full suite + smoke are green

---

## Worktree policy

- Create one worktree per unit / per parallel stream.
- When a worktree branch is green, merge to `main` with `--no-ff` and descriptive message.
- Remove stale worktrees after merge.

---

## Next immediate step

- Complete **Phase 5.3** hyper-extract integration.
- Run `backend/benchmarks/smoke_doctrine.py` and `backend/tests/` full suite.
- Commit current fixes and push `main`.
- Produce `docs/PENDING_AND_EDGE_CASES.md` handoff document.
