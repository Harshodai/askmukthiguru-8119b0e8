"""Slice D — bounded waits: no bare sleeps, no unbounded joins.

1. Coordinator memory probe (the ``0.2 s`` ``wait_for``): a hung memory
   source must resolve conservatively (eligible ``True``) in well under 2 s.
   An unbounded probe would take the full 5 s hang.
2. Blocking-join proof at the threading level: a worker that needs 0.3 s
   must hold the joining thread for >= 0.25 s with its verdict visible. An
   instant-fake join (return without waiting) fails the elapsed floor AND
   the verdict assertion.
3. Answerability join through the real pipeline: a 0.5 s gate worker must be
   waited on (served clip, ``answerability_calls == 1``, elapsed >= 0.4 s).
   A join that raced ahead would take the indeterminate-abstain path.

Every async wait below is ``asyncio.wait_for``-bounded; every thread join
passes an explicit timeout.
"""

from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = [pytest.mark.answerability_real]


@pytest.mark.asyncio
async def test_hung_memory_probe_resolves_inside_two_seconds():
    """The 0.2 s probe bound fires; eligibility falls back conservative-True."""
    from app.pipeline.pipeline_coordinator import PipelineCoordinator

    async def _hung(user_id, limit=1):
        await asyncio.sleep(5.0)
        return [{"m": 1}]

    coord = PipelineCoordinator.__new__(PipelineCoordinator)
    profile = MagicMock()
    profile.get_recent_memories = AsyncMock(side_effect=_hung)
    coord.container = SimpleNamespace(
        user_profile=profile,
        memory_service=None,
        canonical_memory_integration=None,
        supabase_client=None,
    )
    confirmed: list[bool] = []
    start = time.monotonic()
    eligible = await asyncio.wait_for(
        coord._compute_personalization_eligible(
            "11111111-1111-4111-8111-111111111111", confirmed
        ),
        timeout=10,
    )
    elapsed = time.monotonic() - start
    assert eligible is True, "failed probe must stay conservative (eligible)"
    assert elapsed < 2.0, f"probe was not bounded at 0.2 s (took {elapsed:.2f} s)"


def test_thread_join_blocks_until_worker_finishes():
    """A real blocking join: elapsed covers the worker's 0.3 s + verdict set."""
    box: dict = {}

    def _worker():
        time.sleep(0.3)
        box["verdict"] = True

    thread = threading.Thread(target=_worker, daemon=True, name="slice-d-join-proof")
    start = time.monotonic()
    thread.start()
    thread.join(timeout=5.0)  # bounded join, never bare join()
    elapsed = time.monotonic() - start
    assert not thread.is_alive(), "worker still alive after a 5 s bounded join"
    assert elapsed >= 0.25, (
        f"join returned in {elapsed:.3f} s without waiting for the worker"
    )
    assert box.get("verdict") is True


def test_answerability_join_waits_for_slow_gate_worker(monkeypatch):
    """Slow (0.5 s) YES gate through ``FirstPersonPipeline.execute``: served,
    not indeterminate-abstained, and the wall clock proves the join waited."""
    import hashlib as _h

    from app.config import settings
    from services.first_person_pipeline import (
        _ANSWERABILITY_SYSTEM_PROMPT,
        FirstPersonPipeline,
    )

    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", True)
    monkeypatch.setattr(settings, "first_person_relevance_gate_enabled", False)
    monkeypatch.setattr(settings, "first_person_llm_rerank_enabled", False)
    monkeypatch.setattr(settings, "first_person_content_quality_gate_enabled", False)

    text = (
        "Suffering arises from resistance to what is, and the moment you stop resisting, "
        "something shifts within you and peace is already here with you always today."
    )

    class _SlowGateLLM:
        def __init__(self):
            self.answerability_calls = 0

        def generate(self, system_prompt="", user_prompt="", **kw):
            if system_prompt == _ANSWERABILITY_SYSTEM_PROMPT:
                self.answerability_calls += 1
                time.sleep(0.5)  # the worker under test: slow but inside budget
                return "YES"
            raise AssertionError("no other LLM call expected with gates off")

    store = MagicMock()
    store.collection = "first_person_v1"
    store.search_hybrid.return_value = [
        {
            "point_id": "v1",
            "video_id": "v1",
            "start_ms": 1000,
            "end_ms": 5000,
            "speaker": "Sri Preethaji",
            "teacher_id": "preethaji",
            "transcript_hash": _h.sha256(text.encode()).hexdigest(),
            "verbatim_text": text,
            "passage_dense": [1.0, 0.0],
            "source_url": "https://youtube.com/watch?v=v1",
        }
    ]
    redis = MagicMock()
    redis.get.return_value = None
    stub = _SlowGateLLM()
    pipeline = FirstPersonPipeline(
        store=store, redis_client=redis, calibration_profile=None, llm_service=stub
    )
    start = time.monotonic()
    res = pipeline.execute(query="What is stillness?", query_dense_vector=[1.0, 0.0])
    elapsed = time.monotonic() - start
    assert stub.answerability_calls == 1
    assert res.status != "abstained", (
        "slow gate must be joined, not raced past into indeterminate abstention"
    )
    assert len(res.citations) == 1
    assert elapsed >= 0.4, (
        f"execute returned in {elapsed:.3f} s; the join did not wait for the gate"
    )


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-q"]))
