# OKF: Adaptive Chunking Principles

> **Source:** ekimetrics/adaptive-chunking (GitHub) + 2026 RAG benchmarks
> **Domain:** Ingestion, RAG Quality
> **Last updated:** 2026-07-04

## Core Teaching

Adaptive chunking is NOT a static rule — it dynamically selects the best splitting strategy *per document* using intrinsic quality metrics. The wrong chunking strategy creates up to a **9% recall gap**.

## The Five Intrinsic Metrics (MukthiGuru Implementation)

| Metric | Meaning | Good Range |
|--------|---------|-----------|
| **SC** (Size Compliance) | Chunks within 200–1200 chars | > 0.7 |
| **ICC** (Intrachunk Cohesion) | Cosine similarity of sentences to chunk | > 0.65 |
| **DCC** (Discourse Continuity) | Bigram overlap across chunk boundaries | > 0.5 |
| **BI** (Block Integrity) | % of chunks NOT ending mid-sentence | > 0.8 |
| **RC** (Redundancy-Coherence) | No near-duplicate chunks (cosine < 0.95) | > 0.9 |

## Decision Logic

```
if SC + ICC (Recursive) > SC + ICC (Semantic):
    use Recursive splitting (fast, low latency)
else:
    use Semantic splitting (slower, better for long-form)
```

**Special Cases:**
- Short-form (< 5000 chars / Instagram Reels): Use Recursive with min_chars=50 fallback
- Boundary-aware chunker (`use_boundary_chunker=True`): Bypasses adaptive scoring entirely
- Images: OCR text → quality gate → recursive chunking (no semantic needed)

## Code Location

- **Core:** `backend/ingest/adaptive_chunking.py` — `AdaptiveChunker.chunk_document()`
- **Adapter (extended metrics):** `backend/services/adaptive_chunking_adapter.py`
- **Pipeline hook:** `backend/ingest/pipeline.py:_split_text()` line ~1661
- **Config:** `settings.use_adaptive_chunking` (default: True)

## Key Insight from 2026 Research

> "Adaptive frameworks have been shown to increase answer correctness by up to 72% compared to fixed-size chunking for long-form spiritual content." — arxiv 2026

Chunk sizes should align with embedding model context window (512 tokens for current model) to avoid silent truncation — leading cause of mediocre RAG.

## What NOT To Do

- Never set `use_adaptive_chunking=False` for production — falls back to dumb recursive splitting
- Never increase `adaptive_chunking_min_chars` above 2000 — short reels get bypassed
- Never bypass the Data Quality Gate — OCR noise and whisper errors will corrupt the index
