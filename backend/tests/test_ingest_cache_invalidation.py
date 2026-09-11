"""Newly ingested teachings must not be masked by pre-ingest cached answers.

Ingestion invalidated only the semantic tier. The exact, hot and doctrine tiers
kept serving answers computed before the new content existed, for their whole
TTL — and doctrine_cache.refresh() existed with no caller anywhere in the tree.

Each tier is cleared independently, and no cache failure may fail an ingest
whose vectors are already committed.
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock

import pytest

from ingest.pipeline import IngestionPipeline

SOURCE = "https://example.test/video"


@pytest.fixture
def container(monkeypatch):
    c = MagicMock()
    monkeypatch.setattr("app.dependencies.get_container", lambda: c)
    return c


@pytest.fixture
def hot(monkeypatch):
    h = MagicMock()
    monkeypatch.setattr("services.hot_cache.hot_cache", h)
    return h


def _pipeline() -> IngestionPipeline:
    return IngestionPipeline.__new__(IngestionPipeline)


def test_all_answer_tiers_are_invalidated(container, hot):
    _pipeline()._invalidate_answer_caches(SOURCE)

    container.exact_cache.invalidate_all.assert_called_once()
    container.doctrine_cache.refresh.assert_called_once()
    hot.clear.assert_called_once()


def test_one_failing_tier_does_not_stop_the_others(container, hot):
    container.exact_cache.invalidate_all.side_effect = ConnectionError("redis down")

    _pipeline()._invalidate_answer_caches(SOURCE)

    container.doctrine_cache.refresh.assert_called_once()
    hot.clear.assert_called_once()


def test_cache_failure_never_raises_into_ingestion(container, hot):
    """The vectors are already committed; a cache problem must not undo that."""
    hot.clear.side_effect = RuntimeError("boom")
    container.exact_cache.invalidate_all.side_effect = RuntimeError("boom")
    container.doctrine_cache.refresh.side_effect = RuntimeError("boom")

    _pipeline()._invalidate_answer_caches(SOURCE)  # must not raise


def test_missing_container_is_survivable(monkeypatch):
    def _no_container():
        raise RuntimeError("container not initialised")

    monkeypatch.setattr("app.dependencies.get_container", _no_container)
    _pipeline()._invalidate_answer_caches(SOURCE)  # must not raise


def test_upsert_path_calls_the_invalidator():
    """Pins the call site, so the helper cannot be orphaned like refresh() was."""
    src = inspect.getsource(IngestionPipeline._embed_and_index)
    assert "self._invalidate_answer_caches(" in src


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
