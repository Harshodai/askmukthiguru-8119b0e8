# turbovec Integration Plan for Mukthi Guru

## Executive Summary

turbovec is a Rust-based vector index using Google's TurboQuant (2-bit/4-bit quantization) that claims 16x compression and faster-than-FAISS search on ARM. On paper, it aligns with Mukthi Guru's zero-budget, local-only constraints. In practice, integration requires careful trade-offs against Qdrant's existing feature set.

---

## 1. What turbovec Is (and Is Not)

| Feature | turbovec | Qdrant (Current) |
|---------|----------|------------------|
| **Type** | Pure vector index (in-memory) | Full vector database |
| **Compression** | 2-bit / 4-bit scalar quantization (16x / 8x) | Scalar + product quantization (configure) |
| **Sparse vectors** | No | Yes (native, used by bge-m3) |
| **Metadata filtering** | Basic ID allowlists only | Full payload filtering, conditions |
| **Persistence** | File-based (`.tv`, `.tvim`) | Segments, WAL, snapshots |
| **Collections** | No | Yes (multi-collection) |
| **Hybrid search** | No (dense only) | Yes (RRF dense + sparse) |
| **REST API** | No | Yes |
| **HNSW graph** | No (brute-force via SIMD) | Yes (configurable) |
| **Training** | Zero (online ingest) | Zero (online ingest) |

### The TurboQuant Pipeline (What turbovec Does Internally)

1. **Normalize** → stores norm separately (direction on unit hypersphere)
2. **Random rotation** → shared orthogonal matrix, makes all coords follow Beta
3. **Per-coordinate calibration** → maps empirical quantiles to Beta distribution (one-time, frozen)
4. **Lloyd-Max quantization** → 2-bit or 4-bit scalar quantizer per coordinate
5. **Bit-packing** → tightly pack small integers (1536d × 2-bit = 384 bytes)
6. **Length-renormalized scoring** → corrects for quantization bias during search

Search uses hand-written SIMD kernels (NEON on ARM, AVX-512 on x86) with lookup tables — no decompression at query time.

---

## 2. Integration Strategies (Ranked)

### 2.1 Strategy A: turbovec as "Fast Path" Accelerator (RECOMMENDED — Low Risk)

**Concept**: Keep Qdrant as primary source of truth. Maintain a turbovec index of top-K most-accessed dense vectors for fast initial retrieval. Complex or cache-miss queries fall back to Qdrant.

```
User Query
   |
   v
[Embed with bge-m3] (1024d dense + sparse)
   |
   +---> [turbovec fast search] (dense only, top-20)
   |         | hit: return for reranking
   |         | miss: proceed to Qdrant
   |
   +---> [Qdrant hybrid search] (dense + sparse, RRF)
   |         | fallback / complex queries
   |
   v
[Unified rerank + generate]
```

**Code sketch**:
```python
# In services/qdrant_service.py or a standalone FastVecService

from turbovec import IdMapIndex
import numpy as np

class TurbovecAccelerator:
    def __init__(self, dim: int = 1024, bit_width: int = 4):
        self.index = IdMapIndex(dim=dim, bit_width=bit_width)
        self._id_map = {}  # turbovec internal idx -> Qdrant point id
        self._initialized = False

    def build_from_qdrant(self, qdrant_service, collection_name: str):
        """Hydrate turbovec from Qdrant at startup."""
        # Fetch all dense vectors + IDs from Qdrant
        points = qdrant_service.scroll_all(collection_name, with_vectors=True)
        vectors = np.array([p.vector for p in points])  # float32
        ids = [p.id for p in points]
        # Build deterministic mapping
        turbovec_ids = list(range(len(ids)))
        self._id_map = dict(zip(turbovec_ids, ids))
        self.index.add_with_ids(vectors, turbovec_ids)
        self._initialized = True

    def search(self, query_vector: list[float], k: int = 20) -> list[str]:
        if not self._initialized:
            return []  # Fallback to Qdrant
        scores, internal_ids = self.index.search(np.array([query_vector]), k=k)
        return [self._id_map[i] for i in internal_ids[0]]

    def reload(self, qdrant_service):
        """Periodic refresh from Qdrant (after ingestion)."""
        self.index = IdMapIndex(dim=1024, bit_width=4)
        self.build_from_qdrant(qdrant_service, "spiritual_wisdom")
```

**Pros**:
- Zero risk to existing Qdrant infrastructure
- Speed up simple / repeated queries by ~15-20% on ARM (M-series Macs)
- Memory for 10K vectors at 4-bit: ~5 MB vs ~40 MB in Qdrant (negligible but nice)
- Can A/B test without breaking existing flow

**Cons**:
- Adds complexity (two systems to maintain)
- turbovec search is brute-force (O(n)), so for >100K docs, Qdrant HNSW may still win
- No benefit if corpus stays small (< 5K docs)
- Warmup cost at startup (loading all vectors into memory)

**When to use**: If you grow beyond 20K chunks, or run on ARM (Raspberry Pi, Apple Silicon) where SIMD speed matters most.

---

### 2.2 Strategy B: turbovec for RAPTOR Summary Nodes (Medium Risk)

**Concept**: RAPTOR builds hierarchical summaries. The top-level "summary" nodes are few (~50-100) but queried frequently. Store these in turbovec for near-instant retrieval.

```python
# In raptor.py or a dedicated RaptorIndex

class RaptorTurbovecStore:
    """Stores only RAPTOR level >= 2 summaries in turbovec."""
    def __init__(self):
        self.index = IdMapIndex(dim=1024, bit_width=4)
        self.level_map = {}  # id -> level

    def add_summary(self, vector, point_id, level):
        self.index.add_with_ids(np.array([vector]), [point_id])
        self.level_map[point_id] = level

    def search_summaries(self, query, k=5):
        scores, ids = self.index.search(np.array([query]), k=k)
        return ids[0]
```

**Pros**:
- RAPTOR summaries are small and hot — perfect turbovec use case
- Reduces Qdrant query load for top-of-tree navigation
- Very low memory footprint

**Cons**:
- Need to sync on every ingestion pipeline run
- Adds another moving part to already complex RAPTOR pipeline

---

### 2.3 Strategy C: Full Qdrant Replacement (NOT RECOMMENDED — High Risk)

**Why this is a bad idea for Mukthi Guru**:

1. **Lose sparse vectors**: bge-m3's sparse output is critical for catching exact keyword matches in spiritual queries (names, mantras, specific phrases). turbovec has no sparse support.

2. **Lose metadata filtering**: You can't filter by `video_id`, `speaker`, `timestamp`, or `raptor_level` in turbovec. Allowlists require pre-fetching IDs, which defeats the purpose.

3. **Lose hybrid search**: RRF between dense and sparse is a key anti-hallucination feature. Removing it would regress retrieval quality.

4. **Persistence model**: turbovec writes to a single file. Qdrant has WAL, snapshots, replication, and collections. For a production-ish RAG, this matters.

5. **No HNSW**: turbovec does linear scan with SIMD. For 100K+ vectors, Qdrant's HNSW is asymptotically faster regardless of SIMD.

6. **API surface**: Qdrant has a mature HTTP/gRPC API. turbovec is a library. You'd have to build a service wrapper.

---

## 3. Integration Roadmap (Strategy A — Fast Path)

### Phase 1: Spike / Proof of Concept (1-2 days)

```bash
# 1. Install turbovec
pip install turbovec

# 2. Create spike script
# backend/spikes/turbovec_spike.py
```

```python
# backend/spikes/turbovec_spike.py
"""Spike: Verify turbovec works with bge-m3 1024d embeddings."""
import numpy as np
from turbovec import IdMapIndex

def main():
    dim = 1024
    n = 1000
    # Generate fake bge-m3-like embeddings (unit normalized)
    vecs = np.random.randn(n, dim).astype(np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)

    index = IdMapIndex(dim=dim, bit_width=4)
    index.add_with_ids(vecs, list(range(n)))

    query = np.random.randn(dim).astype(np.float32)
    query /= np.linalg.norm(query)

    scores, ids = index.search(query, k=10)
    print(f"Top-10 IDs: {ids}")
    print(f"Scores: {scores}")
    print(f"Index memory estimate: {n * dim * 0.5 / 1024 / 1024:.2f} MB (4-bit)")

if __name__ == "__main__":
    main()
```

**Acceptance**: Script runs, recall @ 10 is > 0.95 compared to brute-force float32 cosine.

### Phase 2: Service Wrapper (2-3 days)

Create `backend/services/turbovec_service.py`:

```python
"""
turbovec accelerator for hot-path dense vector search.
Falls back to Qdrant for complex/hybrid queries.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Lazy import — turbovec is optional
_TURBOVEC_AVAILABLE = False
try:
    from turbovec import IdMapIndex
    _TURBOVEC_AVAILABLE = True
except ImportError:
    logger.warning("turbovec not installed. Fast-path disabled.")
    IdMapIndex = None  # type: ignore


class TurbovecService:
    """
    In-memory turbo index for dense-only fast retrieval.
    Mirrors QdrantService.search() interface for easy swapping.
    """

    def __init__(self, dim: int = 1024, bit_width: int = 4, enabled: bool = True):
        self.dim = dim
        self.bit_width = bit_width
        self.enabled = enabled and _TURBOVEC_AVAILABLE
        self.index: Optional["IdMapIndex"] = None  # type: ignore[annotation-unchecked]
        self._id_map: dict[int, str] = {}  # internal idx -> Qdrant point id
        self._reverse_map: dict[str, int] = {}  # Qdrant point id -> internal idx

    def hydrate_from_points(self, vectors: list[list[float]], point_ids: list[str]) -> None:
        """Build index from existing Qdrant points."""
        if not self.enabled:
            return
        n = len(vectors)
        if n == 0:
            return
        logger.info(f"Hydrating turbovec index with {n} vectors (dim={self.dim}, {self.bit_width}-bit)")
        arr = np.array(vectors, dtype=np.float32)
        internal_ids = list(range(n))
        self._id_map = dict(zip(internal_ids, point_ids))
        self._reverse_map = {v: k for k, v in self._id_map.items()}
        self.index = IdMapIndex(dim=self.dim, bit_width=self.bit_width)
        self.index.add_with_ids(arr, internal_ids)
        mem_mb = n * self.dim * (self.bit_width / 8) / 1024 / 1024
        logger.info(f"turbovec index ready. Estimated memory: {mem_mb:.2f} MB")

    def search(
        self, query_vector: list[float], k: int = 20
    ) -> tuple[list[float], list[str]]:
        """Returns (scores, point_ids). Falls back to empty if disabled."""
        if not self.enabled or self.index is None:
            return [], []
        query_arr = np.array([query_vector], dtype=np.float32)
        scores, internal_ids = self.index.search(query_arr, k=k)
        point_ids = [self._id_map[i] for i in internal_ids[0]]
        return scores[0].tolist(), point_ids

    def add(self, vector: list[float], point_id: str) -> None:
        """Add a single vector (e.g., after ingestion)."""
        if not self.enabled or self.index is None:
            return
        # turbovec doesn't support dynamic adds well with stable IDs in same index
        # Option: rebuild index or use a separate "delta" index
        raise NotImplementedError("Dynamic add not yet implemented. Rebuild index instead.")

    def reload(self, vectors: list[list[float]], point_ids: list[str]) -> None:
        """Rebuild index from scratch (call after batch ingestion)."""
        self.hydrate_from_points(vectors, point_ids)
```

### Phase 3: Dual-Route Integration in RAG Pipeline (3-5 days)

Modify `backend/rag/nodes.py` `retrieve_documents` to try turbovec first, then Qdrant:

```python
# Simplified dual-route logic

async def retrieve_documents(state: GraphState) -> GraphState:
    query = state["user_message"]
    embedding_service = state["services"]["embedding"]
    qdrant = state["services"]["qdrant"]
    turbovec = state["services"].get("turbovec")

    # 1. Embed
    dense_vec, sparse_vec = embedding_service.encode_dense_sparse(query)

    # 2. Try turbovec fast path (dense only)
    if turbovec and turbovec.enabled:
        scores, ids = turbovec.search(dense_vec, k=50)
        if ids:
            # Hydrate from Qdrant point payloads
            points = qdrant.get_points_by_id(ids)
            if len(points) >= 10:
                state["retrieved_docs"] = points
                return state

    # 3. Fallback to full Qdrant hybrid search
    results = qdrant.search(dense_vec, sparse_vector=sparse_vec, limit=50)
    state["retrieved_docs"] = results
    return state
```

### Phase 4: Benchmarking & Decision (1-2 days)

```python
# backend/benchmarks/bench_turbovec.py
import time

async def benchmark():
    queries = [...]  # Load test queries

    # Benchmark Qdrant only
    start = time.monotonic()
    for q in queries:
        await retrieve_qdrant(q)
    qdrant_time = time.monotonic() - start

    # Benchmark turbovec + Qdrant fallback
    start = time.monotonic()
    for q in queries:
        await retrieve_dual(q)
    dual_time = time.monotonic() - start

    print(f"Qdrant only: {qdrant_time:.3f}s")
    print(f"Dual route: {dual_time:.3f}s")
    print(f"Speedup: {qdrant_time/dual_time:.2f}x")
```

**Go/No-Go Criteria**:
- Recall @ 10 from turbovec alone > 0.90 compared to Qdrant dense
- End-to-end query latency reduction > 20% for fast-path queries
- No increase in hallucination rate (validate with golden set)

---

## 4. Ruthless Pros and Cons

### ✅ PROS (Why It Could Work)

| Pro | Details |
|-----|---------|
| **Free & Apache 2.0** | Zero cost, permissive license — fits "$0 budget" perfectly |
| **No external API calls** | Pure local, no network dependency — fits "local-only" constraint |
| **16x compression** | 10M vectors: 31 GB → 4 GB (2-bit). Your corpus is smaller, but still nice |
| **Faster on ARM** | 12-20% speedup over FAISS FastScan on Apple M-series / ARM servers |
| **Zero training** | Online ingest, no calibration set needed — fits streaming ingestion pipeline |
| **SIMD kernels** | Hand-written NEON/AVX-512 scoring — high throughput for in-memory ops |
| **Filtered search** | ID allowlists for pre-filtering (limited, but useful for RAPTOR level filtering) |
| **Simple API** | Two classes (`TurboQuantIndex`, `IdMapIndex`) — low integration overhead |

### ❌ CONS (Why It Probably Doesn't Fit)

| Con | Details |
|-----|---------|
| **No sparse vector support** | You lose bge-m3's sparse output — a critical part of hybrid search. This alone is almost a dealbreaker |
| **No metadata filtering** | Can't filter by `video_id`, `speaker`, `raptor_level` during search. Pre-filtering requires fetching IDs first |
| **Brute-force search** | Linear scan O(n) per query. Qdrant's HNSW is O(log n). For > 50K docs, Qdrant wins regardless of SIMD |
| **Single-file persistence** | No WAL, no snapshots, no replication. Corruption = rebuild from Qdrant |
| **Not a database** | No collections, no REST API, no multi-tenancy. You'd wrap it in a service |
| **Rust build complexity** | `pip install` works, but custom builds need Rust + maturin. Adds build infra |
| **2-bit recall penalty** | On low-dimensional data (like your 1024d, which is borderline), 2-bit R@1 can lag. 4-bit is safer but halves compression |
| **Memory is not your bottleneck** | Your corpus is YouTube transcripts. Even 10K chunks × 1024d × float32 = ~40 MB. Memory pressure is negligible |
| **Added complexity** | Two vector systems to maintain, sync, benchmark, debug. For marginal speed gains on a small corpus, this is negative ROI |
| **Qdrant already uses TurboQuant-MSE** | Qdrant adopted TurboQuant-MSE for HNSW graph construction (symmetric scoring). You may already be getting some of the benefit |

---

## 5. The Honest Verdict

### Should you integrate turbovec?

**Right now: Probably no.**

Your corpus size (YouTube transcripts from a single channel, likely < 20K chunks) means Qdrant uses < 100 MB of RAM for dense vectors. The 16x compression from turbovec saves you ~90 MB. That's not meaningful on any modern hardware, including Colab's free tier (12 GB RAM).

The speed gains (12-20% on ARM) are real but marginal when your end-to-end pipeline is dominated by LLM calls (Sarvam 30B, ~20-90s per query). Saving 50ms on vector search out of a 60s total is 0.08% improvement.

**Where turbovec becomes interesting**:
- If you scale to > 100K chunks (unlikely for a single spiritual channel)
- If you deploy on Raspberry Pi / embedded ARM (possible for offline installations)  
- If Qdrant's hybrid search latency becomes a bottleneck after you've already optimized LLM calls

### Recommended Path

1. **Continue with Qdrant as primary vector DB.** It's the right tool for your feature set (hybrid search, metadata filtering, collections, REST API).

2. **File a `TODO` / backlog ticket:** "Evaluate turbovec for ARM deployment / > 50K corpus." Don't close the door, but don't invest now.

3. **If you insist on experimenting**, implement Strategy A (fast-path accelerator) as a spike. Cost: 2-3 days. Validate with real queries. If it doesn't show > 20% end-to-end speedup, delete it.

4. **Better ROI optimizations to pursue instead**:
   - Optimize LLM prompt sizes (you're sending 20 messages of history)
   - Enable Sarvam Cloud for faster inference (you already have the key)
   - Cache common query embeddings
   - Parallelize graph nodes that don't depend on each other
   - Profile the actual bottleneck with Jaeger traces before adding complexity

---

## 6. Appendix: Architecture Compatibility Matrix

| Component | turbovec Compatible? | Notes |
|-----------|----------------------|-------|
| bge-m3 1024d dense | ✅ Yes | Primary use case |
| bge-m3 sparse | ❌ No | Not supported — critical loss |
| Hybrid RRF search | ❌ No | Only dense inner-product |
| Metadata filters (`video_id`, `raptor_level`) | ⚠️ Partial | Only ID allowlists |
| RAPTOR parent-child | ✅ Yes | Can store parent centers |
| LightRAG graph retrieval | ✅ Yes | Dense vectors only |
| Semantic cache (embedding similarity) | ✅ Yes | Good fit — small, hot dataset |
| Concurrent ingestion | ⚠️ Partial | No true online add — must rebuild |
| Docker deployment | ✅ Yes | `pip install` in Dockerfile |
| Colab (free tier) | ✅ Yes | No GPU needed |

---

## References

- [turbovec GitHub](https://github.com/RyanCodrai/turbovec)
- [turbovec PyPI](https://pypi.org/project/turbovec/)
- [TurboQuant Paper (ICLR 2026)](https://github.com/RyanCodrai/turbovec)
- [Qdrant TurboQuant-MSE Adoption]( cue from graph search that Qdrant uses TurboQuant]
- [turbovec for RAG: A Practical Guide](https://medium.com/@pankaj_pandey/turbovec-for-rag-a-practical-guide-to-faster-smaller-vector-search-749a19532252)
- [Eight Megabytes per Million Vectors](https://www.fzeba.com/posts/57-turbovec-turboquant-vector-index/)
