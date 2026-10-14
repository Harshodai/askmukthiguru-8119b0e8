"""T-B14 backend half — explicit "personalize this teaching" opt-in.

Default answer path is first-person-only; the general generating pipeline may
run for a turn ONLY when the request carries a validated ``personalize_teaching``
ref AND the seeker is signed in, non-incognito, and has a personal knowledge
graph (memory). The backend looks the served clip up itself (video_id +
timestamp with a small tolerance) and never trusts client-provided text.

All tests are host-side with mocks only: no Qdrant, no Neo4j, no LLM calls.
"""

from __future__ import annotations

import hashlib
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

_VIDEO_ID = "dQw4w9WgXcQ"  # 11-char YouTube id shape (synthetic test value)
_CLIP_TEXT = (
    "Awareness sees the movement of thought without following it, and in "
    "that seeing the mind grows still on its own."
)


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
    # A real stored clip carries the sha256 of its own text; the stage applies
    # the serve-time integrity gate, so the fixture must be a servable clip.
    payload.setdefault(
        "transcript_hash",
        hashlib.sha256(payload["verbatim_text"].encode("utf-8")).hexdigest(),
    )
    return payload


def _request(**overrides) -> object:
    from app.schemas import ChatRequest

    base = {
        "messages": [],
        "user_message": "Please personalize this teaching for me.",
    }
    base.update(overrides)
    return ChatRequest(**base)


def _ctx(request, *, user_id="11111111-1111-4111-8111-111111111111", **overrides) -> object:
    from app.pipeline.stages.context import PipelineContext

    params = {
        "container": MagicMock(),
        "coordinator": MagicMock(),
        "request": request,
        "user_msg": "Please personalize this teaching for me.",
        "preferred_lang": "en",
        "trace_id": "trace-personalize-test",
        "start_time": time.time(),
        "state": {"user_msg_en": "Please personalize this teaching for me."},
        "user_id": user_id,
        "incognito": False,
        "personalization_eligible": True,
    }
    params.update(overrides)
    return PipelineContext(**params)


# ---------------------------------------------------------------------------
# 1. Request schema
# ---------------------------------------------------------------------------


def test_personalize_ref_accepted_when_well_formed():
    from app.schemas import ChatRequest

    body = ChatRequest(
        messages=[],
        user_message="Please personalize this teaching for me.",
        personalize_teaching={"video_id": _VIDEO_ID, "timestamp_seconds": 99},
    )
    assert body.personalize_teaching is not None
    assert body.personalize_teaching.video_id == _VIDEO_ID
    assert body.personalize_teaching.timestamp_seconds == 99


def test_personalize_ref_absent_by_default():
    from app.schemas import ChatRequest

    body = ChatRequest(messages=[], user_message="how do I find inner peace?")
    assert body.personalize_teaching is None


def test_personalize_ref_rejects_negative_timestamp():
    from app.schemas import ChatRequest

    with pytest.raises(ValidationError):
        ChatRequest(
            messages=[],
            user_message="x",
            personalize_teaching={"video_id": _VIDEO_ID, "timestamp_seconds": -1},
        )


def test_personalize_ref_rejects_nan_timestamp():
    from app.schemas import ChatRequest

    with pytest.raises(ValidationError):
        ChatRequest(
            messages=[],
            user_message="x",
            personalize_teaching={"video_id": _VIDEO_ID, "timestamp_seconds": float("nan")},
        )


def test_personalize_ref_rejects_infinite_timestamp():
    from app.schemas import ChatRequest

    with pytest.raises(ValidationError):
        ChatRequest(
            messages=[],
            user_message="x",
            personalize_teaching={"video_id": _VIDEO_ID, "timestamp_seconds": float("inf")},
        )


def test_personalize_ref_rejects_malformed_video_id():
    from app.schemas import ChatRequest

    with pytest.raises(ValidationError):
        ChatRequest(
            messages=[],
            user_message="x",
            personalize_teaching={"video_id": "not-a-video-id!!", "timestamp_seconds": 3},
        )


# ---------------------------------------------------------------------------
# 2. Gate — no ref means the default path is untouched
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stage_ignores_turns_without_a_ref():
    from app.pipeline.stages.personalize_stage import PersonalizeStage

    ctx = _ctx(_request())
    assert await PersonalizeStage().run(ctx) is None
    assert "personalize_clip" not in ctx.state


@pytest.mark.asyncio
async def test_stage_ignores_mock_shaped_requests():
    """Existing stage tests build ctx with MagicMock requests: a MagicMock
    attribute must never read as an opt-in (same trap as cache_bypass)."""
    from app.pipeline.stages.personalize_stage import PersonalizeStage

    ctx = _ctx(MagicMock())
    assert await PersonalizeStage().run(ctx) is None
    assert "personalize_clip" not in ctx.state


# ---------------------------------------------------------------------------
# 3. Gate — rejections carry a distinct route_decision
# ---------------------------------------------------------------------------


def _ref_kwargs(**overrides) -> dict:
    ref = {"video_id": _VIDEO_ID, "timestamp_seconds": 99}
    ref.update(overrides)
    return {"personalize_teaching": ref}


@pytest.mark.asyncio
async def test_anonymous_seeker_rejected():
    from app.pipeline.stages.personalize_stage import PersonalizeStage

    ctx = _ctx(_request(**_ref_kwargs()), user_id="anonymous")
    result = await PersonalizeStage().run(ctx)
    assert result is not None
    assert result.route_decision.startswith("personalize_declined")
    assert "anonymous" in result.route_decision
    assert result.citations == []


@pytest.mark.asyncio
async def test_signed_anonymous_session_rejected():
    from app.pipeline.stages.personalize_stage import PersonalizeStage

    ctx = _ctx(_request(**_ref_kwargs()), user_id="anon:deadbeef")
    result = await PersonalizeStage().run(ctx)
    assert result is not None
    assert result.route_decision.startswith("personalize_declined")


@pytest.mark.asyncio
async def test_incognito_seeker_rejected():
    from app.pipeline.stages.personalize_stage import PersonalizeStage

    ctx = _ctx(_request(**_ref_kwargs(), incognito=True), incognito=True)
    result = await PersonalizeStage().run(ctx)
    assert result is not None
    assert result.route_decision.startswith("personalize_declined")
    assert "incognito" in result.route_decision


@pytest.mark.asyncio
async def test_seeker_without_graph_rejected(monkeypatch):
    from app.pipeline.stages import personalize_stage as stage_module
    from app.pipeline.stages.personalize_stage import PersonalizeStage

    monkeypatch.setattr(stage_module, "_store_for_request", lambda: MagicMock())
    ctx = _ctx(_request(**_ref_kwargs()), personalization_eligible=False)
    result = await PersonalizeStage().run(ctx)
    assert result is not None
    assert result.route_decision.startswith("personalize_declined")
    assert "no_graph" in result.route_decision


@pytest.mark.asyncio
async def test_unknown_video_rejected(monkeypatch):
    from app.pipeline.stages import personalize_stage as stage_module
    from app.pipeline.stages.personalize_stage import PersonalizeStage

    store = MagicMock()
    store.get_clip_by_video_and_start.return_value = None
    monkeypatch.setattr(stage_module, "_store_for_request", lambda: store)
    ctx = _ctx(_request(**_ref_kwargs(video_id="AAAAAAAAAAA")))
    result = await PersonalizeStage().run(ctx)
    assert result is not None
    assert result.route_decision.startswith("personalize_declined")
    assert "unknown_clip" in result.route_decision
    store.get_clip_by_video_and_start.assert_called_once()


@pytest.mark.asyncio
async def test_timestamp_far_from_any_clip_rejected(monkeypatch):
    from app.pipeline.stages import personalize_stage as stage_module
    from app.pipeline.stages.personalize_stage import PersonalizeStage

    store = MagicMock()
    store.get_clip_by_video_and_start.return_value = None
    monkeypatch.setattr(stage_module, "_store_for_request", lambda: store)
    ctx = _ctx(_request(**_ref_kwargs(timestamp_seconds=9999)))
    result = await PersonalizeStage().run(ctx)
    assert result is not None
    assert "unknown_clip" in result.route_decision


@pytest.mark.asyncio
async def test_decline_is_distinct_from_first_person_abstain(monkeypatch):
    from app.pipeline.stages import personalize_stage as stage_module
    from app.pipeline.stages.personalize_stage import PersonalizeStage

    store = MagicMock()
    store.get_clip_by_video_and_start.return_value = None
    monkeypatch.setattr(stage_module, "_store_for_request", lambda: store)
    ctx = _ctx(_request(**_ref_kwargs()))
    result = await PersonalizeStage().run(ctx)
    assert result is not None
    assert result.route_decision != "first_person_abstain"


# ---------------------------------------------------------------------------
# 4. Happy path — validated turn is marked for the general graph
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_turn_stashes_server_looked_up_clip(monkeypatch):
    from app.pipeline.stages import personalize_stage as stage_module
    from app.pipeline.stages.personalize_stage import PersonalizeStage

    clip = _clip_payload()
    store = MagicMock()
    store.get_clip_by_video_and_start.return_value = clip
    monkeypatch.setattr(stage_module, "_store_for_request", lambda: store)
    ctx = _ctx(_request(**_ref_kwargs()))
    assert await PersonalizeStage().run(ctx) is None
    stashed = ctx.state.get("personalize_clip")
    assert stashed is not None
    # Looked up server-side: the stored text wins, never client text.
    assert stashed["verbatim_text"] == _CLIP_TEXT
    assert stashed["video_id"] == _VIDEO_ID
    # The lookup used the requested ref (small tolerance applied inside).
    store.get_clip_by_video_and_start.assert_called_once()
    call_args, call_kwargs = store.get_clip_by_video_and_start.call_args
    assert (call_args[0] if call_args else call_kwargs.get("video_id")) == _VIDEO_ID
    assert (call_args[1] if len(call_args) > 1 else call_kwargs.get("timestamp_seconds")) == 99


@pytest.mark.asyncio
async def test_lookup_uses_requested_ref_not_client_text(monkeypatch):
    from app.pipeline.stages import personalize_stage as stage_module
    from app.pipeline.stages.personalize_stage import PersonalizeStage

    seen = {}

    class _Store:
        def get_clip_by_video_and_start(self, video_id, timestamp_seconds, **_kw):
            seen["video_id"] = video_id
            seen["timestamp_seconds"] = timestamp_seconds
            return _clip_payload()

    monkeypatch.setattr(stage_module, "_store_for_request", _Store)
    ctx = _ctx(_request(**_ref_kwargs(timestamp_seconds=99)))
    assert await PersonalizeStage().run(ctx) is None
    assert seen == {"video_id": _VIDEO_ID, "timestamp_seconds": 99}


@pytest.mark.asyncio
async def test_clip_failing_integrity_gate_is_declined(monkeypatch):
    """A stored clip whose text no longer matches its hash is never accepted."""
    from app.pipeline.stages import personalize_stage as stage_module
    from app.pipeline.stages.personalize_stage import PersonalizeStage

    store = MagicMock()
    store.get_clip_by_video_and_start.return_value = _clip_payload(transcript_hash="0" * 64)
    monkeypatch.setattr(stage_module, "_store_for_request", lambda: store)
    ctx = _ctx(_request(**_ref_kwargs()))
    result = await PersonalizeStage().run(ctx)
    assert result is not None
    assert result.route_decision == "personalize_declined_unknown_clip"
    assert "personalize_clip" not in ctx.state


@pytest.mark.asyncio
async def test_non_teacher_speaker_clip_is_declined(monkeypatch):
    from app.pipeline.stages import personalize_stage as stage_module
    from app.pipeline.stages.personalize_stage import PersonalizeStage

    store = MagicMock()
    store.get_clip_by_video_and_start.return_value = _clip_payload(speaker="Host")
    monkeypatch.setattr(stage_module, "_store_for_request", lambda: store)
    ctx = _ctx(_request(**_ref_kwargs()))
    result = await PersonalizeStage().run(ctx)
    assert result is not None
    assert result.route_decision == "personalize_declined_unknown_clip"


@pytest.mark.asyncio
async def test_ref_with_any_other_question_is_declined(monkeypatch):
    """A ref must not unlock the generating graph for an arbitrary question."""
    from app.pipeline.stages import personalize_stage as stage_module
    from app.pipeline.stages.personalize_stage import PersonalizeStage

    store = MagicMock()
    store.get_clip_by_video_and_start.return_value = _clip_payload()
    monkeypatch.setattr(stage_module, "_store_for_request", lambda: store)
    ctx = _ctx(
        _request(**_ref_kwargs(), user_message="What should I do about my marriage?"),
        user_msg="What should I do about my marriage?",
    )
    result = await PersonalizeStage().run(ctx)
    assert result is not None
    assert result.route_decision == "personalize_declined_unexpected_prompt"
    store.get_clip_by_video_and_start.assert_not_called()
    assert "personalize_clip" not in ctx.state


def test_citation_carries_hash_and_clamps_playback_to_video_length():
    from app.pipeline.stages.personalize_stage import build_personalize_citation
    from services.first_person_pipeline import CITATION_PLAYBACK_PAD_S

    clip = _clip_payload(duration_ms=129_100)
    cit = build_personalize_citation(clip)
    assert cit["transcript_hash"] == clip["transcript_hash"]
    assert cit["playback_start_seconds"] == round(99.0 - CITATION_PLAYBACK_PAD_S, 2)
    assert cit["playback_end_seconds"] == 129.1, "must clamp to the video length"
    assert build_personalize_citation(_clip_payload())["playback_end_seconds"] == round(
        129.0 + CITATION_PLAYBACK_PAD_S, 2
    )


@pytest.mark.asyncio
async def test_uncitable_clip_is_declined_before_the_graph_runs(monkeypatch):
    from app.pipeline.stages import personalize_stage as stage_module
    from app.pipeline.stages.personalize_stage import PersonalizeStage

    store = MagicMock()
    store.get_clip_by_video_and_start.return_value = _clip_payload(end_ms=None)
    monkeypatch.setattr(stage_module, "_store_for_request", lambda: store)
    ctx = _ctx(_request(**_ref_kwargs()))
    result = await PersonalizeStage().run(ctx)
    assert result is not None
    assert result.route_decision == "personalize_declined_unknown_clip"


def test_store_lookup_filters_on_eligibility_and_rights():
    """The lookup carries the same serving filter as search_hybrid."""
    from services.first_person_store import FirstPersonStore

    client = MagicMock()
    client.scroll.return_value = ([], None)
    FirstPersonStore(collection="c", client=client).get_clip_by_video_and_start(_VIDEO_ID, 99)
    keys = [c.key for c in client.scroll.call_args.kwargs["scroll_filter"].must]
    assert "first_person_eligible" in keys and "rights_cleared" in keys


def test_store_lookup_huge_finite_timestamp_returns_none():
    from services.first_person_store import FirstPersonStore

    client = MagicMock()
    assert (
        FirstPersonStore(collection="c", client=client).get_clip_by_video_and_start(
            _VIDEO_ID, 1e306
        )
        is None
    )
    client.scroll.assert_not_called()


def test_first_person_router_yields_to_a_valid_personalize_turn(monkeypatch):
    from app.config import settings
    from rag.pipeline_registry import select_pipeline

    monkeypatch.setattr(settings, "first_person_chat_bridge_enabled", True)
    monkeypatch.setattr(settings, "first_person_route_enabled", True)
    monkeypatch.setattr(settings, "first_person_mode", "retrieval_only")
    state = {
        "question": "Please personalize this teaching for me.",
        "personalize_clip": _clip_payload(),
    }
    module = select_pipeline(state)
    assert module is not None
    assert module.name == "general"


def test_first_person_router_still_claims_ordinary_turns(monkeypatch):
    from app.config import settings
    from rag.pipeline_registry import select_pipeline

    monkeypatch.setattr(settings, "first_person_chat_bridge_enabled", True)
    monkeypatch.setattr(settings, "first_person_route_enabled", True)
    monkeypatch.setattr(settings, "first_person_mode", "retrieval_only")
    module = select_pipeline({"question": "how do I find inner peace?"})
    assert module is not None
    assert module.name == "first_person"


# ---------------------------------------------------------------------------
# 5. Store lookup — video + start tolerance, nearest wins
# ---------------------------------------------------------------------------


def _scroll_points(*payloads):
    return [SimpleNamespace(id=p["point_id"], payload=p) for p in payloads], None


def test_store_lookup_matches_floor_second_with_tolerance():
    from services.first_person_store import FirstPersonStore

    store = FirstPersonStore.__new__(FirstPersonStore)
    client = MagicMock()
    # Citation timestamps are floor(start_ms / 1000): 99_400ms serves as t=99s.
    client.scroll.return_value = _scroll_points(_clip_payload(start_ms=99_400))
    store._client = client
    store._collection = "first_person_v8"
    found = store.get_clip_by_video_and_start(_VIDEO_ID, 99)
    assert found is not None
    assert found["verbatim_text"] == _CLIP_TEXT


def test_store_lookup_rejects_distant_start():
    from services.first_person_store import FirstPersonStore

    store = FirstPersonStore.__new__(FirstPersonStore)
    client = MagicMock()
    client.scroll.return_value = _scroll_points(_clip_payload(start_ms=99_000))
    store._client = client
    store._collection = "first_person_v8"
    assert store.get_clip_by_video_and_start(_VIDEO_ID, 9999) is None


def test_store_lookup_returns_none_when_video_unknown():
    from services.first_person_store import FirstPersonStore

    store = FirstPersonStore.__new__(FirstPersonStore)
    client = MagicMock()
    client.scroll.return_value = ([], None)
    store._client = client
    store._collection = "first_person_v8"
    assert store.get_clip_by_video_and_start("AAAAAAAAAAA", 10) is None


def test_store_lookup_picks_nearest_of_several_candidates():
    from services.first_person_store import FirstPersonStore

    store = FirstPersonStore.__new__(FirstPersonStore)
    near = _clip_payload(point_id="near", start_ms=99_200, verbatim_text="NEAR " + _CLIP_TEXT)
    far = _clip_payload(point_id="far", start_ms=99_900, verbatim_text="FAR " + _CLIP_TEXT)
    client = MagicMock()
    client.scroll.return_value = _scroll_points(far, near)
    store._client = client
    store._collection = "first_person_v8"
    found = store.get_clip_by_video_and_start(_VIDEO_ID, 99)
    assert found is not None
    assert found["point_id"] == "near"


# ---------------------------------------------------------------------------
# 6. Happy path through GraphStage — general graph, grounded, labelled
# ---------------------------------------------------------------------------


def _graph_ctx(monkeypatch, clip) -> object:
    from app.pipeline.stages.context import PipelineContext

    container = MagicMock()
    container.user_profile = None
    container.translation = None
    container.guardrails = MagicMock()

    async def _invoke(_state, config=None):
        return {
            "final_answer": "A personalized reflection grounded in the teaching.",
            "intent": "QUERY",
            "citations": [],
            "meditation_step": 0,
            "verification": {"passed": True, "method": "mocked_graph", "citations_verified": False},
            "model_used": "mock-model",
            "model_provider": "mock-provider",
        }

    standard_graph = MagicMock()
    standard_graph.ainvoke = AsyncMock(side_effect=_invoke)
    fast_graph = MagicMock()
    container.standard_graph = standard_graph
    container.fast_graph = fast_graph

    coordinator = MagicMock()

    async def _get_or_run(_key, coro):
        return await coro()

    coordinator.coalescer = MagicMock()
    coordinator.coalescer.get_or_run = AsyncMock(side_effect=_get_or_run)

    request = _request(**_ref_kwargs())
    return PipelineContext(
        container=container,
        coordinator=coordinator,
        request=request,
        user_msg="Please personalize this teaching for me.",
        preferred_lang="en",
        trace_id="trace-personalize-graph",
        start_time=time.time(),
        state={
            "user_msg_en": "Please personalize this teaching for me.",
            "chat_history_en": [],
            "personalize_clip": dict(clip),
        },
        user_id="11111111-1111-4111-8111-111111111111",
        incognito=False,
        personalization_eligible=True,
        preclassified_intent="QUERY",
        detected_query_tier="standard",
    )


@pytest.mark.asyncio
async def test_graph_stage_grounds_labels_and_pins_clip(monkeypatch):
    from app.pipeline.stages.graph_stage import GraphStage
    from app.pipeline.stages.personalize_stage import PERSONALIZED_LABEL

    clip = _clip_payload()
    ctx = _graph_ctx(monkeypatch, clip)
    assert await GraphStage().run(ctx) is None
    # Labelled as personalized (not the teacher's verbatim voice).
    assert PERSONALIZED_LABEL in ctx.final_answer
    # The looked-up clip is pinned as the primary citation.
    assert ctx.citations, "expected the served clip to be pinned as a citation"
    assert ctx.citations[0]["video_id"] == _VIDEO_ID
    assert ctx.citations[0]["verbatim_text"] == _CLIP_TEXT
    # Marked in route metadata for telemetry and review.
    assert ctx.route_metadata.get("personalized_teaching") is True


@pytest.mark.asyncio
async def test_graph_stage_sends_clip_text_to_retrieval(monkeypatch):
    from app.pipeline.stages.graph_stage import GraphStage

    clip = _clip_payload()
    ctx = _graph_ctx(monkeypatch, clip)
    await GraphStage().run(ctx)
    sent_state = ctx.container.standard_graph.ainvoke.call_args[0][0]
    # The general graph retrieves against the looked-up clip text, so the
    # answer is grounded on the served clip rather than the bare prompt.
    assert _CLIP_TEXT in sent_state["question"]
    assert sent_state.get("personalize_clip", {}).get("video_id") == _VIDEO_ID


@pytest.mark.asyncio
async def test_graph_stage_leaves_ordinary_turns_untouched(monkeypatch):
    from app.pipeline.stages.graph_stage import GraphStage
    from app.pipeline.stages.personalize_stage import PERSONALIZED_LABEL

    clip = _clip_payload()
    ctx = _graph_ctx(monkeypatch, clip)
    del ctx.state["personalize_clip"]
    await GraphStage().run(ctx)
    assert PERSONALIZED_LABEL not in ctx.final_answer
    assert ctx.citations == []
    assert ctx.route_metadata.get("personalized_teaching") is not True


# ---------------------------------------------------------------------------
# 7. Cache isolation — different clips must not share a cache entry
# ---------------------------------------------------------------------------


def test_cache_key_covers_the_personalize_ref():
    from app.pipeline.pipeline_coordinator import PipelineCoordinator
    from app.pipeline.stages.personalize_stage import personalize_cache_scope

    coordinator = PipelineCoordinator.__new__(PipelineCoordinator)
    key_plain = coordinator._build_context_aware_cache_key(
        "Please personalize this teaching for me.", "en"
    )
    key_a = coordinator._build_context_aware_cache_key(
        "Please personalize this teaching for me.",
        "en",
        personalize_scope=personalize_cache_scope(
            {"video_id": "dQw4w9WgXcQ", "timestamp_seconds": 99.0}
        ),
    )
    key_b = coordinator._build_context_aware_cache_key(
        "Please personalize this teaching for me.",
        "en",
        personalize_scope=personalize_cache_scope(
            {"video_id": "dQw4w9WgXcQ", "timestamp_seconds": 120.0}
        ),
    )
    assert key_a != key_plain
    assert key_a != key_b


def test_personalize_scope_is_per_seeker_not_per_clip():
    """Review 2026-10-14: the same clip personalized by two seekers must not
    share a cache scope; the user id enters only as a bounded digest."""
    from app.pipeline.pipeline_coordinator import _personalize_scope_for

    ref = {"video_id": "dQw4w9WgXcQ", "timestamp_seconds": 99.0}

    class _Body:
        personalize_teaching = ref

    scope_a = _personalize_scope_for(_Body(), {"id": "seeker-a"})
    scope_b = _personalize_scope_for(_Body(), {"id": "seeker-b"})
    scope_a2 = _personalize_scope_for(_Body(), {"id": "seeker-a"})
    assert scope_a
    assert scope_a2 == scope_a
    assert scope_b != scope_a
    assert "seeker-a" not in scope_a and "seeker-b" not in scope_b
    assert _personalize_scope_for(_Body(), None) != ""
