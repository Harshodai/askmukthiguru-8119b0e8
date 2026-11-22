"""T1-10 (MEM-003): emotional-history reads / course assignment need active consent."""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import orchestrator_utils as utils
from app.config import settings
from app.schemas import ChatRequest, MessagePayload


def _container(consent):
    outbox = SimpleNamespace(active_consent=AsyncMock(return_value=consent))
    memory_service = SimpleNamespace(get_episodic_memories=AsyncMock(return_value=[]))
    profile = SimpleNamespace(get_recent_memories=AsyncMock(return_value=[]))
    return SimpleNamespace(
        memory_outbox=outbox,
        memory_service=memory_service,
        user_profile=profile,
        supabase_client=MagicMock(),
    )


async def _run_prepare(container, monkeypatch):
    monkeypatch.setattr(settings, "proactive_course_assignment_enabled", True)
    body = SimpleNamespace(
        user_message="hello",
        messages=[],
        session_id=None,
        incognito=False,
        conversation_summary="",
    )
    assign = AsyncMock(return_value=None)
    with (
        patch.object(
            utils, "detect_and_prepare_language_info", return_value=(None, "en", False, False)
        ),
        patch.object(utils, "prepare_user_memory", new=AsyncMock(return_value=("", [], None, ""))),
        patch("services.healing_course_service.maybe_assign_healing_course", new=assign),
    ):
        # Signed-in user: the third argument is preferred_lang and `user` carries the id;
        # an anonymous call would skip the block and make these assertions vacuous.
        await utils.prepare_request_state(container, body, "en", user={"id": str(uuid.uuid4())})
        await asyncio.sleep(0.05)  # let the background task run
    return assign


@pytest.mark.asyncio
async def test_no_consent_no_read_and_no_write(monkeypatch):
    c = _container(consent=None)
    assign = await _run_prepare(c, monkeypatch)
    c.memory_service.get_episodic_memories.assert_not_awaited()
    c.user_profile.get_recent_memories.assert_not_awaited()
    assign.assert_not_awaited()


@pytest.mark.asyncio
async def test_consent_keeps_current_behaviour(monkeypatch):
    c = _container(consent={"granted": True})
    assign = await _run_prepare(c, monkeypatch)
    c.memory_service.get_episodic_memories.assert_awaited()
    assign.assert_awaited()


@pytest.mark.asyncio
async def test_consent_lookup_error_fails_closed():
    c = _container(consent={"granted": True})
    c.memory_outbox.active_consent = AsyncMock(side_effect=RuntimeError("db down"))
    assert await utils.has_active_memory_consent(c, "u") is False
    assert await utils.has_active_memory_consent(SimpleNamespace(), "u") is False


@pytest.mark.asyncio
async def test_proactive_serene_mind_needs_consent():
    from app.pipeline.stages.distress_stage import DistressStage
    from services.serene_mind_engine import DistressAssessment, DistressLevel

    proactive = DistressAssessment(
        level=DistressLevel.MODERATE,
        confidence=0.8,
        detected_signals=["x"],
        language_detected="en",
        recommended_response_type="meditation",
    )
    profile = MagicMock()
    profile.get_last_meditation_session = AsyncMock(return_value=None)
    serene = MagicMock()
    serene.analyze_distress_trend = AsyncMock(return_value=proactive)
    serene.get_response.return_value = "optional"

    for consent, expect in ((None, False), ({"granted": True}, True)):
        serene.analyze_distress_trend.reset_mock()
        container = SimpleNamespace(
            serene_mind=serene,
            user_profile=profile,
            memory_outbox=SimpleNamespace(active_consent=AsyncMock(return_value=consent)),
        )
        ctx = SimpleNamespace(container=container)
        out = await DistressStage()._maybe_trigger_proactive_serene_mind(
            ctx, proactive, "u", SimpleNamespace(last_serene_mind_at=0), {}
        )
        assert out["triggered"] is expect
        assert serene.analyze_distress_trend.await_count == (1 if expect else 0)


@pytest.mark.asyncio
async def test_anonymous_identity_skips_the_uuid_consent_lookup():
    """`anon:<payload>` ids cannot own a receipt; the uuid column must never see them."""
    c = _container(consent={"granted": True})
    assert await utils.has_active_memory_consent(c, "anon:eyJhbGciOi.payload") is False
    c.memory_outbox.active_consent.assert_not_awaited()


@pytest.mark.asyncio
async def test_temporary_request_drops_memory_and_summary_context(monkeypatch):
    """Temporary Chat must not read or carry durable personalization context."""
    body = ChatRequest(
        user_message="TEMPORARY-MARKER-DO-NOT-PERSIST",
        messages=[
            MessagePayload(
                role="user",
                content="A prior private turn that must not become durable context",
            )
        ],
        conversation_summary="A private summary that must be ignored",
        incognito=True,
    )
    container = SimpleNamespace()
    memory_mock = AsyncMock(
        return_value=("durable memory", [{"level": "old"}], {"name": "profile"}, "evidence")
    )
    monkeypatch.setattr(
        utils, "detect_and_prepare_language_info", lambda *_args: (None, "en", False, False)
    )
    monkeypatch.setattr(utils, "prepare_user_memory", memory_mock)
    monkeypatch.setattr(settings, "proactive_course_assignment_enabled", True)

    state = await utils.prepare_request_state(
        container,
        body,
        "en",
        user={"id": str(uuid.uuid4())},
    )

    assert state["memory_context"] == ""
    assert state["canonical_memory_evidence"] == ""
    assert state["distress_history"] == []
    assert state["user_profile"] is None
    assert state["conversation_summary"] == ""
    memory_mock.assert_not_awaited()
