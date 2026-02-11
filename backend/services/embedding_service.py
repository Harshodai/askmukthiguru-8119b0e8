"""
Mukthi Guru — Embedding & Reranking Service

Design Patterns:
  - Singleton (via module-level instance): Models loaded once, reused
  - Strategy Pattern: Separate encode() and rerank() strategies
  - Pipeline Pattern: Retrieve (broad) → Rerank (precise) → Return (top-k)

Models:
  - Encoder: all-MiniLM-L6-v2 (80MB, 384 dims, CPU)
  - Reranker: cross-encoder/ms-marco-MiniLM-L-6-v2 (90MB, CPU)
  
The CrossEncoder reranker is the single biggest precision boost in the pipeline.
It takes top-20 from Qdrant and produces top-3 by deeply comparing query+doc pairs.
"""

import logging
from typing import Optional

from sentence_transformers import SentenceTransformer, CrossEncoder

from app.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Dual-model service: fast bi-encoder for indexing/search + 
    precise cross-encoder for reranking.
    
    Why two models?
    - Bi-encoder: O(1) per query (pre-computed vectors). Used at indexing time
      and for the initial broad search.
    - Cross-encoder: O(n) per query (scores each query-doc pair). Used only at
      reranking time on the top-20 results. Much more accurate but slower.
    """

    def __init__(self) -> None:
        """Load both models to CPU. GPU is reserved for the LLM."""
        logger.info(f"Loading encoder: {settings.embedding_model}")
        self._encoder = SentenceTransformer(
            settings.embedding_model,
            device="cpu",
        )

        logger.info(f"Loading reranker: {settings.reranker_model}")
        self._reranker = CrossEncoder(
            settings.reranker_model,
            device="cpu",
        )

        logger.info("Embedding service ready")

    def encode(self, texts: list[str]) -> list[list[float]]:
        """
        Encode texts into dense vectors.
        
        Used for:
        1. Indexing (ingestion pipeline → Qdrant)
        2. Query embedding (user question → search vector)
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of embedding vectors (384 dims each)
        """
        embeddings = self._encoder.encode(
            texts,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return embeddings.tolist()

    def encode_single(self, text: str) -> list[float]:
        """Encode a single text string. Convenience wrapper."""
        return self.encode([text])[0]

    def rerank(
        self,
        query: str,
        documents: list[dict],
        top_k: Optional[int] = None,
    ) -> list[dict]:
        """
        Rerank documents using CrossEncoder for maximum precision.
        
        This is the 🔑 precision layer in the anti-hallucination pipeline.
        
        Pipeline: Qdrant returns 20 docs (from bi-encoder cosine similarity)
                  → CrossEncoder deeply scores each (query, doc) pair
                  → Return only the top-3 most semantically relevant
        
        Research shows CrossEncoder reranking improves retrieval precision
        by 30-50% over bi-encoder alone.
        
        Args:
            query: User's question
            documents: List of dicts with 'text' key from Qdrant search
            top_k: How many to keep (default from config: 3)
            
        Returns:
            Top-k documents sorted by CrossEncoder score (descending)
        """
        if top_k is None:
            top_k = settings.rag_top_k_rerank

        if not documents:
            return []

        # Create (query, document) pairs for the CrossEncoder
        pairs = [(query, doc["text"]) for doc in documents]

        # Score all pairs — this is the expensive but precise operation
        scores = self._reranker.predict(pairs)

        # Attach scores and sort
        for doc, score in zip(documents, scores):
            doc["rerank_score"] = float(score)

        # Sort descending by rerank score, keep top-k
        ranked = sorted(documents, key=lambda d: d["rerank_score"], reverse=True)
        top_docs = ranked[:top_k]

        logger.debug(
            f"Reranked {len(documents)} → {len(top_docs)} docs. "
            f"Top score: {top_docs[0]['rerank_score']:.4f}" if top_docs else "No docs"
        )

        return top_docs
