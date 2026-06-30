"""LangChain GPTCache integration for LLM call deduplication."""

from __future__ import annotations

import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def _get_default_embedding_func(settings):
    """Load BGE-M3 via SBERT wrapper for GPTCache."""
    from gptcache.embedding import SBERT
    return SBERT(model=settings.embedding_model).to_embeddings


def init_llm_cache(embedding_func: Optional[Callable] = None):
    """
    Initializes the global LangChain cache using GPTCache with SEMANTIC similarity.

    Uses Qdrant (already running) as vector store + BGE-M3 embeddings (already loaded).
    This intercepts redundant LLM calls (particularly during LightRAG extraction)
    to drastically cut down latency and repetition.

    Args:
        embedding_func: Optional custom embedding function. If provided, it will be
            used instead of creating a new SBERT instance. This is useful when
            the caller already has an EmbeddingService loaded and wants to avoid
            loading the model twice.

    Gracefully skips if gptcache is not installed.
    """
    try:
        import os
        import re

        from gptcache import Cache, Config
        from gptcache.manager.factory import manager_factory
        from gptcache.processor.post import temperature_softmax
        from gptcache.processor.pre import get_prompt
        from gptcache.similarity_evaluation.distance import SearchDistanceEvaluation
        from langchain.globals import set_llm_cache
        from langchain_community.cache import GPTCache

        from app.config import settings

        os.makedirs("data/gptcache", exist_ok=True)

        # Monkeypatch: gptcache's QdrantVectorStore.search uses the removed QdrantClient.search.
        # Replace with query_points so the LLM call cache works with qdrant-client >=1.7.
        from gptcache.manager.vector_data.qdrant import QdrantVectorStore

        def _patched_qdrant_search(self, data, top_k=-1):
            if top_k == -1:
                top_k = self.top_k
            results = self._client.query_points(
                collection_name=self._collection_name,
                query=data.reshape(-1).tolist(),
                limit=top_k,
                with_payload=False,
            )
            return [(p.score, p.id) for p in results.points]

        QdrantVectorStore.search = _patched_qdrant_search

        # Use the caller-provided embedding function, or load default BGE-M3 via SBERT
        if embedding_func is None:
            from gptcache.embedding import SBERT
            embedder = SBERT(model=settings.embedding_model)
            embedding_func = embedder.to_embeddings

        def init_gptcache(cache_obj: Cache, llm: str):
            safe_llm_name = re.sub(r"[^a-zA-Z0-9_]", "_", llm)

            # Qdrant vector store + SQLite for metadata
            data_manager = manager_factory(
                manager="sqlite,qdrant",
                data_dir=f"data/gptcache/{safe_llm_name}",
                max_size=10000,
                vector_params={
                    "url": settings.qdrant_url,
                    "collection_name": f"gptcache_{safe_llm_name}",
                    "dimension": settings.embedding_dimension,
                    "location": None,
                },
                scalar_params={
                    "table_len_config": {
                        "question_question": 5000,
                        "answer_answer": 5000,
                    }
                },
                eviction_params={
                    "policy": "LRU",
                    "max_size": 10000,
                }
            )

            cache_obj.init(
                pre_embedding_func=get_prompt,
                embedding_func=embedding_func,
                data_manager=data_manager,
                similarity_evaluation=SearchDistanceEvaluation(),
                post_process_messages_func=temperature_softmax,
                config=Config(
                    similarity_threshold=getattr(settings, "SEMANTIC_CACHE_SIMILARITY", 0.85),
                ),
            )

        set_llm_cache(GPTCache(init_gptcache))
        logger.info("GPTCache semantic caching attached to LangChain (Qdrant + shared embedder)")
    except ImportError:
        logger.info(
            "GPTCache not installed — skipping LLM call caching. Install with: pip install gptcache"
        )
    except Exception as e:
        logger.error(f"Failed to initialize GPTCache: {e}")
