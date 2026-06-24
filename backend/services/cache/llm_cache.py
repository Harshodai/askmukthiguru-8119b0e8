"""LangChain GPTCache integration for LLM call deduplication."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def init_llm_cache():
    """
    Initializes the global LangChain cache using GPTCache with SEMANTIC similarity.

    Uses Qdrant (already running) as vector store + BGE-M3 embeddings (already loaded).
    This intercepts redundant LLM calls (particularly during LightRAG extraction)
    to drastically cut down latency and repetition.

    Gracefully skips if gptcache is not installed.
    """
    try:
        import os
        import re

        from gptcache import Cache, Config
        from gptcache.embedding import SBERT
        from gptcache.manager.factory import manager_factory
        from gptcache.processor.post import temperature_softmax
        from gptcache.processor.pre import get_prompt
        from gptcache.similarity_evaluation.distance import SearchDistanceEvaluation
        from langchain.globals import set_llm_cache
        from langchain_community.cache import GPTCache

        from app.config import settings

        os.makedirs("data/gptcache", exist_ok=True)

        # Use our existing BGE-M3 model (1024-dim, multilingual) via SBERT wrapper
        embedder = SBERT(model=settings.embedding_model)

        def init_gptcache(cache_obj: Cache, llm: str):
            safe_llm_name = re.sub(r"[^a-zA-Z0-9_]", "_", llm)

            # Qdrant vector store + SQLite for metadata
            data_manager = manager_factory(
                manager="sqlite,qdrant",
                data_dir=f"data/gptcache/{safe_llm_name}",
                max_size=10000,
                vector_params={
                    "url": settings.qdrant_url,  # http://qdrant:6333
                    "collection_name": f"gptcache_{safe_llm_name}",
                    "dimension": settings.embedding_dimension,  # 1024
                },
                scalar_params={
                    "table_len_config": {
                        "question_question": 5000,  # Support longer prompts
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
                embedding_func=embedder.to_embeddings,
                data_manager=data_manager,
                similarity_evaluation=SearchDistanceEvaluation(),
                post_process_messages_func=temperature_softmax,
                config=Config(
                    similarity_threshold=getattr(settings, "SEMANTIC_CACHE_SIMILARITY", 0.85),
                ),
            )

        set_llm_cache(GPTCache(init_gptcache))
        logger.info("GPTCache semantic caching attached to LangChain (Qdrant + BGE-M3)")
    except ImportError:
        logger.info(
            "GPTCache not installed — skipping LLM call caching. Install with: pip install gptcache"
        )
    except Exception as e:
        logger.error(f"Failed to initialize GPTCache: {e}")
