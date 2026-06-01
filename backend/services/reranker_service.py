"""
Mukthi Guru — FlashRank Reranker Service

Integrates PrithivirajDamodaran/FlashRank for ultra-fast, lightweight document reranking.
Features:
  - ONNX runtime backend (no PyTorch, 50% lower latency, 1GB smaller RAM footprint).
  - Dynamic platform/architecture auto-tuning (loads MultiBERT-L-12 on macOS for multilingual Indic languages, MiniLM-L-6-v2 in constrained environments).
  - Graceful fallback to sentence-transformers CrossEncoder in case of ONNX or model loading failure.
"""

from __future__ import annotations

import asyncio
import logging
import platform
import time
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


class RerankerService:
    """
    High-performance reranking service utilizing FlashRank (ONNX)
    with sentence-transformers CrossEncoder fallback.
    """

    def __init__(self) -> None:
        """Initialize the reranker service (lazy-loaded)."""
        import threading

        self._ranker = None
        self._fallback_reranker = None
        self._lock = threading.Lock()
        self._is_fallback = False
        logger.info("FlashRank Reranker service initialized (lazy load)")

    def _ensure_model(self) -> None:
        """Ensure that either FlashRank or the fallback CrossEncoder model is loaded."""
        if self._ranker is not None or self._fallback_reranker is not None:
            return

        with self._lock:
            # Check double-lock pattern
            if self._ranker is not None or self._fallback_reranker is not None:
                return

            if not settings.use_flashrank:
                logger.info(
                    "FlashRank is explicitly disabled in settings. Loading sentence-transformers fallback reranker."
                )
                self._load_fallback()
                return

            try:
                from flashrank import Ranker

                # Dynamic model auto-tuning
                model_name = settings.flashrank_model
                if model_name == "auto":
                    # Detect OS and Architecture
                    system_platform = platform.system()
                    machine = platform.machine()
                    logger.info(
                        f"Auto-tuning reranker: system={system_platform}, machine={machine}"
                    )

                    if system_platform == "Darwin" and (
                        "arm" in machine.lower()
                        or "m1" in machine.lower()
                        or "m2" in machine.lower()
                        or "m3" in machine.lower()
                    ):
                        # Apple Silicon (macOS M1/M2/M3/M4) -> use multilingual model for Indian language transcript support
                        model_name = "ms-marco-MultiBERT-L-12"
                        logger.info(
                            "Selected 'ms-marco-MultiBERT-L-12' for Apple Silicon to support rich multilingual spiritual wisdom."
                        )
                    else:
                        # Default to lighter model in constrained environments
                        model_name = "ms-marco-MiniLM-L-6-v2"
                        logger.info(
                            "Selected light 'ms-marco-MiniLM-L-6-v2' for resource-constrained or generic environments."
                        )

                logger.info(f"Initializing FlashRank with model: {model_name}")
                start_time = time.perf_counter()

                # Note: FlashRank downloads models to cache folder if not present
                self._ranker = Ranker(model_name=model_name)

                duration = time.perf_counter() - start_time
                logger.info(
                    f"FlashRank successfully initialized in {duration:.4f}s using {model_name}"
                )
                self._is_fallback = False

            except Exception as e:
                logger.error(
                    f"❌ Failed to initialize FlashRank reranker (ONNX). Fallback will trigger: {e}",
                    exc_info=True,
                )
                self._load_fallback()

    def _load_fallback(self) -> None:
        """Load the fallback sentence-transformers CrossEncoder."""
        try:
            import torch
            from sentence_transformers import CrossEncoder

            device = "cpu"
            if torch.cuda.is_available():
                device = "cuda"
            elif torch.backends.mps.is_available():
                device = "mps"

            logger.info(f"Loading fallback reranker: {settings.reranker_model} on device: {device}")
            start_time = time.perf_counter()
            self._fallback_reranker = CrossEncoder(
                settings.reranker_model,
                device=device,
            )
            duration = time.perf_counter() - start_time
            logger.info(f"Fallback CrossEncoder loaded successfully in {duration:.4f}s")
            self._is_fallback = True
        except Exception as e:
            logger.critical(
                f"❌ CRITICAL FAILURE: Could not load fallback reranker: {e}", exc_info=True
            )
            raise e

    async def rerank(
        self,
        query: str,
        documents: list[dict[str, Any]],
        top_k: int | None = None,
        min_score: float | None = None,
    ) -> list[dict[str, Any]]:
        """
        Rerank documents using FlashRank (ONNX) with sentence-transformers fallback.
        Runs asynchronously in a separate thread to prevent event loop blocking.
        """
        return await asyncio.to_thread(self._rerank_sync, query, documents, top_k, min_score)

    def _rerank_sync(
        self,
        query: str,
        documents: list[dict[str, Any]],
        top_k: int | None = None,
        min_score: float | None = None,
    ) -> list[dict[str, Any]]:
        """
        Synchronous core reranking method.
        """
        if top_k is None:
            top_k = settings.rag_top_k_rerank

        if not documents:
            return []

        self._ensure_model()

        effective_min_score = min_score if min_score is not None else settings.rerank_min_score
        start_time = time.perf_counter()

        if not self._is_fallback and self._ranker is not None:
            try:
                from flashrank import RerankRequest

                # Format passages for FlashRank: [{"id": idx, "text": doc["text"]}]
                # Store the original docs mapped by index to preserve all original metadata (metadata, ids, etc.)
                passages = []
                for idx, doc in enumerate(documents):
                    passages.append({"id": idx, "text": doc.get("text", "")})

                rerank_request = RerankRequest(query=query, passages=passages)

                # FlashRank returns a list of dictionaries with 'id', 'text', 'score' ordered by score descending
                results = self._ranker.rerank(rerank_request)

                # Reconstruct and score documents
                reranked_docs = []
                for result in results:
                    orig_idx = int(result["id"])
                    orig_doc = documents[orig_idx].copy()

                    # FlashRank scores are in range [0, 1]
                    score = float(result["score"])
                    orig_doc["rerank_score"] = score
                    orig_doc["rerank_raw_logit"] = (
                        score  # FlashRank does not expose logits directly, so use score
                    )
                    reranked_docs.append(orig_doc)

                duration = time.perf_counter() - start_time
                logger.info(f"FlashRank reranked {len(documents)} docs in {duration:.4f}s")

                # Filter by threshold
                above_threshold = [
                    d for d in reranked_docs if d["rerank_score"] >= effective_min_score
                ]

                if not above_threshold and reranked_docs:
                    # If ALL docs are below threshold, keep the top 1 as minimum fallback
                    above_threshold = reranked_docs[:1]
                    logger.warning(
                        f"All {len(reranked_docs)} docs scored below threshold {effective_min_score}. "
                        f"Keeping top-1 (score={reranked_docs[0]['rerank_score']:.4f})"
                    )

                filtered_count = len(reranked_docs) - len(above_threshold)
                if filtered_count > 0:
                    logger.info(
                        f"FlashRank threshold {effective_min_score}: filtered {filtered_count} docs below threshold"
                    )

                return above_threshold[:top_k]

            except Exception as e:
                logger.error(
                    f"❌ FlashRank rerank execution failed, falling back to CrossEncoder: {e}",
                    exc_info=True,
                )
                # Fall through to the sentence-transformers CrossEncoder fallback below
                self._load_fallback()

        # Fallback CrossEncoder execution
        logger.info("Executing CrossEncoder fallback reranking.")
        pairs = [(query, doc["text"]) for doc in documents]
        raw_scores = self._fallback_reranker.predict(pairs)

        import numpy as np

        def _sigmoid(x):
            return 1.0 / (1.0 + np.exp(-x))

        reranked_docs = []
        for doc, raw_score in zip(documents, raw_scores):
            doc_copy = doc.copy()
            score = float(_sigmoid(raw_score))
            doc_copy["rerank_score"] = score
            doc_copy["rerank_raw_logit"] = float(raw_score)
            reranked_docs.append(doc_copy)

        reranked_docs = sorted(reranked_docs, key=lambda d: d["rerank_score"], reverse=True)
        duration = time.perf_counter() - start_time
        logger.info(f"CrossEncoder fallback reranked {len(documents)} docs in {duration:.4f}s")

        above_threshold = [d for d in reranked_docs if d["rerank_score"] >= effective_min_score]

        if not above_threshold and reranked_docs:
            above_threshold = reranked_docs[:1]
            logger.warning(
                f"All {len(reranked_docs)} docs scored below threshold {effective_min_score}. "
                f"Keeping top-1 (score={reranked_docs[0]['rerank_score']:.4f})"
            )

        filtered_count = len(reranked_docs) - len(above_threshold)
        if filtered_count > 0:
            logger.info(
                f"Fallback CrossEncoder threshold {effective_min_score}: filtered {filtered_count} docs below threshold"
            )

        return above_threshold[:top_k]
