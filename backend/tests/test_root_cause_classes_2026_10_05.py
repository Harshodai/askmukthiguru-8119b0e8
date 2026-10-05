"""Root-cause class regressions (2026-10-05, Manus traceability pass).

Each test drives the real function with the failure injected. Classes are
named in docs/audits/manus-traceability-2026-10-05.md and lessons.md.
"""

from __future__ import annotations

import hashlib
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.pipeline.stages import first_person_bridge as bridge_module
from app.pipeline.stages.context import PipelineContext
from app.pipeline.stages.doctrine_cache_stage import DoctrineCacheStage
from app.pipeline.stages.first_person_bridge import FirstPersonBridgeStage
from services.first_person_pipeline import FirstPersonPipeline, load_calibration_profile

_TEXT = (
    "Suffering arises from resistance to what is. The moment you stop resisting, "
    "something shifts within you, not an escape, but a recognition of the truth."
)
_HASH = hashlib.sha256(_TEXT.encode("utf-8")).hexdigest()


def _clip(**over):
    base = {
        "point_id": "p1",
        "video_id": "vid_abc",
        "title": "Why we suffer",
        "start_ms": 65000,
        "end_ms": 75000,
        "duration_ms": 600000,
        "speaker": "Sri Preethaji",
        "teacher_id": "preethaji",
        "transcript_hash": _HASH,
        "verbatim_text": _TEXT,
        "passage_dense": [1.0, 0.0],
        "source_url": "https://youtube.com/watch?v=vid_abc",
        "caption_status": "auto_transcript",
    }
    base.update(over)
    return base


def _pipeline(clips, profile=None, cached=None):
    store = MagicMock()
    store.collection = "first_person_v1"
    store.search_hybrid.return_value = clips
    store.points_servable.return_value = True
    redis = MagicMock()
    redis.get.return_value = json.dumps(cached) if cached is not None else None
    return FirstPersonPipeline(store=store, redis_client=redis, calibration_profile=profile), redis


# ---------------------------------------------------------------------------
# Class: a cache that ignores a bypass flag
# ---------------------------------------------------------------------------


def test_fp_exact_cache_honours_cache_bypass():
    pipe, redis = _pipeline([_clip()])
    pipe.execute(query="What causes suffering?", query_dense_vector=[1.0, 0.0], cache_bypass=True)
    redis.get.assert_not_called()
    redis.set.assert_not_called()
    # control: without the flag the cache is read and written
    pipe.execute(query="What causes suffering?", query_dense_vector=[1.0, 0.0])
    assert redis.get.called and redis.set.called


def _bridge_ctx(**over):
    container = MagicMock()
    container.guardrails = AsyncMock()
    container.guardrails.check_output.return_value = {"blocked": False, "reason": None}
    container.embedding = AsyncMock()
    container.embedding.encode_single_full_async.return_value = {
        "dense": [0.0] * int(settings.embedding_dimension),
        "sparse": {},
    }
    container.serene_mind = None
    container.translation = None
    ctx = PipelineContext(
        container=container,
        coordinator=MagicMock(),
        request=MagicMock(),
        user_msg="what is the beautiful state?",
        preferred_lang="en",
        is_indic=False,
        trace_id="t-rc",
        start_time=time.time(),
        state={"user_msg_en": "what is the beautiful state?"},
    )
    for k, v in over.items():
        setattr(ctx, k, v)
    return ctx


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "flags,expected",
    [({}, False), ({"cache_bypass": True}, True), ({"incognito": True}, True)],
)
async def test_bridge_passes_cache_bypass_and_incognito_to_fp_cache(monkeypatch, flags, expected):
    monkeypatch.setattr(settings, "first_person_chat_bridge_enabled", True)
    monkeypatch.setattr(settings, "first_person_route_enabled", True)
    monkeypatch.setattr(settings, "first_person_mode", "retrieval_only")
    fp = MagicMock()
    fp.execute = MagicMock(
        return_value=MagicMock(status="abstained", is_direct_answer=False, citations=[])
    )
    monkeypatch.setattr(bridge_module, "_fp_pipeline", lambda c: fp)
    await FirstPersonBridgeStage().run(_bridge_ctx(**flags))
    assert fp.execute.call_args.kwargs["cache_bypass"] is expected


@pytest.mark.asyncio
@pytest.mark.parametrize("flags", [{"cache_bypass": True}, {"incognito": True}])
async def test_doctrine_cache_honours_bypass_flags(monkeypatch, flags):
    monkeypatch.setattr(settings, "doctrine_cache_enabled", True)
    ctx = _bridge_ctx(**flags)
    ctx.container.doctrine_cache = MagicMock()
    assert await DoctrineCacheStage().run(ctx) is None
    ctx.container.doctrine_cache.lookup.assert_not_called()


# ---------------------------------------------------------------------------
# Class: a cache read placed before a safety gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_doctrine_cache_never_answers_a_crisis_message(monkeypatch):
    monkeypatch.setattr(settings, "doctrine_cache_enabled", True)
    msg = "I want to end my life, what is the beautiful state?"
    ctx = _bridge_ctx(user_msg=msg, state={"user_msg_en": msg})
    ctx.container.doctrine_cache = MagicMock()
    assert await DoctrineCacheStage().run(ctx) is None
    ctx.container.doctrine_cache.lookup.assert_not_called()


def test_fp_route_cache_hit_cannot_skip_the_topic_rail(monkeypatch):
    """A clip cached for a question that a newer safety pattern now redirects
    must not be served from the route: the cache is read after the rail."""
    from app.api import first_person as fp_api
    from app.dependencies import get_container_async
    from app.main import app

    monkeypatch.setattr(settings, "first_person_mode", "retrieval_only")
    monkeypatch.setattr(settings, "first_person_route_enabled", True)
    q = "My partner abuses me; should I call and apologize?"
    stale = {
        "answer_text": f'"{_TEXT}"',
        "citations": [{"verbatim_text": _TEXT, "speaker": "Sri Preethaji"}],
        "status": "success",
        "is_direct_answer": True,
    }
    pipe, redis = _pipeline([_clip()], cached=stale)

    class _C:
        embedding = AsyncMock()
        guardrails = AsyncMock()

    _C.embedding.encode_single_full_async.return_value = {"dense": [1.0, 0.0], "sparse": {}}
    _C.guardrails.check_output.return_value = {"blocked": False}
    _C.translation = None
    app.dependency_overrides[get_container_async] = lambda: _C()
    try:
        with patch.object(fp_api, "_pipeline", lambda *a, **k: pipe):
            resp = TestClient(app).post("/api/first-person/query", json={"query": q})
    finally:
        app.dependency_overrides.pop(get_container_async, None)
    data = resp.json()
    assert data["status"] == "crisis_redirect"
    assert data["citations"] == []
    redis.get.assert_not_called()


# ---------------------------------------------------------------------------
# Class: a gate that fails open (output rail on the first-person route)
# ---------------------------------------------------------------------------


def _route_with_rail(monkeypatch, rail):
    from app.api import first_person as fp_api
    from app.dependencies import get_container_async
    from app.main import app

    monkeypatch.setattr(settings, "first_person_mode", "retrieval_only")
    monkeypatch.setattr(settings, "first_person_route_enabled", True)
    pipe, _ = _pipeline([_clip()])

    class _C:
        embedding = AsyncMock()
        guardrails = rail

    _C.embedding.encode_single_full_async.return_value = {"dense": [1.0, 0.0], "sparse": {}}
    _C.translation = None
    app.dependency_overrides[get_container_async] = lambda: _C()
    try:
        with patch.object(fp_api, "_pipeline", lambda *a, **k: pipe):
            return (
                TestClient(app)
                .post("/api/first-person/query", json={"query": "What causes suffering?"})
                .json()
            )
    finally:
        app.dependency_overrides.pop(get_container_async, None)


class _Rail:
    def __init__(self, verdict=None, exc=None):
        self.verdict, self.exc = verdict, exc

    async def check_output(self, _text):
        if self.exc:
            raise self.exc
        return self.verdict


@pytest.mark.parametrize(
    "rail",
    [
        None,
        _Rail(exc=RuntimeError("rail down")),
        _Rail(verdict={"blocked": True, "reason": "x"}),
        _Rail(verdict="garbage"),
    ],
    ids=["missing", "raises", "blocked", "malformed"],
)
def test_fp_route_output_rail_fails_closed(monkeypatch, rail):
    data = _route_with_rail(monkeypatch, rail)
    assert data["status"] == "abstained"
    assert data["citations"] == []


def test_fp_route_output_rail_pass_serves_clip(monkeypatch):
    data = _route_with_rail(monkeypatch, _Rail(verdict={"blocked": False}))
    assert data["citations"] and data["status"] == "weak_match"


# ---------------------------------------------------------------------------
# Class: a label stronger than its evidence (uncalibrated "direct answer")
# ---------------------------------------------------------------------------

_DEMOTED = {"threshold": 0.45, "score_kind": "cosine", "claims": "none"}


def test_demoted_profile_never_earns_direct_by_default(tmp_path):
    p = tmp_path / "demoted.json"
    p.write_text(json.dumps(_DEMOTED))
    assert load_calibration_profile(str(p), "first_person_v7") is None


def test_shipped_v7_profile_is_not_loaded_by_default():
    store = MagicMock()
    store.collection = "first_person_v7"
    assert FirstPersonPipeline(store=store, redis_client=None)._profile is None


def test_demoted_profile_is_explicit_owner_opt_in(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "first_person_uncalibrated_direct_enabled", True)
    p = tmp_path / "demoted.json"
    p.write_text(json.dumps(_DEMOTED))
    assert load_calibration_profile(str(p), "first_person_v7")["threshold"] == 0.45


def test_topic_keyword_in_question_does_not_raise_confidence():
    """The removed +0.1 keyword boost let 'suffering' in the QUESTION push a
    0.85 clip over a 0.9 fitted threshold."""
    profile = {
        "threshold": 0.9,
        "score_kind": "dense_cosine",
        "n": 400,
        "ucb_risk": 0.01,
        "target_risk": 0.01,
        "collection": "first_person_v1",
        "fitted_at": "2026-10-05",
    }
    clip = _clip(passage_dense=[0.85, (1 - 0.85**2) ** 0.5])
    pipe, _ = _pipeline([clip], profile=profile)
    res = pipe.execute(query="What is suffering and the ego?", query_dense_vector=[1.0, 0.0])
    assert res.is_direct_answer is False and res.status == "weak_match"
    assert res.citations[0]["confidence"] == pytest.approx(0.85, abs=1e-6)
