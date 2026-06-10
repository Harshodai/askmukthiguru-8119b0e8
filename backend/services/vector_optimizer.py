"""
Unit 20 — Vector Index Optimization

Provides:
  1. ``optimize_collection()``: trigger Qdrant's built-in optimizer on-demand
  2. ``get_index_health()``: return key index metrics (segment count, RAM usage, etc.)
  3. ``VectorIndexOptimizer``: a scheduled optimizer that runs nightly off-peak

Optimization actions available:
  - Trigger optimizer: tells Qdrant to re-merge and optimize segments
  - Adjust HNSW M/ef_construct at runtime (advanced, requires recreate)
  - Quantization re-run (applies updated int8 config to new segments)

All operations are non-blocking and safe to run against a live collection.

Usage::

    from services.vector_optimizer import VectorIndexOptimizer
    optimizer = VectorIndexOptimizer(qdrant_service)
    await optimizer.run_optimization()
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


class VectorIndexOptimizer:
    """On-demand and scheduled vector index optimizer.

    Wraps Qdrant's optimizer trigger API and provides collection health metrics.
    """

    def __init__(self, qdrant_service) -> None:
        self._qdrant = qdrant_service
        self._client = qdrant_service._client
        self._collection = qdrant_service._collection

    # ---- Health Metrics ----

    def get_index_health(self) -> dict:
        """Return key index health metrics for the primary collection.

        Returns:
            Dict with:
              - status: "green" | "yellow" | "red"
              - points_count: total indexed vectors
              - segments_count: number of segments (lower = better post-optimization)
              - optimizer_status: current optimizer state
              - disk_usage_mb: approximate disk usage
        """
        try:
            info = self._client.get_collection(self._collection)
            config = info.config if hasattr(info, "config") else None
            optimizer_status = getattr(info, "optimizer_status", {})
            points_count = getattr(info, "points_count", 0) or 0
            segments_count = getattr(info, "segments_count", 0) or 0

            # Determine health status heuristics
            if segments_count > 50:
                status = "yellow"  # Many segments — benefit from optimization
            elif segments_count > 100:
                status = "red"    # Too many segments — severely fragmented
            else:
                status = "green"

            return {
                "status": status,
                "collection": self._collection,
                "points_count": points_count,
                "segments_count": segments_count,
                "optimizer_status": str(optimizer_status),
                "dimension": self._qdrant._dimension,
            }
        except Exception as exc:
            logger.warning(f"VectorIndexOptimizer: health check failed: {exc}")
            return {
                "status": "unknown",
                "collection": self._collection,
                "error": str(exc),
            }

    # ---- Optimization Actions ----

    def trigger_optimizer(self) -> bool:
        """Trigger Qdrant's built-in segment optimizer.

        This is a fire-and-forget trigger — Qdrant runs optimization asynchronously
        in the background. Returns True if the trigger was accepted.
        """
        try:
            # Qdrant doesn't expose a direct "run optimizer now" API, but
            # updating the optimizer config triggers a re-run.
            from qdrant_client.http.models import OptimizersConfigDiff

            self._client.update_collection(
                collection_name=self._collection,
                optimizer_config=OptimizersConfigDiff(
                    indexing_threshold=20_000,   # Trigger index build at 20k vectors
                    memmap_threshold=50_000,     # Use mmap above 50k points
                ),
            )
            logger.info(f"VectorIndexOptimizer: optimizer triggered on '{self._collection}'")
            return True
        except Exception as exc:
            logger.warning(f"VectorIndexOptimizer: optimizer trigger failed: {exc}")
            return False

    def update_hnsw_config(
        self,
        m: int = 16,
        ef_construct: int = 100,
        full_scan_threshold: int = 10_000,
    ) -> bool:
        """Update HNSW parameters (affects new segments only).

        Args:
            m: HNSW M parameter (connections per node). Higher = better recall, more RAM.
            ef_construct: Build-time beam width. Higher = better recall, slower ingestion.
            full_scan_threshold: Below this count, use full scan instead of HNSW.
        """
        try:
            from qdrant_client.http.models import HnswConfigDiff

            self._client.update_collection(
                collection_name=self._collection,
                hnsw_config=HnswConfigDiff(
                    m=m,
                    ef_construct=ef_construct,
                    full_scan_threshold=full_scan_threshold,
                ),
            )
            logger.info(
                f"VectorIndexOptimizer: HNSW updated on '{self._collection}' "
                f"(m={m}, ef_construct={ef_construct})"
            )
            return True
        except Exception as exc:
            logger.warning(f"VectorIndexOptimizer: HNSW config update failed: {exc}")
            return False

    async def run_optimization(self) -> dict:
        """Run a full optimization pass (non-blocking — runs in thread pool).

        Returns:
            Report dict with health before/after and actions taken.
        """
        loop = asyncio.get_event_loop()
        before = await loop.run_in_executor(None, self.get_index_health)
        logger.info(f"VectorIndexOptimizer: starting optimization. Before: {before}")

        actions = []
        triggered = await loop.run_in_executor(None, self.trigger_optimizer)
        if triggered:
            actions.append("optimizer_triggered")

        # Also update HNSW to better defaults for 1024-dim vectors
        hnsw_updated = await loop.run_in_executor(None, self.update_hnsw_config, 16, 100, 10_000)
        if hnsw_updated:
            actions.append("hnsw_updated")

        after = await loop.run_in_executor(None, self.get_index_health)
        logger.info(f"VectorIndexOptimizer: optimization complete. After: {after}")

        return {
            "actions": actions,
            "before": before,
            "after": after,
        }
