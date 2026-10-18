"""Slice D — personalize end-to-end: coordinator verdict drives the stage gate.

The fixtures must NOT bypass the gate: ``personal_context_confirmed`` is
derived from ``PipelineCoordinator._compute_personalization_eligible`` (the
real pre-stage probe, bounded by its internal 0.2 s ``wait_for``) exactly as
``PipelineCoordinator.execute`` derives it — never hand-set to force a path.

Non-tautology notes:
- Denied case: the clip store is a raising stub. A decline BEFORE the lookup
  never touches it (no raise); a gate bypass would explode. The
  ``route_decision`` must be the ``no_graph`` decline with zero citations.
- Admitted case: a profile WITH memories confirms context, the stage reaches
  the store (called once with the requested ref), and the turn passes through
  with the server-looked-up clip stashed — proving the gate, not the
  fixture, decides.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

_VIDEO_ID = "dQw4w9WgXcQ"  # 11-char YouTube id shape (synthetic test value)
_CLIP_TEXT = (
    "Awareness sees the movement of thought without following it, and in "
    "that seeing the mind grows still on its own."
)
_UID = "11111111-1111-4111-8111-111111111111"


def _clip_payload(**overrides) -> dict:
    payload = {
        "point_id": "test-point-1",
        "video_id": _VIDEO_ID,
        "start_ms": 99_000,
        "end_ms": 129_000,
        "speaker": "Sri Preethaji",
        "teacher_id": "preethaji",
        "verbatim_text": _CLIP_TEXT,
        "source_url": f"https://www.youtube.com/watch?v={_VIDEO_ID}",
        "title": "Synthetic test discourse",
    }
    payload.update(overrides)
    payload.setdefault(
        "transcript_hash",
        hashlib.sha256(payload["verbatim_text"].encode("utf-8")).hexdigest(),
    )
    return payload


def _request():
    from app.schemas import ChatRequest

    return ChatRequest(
        messages=[],
        user_message="Please personalize this teaching for me.",
        personalize_teaching={"video_id": _VIDEO_ID, "timestamp_seconds": 99},
    )


def _coordinator(profile_memories, memory_core=None):
    from app.pipeline.pipeline_coordinator import PipelineCoordinator

    coord = PipelineCoordinator.__new__(PipelineCoordinator)
    profile = MagicMock()
    profile.get_recent_memories = AsyncMock(return_value=profile_memories)
    memory_service = MagicMock()
    memory_service.get_core = AsyncMock(return_value=memory_core)
    coord.container = SimpleNamespace(
        user_profile=profile,
        memory_service=memory_service,
        canonical_memory_integration=None,
        supabase_client=None,
    )
    return coord


def _ctx_from_coordinator_verdict(request, eligible: bool, confirmed: list):
    """Build ctx the way PipelineCoordinator.execute does — no hand-set flags."""
    from app.pipeline.stages.context import PipelineContext

    return PipelineContext(
        container=MagicMock(),
        coordinator=MagicMock(),
        request=request,
        user_msg="Please personalize this teaching for me.",
        preferred_lang="en",
        trace_id="trace-slice-d-e2e",
        start_time=time.time(),
        state={"user_msg_en": "Please personalize this teaching for me."},
        user_id=_UID,
        incognito=False,
        personalization_eligible=eligible,
        personal_context_confirmed=bool(confirmed) and True,
    )


async def _probe(ctx_request, coord) -> tuple[bool, list]:
    confirmed: list[bool] = []
    eligible = await asyncio.wait_for(
        coord._compute_personalization_eligible(_UID, confirmed), timeout=10
    )
    return eligible, confirmed


@pytest.mark.asyncio
async def test_coordinator_denied_ctx_declines_before_store_lookup(monkeypatch):
    """Empty memory sources -> coordinator denies -> stage declines no_graph
    WITHOUT touching the clip store (raising stub proves pre-lookup exit)."""
    from app.pipeline.stages import personalize_stage as stage_module
    from app.pipeline.stages.personalize_stage import PersonalizeStage

    coord = _coordinator(profile_memories=[], memory_core=None)
    eligible, confirmed = await _probe(_request(), coord)
    assert eligible is False and confirmed == []

    def _raising_store():
        raise AssertionError("store must not be reached on a coordinator-denied turn")

    monkeypatch.setattr(stage_module, "_store_for_request", _raising_store)
    ctx = _ctx_from_coordinator_verdict(_request(), eligible, confirmed)
    result = await asyncio.wait_for(PersonalizeStage().run(ctx), timeout=10)
    assert result is not None
    assert result.route_decision == "personalize_declined_no_graph"
    assert result.citations == []
    assert "personalize_clip" not in ctx.state


@pytest.mark.asyncio
async def test_coordinator_confirmed_ctx_reaches_store_lookup(monkeypatch):
    """A memory source WITH data -> coordinator confirms -> stage performs
    the server-side lookup and passes the turn through with the clip stashed."""
    from app.pipeline.stages import personalize_stage as stage_module
    from app.pipeline.stages.personalize_stage import PersonalizeStage

    coord = _coordinator(profile_memories=[{"m": 1}], memory_core=None)
    eligible, confirmed = await _probe(_request(), coord)
    assert eligible is True and confirmed == [True]

    store = MagicMock()
    store.get_clip_by_video_and_start.return_value = _clip_payload()
    monkeypatch.setattr(stage_module, "_store_for_request", lambda: store)
    ctx = _ctx_from_coordinator_verdict(_request(), eligible, confirmed)
    result = await asyncio.wait_for(PersonalizeStage().run(ctx), timeout=10)
    assert result is None, "a confirmed turn must pass through, not decline"
    store.get_clip_by_video_and_start.assert_called_once()
    stashed = ctx.state.get("personalize_clip")
    assert stashed is not None and stashed["verbatim_text"] == _CLIP_TEXT


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-q"]))
