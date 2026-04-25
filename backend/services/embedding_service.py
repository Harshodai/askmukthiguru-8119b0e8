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
        """Load bge-m3 and reranker models."""
        from FlagEmbedding import BGEM3FlagModel

        logger.info(f"Loading encoder: {settings.embedding_model}")
        self._encoder = BGEM3FlagModel(
            settings.embedding_model,
            use_fp16=False,   # FP16 requires CUDA; use False for CPU/Mac Docker
            device="cpu",
        )

        logger.info(f"Loading reranker: {settings.reranker_model}")
        from sentence_transformers import CrossEncoder
        self._reranker = CrossEncoder(
            settings.reranker_model,
            device="cpu",
        )

        logger.info("Embedding service ready (bge-m3 multilingual)")

    def encode(self, texts: list[str]) -> list[list[float]]:
        """
        Encode texts into dense vectors only (backward compatible).

        Used for clustering (RAPTOR) and simple comparisons where
        sparse vectors are not needed.

        Returns:
            List of dense embedding vectors (1024 dims each)
        """
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
                  -> Return only the top-k most semantically relevant
        """
        if top_k is None:
            top_k = settings.rag_top_k_rerank

        if not documents:
            return []

        pairs = [(query, doc["text"]) for doc in documents]
        scores = self._reranker.predict(pairs)

        for doc, score in zip(documents, scores):
            doc["rerank_score"] = float(score)

        ranked = sorted(documents, key=lambda d: d["rerank_score"], reverse=True)
        top_docs = ranked[:top_k]

        logger.debug(
            f"Reranked {len(documents)} -> {len(top_docs)} docs. "
            f"Top score: {top_docs[0]['rerank_score']:.4f}" if top_docs else "No docs"
        )

        return top_docs
