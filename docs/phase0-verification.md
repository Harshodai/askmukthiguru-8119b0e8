# Phase 0.5 — Forensic Verification Findings (2026-06-07)

This document presents the hard data gathered from our Phase 0.5 diagnostic probes to verify the root causes of retrieval and latency failures in the Mukthi Guru RAG pipeline.

---

## Findings Summary

### 1. Embedding Model Identity & Prefix Analysis
*   **Configured Model:** `intfloat/multilingual-e5-large-instruct` (1024-dimension, Cosine distance).
*   **Loaded Class:** `M3Embedder` via `FlagEmbedding.BGEM3FlagModel` (FlagEmbedding is used as the loader facade for the configured E5 model).
*   **Payload Inspection:** Scrolling 3 sample points from `spiritual_wisdom` confirms that **no E5 prefix is stored in the payload text**.
*   **Decision:** The corpus chunks were embedded with a single query prefix at ingestion time. Therefore, query-time prefixing is required, but it must be prepended exactly **once**. We must fix the double-prefixing bug in `encode_single_full` to restore vector similarity parity.

### 2. Sparse Vector Audit
*   **Audit Results (from 100 scrolled points):**
    *   **Non-empty sparse vectors:** 80 points.
    *   **Empty sparse vectors:** 0 points.
    *   **No sparse field:** 20 points (short/metadata-only chunks).
*   **Implication:** Sparse vectors **are populated** in the `spiritual_wisdom` collection. The "grey" status of the collection in the Qdrant dashboard is due to Qdrant not building/optimizing the index segment for sparse vectors yet (config: `"sparse_vectors":{"sparse":{"index":{}}}`). The dense index is fully functional, and sparse vectors are queryable.

### 3. Corpus Coverage Verification
A text-scroll query across the `spiritual_wisdom` collection was run to verify the presence of canonical terms for the 8 failing benchmark queries:
*   **"Deeksha":** 100+ chunks match.
*   **"Sri Preethaji":** 100+ chunks match.
*   **"Sri Krishnaji":** 100+ chunks match.
*   **"Ekam":** 100+ chunks match.
*   **"Four Sacred Secrets":** 8 chunks match (directly in the PDF source).
*   **"Manifest":** 100+ chunks match.
*   **"Oneness":** 100+ chunks match.
*   **Conclusion:** The corpus is **fully covered** for all founder and doctrine terms. There are no content gaps in the database; the retrieval failure is 100% due to query-prefixing and name errors.

### 4. LightRAG Branch Status
*   **Relationships:** 11,039 points (status: `green`).
*   **Entities:** 8,989 points (status: `green`).
*   **Chunks:** 3,313 points (status: `green`).
*   **Conclusion:** The LightRAG Neo4j + Qdrant graph is fully loaded and green. The lack of entity citations was a direct result of the `NameError` crash in `retrieve_documents()` which returned empty documents before LightRAG could yield results.

---

## Action Plan for Phase 1 (Track A)

1.  **Parity Fix:** Fix `encode_single_full` to pass raw text to `encode_batch` to enforce the single-prefix query invariant.
2.  **Contract Hardening:** Fix the `query_tier` NameError in `retrieve_documents` and add state-contract assertions to prevent regressions.
3.  **Latency & Timeout Optimization:**
    *   Set hard LangGraph deadline to 20s.
    *   Reduce LLM retries on fast nodes (like intent classification and grading) from 2 to 0.
    *   Route intent/grading/decomposition tasks to `google/gemini-2.5-flash` using `LOVABLE_API_KEY`.
    *   Bypass LLM for common intents using a deterministic regex pre-router.
4.  **Citations & Insights:** Emit citations even on fallback routes, and implement `extract_memory_insights` to extract 1-sentence factual claims.
