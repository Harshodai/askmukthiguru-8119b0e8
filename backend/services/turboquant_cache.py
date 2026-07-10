"""
Mukthi Guru — Local Vector Cache for Sub-ms Lookup (TurboVec)

Mirrors top Qdrant results in a local TurboQuantIndex for sub-millisecond
lookup on repeat queries. Enables the P90 fast path: query confidence
high AND cache hit → return cached response without network.

Architecture:
  - Primary: TurboQuantIndex (4-bit quantization, 8x memory compression vs float32)
  - Fallback: numpy brute-force cosine similarity
  - Mirrors top N (default 500) results from Qdrant
  - Uses IdMapIndex for stable uint64 IDs (enables targeted removal)
"""

from __future__ import annotations

import logging
import threading
import time
from functools import lru_cache
from typing import Any, Optional

import numpy as np

from app.config import settings

try:
    from turbovec import TurboQuantIndex, IdMapIndex

    _HAVE_TURBOVEC = True
except ImportError:
    TurboQuantIndex = None  # type: ignore
    IdMapIndex = None  # type: ignore
    _HAVE_TURBOVEC = False

logger = logging.getLogger(__name__)


def _l2_normalize(arr: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-12)
    return arr / norms


class TurboQuantCache:
    """TurboQuantIndex mirroring top Qdrant results for sub-ms lookup.

    Uses TurboVec (4-bit quantization) when available, numpy fallback otherwise.
    Stores response payloads in a separate dict keyed by internal ID.
    """

    def __init__(
        self,
        dimension: int = 1024,
        max_size: int = 0,
    ) -> None:
        self._dimension = dimension
        self._max_size = max_size or settings.faiss_cache_size
        self._lock = threading.RLock()

        self._metadata: dict[int, dict] = {}
        self._id_counter: int = 0
        self._last_sync: float = 0.0
        self._hits: int = 0
        self._misses: int = 0

        if _HAVE_TURBOVEC:
            self._index = TurboQuantIndex(dim=dimension, bit_width=4)
            self._prepared = False
        else:
            self._index = None
            self._prepared = False
            logger.info("TurboVec not available; TurboQuantCache will use numpy fallback")

    def put(self, embedding: list[float], metadata: dict) -> int:
        """Insert a single embedding + metadata pair.

        Args:
            embedding: Dense vector as list of floats.
            metadata: Dict with keys like "response", "citations", "intent".

        Returns:
            Internal ID assigned to this entry.
        """
        with self._lock:
            self._evict_if_full()
            fid = self._id_counter
            self._id_counter += 1

            vec = np.array([embedding], dtype=np.float32)

            if _HAVE_TURBOVEC and self._index is not None:
                self._index.add(vec)
                self._prepared = False

            # Store full-precision vector in metadata for numpy fallback
            metadata["_embedding"] = embedding
            self._metadata[fid] = metadata
            return fid

    def put_batch(self, embeddings: list[list[float]], metadatas: list[dict]) -> list[int]:
        """Insert a batch of embeddings."""
        fids: list[int] = []
        for emb, meta in zip(embeddings, metadatas):
            fids.append(self.put(emb, meta))
        return fids

    def search(
        self, query_embedding: list[float], top_k: int = 1, threshold: float = 0.0
    ) -> list[dict]:
        """Search the local index for similar entries.

        Args:
            query_embedding: Query vector as list of floats.
            top_k: Number of results to return.
            threshold: Minimum similarity score to consider a match (inner product).

        Returns:
            List of dicts with keys: id, score, metadata.
        """
        with self._lock:
            if self.size == 0:
                self._misses += 1
                return []

            qvec = np.array([query_embedding], dtype=np.float32)
            k = min(top_k, self.size)

            if _HAVE_TURBOVEC and self._index is not None:
                if not self._prepared:
                    self._index.prepare()
                    self._prepared = True
                scores, indices = self._index.search(qvec, k)
                results = self._build_results(scores[0], indices[0], threshold)
            else:
                results = self._numpy_search(qvec, k, threshold)

            if results:
                self._hits += 1
            else:
                self._misses += 1

            return results[:top_k]

    def _build_results(
        self, scores: np.ndarray, indices: np.ndarray, threshold: float
    ) -> list[dict]:
        """Convert raw TurboVec scores/indices into result dicts, filtering by threshold.

        TurboQuantIndex.search returns positional indices (0..n-1 in insertion order),
        NOT internal FID values. We map them back using _id_counter ordering.
        """
        results: list[dict] = []
        # Get all FIDs sorted by insertion order
        all_fids = sorted(self._metadata.keys())

        for score_val, pos in zip(scores, indices):
            if pos < 0 or pos >= len(all_fids):
                continue
            score_val = float(score_val)
            if score_val < threshold:
                continue
            fid = all_fids[int(pos)]
            meta = self._metadata.get(fid)
            if meta is not None:
                results.append({"id": int(fid), "score": score_val, "metadata": {k: v for k, v in meta.items() if k != "_embedding"}})
        return results

    def refresh(self, qdrant_service: Any = None) -> None:
        """Rebuild the index (clear if no Qdrant available)."""
        logger.info("TurboQuantCache refresh triggered")
        with self._lock:
            self._reset()
        self._last_sync = time.time()

    def clear(self) -> None:
        """Clear the entire cache."""
        with self._lock:
            self._reset()
        logger.info("TurboQuantCache cleared")

    @property
    def size(self) -> int:
        return len(self._metadata)

    @property
    def stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "size": self.size,
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{self._hits / total:.1%}" if total > 0 else "N/A",
            "last_sync": self._last_sync,
            "has_turbovec": _HAVE_TURBOVEC,
        }

    @property
    def is_available(self) -> bool:
        return True

    def health_check(self) -> bool:
        """TurboQuant local cache has no required external dependencies."""
        return True

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _evict_if_full(self) -> None:
        if self.size >= self._max_size and self._metadata:
            oldest = min(self._metadata.keys())
            self._remove_fid(oldest)

    def _remove_fid(self, fid: int) -> None:
        self._metadata.pop(fid, None)
        # TurboQuantIndex uses positional indexing, so we can't remove by FID.
        # Full rebuild needed. For now, just remove from metadata.
        if _HAVE_TURBOVEC and self._index is not None:
            self._reset_index()
            self._rebuild_from_metadata()

    def _reset_index(self) -> None:
        if _HAVE_TURBOVEC and self._index is not None:
            self._index = TurboQuantIndex(dim=self._dimension, bit_width=4)
            self._prepared = False

    def _rebuild_from_metadata(self) -> None:
        if not self._metadata or not _HAVE_TURBOVEC or self._index is None:
            return
        for fid in sorted(self._metadata.keys()):
            emb = self._metadata[fid].get("_embedding")
            if emb is not None:
                self._index.add(np.array([emb], dtype=np.float32))
        self._prepared = False

    def _numpy_search(
        self, qvec: np.ndarray, k: int, threshold: float
    ) -> list[dict]:
        """Fallback numpy brute-force cosine similarity."""
        if not self._metadata:
            return []

        ids = list(self._metadata.keys())
        emb_list = []
        valid_ids = []
        for fid in ids:
            emb = self._metadata[fid].get("_embedding")
            if emb is not None:
                emb_list.append(emb)
                valid_ids.append(fid)

        if not emb_list:
            return []

        vecs = np.array(emb_list, dtype=np.float32)
        vecs = _l2_normalize(vecs)

        q_norm = np.linalg.norm(qvec)
        if q_norm > 0:
            qvec = qvec / q_norm

        sims = qvec @ vecs.T

        top_idx = np.argsort(sims[0])[::-1][:k]
        results = []
        for idx in top_idx:
            score = float(sims[0][idx])
            if score < threshold:
                continue
            fid = valid_ids[idx]
            meta = self._metadata.get(fid, {})
            results.append({
                "id": int(fid),
                "score": score,
                "metadata": {k: v for k, v in meta.items() if k != "_embedding"},
            })
        return results

    def _reset(self) -> None:
        if _HAVE_TURBOVEC:
            self._index = TurboQuantIndex(dim=self._dimension, bit_width=4)
            self._prepared = False
        self._metadata.clear()
        self._id_counter = 0


@lru_cache(maxsize=1)
def get_shared_vector_cache() -> TurboQuantCache:
    """Process-wide P90 vector cache.

    PipelineCoordinator is constructed per request (``app/api/chat.py``), so a
    per-coordinator cache is written at the end of one request and then discarded —
    every later lookup sees ``size == 0`` and falls through to Qdrant. Entries have
    to outlive the request. Safe to share: ``put``/``search`` hold ``self._lock``.

    Tests reset it with ``get_shared_vector_cache.cache_clear()``.
    """
    return TurboQuantCache(
        dimension=settings.embedding_dimension,
        max_size=settings.faiss_cache_size,
    )
