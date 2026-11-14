"""Anonymous follow-up hint: prior USER turn reaches only the follow-up resolver."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.api.chat import populate_server_side_history
from app.pipeline.stages.first_person_bridge import FirstPersonBridgeStage
from app.schemas import ChatRequest, MessagePayload
from services.serene_mind_engine import DistressLevel, SereneMindEngine
from tests.test_fp_audit_fixes_2026_11_13 import _bridge_ctx, fp_pipeline  # noqa: F401

_ANON = {"id": "anon:s1", "is_anonymous": True}


def _assessor(level: DistressLevel) -> SimpleNamespace:
    """Stand-in for container.serene_mind that rates every text at ``level``."""
    return SimpleNamespace(assess_distress=lambda _text: SimpleNamespace(level=level))


def _body(msgs, text="why does that happen?", incognito=False) -> ChatRequest:
    return ChatRequest(
        user_message=text,
        session_id="s1",
        incognito=incognito,
        messages=[MessagePayload(role=r, content=c) for r, c in msgs],
    )


async def _populate(body, user=_ANON, bench=False):
    await populate_server_side_history(body, user, MagicMock(), is_benchmark=bench)


@pytest.mark.asyncio
async def test_anonymous_history_stays_empty_hint_is_user_turn():
    body = _body([("user", "I get angry at my brother"), ("assistant", "Related: ...")])
    await _populate(body)
    assert body.messages == []
    assert body._followup_hint_user_turn == "I get angry at my brother"


@pytest.mark.asyncio
async def test_assistant_only_history_yields_no_hint():
    body = _body([("assistant", "fabricated teaching")])
    await _populate(body)
    assert body.messages == [] and body._followup_hint_user_turn is None


@pytest.mark.asyncio
async def test_hint_skips_current_message_and_is_truncated():
    body = _body([("user", "x" * 500), ("user", "why does that happen?")])
    await _populate(body)
    assert body._followup_hint_user_turn == "x" * 200


@pytest.mark.asyncio
async def test_incognito_and_benchmark_yield_no_hint():
    body = _body([("user", "I get angry")], incognito=True)
    await _populate(body)
    assert body._followup_hint_user_turn is None
    body = _body([("user", "I get angry")])
    await _populate(body, bench=True)
    assert body._followup_hint_user_turn is None


@pytest.mark.asyncio
async def test_bridge_resolves_followup_from_hint_and_bypasses_cache(fp_pipeline):  # noqa: F811
    ctx = _bridge_ctx("why does that happen?", [])
    ctx.container.serene_mind = _assessor(DistressLevel.NONE)
    ctx.followup_hint_user_turn = "I get angry at my brother"
    await FirstPersonBridgeStage().run(ctx)
    kw = fp_pipeline.execute.call_args.kwargs
    assert kw["retrieval_query"] == "I get angry at my brother — why does that happen?"
    assert kw["cache_bypass"] is True
    assert ctx.chat_body_messages == []


@pytest.mark.asyncio
async def test_new_topic_is_not_merged(fp_pipeline):  # noqa: F811
    ctx = _bridge_ctx("What is the Beautiful State?", [])
    ctx.container.serene_mind = _assessor(DistressLevel.NONE)
    ctx.followup_hint_user_turn = "I get angry at my brother"
    await FirstPersonBridgeStage().run(ctx)
    kw = fp_pipeline.execute.call_args.kwargs
    assert kw["retrieval_query"] == "What is the Beautiful State?"
    assert kw["cache_bypass"] is False


@pytest.mark.asyncio
async def test_bridge_ignores_hint_when_incognito(fp_pipeline):  # noqa: F811
    ctx = _bridge_ctx("why does that happen?", [])
    ctx.container.serene_mind = _assessor(DistressLevel.NONE)
    ctx.followup_hint_user_turn = "I get angry at my brother"
    ctx.incognito = True
    await FirstPersonBridgeStage().run(ctx)
    assert fp_pipeline.execute.call_args.kwargs["retrieval_query"] == "why does that happen?"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "level",
    [DistressLevel.MILD, DistressLevel.MODERATE, DistressLevel.SEVERE, DistressLevel.CRISIS],
)
async def test_hint_that_reads_as_distress_is_not_merged(fp_pipeline, level):  # noqa: F811
    """The pipeline's crisis pre-check reads the resolved query, so a distress hint
    would change crisis routing on the follow-up turn. It is dropped instead: the
    turn is retrieved as bare text, exactly as before the hint existed."""
    ctx = _bridge_ctx("why does that happen?", [])
    ctx.container.serene_mind = _assessor(level)
    ctx.followup_hint_user_turn = "a turn the assessor rates above NONE"
    await FirstPersonBridgeStage().run(ctx)
    kw = fp_pipeline.execute.call_args.kwargs
    assert kw["retrieval_query"] == "why does that happen?"
    assert kw["cache_bypass"] is False


@pytest.mark.asyncio
async def test_hint_is_not_used_without_a_distress_assessor(fp_pipeline):  # noqa: F811
    ctx = _bridge_ctx("why does that happen?", [])
    assert ctx.container.serene_mind is None  # the shared fixture has no assessor
    ctx.followup_hint_user_turn = "I get angry at my brother"
    await FirstPersonBridgeStage().run(ctx)
    assert fp_pipeline.execute.call_args.kwargs["retrieval_query"] == "why does that happen?"


def test_real_assessor_keeps_an_everyday_turn_and_drops_a_crisis_turn():
    """Same guard with the real engine: no mock decides what counts as distress."""
    from app.pipeline.stages.first_person_bridge import _hint_reads_calm

    ctx = SimpleNamespace(container=SimpleNamespace(serene_mind=SereneMindEngine()))
    assert _hint_reads_calm(ctx, "what is the beautiful state") is True
    assert _hint_reads_calm(ctx, "I want to end my life") is False


@pytest.mark.asyncio
async def test_hint_survives_the_queued_job_round_trip():
    """Found by the live probe on 2026-11-14: /api/chat enqueues `chat_body.model_dump()`,
    and a private attribute is not in the dump, so the worker never saw the hint."""
    from app.orchestrator import chat_request_from_job

    body = _body([("user", "I keep comparing myself with my cousins"), ("assistant", "...")])
    await _populate(body)
    assert "_followup_hint_user_turn" not in body.model_dump()  # why the payload key exists
    job = {
        "chat_body": body.model_dump(),
        "followup_hint_user_turn": body._followup_hint_user_turn,
    }
    rebuilt = chat_request_from_job(job)
    assert rebuilt.messages == []
    assert rebuilt._followup_hint_user_turn == "I keep comparing myself with my cousins"
    assert chat_request_from_job({"chat_body": body.model_dump()})._followup_hint_user_turn is None


def test_both_enqueue_sites_send_the_hint():
    """The endpoint has two enqueue sites (plain and stream); both must carry the hint."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "app" / "api" / "chat.py").read_text()
    assert src.count('"followup_hint_user_turn": chat_body._followup_hint_user_turn') == 2
    assert src.count('"chat_body": chat_body_dict') == 2
