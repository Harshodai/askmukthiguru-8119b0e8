"""Tests for the B3 graph-ready memory nodes (handoff §B3).

inject_memory_context / memory_relevance_gate live in rag.memory and are
exercised here with a fake MemoryService — no Supabase, no embeddings, no
LLM. The topology wiring into graph_strategies.py is deliberately deferred
(see the module docstring in rag/memory.py); these tests pin the node
contract so the wiring lands safely later.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from rag.memory import (
    _memory_skip_reason,
    inject_memory_context,
    memory_relevance_gate,
)

USER_ID = str(uuid.uuid4())


def _state(**overrides):
    base = {
        "question": "What did I tell you about my meditation practice?",
        "intent": "QUERY",
        "user_id": USER_ID,
        "detected_language": "en",
        "memory_context": "",
    }
    base.update(overrides)
    return base


class FakeMemoryService:
    """Deterministic stand-in for MemoryService's read surface."""

    def __init__(self, core=None, semantic=None, summaries=None):
        self.core = core if core is not None else [{"content": "User lives in Pune."}]
        self.semantic = (
            semantic
            if semantic is not None
            else [{"claim": "User meditates every morning.", "confidence": 0.9}]
        )
        self.summaries = (
            summaries
            if summaries is not None
            else [{"summary": "Talked about Ekam visit.", "topics": ["Ekam"]}]
        )
        self.calls: list[tuple] = []

    async def get_core(self, user_id):
        self.calls.append(("get_core", user_id))
        return self.core

    async def search_semantic(self, user_id, query, limit=5, min_similarity=0.6):
        self.calls.append(("search_semantic", user_id, query, limit))
        return self.semantic[:limit]

    async def recent_summaries(self, user_id, limit=3):
        self.calls.append(("recent_summaries", user_id, limit))
        return self.summaries[:limit]


class TestMemoryRelevanceGate:
    def test_query_injects(self):
        assert memory_relevance_gate(_state()) == "inject"

    def test_casual_skips_case_insensitive(self):
        assert memory_relevance_gate(_state(intent="CASUAL")) == "skip"
        assert memory_relevance_gate(_state(intent="casual")) == "skip"

    def test_doctrine_lookup_skips(self):
        assert memory_relevance_gate(_state(intent="doctrine_lookup")) == "skip"

    def test_anonymous_users_skip(self):
        for uid in (None, "", "anonymous", "anon:token-123"):
            assert memory_relevance_gate(_state(user_id=uid)) == "skip", uid

    def test_already_present_skips_without_wipe(self):
        assert _memory_skip_reason(_state(memory_context="prior block")) == "already_present"
        assert memory_relevance_gate(_state(memory_context="prior block")) == "skip"

    def test_disabled_flag_skips(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "feature_memory_enabled", False)
        assert memory_relevance_gate(_state()) == "skip"

    def test_custom_skip_intents(self, monkeypatch):
        import rag.memory as rag_memory

        monkeypatch.setattr(rag_memory, "_memory_skip_intents", lambda: ("meditation",))
        assert memory_relevance_gate(_state(intent="MEDITATION")) == "skip"
        assert memory_relevance_gate(_state(intent="QUERY")) == "inject"


class TestInjectMemoryContext:
    @pytest.mark.asyncio
    async def test_merges_all_three_layers(self):
        svc = FakeMemoryService()
        out = await inject_memory_context(_state(), memory_service=svc)
        assert out["memory_context"]
        assert "User lives in Pune." in out["memory_context"]
        assert "User meditates every morning." in out["memory_context"]
        assert "Earlier session: Talked about Ekam visit." in out["memory_context"]
        assert out["evaluation_trace"]["memory_injected"] is True
        assert out["evaluation_trace"]["memory_chars"] == len(out["memory_context"])
        kinds = [c[0] for c in svc.calls]
        assert kinds == ["get_core", "search_semantic", "recent_summaries"]

    @pytest.mark.asyncio
    async def test_skip_never_wipes_existing_context(self):
        svc = FakeMemoryService()
        out = await inject_memory_context(
            _state(intent="CASUAL", memory_context="orchestrator block"),
            memory_service=svc,
        )
        assert "memory_context" not in out
        assert out["evaluation_trace"] == {
            "memory_injected": False,
            "memory_skip": "already_present",
        }
        assert svc.calls == []

    @pytest.mark.asyncio
    async def test_skip_intent_fetches_nothing(self):
        svc = FakeMemoryService()
        out = await inject_memory_context(_state(intent="CASUAL"), memory_service=svc)
        assert "memory_context" not in out
        assert out["evaluation_trace"]["memory_skip"] == "skip_intent:CASUAL"
        assert svc.calls == []

    @pytest.mark.asyncio
    async def test_fail_open_on_service_errors(self):
        class Exploding:
            async def get_core(self, user_id):
                raise RuntimeError("db down")

            async def search_semantic(self, *a, **k):
                raise RuntimeError("db down")

            async def recent_summaries(self, *a, **k):
                raise RuntimeError("db down")

        out = await inject_memory_context(_state(), memory_service=Exploding())
        assert out.get("memory_context", "") == ""
        assert out["evaluation_trace"]["memory_injected"] is False

    @pytest.mark.asyncio
    async def test_no_results_reports_skip(self):
        svc = FakeMemoryService(core=[], semantic=[], summaries=[])
        out = await inject_memory_context(_state(), memory_service=svc)
        assert out.get("memory_context", "") == ""
        assert out["evaluation_trace"]["memory_skip"] == "no_results"

    @pytest.mark.asyncio
    async def test_no_service_without_container(self, monkeypatch):
        import app.dependencies as deps

        monkeypatch.setattr(deps, "get_container", MagicMock(side_effect=RuntimeError("x")))
        out = await inject_memory_context(_state(), memory_service=None)
        assert out["evaluation_trace"] == {
            "memory_injected": False,
            "memory_skip": "no_service",
        }

    @pytest.mark.asyncio
    async def test_empty_question_skips_semantic_search(self):
        svc = FakeMemoryService()
        out = await inject_memory_context(
            _state(question="", rewritten_query=""), memory_service=svc
        )
        kinds = [c[0] for c in svc.calls]
        assert "search_semantic" not in kinds
        assert "get_core" in kinds and "recent_summaries" in kinds
        assert out["evaluation_trace"]["memory_injected"] is True

    @pytest.mark.asyncio
    async def test_truncates_to_token_budget(self, monkeypatch):
        import rag.memory as rag_memory

        monkeypatch.setattr(rag_memory, "_memory_token_budget", lambda: 20)
        svc = FakeMemoryService(
            core=[{"content": "User lives in Pune and works as a teacher."}] * 10,
            semantic=[{"claim": "User meditates daily at dawn for one hour."}] * 10,
            summaries=[],
        )
        out = await inject_memory_context(_state(), memory_service=svc)
        assert len(out["memory_context"].split()) <= 16  # 20 tokens / 1.3 ratio + margin
        assert out["evaluation_trace"]["memory_injected"] is True

    @pytest.mark.asyncio
    async def test_container_service_used_when_not_passed(self, monkeypatch):
        import app.dependencies as deps

        svc = FakeMemoryService()
        monkeypatch.setattr(deps, "get_container", lambda: SimpleNamespace(memory_service=svc))
        out = await inject_memory_context(_state())
        assert "User lives in Pune." in out["memory_context"]
