# Adaptive Chunking Integration

## Overview

MukthiGuru now ships a lightweight port of the [ekimetrics/adaptive-chunking](https://github.com/ekimetrics/adaptive-chunking) strategy in `backend/ingest/adaptive_chunking.py`. The port evaluates a small, fixed set of chunking candidates per document using cheap intrinsic metrics and picks the winner — no LLM calls are required at chunk time, and the only model used is the shared sentence embedder (`services.embedding_service.EmbeddingService`).

The goal is to move beyond a one-size-fits-all `RecursiveCharacterTextSplitter` and let the chunker adapt to each teaching transcript or document.

## Why this matters for spiritual content

YouTube transcripts mix long monologues, short Q&A exchanges, and repeated themes. A fixed 500-character splitter can:

- cut a teaching mid-sentence, harming retrieval precision;
- dump unrelated sentences into the same chunk, lowering cohesion;
- create many near-duplicate windows around repeated mantras or slogans.

Adaptive chunking keeps sentence boundaries intact, groups semantically contiguous sentences, and avoids redundant chunks.

## Configuration flags

| Flag | Default | Location | Purpose |
|------|---------|----------|---------|
| `use_ingest_adaptive_chunker` | `False` | `backend/app/config.py` | When `True`, `IngestionPipeline._split_text()` uses the new `ingest.adaptive_chunking.AdaptiveChunker` port instead of the homegrown service. |
| `use_adaptive_chunking` | `True` | `backend/app/config.py` | When `True` and the ingest port is disabled, the homegrown `services.adaptive_chunking_adapter.AdaptiveChunkingAdapter` is used. |
| `adaptive_chunking_min_chars` | `5000` | `backend/app/config.py` | Documents shorter than this bypass adaptive evaluation and use the fast recursive splitter. |

These values can be overridden in `backend/.env` or `backend/.env.local`.

## How it works

### Candidate strategies

For each qualifying document, the port builds three candidate chunk sets on an 8,000-character sample:

1. **recursive** — `RecursiveCharacterTextSplitter` using `rag_chunk_size` / `rag_chunk_overlap`.
2. **recursive_small** — `RecursiveCharacterTextSplitter` at half the configured chunk size.
3. **semantic** — sentence-level split using embedding similarity between consecutive sentences; boundaries are placed at local minima in similarity.

The winning candidate is then applied to the full document.

### Intrinsic quality metrics

Each candidate is scored on five metrics, all computed without an LLM:

| Metric | What it measures | Weight |
|--------|------------------|--------|
| **SC** — Size Compliance | Fraction of chunks inside the target character bounds (200–1,600 chars). | 0.20 |
| **ICC** — Intrachunk Cohesion | Mean cosine similarity of each sentence to its chunk centroid. | 0.30 |
| **DCC** — Discourse / Contextual Coherence | Bigram overlap across adjacent chunk boundaries (Jaccard-like). | 0.20 |
| **BI** — Block Integrity | Fraction of chunks that end at a sentence boundary. | 0.15 |
| **RC** — Redundancy Control | Fraction of chunk pairs whose cosine similarity is below 0.95. | 0.15 |

The weighted sum is clipped to `[0, 1]`. The candidate with the highest score wins.

### Fast path

If a document is shorter than `adaptive_chunking_min_chars` or `use_adaptive_chunking` is `False`, the port immediately returns the recursive splitter output. This keeps ingestion fast for short images, short answers, or tests.

### Fallbacks

- If embedding the sentences for the semantic candidate fails, the port falls back to the recursive splitter.
- If scoring a candidate fails to produce embeddings, a `fallback_score` using only size compliance and block integrity is used so chunking never aborts.

## Relationship to the homegrown adaptive chunking service

There are two co-existing implementations:

| Implementation | Path | Behaviour |
|----------------|------|-----------|
| Homegrown service + ekimetrics adapter | `services/adaptive_chunking_service.py` + `services/adaptive_chunking_adapter.py` | Chooses between recursive and semantic using SC + ICC; logs DCC, BI, RC for observability. |
| Lightweight ekimetrics port | `ingest/adaptive_chunking.py` | Chooses between recursive, recursive_small, and semantic using all five metrics; designed for ingestion-time use. |

`IngestionPipeline._split_text()` prioritizes the new port when `use_ingest_adaptive_chunker=True`; otherwise it uses the homegrown adapter. Both respect `use_adaptive_chunking` and `adaptive_chunking_min_chars`.

## Enabling the new port (curator guide)

1. Open `backend/.env` (or create `backend/.env.local`).
2. Set the flag:
   ```bash
   USE_INGEST_ADAPTIVE_CHUNKER=true
   ADAPTIVE_CHUNKING_MIN_CHARS=5000
   ```
3. Restart the backend.
4. Re-ingest or newly ingest a long teaching (single video, playlist, or PDF) through `/api/ingest` or the ingestion portal at `http://localhost:8000/ingest/`.
5. Watch the logs for lines like:
   ```text
   Adaptive chunking selected 'semantic' for 45231-char document in 0.812s (34 chunks)
   ```

If you see mostly `recursive` being selected for long transcripts, lower `adaptive_chunking_min_chars` or verify that the embedding service is healthy (semantic candidate needs embeddings).

## Pipeline wiring

The integration point is in `backend/ingest/pipeline.py`:

```python
from ingest.adaptive_chunking import AdaptiveChunker

class IngestionPipeline:
    def _split_text(self, text, ...):
        if settings.use_ingest_adaptive_chunker and len(text) >= settings.adaptive_chunking_min_chars:
            chunks = AdaptiveChunker(self._embedder).chunk_document(text)
        elif settings.use_adaptive_chunking:
            chunks = self._adaptive_chunker.chunk_document(text)
        # ...
```

The new port is also used inside `_ingest_video_enhanced` when proposition chunking is not selected:

```python
if apply_props:
    propositions = await self._proposition_split(parent_chunk)
else:
    propositions = self._adaptive_chunker.chunk_document(parent_chunk)
```

Note that the enhanced video path currently still uses the homegrown adapter; switching it to the new port is a future optimization.

## Monitoring and tuning

- **Metric logs**: the port emits the selected strategy, document length, duration, and chunk count at INFO level.
- **Debug logs**: every candidate score is logged at DEBUG level.
- **Tuning knobs**:
  - Lower `adaptive_chunking_min_chars` to apply adaptive chunking to shorter documents.
  - Raise it to reduce ingestion latency for bulk jobs.
  - The target bounds (`min_chunk_chars=200`, `max_chunk_chars=1600`) and sample size (`sample_chars=8000`) are currently code constants; expose them to config if experimentation shows value.

## Tests

Coverage lives in:

- `backend/tests/test_adaptive_chunking.py` — exercises the homegrown service and adapter.
- `backend/benchmarks/chunk_size_evaluation.py` — can evaluate chunk-size trade-offs using the adapter.

## Future work

- Replace the homegrown adapter entirely with the new port once the metrics are validated against the benchmark suite.
- Make the candidate set and metric weights configurable per content type (video, PDF, image OCR).
- Add a transcript-aware sentence splitter for Indic-language content.
- Cache per-document strategy decisions to avoid re-evaluating on re-ingestion.

## Files touched

- `backend/ingest/adaptive_chunking.py` — new port.
- `backend/services/adaptive_chunking_service.py` — homegrown implementation.
- `backend/services/adaptive_chunking_adapter.py` — ekimetrics metrics adapter.
- `backend/ingest/pipeline.py` — wiring and strategy selection.
- `backend/app/config.py` — feature flags and thresholds.
- `backend/tests/test_adaptive_chunking.py` — tests.
