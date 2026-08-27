"""Schema-drift guard for the semantic cache adapters (Task H1.1).

Verifies:
  (a) ``SemanticCacheAdapter.get`` accepts ``(query, threshold=None)``.
  (b) ``SemanticCacheAdapter.put`` accepts the kwargs ``cache_stage.py`` passes
      (query, response, intent, citations, meditation_step).
  (c) The dead ``QdrantSemanticCache`` class no longer exists in
      ``services.semantic_cache`` (import should fail).
  (d) ``SemanticCacheService`` is still importable for backward compat.
"""

from __future__ import annotations

import inspect

import pytest


def _adapter_signature(fn):
    return inspect.signature(fn)


class TestSemanticCacheSchema:
    def test_adapter_get_accepts_query_and_threshold(self) -> None:
        from services.cache.semantic_adapter import SemanticCacheAdapter

        sig = _adapter_signature(SemanticCacheAdapter.get)
        params = list(sig.parameters)
        assert params[:2] == ["self", "query"], (
            f"SemanticCacheAdapter.get must start with (self, query); got {params}"
        )
        assert "threshold" in sig.parameters, (
            "SemanticCacheAdapter.get must accept a `threshold` kwarg"
        )
        assert sig.parameters["threshold"].default is None, (
            "SemanticCacheAdapter.get `threshold` must default to None"
        )

    def test_adapter_put_accepts_cache_stage_kwargs(self) -> None:
        from services.cache.semantic_adapter import SemanticCacheAdapter

        sig = _adapter_signature(SemanticCacheAdapter.put)
        expected = ["self", "query", "response", "intent", "citations", "meditation_step"]
        actual = list(sig.parameters)
        assert actual == expected, (
            f"SemanticCacheAdapter.put params must match cache_stage.py call; "
            f"expected {expected}, got {actual}"
        )
        assert sig.parameters["meditation_step"].default == 0, (
            "SemanticCacheAdapter.put `meditation_step` must default to 0"
        )

    def test_qdrant_semantic_cache_removed_from_module(self) -> None:
        import services.semantic_cache as mod

        assert not hasattr(mod, "QdrantSemanticCache"), (
            "Dead QdrantSemanticCache must be removed from services.semantic_cache"
        )

    def test_qdrant_semantic_cache_class_not_importable_by_name(self) -> None:
        with pytest.raises(ImportError):
            from services.semantic_cache import QdrantSemanticCache  # noqa: F401

            _ = QdrantSemanticCache

    def test_redis_key_is_callable_on_an_instance(self) -> None:
        """Regression: ``_redis_key`` was defined without ``@staticmethod`` but
        called as ``self._redis_key(scope, point_id)`` — Python binds ``self``
        into the first positional slot, so every real call (get/put/invalidate)
        raised ``TypeError: _redis_key() takes 2 positional arguments but 3
        were given`` and the semantic cache never actually cached anything.
        Signature inspection alone (see the other tests in this file) cannot
        catch this class of bug: it only fires on an actual bound call.
        """
        from services.cache.semantic_adapter import SemanticCacheAdapter
        from rag.corpus_scope import CorpusScope

        scope = CorpusScope(tenant_id="t1", corpus_id="c1")
        instance = SemanticCacheAdapter.__new__(SemanticCacheAdapter)

        key = instance._redis_key(scope, "point-1")

        assert key == "mukthiguru:semcache:t1:c1:all:point-1"

    def test_legacy_service_still_importable(self) -> None:
        from services.semantic_cache import SemanticCacheService

        assert SemanticCacheService is not None
        assert hasattr(SemanticCacheService, "get")
        assert hasattr(SemanticCacheService, "put")
