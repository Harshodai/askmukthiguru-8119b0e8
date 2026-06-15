"""Module-level service references injected by graph builder at startup.

All node modules import service instances from here.
"""

from __future__ import annotations

from typing import Any

# Service references populated by init_services()
_ollama: Any = None
_embedder: Any = None
_qdrant: Any = None
_lightrag: Any = None
_serene_mind: Any = None
_injected_semantic_cache: Any = None
_fallback_cache: Any = None
_context_compressor: Any = None
_lettuce_detect: Any = None
_reranker: Any = None
_web_search: Any = None


def __getattr__(name: str) -> Any:
    if name == "_semantic_cache":
        global _injected_semantic_cache, _fallback_cache
        if _injected_semantic_cache is not None:
            return _injected_semantic_cache
        if _fallback_cache is None:
            from services.cache_service import InMemoryCacheAdapter
            _fallback_cache = InMemoryCacheAdapter()
        return _fallback_cache
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def init_services(
    ollama: Any,
    embedder: Any,
    qdrant: Any,
    lightrag: Any = None,
    serene_mind: Any = None,
    context_compressor=None,
    web_search=None,
    semantic_cache: Any = None,
) -> None:
    """Inject service dependencies into the nodes module.

    Called once during graph construction.

    Raises:
        ValueError: If any required service is None.
    """
    if not all([ollama, embedder, qdrant]):
        missing = []
        if not ollama:
            missing.append("ollama")
        if not embedder:
            missing.append("embedder")
        if not qdrant:
            missing.append("qdrant")
        raise ValueError(f"init_services: missing services: {', '.join(missing)}")

    from rag.resolve_followup import set_ollama as set_followup_ollama
    from services.lettuce_detect_service import LettuceDetectService
    from services.reranker_service import RerankerService

    global _ollama, _embedder, _qdrant, _lightrag, _serene_mind, _lettuce_detect, _reranker, _web_search, _injected_semantic_cache

    _ollama = ollama
    _embedder = embedder
    _qdrant = qdrant
    _lightrag = lightrag
    _serene_mind = serene_mind
    _web_search = web_search
    _injected_semantic_cache = semantic_cache

    _reranker = RerankerService()
    _lettuce_detect = LettuceDetectService(embedder)

    # Inject ollama into follow-up resolver
    set_followup_ollama(ollama)
