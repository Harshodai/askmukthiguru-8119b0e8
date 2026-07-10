"""Regression guard: the P90 vector cache must outlive a single request.

A fresh ``PipelineCoordinator`` is built per request in ``app/api/chat.py``. When the
TurboQuantCache lived on that instance, ``CacheUpdateStage`` wrote entries that were
discarded with the coordinator, so ``_check_vector_cache`` always saw ``size == 0``
and fell through to Qdrant on every request.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.config import settings
from app.pipeline.pipeline_coordinator import PipelineCoordinator
from services.turboquant_cache import get_shared_vector_cache


@pytest.fixture(autouse=True)
def _fresh_shared_cache():
    get_shared_vector_cache.cache_clear()
    yield
    get_shared_vector_cache().clear()
    get_shared_vector_cache.cache_clear()


def test_vector_cache_is_shared_across_coordinators():
    """Two per-request coordinators must bind the same cache object."""
    first = PipelineCoordinator(MagicMock())._ensure_vector_cache()
    second = PipelineCoordinator(MagicMock())._ensure_vector_cache()

    assert first is second, "each request rebuilt the vector cache — P90 tier can never hit"


def test_entry_written_by_one_request_is_visible_to_the_next():
    """The write in CacheUpdateStage must be readable by a later request's coordinator."""
    embedding = [0.1] * settings.embedding_dimension

    writer = PipelineCoordinator(MagicMock())
    writer._ensure_vector_cache().put(embedding=embedding, metadata={"response": "cached answer"})

    reader_cache = PipelineCoordinator(MagicMock())._ensure_vector_cache()
    assert reader_cache.size == 1

    hits = reader_cache.search(query_embedding=embedding, top_k=1, threshold=0.9)
    assert hits and hits[0]["metadata"]["response"] == "cached answer"
