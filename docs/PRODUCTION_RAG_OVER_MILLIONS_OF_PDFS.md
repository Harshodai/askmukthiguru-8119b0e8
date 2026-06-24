# Production RAG over Millions of PDFs — MukthiGuru Mapping

## Summary

The most reliable way to improve a RAG system is not to swap the LLM but to improve what reaches the model: **better chunks, cleaner context, stricter filtering, and fewer duplicates**. This document maps each retrieval-quality principle from production RAG literature to the current MukthiGuru implementation and flags what remains to be done.

The codebase already covers most principles at least partially; the remaining work is mostly about enabling gated defaults, finishing decomposition, and validating with benchmarks.

---

## 1. Better chunking strategy

**Principle:** A uniform chunk size harms retrieval. Sentence-aware, semantic, and hierarchical chunking produce chunks that are self-contained and topically coherent.

### MukthiGuru implementation status: **Partial — mature but not default everywhere**

| Capability | Status | Location |
|------------|--------|----------|
| Boundary-aware chunker (paragraph + sentence boundaries, whole-sentence overlap) | Implemented, opt-in | `backend/ingest/boundary_chunker.py` |
| Homegrown adaptive chunking (recursive vs. semantic, SC + ICC) | Implemented, default for long docs | `backend/services/adaptive_chunking_service.py` + `services.adaptive_chunking_adapter.py` |
| ekimetrics adaptive-chunking port (recursive / recursive_small / semantic, five metrics) | Implemented, opt-in | `backend/ingest/adaptive_chunking.py` |
| Proposition chunking (LLM-decomposed atomic statements) | Implemented, used in enhanced path | `backend/services/proposition_service.py`, `ingest/pipeline.py:_proposition_split()` |
| Parent-Child hierarchical indexing | Implemented | `backend/ingest/pipeline.py:_hierarchical_split()`, `ingest/raptor.py` |
| Sentence-boundary child chunks (~400 char target) | Implemented | `backend/ingest/pipeline.py:_hierarchical_split()` |

### What is missing / gated

- The boundary chunker is gated behind `use_boundary_chunker=False`.
- The ekimetrics port is gated behind `use_ingest_adaptive_chunker=False`.
- The enhanced video path still defaults to the homegrown adaptive adapter; switching it to the ekimetrics port is pending validation.
- There is no transcript-aware Indic-language sentence splitter yet.

---

## 2. Metadata filtering

**Principle:** Filter before ranking. Use source, language, tags, and content type to reduce the candidate set and improve precision.

### MukthiGuru implementation status: **Implemented — used in chat and ingestion**

| Field | Where stored | Where used |
|-------|--------------|------------|
| `source_url` | Qdrant chunk metadata | `qdrant_service.py:build_source_url_filter()`, dedup by source |
| `title` | Qdrant chunk metadata | `qdrant_service.py:build_title_filter()` |
| `source_type` (video / image / text / document) | Qdrant chunk metadata (`source_type` / `content_type`) | Ingestion writes it; retrieval can filter on it |
| `tags` | Qdrant chunk metadata + `kb_sources` table | Chat requests can pass `knowledge_tags`; Qdrant applies tag filter |
| `language` | Qdrant chunk metadata | `qdrant_service.py:build_language_filter()` |
| `content_type` | Qdrant chunk metadata | `qdrant_service.py:build_metadata_filter()` |

The chat pipeline already threads `knowledge_tags` from `GraphState` through `retrieve_for_single_query` and into `qdrant.search()`. The filter builder is in `backend/services/qdrant_service.py` (`build_metadata_filter`, `build_tags_filter`, `_build_tag_conditions`).

### What is missing / gated

- Tag multi-select UI in the ingestion portal exists only partially.
- There is no hard exclude for `tags: ["sky"]` unless the request explicitly includes `"sky"`.
- Assistant-aware tag filtering (Phase 5.1) is partially wired but needs completion.

---

## 3. Removing duplicate content

**Principle:** Near-duplicate chunks waste context window and dilute ranking scores. Deduplicate at ingestion and again at retrieval.

### MukthiGuru implementation status: **Implemented — opt-in at both layers**

| Capability | Status | Location |
|------------|--------|----------|
| MinHash-style near-duplicate detection | Implemented | `backend/ingest/deduplication.py` |
| Ingestion-time dedup (chunks + paired metadata) | Implemented, gated by `ingestion_deduplication_enabled` | `backend/ingest/pipeline.py:_embed_and_index()` calls `deduplicate_by_payload()` |
| Retrieval-time dedup | Implemented, gated by `retrieval_deduplication_enabled` | `backend/rag/nodes/retrieval.py:_apply_retrieval_dedup()` |
| Hash-based uniqueness guard in RRF merge | Implemented | `backend/rag/nodes/retrieval.py` uses `hash(doc["text"][:100])` |

### What is missing / gated

- Both dedup passes are disabled by default and must be enabled via config.
- There is no persisted duplicate index or bloom filter across re-ingestion.

---

## 4. Retrieving fewer but more relevant chunks

**Principle:** Ten great chunks beat thirty mediocre ones. Drop low-scoring docs, apply a score floor, and use diversity reranking.

### MukthiGuru implementation status: **Implemented — mostly gated or implicit**

| Capability | Status | Location |
|------------|--------|----------|
| Score-delta cutoff (`score >= 0.5 * top_score`) | Implemented, gated by `retrieval_score_delta_enabled` | `backend/rag/nodes/retrieval.py:_apply_score_delta_cutoff()` |
| MMR diversity reranking | Implemented | `backend/services/qdrant_service.py:mmr_select()` |
| CrossEncoder rerank floor (`rerank_min_score=0.35`) | Implemented | `backend/app/config.py`, `backend/rag/nodes/reranking.py` |
| CRAG relevance grading (batch LLM grading) | Implemented | `backend/rag/nodes/retrieval.py` / `verification.py` |
| Top-k reduction after cutoff (`rag_top_k_retrieval_after_cutoff`) | Implemented | `backend/rag/nodes/retrieval.py` |
| Adaptive parent excerpting (truncate long parent text to ~1,500 char query-focused window) | Implemented | `backend/rag/nodes/retrieval.py:_adaptive_parent_excerpt()` |

### What is missing / gated

- `retrieval_score_delta_enabled` is currently `False` by default.
- The default `rag_top_k_retrieval=30` is still high; enabling the cutoff and lowering the cap should be validated with `smoke_doctrine.py` and `ruthless_benchmark.py`.
- CRAG floor enforcement is present but not wired to automatically raise a rewrite if the floor fails.

---

## 5. Improving document preprocessing

**Principle:** Garbage in, garbage out. Clean timestamps, filler words, and transcript artifacts; normalize terminology; summarize long sources.

### MukthiGuru implementation status: **Implemented**

| Capability | Status | Location |
|------------|--------|----------|
| Transcript artifact removal (timestamps, `[Music]`, `>> Speaker:`, HTML tags) | Implemented | `backend/ingest/cleaner.py:clean_transcript()` |
| Repeated token collapse | Implemented | `backend/ingest/cleaner.py` (`_REPEATED_TOKEN_RE`) |
| Filler word removal | Implemented | `backend/ingest/cleaner.py` (`FILLER_WORDS`) |
| Spiritual term normalization (`DOCTRINE_SYNONYMS`) | Implemented | `backend/ingest/cleaner.py:normalize_spiritual_terms()` |
| LLM transcript correction before auditing | Implemented | `backend/ingest/corrector.py`, called in `ingest/pipeline.py` |
| LLM quality audit / rejection gate | Implemented | `backend/ingest/auditor.py` |
| Parent-chunk summarization for RAPTOR | Implemented, gated by `raptor_parent_summaries_enabled` | `backend/ingest/raptor.py:summarize_parent_chunks()` |

### What is missing / gated

- `raptor_parent_summaries_enabled` is not set by default in `backend/app/config.py`; enable it for richer RAPTOR summaries.
- There is no explicit paragraph-boundary-preserving overlap yet; the boundary chunker is the closest equivalent.

---

## 6. Production RAG over millions of PDFs — direct checklist

This section answers the "Production RAG over millions of PDFs" checklist directly: what MukthiGuru implements, how, what is missing, and the corresponding `.claude/GOAL.md` tracking item.

---

### 6.1 Ingestion pipeline

| Capability | Status | How it works | Gaps | GOAL tracking |
|---|---|---|---|---|
| Offline execution | Partial | `backend/ingest/pipeline.py:ingest_file()` / `ingest_url()` can be called from CLI/scripts (`scripts/ingestion/*`); Celery workers (`backend/celery_config.py`, `backend/tasks/ingest_tasks.py`) run transcription/embedding/indexing async; `/api/ingest` is backed by the job queue when `queue_enabled=true`. | No dedicated offline-only worker pool; playlist ingestion still runs online by default. | `.claude/GOAL.md` Phase 5.5 |
| S3 / GCS loading | Not implemented | — | No boto3 / GCS loaders exist; PDFs must be local files or image URLs. | Not tracked in GOAL |
| OCR | Implemented | `backend/ingest/image_loader.py` uses EasyOCR; `backend/ingest/pipeline.py:_ingest_image()` routes image URLs; languages set via `ocr_languages` (`backend/app/config.py`). | Only image URLs are OCR'd; scanned PDF pages are not processed. | `.claude/GOAL.md` Phase 5.5 |
| PDF-to-text | Implemented | `backend/ingest/pipeline.py:ingest_file()` extracts text with `pypdf.PdfReader`; `pymupdf` is in `backend/requirements.txt` but unused. | No layout-aware extraction; tables, headers, and page structure are lost. | Not tracked in GOAL |
| Chunking 512-2000 tokens | Partial | Default chunking uses characters: `rag_chunk_size=1500`, `rag_chunk_overlap=200` (`backend/app/config.py`); hierarchical child target is ~400 chars; boundary and adaptive chunkers are opt-in. | Chunk sizes are character-based, not token-based; no explicit 512-2000 token budget. | `.claude/GOAL.md` Phase 5.5 |
| Metadata (`doc_id`, `page_number`, `section_title`, `product_name`, `source`, `creation_timestamp`) | Partial | Qdrant payload stores `source_url`, `title`, `speaker`, `topic`, `content_type`, `source_type`, `language`, `tags`, `chunk_index`, `raptor_level`, `parent_id`, `parent_text`, `phonetic_tokens`. | No `doc_id`, `page_number`, `section_title`, `product_name`, or `creation_timestamp` for PDFs. | `.claude/GOAL.md` Phase 5.1 (tags), Phase 5.5 |
| Async processing | Implemented | `backend/celery_config.py` defines `transcription`, `embedding`, `indexing`, and `ingestion` queues; `backend/tasks/ingest_tasks.py` implements the tasks; `queue_concurrency=5`, `queue_default_timeout=300`. | Celery tasks only cover the YouTube path today; PDF ingestion is synchronous unless wrapped manually. | `.claude/GOAL.md` Phase 5.5 |

---

### 6.2 Embeddings & indexing

| Capability | Status | How it works | Gaps | GOAL tracking |
|---|---|---|---|---|
| Batch embedding | Implemented | `backend/services/embedding_service.py:encode_batch()` is called once per source in `backend/ingest/pipeline.py:_embed_and_index()`; Qdrant upsert batches are size 100 in `backend/services/qdrant/indexer.py:upsert_chunks()`. | No env-exposed `EMBEDDING_BATCH_SIZE`; the model's internal batch default governs. | Not tracked in GOAL |
| Qdrant / Milvus / Vespa / ES / Pinecone | Partial | Qdrant is the only supported vector store (`qdrant_url`, `qdrant_collection`, `qdrant_local_path` in `backend/app/config.py`). | Milvus, Vespa, Elasticsearch, and Pinecone are not implemented. | Not tracked in GOAL |
| Sharding | Not implemented | Single collection (`spiritual_wisdom`). | No collection/partition sharding by source, date, or tag. | Not tracked in GOAL |
| ANN | Implemented | Qdrant uses HNSW by default for dense vectors; sparse vectors use an inverted index. Collection creation is in `backend/services/qdrant/client.py:init_collection()`. | HNSW parameters (`m`, `ef_construct`, `ef`) are not tuned for the main collection. | Not tracked in GOAL |
| HNSW / IVF / PQ | Partial | Main collection uses HNSW defaults and `ScalarQuantization` INT8 with `always_ram=True`; the semantic-cache collection explicitly sets HNSW config. | No IVF, no Product Quantization, and vectors are not forced `on_disk` (only payload). | Not tracked in GOAL |
| Metadata storage | Implemented | All metadata lives in Qdrant payload with payload indexes on `raptor_level`, `phonetic_tokens`, `source_url`, `source_type`, `language`, and `tags` (`backend/services/qdrant/client.py`). | Indexes exist, but `section_title`/`page_number` are not stored. | `.claude/GOAL.md` Phase 5.1 |

---

### 6.3 Retrieval pipeline

The live chat path is: **metadata filter → answer cache → vector search → RRF merge → score-delta cutoff / dedup → reranker → CRAG grading → context assembly → LLM**.

| Step | Status | Concrete file / flag |
|---|---|---|
| Metadata filter | Implemented | `backend/services/qdrant_service.py` (`build_metadata_filter`, `build_tags_filter`, `build_source_url_filter`, `build_language_filter`); driven by `knowledge_tags` in the chat request. |
| Answer cache before search | Implemented | `backend/rag/nodes/retrieval.py:retrieve_documents()` checks `_services._semantic_cache.get()`; enabled via `semantic_cache_enabled` and `use_qdrant_semantic_cache`. |
| Vector search | Implemented | `backend/services/qdrant_service.py:search()` with dense + sparse hybrid; default `rag_top_k_retrieval=30`. |
| RRF merge + diversity | Implemented | `backend/rag/nodes/retrieval.py` merges Qdrant summary/leaf results and optional LightRAG graph via `_rrf_docs()`; MMR selection via `qdrant.mmr_select()`. |
| Score-delta cutoff | Implemented, gated | `backend/rag/nodes/retrieval.py:_apply_score_delta_cutoff()`; flag `retrieval_score_delta_enabled` (currently defaults to `False`). |
| Retrieval dedup | Implemented, gated | `backend/rag/nodes/retrieval.py:_apply_retrieval_dedup()`; flag `retrieval_deduplication_enabled` (currently defaults to `False`). |
| Reranker | Implemented | `backend/rag/nodes/reranking.py:rerank_documents()` uses FlashRank when `use_flashrank=true`, otherwise CrossEncoder/ColBERT cascade; `rerank_min_score=0.35`; `rag_top_k_rerank=10`. |
| 5-10 chunks to LLM | Implemented | `rag_top_k_rerank=10` is the default hard cap; CRAG grading (`grade_documents`) further trims to relevant docs, usually ≤10. |

**Gaps:** score-delta and retrieval dedup are off by default; there is no persistent query-plan cache; the CRAG floor does not yet auto-trigger a query rewrite.

**GOAL tracking:** `.claude/GOAL.md` Phase 5.5 (enable `retrieval_score_delta_enabled`, `retrieval_deduplication_enabled`, lower `rag_top_k_retrieval`, wire CRAG floor to rewrite).

---

### 6.4 Caching

| Cache tier | Status | How it works | Gaps | GOAL tracking |
|---|---|---|---|---|
| Answer cache | Implemented | `backend/services/semantic_cache.py` provides Redis-based `SemanticCacheService` and Qdrant-based `QdrantSemanticCache`; `backend/services/doctrine_cache.py` provides exact/fuzzy doctrine cache; config flags `semantic_cache_enabled`, `semantic_cache_similarity=0.92`, `semantic_cache_ttl=604800`. | Redis semantic cache scans all entries (O(n)); Qdrant cache is shared/global. | `.claude/GOAL.md` Phase 5.5 |
| Retrieval cache | Partial | `backend/services/cache/memory_adapter.py:SearchResultCache` exists but is **not wired** into the live retrieval path. | No persistent retrieval-result cache; same queries re-run Qdrant. | Not tracked in GOAL |
| Data cache (vectors, parsed PDFs, metadata) | Partial | Vectors stored in Qdrant; metadata in payload + `kb_sources` Supabase table; `IngestionCheckpoint` skips duplicate `content_hash`. | Parsed PDFs live only in memory; no persistent parsed-PDF/object store beyond the extracted text. | `.claude/GOAL.md` Phase 5.5 |
| Embedding cache | Implemented | `backend/services/cache/memory_adapter.py:EmbeddingCache` is an in-process LRU of size `embedding_cache_size=10000`; avoids re-embedding the same text across retrieval, rerank, and semantic cache. | Per-process only. | Not tracked in GOAL |

Cache observability: `GET /api/metrics/cache` (`backend/app/api/cache_metrics.py`) returns hot/exact/semantic tier stats.

---

### 6.5 Monitoring & evaluation

| Metric type | Status | How it works | Gaps | GOAL tracking |
|---|---|---|---|---|
| Retrieval metrics (Recall@K, Precision@K, MRR) | Partial | `backend/benchmarks/native_eval.py` measures context precision; `backend/benchmarks/ragas_eval.py` runs `context_recall`, `context_precision`, `faithfulness`, `answer_relevancy`; `backend/tests/test_retrieval_quality.py` covers cutoffs and dedup. | MRR is not implemented; no automated nightly retrieval-metric dashboard. | `.claude/GOAL.md` Phase 6 |
| System metrics (latency, throughput, cache hit rate, error rate) | Implemented | Prometheus metrics in `backend/app/metrics.py` exposed at `GET /api/metrics`: `REQUEST_LATENCY`, `RAG_LATENCY`, `RETRIEVAL_LATENCY`, `LLM_REQUEST_DURATION`, `CACHE_HIT_RATIO`, `CACHE_OPERATIONS`, `LLM_ERRORS`, `NODE_ERROR_TOTAL`, etc. | No dedicated throughput counter; no P95/P99 alert wiring yet. | Not tracked in GOAL |
| Quality metrics (feedback, hallucination rate, groundedness) | Partial | `backend/services/feedback_service.py` writes ratings to Supabase `feedback_events`; `backend/evaluation/llm_judge.py` scores groundedness, doctrinal consistency, tone, citations, refusal; `backend/services/lettuce_detect_service.py` checks faithfulness; `RETRIEVAL_RELEVANCE_RATIO` gauge. | No unified hallucination-rate dashboard; LLM judge falls back to a stub unless `EMERGENT_LLM_KEY` is configured. | `.claude/GOAL.md` Phase 6 |
| Re-embedding / rebuilding | Not implemented | `backend/scripts/ops/reprocess_contextual.py` can re-embed existing points; `backend/scripts/warm_cache.py` warms the semantic cache. | No scheduled job rebuilds the index when the embedding model changes or data drifts. | Not tracked in GOAL |

**GOAL task tracking summary**

- `.claude/GOAL.md` **Phase 5.1** — custom assistants + tag filtering (covers metadata filtering gaps).
- `.claude/GOAL.md` **Phase 5.5** — production RAG defaults: enable score-delta and dedup, lower `rag_top_k_retrieval`, enable RAPTOR summaries, build a persisted cross-ingest duplicate index, add Indic sentence splitter, wire CRAG floor to rewrite.
- `.claude/GOAL.md` **Phase 6** — continuous verification: run `smoke_doctrine.py` and `ruthless_benchmark.py` with the new defaults.

---

## Implementation matrix

| Principle | Implemented | Default on | Gated flag / config | Tests |
|-----------|-------------|------------|---------------------|-------|
| Better chunking | Yes | Partially | `use_boundary_chunker`, `use_ingest_adaptive_chunker` | `test_adaptive_chunking.py`, `chunk_size_evaluation.py` |
| Metadata filtering | Yes | Partially | `knowledge_tags` request field | `test_retrieve_documents_contract.py` |
| Deduplication | Yes | No | `ingestion_deduplication_enabled`, `retrieval_deduplication_enabled` | — |
| Fewer-but-better chunks | Yes | Partially | `retrieval_score_delta_enabled` | `test_retrieval_quality.py`, `test_graph_strategies.py` |
| Preprocessing | Yes | Yes | `data_audit_enabled` | `test_ingestion_pipeline.py` |
| Ingestion pipeline | Partial | Partially | `queue_enabled`, `rag_chunk_size`, `ocr_languages` | `test_ingestion_pipeline.py`, `test_ingest_adaptive_chunking.py` |
| Embeddings & indexing | Partial | Yes (Qdrant) | `qdrant_url`, `embedding_model`, `embedding_dimension` | `test_embedding_service.py`, `test_retrieve_documents_contract.py` |
| Retrieval pipeline | Implemented | Partially | `rag_top_k_retrieval`, `rag_top_k_rerank`, `use_flashrank` | `test_retrieval_quality.py`, `test_graph_strategies.py` |
| Caching | Partial | Yes (answer/embedding) | `semantic_cache_enabled`, `use_qdrant_semantic_cache`, `embedding_cache_size` | `test_hot_cache.py` |
| Monitoring & evaluation | Partial | Yes (metrics) | `llm_judge_provider_model` | `test_benchmarks.py`, `test_observability.py` |

---

## Recommended next steps

1. **Enable the ekimetrics port by default** after one benchmark run confirms no regression:
   ```bash
   USE_INGEST_ADAPTIVE_CHUNKER=true
   ```
2. **Turn on retrieval deduplication and score-delta cutoff** and measure latency/quality:
   ```bash
   RETRIEVAL_DEDUPLICATION_ENABLED=true
   RETRIEVAL_SCORE_DELTA_ENABLED=true
   ```
3. **Lower default top-k** from 30 to 15–20 once the cutoff is active and validated.
4. **Enable `raptor_parent_summaries_enabled`** for hierarchical ingestion runs.
5. **Expose the missing config knobs** in `backend/app/config.py`: `retrieval_score_delta_enabled`, `retrieval_deduplication_enabled`, `ingestion_deduplication_enabled`, `rag_top_k_retrieval_after_cutoff`, `retrieval_dedup_threshold`, `ingestion_dedup_threshold`.
6. **Add S3 / GCS PDF loader and scanned-PDF OCR** so the ingestion pipeline matches the "millions of PDFs" scale.
7. **Capture PDF structure metadata** (`doc_id`, `page_number`, `section_title`, `creation_timestamp`) in Qdrant payload.
8. **Wire the retrieval cache** (`SearchResultCache`) into `retrieve_for_single_query` or replace it with the Qdrant semantic cache.
9. **Add MRR reporting** and a scheduled re-embedding / rebuild job.
10. **Run Phase 6 verification** (`smoke_doctrine.py` + `ruthless_benchmark.py`) with the Phase 5.5 defaults enabled.

---

## Key files

- `backend/ingest/pipeline.py` — orchestrates chunking, dedup, metadata, RAPTOR.
- `backend/ingest/cleaner.py` — transcript preprocessing.
- `backend/ingest/boundary_chunker.py` — sentence/paragraph chunker.
- `backend/ingest/adaptive_chunking.py` — ekimetrics port.
- `backend/ingest/deduplication.py` — MinHash dedup.
- `backend/ingest/image_loader.py` — OCR loader.
- `backend/celery_config.py` — Celery queues and routing.
- `backend/tasks/ingest_tasks.py` — async ingestion tasks.
- `backend/rag/nodes/retrieval.py` — retrieval node with cutoff, dedup, MMR.
- `backend/rag/nodes/reranking.py` — reranker and CRAG grading.
- `backend/services/qdrant_service.py` — filter builders and MMR selection.
- `backend/services/qdrant/client.py` — Qdrant collection creation and payload indexes.
- `backend/services/qdrant/indexer.py` — batch upsert and deterministic IDs.
- `backend/services/semantic_cache.py` — Redis + Qdrant answer cache.
- `backend/services/doctrine_cache.py` — exact/fuzzy doctrine cache.
- `backend/services/cache/memory_adapter.py` — in-memory embedding, exact, and search-result caches.
- `backend/services/feedback_service.py` — user feedback persistence.
- `backend/app/metrics.py` — Prometheus production metrics.
- `backend/app/api/cache_metrics.py` — cache tier observability endpoint.
- `backend/evaluation/llm_judge.py` — LLM-as-judge groundedness/hallucination scoring.
- `backend/benchmarks/native_eval.py` — native context precision / faithfulness evaluation.
- `backend/benchmarks/ragas_eval.py` — RAGAS retrieval metrics.
- `backend/app/config.py` — all feature flags and thresholds.
