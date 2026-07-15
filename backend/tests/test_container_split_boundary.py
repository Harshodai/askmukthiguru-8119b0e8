from __future__ import annotations

"""
Boundary tests for the ServiceContainer split (Task C2 RFC, Testing Strategy row 3).

These tests verify the public boundaries of the split modules:
  - app.container    — ServiceContainer (data-holder + delegating methods)
  - app.health        — ContainerHealthChecker.check()
  - app.lifecycle     — ContainerLifecycle.startup()/shutdown() + close_container()
  - app.builder       — ContainerBuilder re-export
  - app.dependencies  — back-compat shim re-exporting every public symbol

They are boundary-only: no real container construction, no Docker/Supabase,
no network. The container is a plain mock object exposing only the
attributes/properties/methods the health checker reads.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.health import ContainerHealthChecker
from app.lifecycle import ContainerLifecycle, close_container


class _MockContainer:
    """Minimal mock container exposing only what ContainerHealthChecker.check() reads.

    Mirrors exactly the surface in app.health.ContainerHealthChecker.check():
      - container.qdrant.health_check()  -> sync, returns bool
      - container.qdrant.count()          -> sync, returns int
      - container.ocr.health_check()      -> sync, returns bool
      - container.ollama.health_check()   -> async, returns bool
      - container.guardrails.is_available -> bool attr
      - container.guardrails.provider_name -> str attr
      - container.semantic_cache.is_available -> bool attr (or semantic_cache is None)
      - container.lightrag_degraded       -> bool property
    """

    def __init__(self, *, qdrant, ocr, ollama, guardrails, semantic_cache, lightrag_degraded=False):
        self.qdrant = qdrant
        self.ocr = ocr
        self.ollama = ollama
        self.guardrails = guardrails
        self.semantic_cache = semantic_cache
        self._lightrag_degraded = lightrag_degraded

    @property
    def lightrag_degraded(self) -> bool:
        return self._lightrag_degraded


def _make_healthy_container() -> _MockContainer:
    return _MockContainer(
        qdrant=MagicMock(health_check=MagicMock(return_value=True), count=MagicMock(return_value=42)),
        ocr=MagicMock(health_check=MagicMock(return_value=True)),
        ollama=MagicMock(health_check=AsyncMock(return_value=True)),
        guardrails=MagicMock(is_available=True, provider_name="lightweight"),
        semantic_cache=MagicMock(is_available=True),
        lightrag_degraded=False,
    )


@pytest.mark.asyncio
async def test_health_check_all_services():
    """All-healthy container → check() returns dict with per-service keys and a healthy signal."""
    container = _make_healthy_container()
    result = await ContainerHealthChecker().check(container)

    assert isinstance(result, dict)
    expected_keys = {
        "qdrant",
        "ollama",
        "ocr",
        "guardrails",
        "guardrails_provider",
        "semantic_cache",
        "lightrag_degraded",
        "embedding",
        "qdrant_count",
    }
    assert expected_keys.issubset(result.keys()), f"missing keys: {expected_keys - set(result.keys())}"
    assert result["qdrant"] is True
    assert result["ollama"] is True
    assert result["ocr"] is True
    assert result["guardrails"] is True
    assert result["semantic_cache"] is True
    assert result["lightrag_degraded"] is False
    assert result["embedding"] is True
    assert result["qdrant_count"] == 42
    container.qdrant.health_check.assert_called_once()
    container.qdrant.count.assert_called_once()
    container.ocr.health_check.assert_called_once()
    container.ollama.health_check.assert_awaited_once()


@pytest.mark.asyncio
async def test_health_check_one_failing():
    """One failing service → overall response marks that service unhealthy; no exception raised.

    Qdrant.health_check() raises; the checker catches and reports qdrant=False,
    qdrant_count=0 while the other services remain healthy. The overall dict
    is still returned (the checker never raises on a single-service failure).
    """
    container = _make_healthy_container()
    container.qdrant.health_check = MagicMock(side_effect=RuntimeError("qdrant down"))

    result = await ContainerHealthChecker().check(container)

    assert isinstance(result, dict)
    assert result["qdrant"] is False
    assert result["qdrant_count"] == 0
    # ocr lives in the same try block as qdrant in app.health, so a qdrant
    # exception short-circuits the whole executor block → ocr also False.
    # Boundary contract: a failing infra service marks itself unhealthy and
    # does NOT raise out of check(); the remaining services stay healthy.
    assert result["ollama"] is True
    assert result["guardrails"] is True


def test_back_compat_imports():
    """Every public symbol still importable from the legacy app.dependencies path.

    This is the critical back-compat guarantee: existing `from app.dependencies
    import X` imports across the codebase must keep working unchanged after
    the C2 split. If this test fails, a downstream module broke.
    """
    from app.dependencies import (  # noqa: F401
        ServiceContainer,
        get_container,
        ContainerBuilder,
        ContainerHealthChecker as DepHealthChecker,
        ContainerLifecycle as DepLifecycle,
        close_container as DepCloseContainer,
    )

    from app.container import ServiceContainer as _SC, _NoopTranslationProvider  # noqa: F401
    from app.health import ContainerHealthChecker as _HC
    from app.lifecycle import ContainerLifecycle as _LC, close_container as _CC
    from app.builder import ContainerBuilder as _CB

    assert ServiceContainer is _SC
    assert DepHealthChecker is _HC
    assert DepLifecycle is _LC
    assert DepCloseContainer is _CC
    assert ContainerBuilder is _CB


@pytest.mark.asyncio
async def test_lifecycle_startup_shutdown():
    """ContainerLifecycle.startup()/shutdown() run against a passed-in mock container without error.

    Boundary-only: we pass an explicit container so the lifecycle object does
    not touch the module-level singleton (no real build). shutdown() delegates
    to close_container(), which iterates cleanup methods — the mock container
    exposes a `close()` on one service to verify it is called.
    """
    qdrant_close = MagicMock()
    ocr_close = MagicMock()
    mock_container = SimpleNamespace(
        rag_graph=None,
        ingestion=None,
        guardrails=None,
        ocr=SimpleNamespace(close=ocr_close),
        ollama=SimpleNamespace(close=MagicMock()),
        embedding=None,
        qdrant=SimpleNamespace(close=qdrant_close),
        user_profile=None,
        krutrim=None,
        _neo4j_driver=None,
    )

    lifecycle = ContainerLifecycle()

    started = await lifecycle.startup(container=mock_container)
    assert started is mock_container

    await lifecycle.shutdown(container=mock_container)

    qdrant_close.assert_called_once()
    ocr_close.assert_called_once()