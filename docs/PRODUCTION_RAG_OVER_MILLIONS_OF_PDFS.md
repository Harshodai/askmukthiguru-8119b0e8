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

## Implementation matrix

| Principle | Implemented | Default on | Gated flag | Tests |
|-----------|-------------|------------|------------|-------|
| Better chunking | Yes | Partially | `use_boundary_chunker`, `use_ingest_adaptive_chunker` | `test_adaptive_chunking.py`, `chunk_size_evaluation.py` |
| Metadata filtering | Yes | Partially | `knowledge_tags` request field | `test_retrieve_documents_contract.py` |
| Deduplication | Yes | No | `ingestion_deduplication_enabled`, `retrieval_deduplication_enabled` | — |
| Fewer-but-better chunks | Yes | Partially | `retrieval_score_delta_enabled` | `test_retrieval_quality.py`, `test_graph_strategies.py` |
| Preprocessing | Yes | Yes | `data_audit_enabled` | `test_ingestion_pipeline.py` |

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
3. **Lower default top-k** from 30 to 15–20 once the cutoff is active.
4. **Enable `raptor_parent_summaries_enabled`** for hierarchical ingestion runs.
5. **Finish qdrant_service decomposition** (Unit 12) so metadata-filtering hooks are isolated and testable.

---

## Key files

- `backend/ingest/pipeline.py` — orchestrates chunking, dedup, metadata, RAPTOR.
- `backend/ingest/cleaner.py` — transcript preprocessing.
- `backend/ingest/boundary_chunker.py` — sentence/paragraph chunker.
- `backend/ingest/adaptive_chunking.py` — ekimetrics port.
- `backend/ingest/deduplication.py` — MinHash dedup.
- `backend/rag/nodes/retrieval.py` — retrieval node with cutoff, dedup, MMR.
- `backend/services/qdrant_service.py` — filter builders and MMR selection.
- `backend/app/config.py` — all feature flags and thresholds.
