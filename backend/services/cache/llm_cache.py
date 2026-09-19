"""LangChain GPTCache integration for LLM call deduplication."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Optional

logger = logging.getLogger(__name__)


def init_llm_cache(embedding_func: Optional[Callable] = None):
    """
    Initializes the global LangChain cache using GPTCache with exact-match caching.

    Uses a local map manager (MapDataManager) persisted to flat files.
    This intercepts redundant LLM calls (particularly during LightRAG extraction)
    to drastically cut down latency and repetition.

    Args:
        embedding_func: Kept for API compatibility; MapDataManager uses prompt text
            keys directly, so caller embedding functions are unused.

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
                max_size=getattr(settings, "gptcache_max_size", 1000),
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
        logger.info("GPTCache exact-match call caching attached to LangChain (local map manager)")
    except ImportError:
        logger.info(
            "GPTCache not installed — skipping LLM call caching. Install with: pip install gptcache"
        )
    except Exception as e:
        logger.error(f"Failed to initialize GPTCache: {e}")
