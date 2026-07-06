"""LangChain GPTCache integration for LLM call deduplication."""

from __future__ import annotations

import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def init_llm_cache(embedding_func: Optional[Callable] = None):
    """Initialize a map-based exact-match LLM call cache via GPTCache."""
    # embedding_func argument kept for API compatibility but intentionally unused:
    # MapDataManager uses the prompt string as the key.
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
        from gptcache.similarity_evaluation.simple import ExactMatchEvaluation
        from langchain.globals import set_llm_cache
        from langchain_community.cache import GPTCache

        from app.config import settings

        os.makedirs("data/gptcache", exist_ok=True)

        
        # MapDataManager expects a hashable key.  We use the prompt text itself as the
        # key (exact-match LLM call cache).  Any caller-provided embedding function is
        # ignored for this exact-match store; semantic similarity is handled separately
        # by TurboQuantCache / Qdrant.
        def embedding_func(text, *args, **kwargs):
            # Normalize lists/tensors to a plain string key.
            if isinstance(text, (list, tuple)) and len(text) == 1:
                text = text[0]
            if not isinstance(text, str):
                text = str(text)
            return text

        def init_gptcache(cache_obj: Cache, llm: str):
            safe_llm_name = re.sub(r"[^a-zA-Z0-9_]", "_", llm)

            # lessons.md §22: use manager="map" to avoid SQLite+Qdrant overhead and
            # qdrant-client version incompatibilities. MapDataManager is an LRU-backed
            # in-memory store persisted to a simple text file.
            data_manager = manager_factory(
                manager="map",
                data_dir=f"data/gptcache/{safe_llm_name}",
                max_size=10000,
            )

            cache_obj.init(
                pre_embedding_func=get_prompt,
                embedding_func=embedding_func,
                data_manager=data_manager,
                similarity_evaluation=ExactMatchEvaluation(),
                post_process_messages_func=temperature_softmax,
                config=Config(
                    similarity_threshold=getattr(settings, "semantic_cache_similarity", 0.87),
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
