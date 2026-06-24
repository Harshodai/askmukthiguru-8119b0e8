# MukthiGuru — Remaining Work & Edge-Case Handoff

**Last updated:** 2026-06-23
**Status:** The large decomposition and integration batches are merged to `main`. A few targeted pieces remain to reach "top notch / all edge cases covered".

---

## 1. What is already done

### Backend decomposition (Units 10–14)
- `backend/rag/prompts.py` decomposed into `backend/rag/prompts/{guardrails,rag,system}.py` with facade.
- `backend/services/cache_service.py` decomposed into `backend/services/cache/` package with fail-closed init and DI health checks.
- `backend/services/qdrant_service.py` decomposed into `backend/services/qdrant/{searcher,indexer,neighbours,raptor,filters,exceptions,utils}.py`.
- `backend/app/main.py` routes moved into `backend/app/api/{chat,health,ingest,memory,profile,speech,job_routes,cache_metrics}.py`.
- `backend/app/dependencies.py` uses `ContainerBuilder` as the active construction path; legacy `ServiceContainer` delegates with a deprecation warning and DI health check runs at startup.

### Frontend decomposition (Units 15–17)
- `src/lib/aiService.ts` decomposed into `src/lib/chat/{transport,streaming,health,placeholder,assistant,errors,config}.ts`.
- Admin dashboard pages refactored into `src/admin/hooks/` and `src/admin/components/`.
- Reusable UI primitives moved to `src/components/common/ui/`.

### Regression tests (Units 18–19)
- Backend contract/wiring/fail-closed pack: `test_chat_contract.py`, `test_graph_strategy_wiring.py`, `test_fail_closed_paths.py`, `test_guardrails*.py`, `test_intent_router.py`, `test_retrieval_quality.py`.
- Frontend regression pack: `src/test/aiService.regression.test.ts`, `src/test/components/{ChatInterface,ChatMessage,LanguageSelector}.test.tsx`.

### Custom Assistants & Notes backend integration
- `AssistantContext` optional field added to chat request contract (`backend/app/schemas.py`).
- `assistant.system_prompt` override applied in prompt assembly while preserving safety layers.
- `assistant.knowledge_tags` filter threaded through `GraphState` → `rag/nodes/retrieval.py` → `QdrantSearcher`.
- Hard exclusion of `tags: ["sky"]` unless the request explicitly includes `"sky"`.
- Chunk payload carries `tags`; `kb_sources` telemetry records tags.
- `assistant_slug` propagated to `chat_queries` telemetry sink.
- `IngestionPipeline.ingest_url()` accepts `tags`; bulk ingest scripts expose `--tags sky,private`.
- Ingestion portal (`ingest-ui/`) has a tag multi-select.

### Retrieval-quality improvements
- `backend/ingest/adaptive_chunking.py` ports the `ekimetrics/adaptive-chunking` strategy and is wired behind `use_ingest_adaptive_chunker`.
- Sentence-boundary chunker in `backend/ingest/boundary_chunker.py`.
- Near-duplicate removal at ingest and retrieval time.
- Score-delta cutoff, MMR diversity reranking, CRAG relevance grading.
- Transcript cleaning, doctrine normalization, LLM correction/auditor gate, RAPTOR parent summaries.

---

## 2. What still needs work

### 2.1 Hyper-extract integration (Phase 5.3)
**Goal:** Pull the highest-value ideas from `https://github.com/yifanfeng97/hyper-extract` into `backend/ingest/` without heavy dependencies.

**Concrete next steps:**
1. Fetch the repo README and core modules (`src/`, `model/`, `utils/`).
2. Identify which parts are applicable:
   - Document-structure parsing / hierarchical section extraction.
   - Atomic fact extraction and redundancy collapse.
   - Graph/hypergraph linking of entities and concepts.
3. Port a lightweight module, e.g. `backend/ingest/hyper_extract_adapter.py`, that:
   - Takes raw transcript/text and returns structured `{sections, atomic_facts, entities, relationships}`.
   - Uses only standard library + existing project deps (no new heavy packages).
   - Is called optionally from `IngestionPipeline` behind a config flag.
4. Add unit tests in `backend/tests/test_hyper_extract_adapter.py`.
5. Write `docs/HYPER_EXTRACT_INTEGRATION.md` explaining what was ported, what was skipped, and how it improves retrieval.

### 2.2 Gated retrieval-quality flags need benchmarking
The following flags exist but are off by default. To reach top-notch quality, validate each with `backend/benchmarks/comprehensive_benchmark.py` or `ruthless_benchmark.py`, then flip the default if quality improves and latency is acceptable:

| Flag | File | What it does |
|------|------|--------------|
| `use_ingest_adaptive_chunker` | `backend/app/config.py` | Use adaptive chunking at ingest time |
| `retrieval_deduplication_enabled` | `backend/app/config.py` | Deduplicate retrieved chunks |
| `retrieval_score_delta_enabled` | `backend/app/config.py` | Drop low-score chunks via score-delta cutoff |

**Concrete next steps:**
1. Run `backend/benchmarks/comprehensive_benchmark.py` with each flag enabled separately and together.
2. Compare hallucination rate, answer relevance, faithfulness, and latency vs baseline.
3. Update `docs/PRODUCTION_RAG_OVER_MILLIONS_OF_PDFS.md` with results.
4. Flip defaults only where the benchmark strictly wins.

### 2.3 Custom Assistants non-regression smoke tests
The integration code is in place but needs a final smoke run.

**Concrete next steps:**
1. Run `backend/benchmarks/smoke_doctrine.py` without an `assistant` block → confirm identical behavior to today.
2. Run a targeted script/chat request with `assistant.knowledge_tags=["sky"]` against a corpus that has **no** SKY chunks → expect graceful fallback, no 500.
3. Run with `assistant.knowledge_tags=["general"]` and verify no SKY chunks appear in retrieval citations.
4. Verify `chat_queries.assistant_slug` is populated for assisted requests.

### 2.4 Database migration for `chat_queries.assistant_slug`
The backend already writes `assistant_slug` into the `chat_queries` insert payload, but the Supabase column may not exist yet.

**Concrete next step:**
- Add a migration to create `chat_queries.assistant_slug text` (nullable).
- Regenerate `src/integrations/supabase/types.ts` so admin dashboards can read it.

### 2.5 End-to-end assistant invite redemption
The spec says the frontend will redeem `sky-...` codes through a Supabase edge function (`redeem-assistant-invite`). Backend does not need to handle it, but make sure:
- `public.assistant_access` RLS allows inserts by the edge function.
- `useAssistants` hook filters visibility correctly.

### 2.6 Full test-suite hygiene
- Keep running `backend/tests/` and `src/test/` + `src/tests/` after every change.
- Keep `main` green and push after each verified batch.
- Clean up any remaining stale worktrees under `.claude/worktrees/`.

---

## 3. Edge cases to cover before calling it "top notch"

| Edge case | How to cover | Status |
|-----------|--------------|--------|
| Empty `assistant` block | Backend defaults to general persona + no tag filter | Code done, smoke pending |
| `assistant.knowledge_tags=[]` | Retrieve across all corpora, still exclude SKY unless requested | Code done, test pending |
| `assistant.knowledge_tags=["sky"]` | Include SKY chunks; verify other assistants cannot see them | Code done, test pending |
| Corpus with zero matching tags | Graceful fallback with "no teachings found yet" | Needs smoke test |
| Malformed tags with spaces/capitals | Normalize to lowercase, strip whitespace at API boundary | Done in `ingest.py` and bulk scripts |
| Ingestion UI submits no tag | Enforce at least `"general"` (client + server) | UI enforces; server defaults |
| Concurrent ingestions overwrite tracker status | `IngestionTracker` keys by URL; consider adding job id if same URL ingested twice | Future improvement |
| Redis tracker stores tags as JSON | Already handled | Done |
| Score-delta cutoff removes all chunks | Ensure fallback to top-k without cutoff | Code exists, needs test |
| Deduplication removes too much | Tune threshold per language and content type | Needs benchmark |
| Adaptive chunker creates oversized chunks | Add max-length guard | Port already includes bounds; test |
| Hyper-extract adds LLM cost at ingest | Make it opt-in and cache results | Design as optional flag |

---

## 4. Recommended finish order

1. **Finish hyper-extract integration** (subagent or focused session) → commit → run backend tests.
2. **Run smoke doctrine** → commit any regression fixes.
3. **Run `backend/benchmarks/comprehensive_benchmark.py` with gated flags** → document results, flip safe defaults.
4. **Apply Supabase migration for `chat_queries.assistant_slug`**.
5. **Run full frontend + backend suites one final time** → push `main`.
6. **Clean worktrees** and close out GOAL.md.

---

## 5. Quick verification commands

```bash
# Backend focused
rtk proxy python3 -m pytest tests/test_assistants_integration.py -q

# Backend full
rtk proxy python3 -m pytest tests/ -q --tb=short

# Smoke
rtk proxy python3 backend/benchmarks/smoke_doctrine.py

# Frontend
rtk proxy npm test -- --run

# Push when green
rtk proxy git push origin main
```

If tokens run out, the next owner should start with step 1 above and use the verification commands after each change.
