"""
Unit test for RAGFlow Gap 1 — Deep Research (recursive sufficiency retrieval).

ONE runnable check: mock the sufficiency judge + retrieve_for_single_query.
No real services. Confirms: (1) sufficient verdict short-circuits, (2) insufficient
verdict fires follow-ups, dedupes, and recurses to a sufficient verdict.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from rag.nodes import deep_research as dr


STATE = {
    "query_tier": "tier3_complex",  # auto-fires
    "intent": "FACTUAL",
    "chat_history": [],
    "selected_clusters": [],
    "knowledge_tags": None,
}


def _verdict(sufficient: bool, queries=None):
    import json

    return json.dumps(
        {
            "is_sufficient": sufficient,
            "missing_information": "" if sufficient else "gap",
            "complementary_queries": queries or [],
        }
    )


def test_sufficient_verdict_short_circuits():
    """Sufficient → no follow-up retrieval, accumulated_docs returned unchanged."""
    docs = [{"id": "c1", "text": "beautiful state is calm"}]
    fake_ollama = AsyncMock()
    fake_ollama._generate_fast = AsyncMock(return_value=_verdict(True))

    with patch.object(dr._services, "_ollama", fake_ollama), patch.object(
        dr, "retrieve_for_single_query", AsyncMock()
    ) as mocked_retrieve:
        out = asyncio.run(
            dr.conduct_deep_research("What is the beautiful state?", docs, STATE, depth=2)
        )

    assert out == docs
    mocked_retrieve.assert_not_called()
    fake_ollama._generate_fast.assert_awaited_once()


def test_insufficient_then_sufficient_dedupes_and_recurses():
    """Round 1 insufficient → follow-up; round 2 sufficient → stop."""
    docs = [{"id": "c1", "text": "beautiful state is calm"}]
    new_docs = [{"id": "c2", "text": "a beautiful state brings joy"}]

    # First call insufficient (1 follow-up), second call sufficient.
    fake_ollama = AsyncMock()
    fake_ollama._generate_fast = AsyncMock(
        side_effect=[_verdict(False, ["joy in beautiful state"]), _verdict(True)]
    )

    with patch.object(dr._services, "_ollama", fake_ollama), patch.object(
        dr, "retrieve_for_single_query", AsyncMock(return_value=new_docs)
    ) as mocked_retrieve:
        out = asyncio.run(
            dr.conduct_deep_research("What is the beautiful state?", docs, STATE, depth=2)
        )

    # Follow-up retrieval fired once, dedupe kept both chunks
    assert mocked_retrieve.await_count == 1
    assert len(out) == 2
    ids = {d["id"] for d in out}
    assert ids == {"c1", "c2"}
    assert fake_ollama._generate_fast.await_count == 2


def test_disabled_does_nothing():
    """Non-activating state returns docs unchanged without any LLM call."""
    docs = [{"id": "c1", "text": "x"}]
    disabled_state = {"query_tier": "fast", "intent": "FACTUAL", "chat_history": []}
    fake_ollama = AsyncMock()
    with patch.object(dr._services, "_ollama", fake_ollama):
        out = asyncio.run(
            dr.conduct_deep_research("q", docs, disabled_state, depth=2)
        )
    assert out == docs
    fake_ollama._generate_fast.assert_not_called()