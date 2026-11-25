"""
Tests for Memgraph-Driven Dynamic Candidate Sizing (MemgraphHarnessSizer).
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app.config import settings
from services.first_person_graph_sizing import HarnessSizingDecision, MemgraphHarnessSizer


class MockSession:
    def __init__(self, record_data: dict):
        self._record_data = record_data

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def run(self, query: str, **kwargs):
        mock_result = MagicMock()
        mock_result.single.return_value = self._record_data
        return mock_result


class MockDriver:
    def __init__(self, record_data: dict):
        self._record_data = record_data

    def session(self):
        return MockSession(self._record_data)


def test_memgraph_sizing_disabled(monkeypatch):
    monkeypatch.setattr(settings, "first_person_memgraph_sizing_enabled", False)
    sizer = MemgraphHarnessSizer()
    decision = sizer.calculate_candidate_size_sync(["span_1"], "What is suffering?")
    assert decision.k == 4
    assert decision.reason == "memgraph_sizing_disabled"


def test_memgraph_sizing_driver_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "first_person_memgraph_sizing_enabled", True)
    sizer = MemgraphHarnessSizer(driver=None)
    with patch.object(sizer, "_get_driver", return_value=None):
        decision = sizer.calculate_candidate_size_sync(["span_1"], "What is suffering?")
        assert decision.k == 5
        assert decision.reason == "driver_unavailable_fallback"


def test_memgraph_sizing_chained_discourse(monkeypatch):
    monkeypatch.setattr(settings, "first_person_memgraph_sizing_enabled", True)
    monkeypatch.setattr(settings, "first_person_memgraph_sizing_min_k", 3)
    monkeypatch.setattr(settings, "first_person_memgraph_sizing_max_k", 12)

    # 3 chained units, 5 concepts, 1 guru -> base(4) + chain(3) + density(2) = 9
    driver = MockDriver({"chain_count": 3, "concept_count": 5, "guru_count": 1})
    sizer = MemgraphHarnessSizer(driver=driver)

    decision = sizer.calculate_candidate_size_sync(
        ["span_1", "span_2"], "Explain the four sacred secrets"
    )
    assert decision.k == 9
    assert decision.chain_count == 3
    assert decision.concept_count == 5
    assert "graph_signals" in decision.reason


def test_memgraph_sizing_comparative(monkeypatch):
    monkeypatch.setattr(settings, "first_person_memgraph_sizing_enabled", True)
    monkeypatch.setattr(settings, "first_person_memgraph_sizing_min_k", 3)
    monkeypatch.setattr(settings, "first_person_memgraph_sizing_max_k", 12)

    # 2 chained units, 2 concepts, 2 gurus -> base(4) + chain(3) + comp(2) = 9
    driver = MockDriver({"chain_count": 2, "concept_count": 2, "guru_count": 2})
    sizer = MemgraphHarnessSizer(driver=driver)

    decision = sizer.calculate_candidate_size_sync(
        ["span_1"], "What is the difference between Krishnaji and Preethaji teachings?"
    )
    assert decision.k >= 9
    assert decision.guru_count == 2


def test_memgraph_sizing_atomic_isolated(monkeypatch):
    monkeypatch.setattr(settings, "first_person_memgraph_sizing_enabled", True)
    monkeypatch.setattr(settings, "first_person_memgraph_sizing_min_k", 3)
    monkeypatch.setattr(settings, "first_person_memgraph_sizing_max_k", 12)

    # 0 chains, 0 concepts -> base(4) + density(-1) = 3
    driver = MockDriver({"chain_count": 0, "concept_count": 0, "guru_count": 1})
    sizer = MemgraphHarnessSizer(driver=driver)

    decision = sizer.calculate_candidate_size_sync(["span_1"], "What is Soul Sync?")
    assert decision.k == 3


@pytest.mark.asyncio
async def test_memgraph_sizing_async_wrapper(monkeypatch):
    monkeypatch.setattr(settings, "first_person_memgraph_sizing_enabled", True)
    driver = MockDriver({"chain_count": 1, "concept_count": 2, "guru_count": 1})
    sizer = MemgraphHarnessSizer(driver=driver)

    decision = await sizer.calculate_candidate_size(["span_1"], "peace of mind")
    assert isinstance(decision, HarnessSizingDecision)
    assert decision.k == 5  # base(4) + chain(1)
