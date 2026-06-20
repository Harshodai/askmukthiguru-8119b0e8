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
_sarvam_cloud: Any = None


# InMemoryCacheAdapter fallback removed (Unit 8) — missing service is now a hard error


def init_services(
    ollama: Any,
    embedder: Any,
    qdrant: Any,
    lightrag: Any = None,
    serene_mind: Any = None,
    context_compressor=None,
    web_search=None,
    semantic_cache: Any = None,
    sarvam_cloud: Any = None,
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

    global _ollama, _embedder, _qdrant, _lightrag, _serene_mind, _lettuce_detect, _reranker, _web_search, _injected_semantic_cache, _sarvam_cloud

    _ollama = ollama
    _embedder = embedder
    _qdrant = qdrant
    _lightrag = lightrag
    _serene_mind = serene_mind
    _web_search = web_search
    _sarvam_cloud = sarvam_cloud
    _injected_semantic_cache = semantic_cache

    _reranker = RerankerService()
    _lettuce_detect = LettuceDetectService(embedder)

    # Inject ollama into follow-up resolver
    set_followup_ollama(ollama)

    # Prime the YAML-driven SemanticRouter (Phase A — de-hardcoding).
    # The router replaces the hardcoded keyword lists (`_CAPABILITY_PATTERNS`,
    # `_SIMPLE_QUERY_PATTERNS`, `_TEMPORAL_PATTERNS`, `_MEDITATION_NOUNS`, etc.)
    # with utterance embeddings declared in backend/config/router_routes.yaml.
    # If the embedder doesn't expose a usable encoder, we log a warning and
    # leave the router in regex-only mode; intent classification then falls
    # back to the LLM path with no regression.
    try:
        from app.config import settings
        if getattr(settings, "use_semantic_router", True):
            from services.semantic_router import IntentSemanticRouter

            encode_fn = _resolve_router_encoder(embedder)
            if encode_fn is not None:
                router = IntentSemanticRouter.get_default()
                router.prime(encode_fn)
    except Exception as exc:  # noqa: BLE001 — never block startup over router
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "SemanticRouter prime failed at init_services: %s. "
            "Intent routing will fall back to LLM classifier.", exc
        )


def _resolve_router_encoder(embedder: Any):
    """Return a callable(text) -> list[float] suitable for SemanticRouter, or
    None if the embedder doesn't expose a recognisable encode method.

    Centralising this lookup lets us swap the production embedder without
    touching the router or the init path. Order of preference:
      1. embedder.encode_single        (returns float vector directly)
      2. embedder.encode_single_full   (returns {'dense': [...], 'sparse': ...})
      3. embedder.encode               (sentence-transformers convention)
    """
    if embedder is None:
        return None

    if hasattr(embedder, "encode_single") and callable(embedder.encode_single):
        return embedder.encode_single

    if hasattr(embedder, "encode_single_full") and callable(embedder.encode_single_full):
        def _encode(text: str) -> list[float]:
            result = embedder.encode_single_full(text)
            if isinstance(result, dict):
                dense = result.get("dense") or result.get("embedding") or []
                return list(dense)
            return list(result)
        return _encode

    if hasattr(embedder, "encode") and callable(embedder.encode):
        def _encode_st(text: str) -> list[float]:
            vec = embedder.encode(text)
            return list(vec.tolist() if hasattr(vec, "tolist") else vec)
        return _encode_st

    return None
