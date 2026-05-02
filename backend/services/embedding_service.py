"""
Mukthi Guru — Embedding & Reranking Service

Models:
  - Encoder: BAAI/bge-m3 (1024 dims, multilingual, native dense+sparse+ColBERT)
  - Reranker: cross-encoder/ms-marco-MiniLM-L-6-v2 (CPU)

bge-m3 produces dense, sparse (lexical), and ColBERT vectors in a single encode() call,
enabling native hybrid search without a separate BM25/sparse encoder. Supports 100+
languages including all 10 target Indian languages.
"""

import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Multilingual embedding service with native hybrid search support.

    bge-m3 produces three vector types in one forward pass:
    - Dense (1024d): For semantic similarity search
    - Sparse (lexical weights): For keyword/BM25-style matching
    - ColBERT (token-level): For fine-grained late interaction (optional)

    This eliminates the need for a separate sparse encoder and enables
    true hybrid search across 100+ languages.
    """

    def __init__(self) -> None:
        """Initialize with None models — will be loaded on first use."""
        import threading
        self._encoder = None
        self._reranker = None
        self._lock = threading.Lock()
        logger.info("Embedding service initialized (lazy load)")

    def _ensure_models(self) -> None:
        """Lazy-load the heavy embedding and reranking models."""
        if self._encoder is not None and self._reranker is not None:
            return
        with self._lock:
            if self._encoder is None:
                from FlagEmbedding import BGEM3FlagModel
                logger.info(f"Loading encoder: {settings.embedding_model}")
                self._encoder = BGEM3FlagModel(
                    settings.embedding_model,
                    use_fp16=False,   # FP16 requires CUDA; use False for CPU/Mac Docker
                    device="cpu",
                )
            if self._reranker is None:
                from sentence_transformers import CrossEncoder
                logger.info(f"Loading reranker: {settings.reranker_model}")
                self._reranker = CrossEncoder(
                    settings.reranker_model,
                    device="cpu",
                )
                logger.info("Embedding service models fully loaded")


    def encode(self, texts: list[str]) -> list[list[float]]:
        """
        Encode texts into dense vectors only (backward compatible).

        Used for clustering (RAPTOR) and simple comparisons where
        sparse vectors are not needed.

        Returns:
            List of dense embedding vectors (1024 dims each)
        """
        self._ensure_models()
        output = self._encoder.encode(
            texts,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        return output['dense_vecs'].tolist()

    def encode_single(self, text: str) -> list[float]:
        """Encode a single text into a dense vector."""
        return self.encode([text])[0]

    def encode_with_sparse(self, texts: list[str]) -> dict:
        """
        Encode texts into both dense and sparse vectors.

        Used at ingestion time and for query encoding in hybrid search.

        Returns:
            dict with:
              - 'dense': list of dense vectors (1024d each)
              - 'sparse': list of sparse dicts {token_id: weight}
        """
        self._ensure_models()
        output = self._encoder.encode(
            texts,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )
        return {
            'dense': output['dense_vecs'].tolist(),
            'sparse': output['lexical_weights'],
        }

    def encode_single_full(self, text: str) -> dict:
        """
        Encode a single text into both dense and sparse vectors.

        Returns:
            dict with 'dense' (list[float]) and 'sparse' (dict of token_id->weight)
        """
        result = self.encode_with_sparse([text])
        return {
            'dense': result['dense'][0],
            'sparse': result['sparse'][0],
        }

    def rerank(
        self,
        query: str,
        documents: list[dict],
        top_k: Optional[int] = None,
    ) -> list[dict]:
        """
        Rerank documents using CrossEncoder for maximum precision.

        Pipeline: Qdrant returns 20 docs (from hybrid search)
                  -> CrossEncoder deeply scores each (query, doc) pair
                  -> Filter by minimum score threshold (rerank_min_score)
                  -> Return only the top-k most semantically relevant
        """
        if top_k is None:
            top_k = settings.rag_top_k_rerank

        if not documents:
            return []

        self._ensure_models()
        pairs = [(query, doc["text"]) for doc in documents]
        scores = self._reranker.predict(pairs)

        for doc, score in zip(documents, scores):
            doc["rerank_score"] = float(score)

        # Score distribution logging for debugging
        if scores is not None and len(scores) > 0:
            import numpy as np
            score_arr = np.array([float(s) for s in scores])
            logger.info(
                f"Reranker scores: min={score_arr.min():.4f}, "
                f"max={score_arr.max():.4f}, mean={score_arr.mean():.4f}, "
                f"median={float(np.median(score_arr)):.4f}"
            )

        ranked = sorted(documents, key=lambda d: d["rerank_score"], reverse=True)

        # Apply minimum score threshold
        min_score = settings.rerank_min_score
        above_threshold = [d for d in ranked if d["rerank_score"] >= min_score]

        if not above_threshold and ranked:
            # If ALL docs are below threshold, keep the top 1 as minimum
            above_threshold = ranked[:1]
            logger.warning(
                f"All {len(ranked)} docs scored below threshold {min_score}. "
                f"Keeping top-1 (score={ranked[0]['rerank_score']:.4f})"
            )

        filtered_count = len(ranked) - len(above_threshold)
        if filtered_count > 0:
            logger.info(
                f"Reranker threshold {min_score}: filtered {filtered_count} docs below threshold"
            )

        top_docs = above_threshold[:top_k]

        logger.info(
            f"Reranked {len(documents)} → {len(top_docs)} docs"
            + (f". Top score: {top_docs[0]['rerank_score']:.4f}" if top_docs else "")
        )

        return top_docs

