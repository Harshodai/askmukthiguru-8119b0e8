"""
Integration tests for /api/first-person/query route.
"""

from unittest.mock import create_autospec, patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.dependencies import get_container_async
from app.main import app
from services.embedding_service import EmbeddingService
from services.first_person_pipeline import FirstPersonPipelineResult

client = TestClient(app)


class _PassRail:
    """Output rail that lets the answer through (the route fails closed without one)."""

    async def check_output(self, _text):
        return {"blocked": False, "reason": None}


@pytest.fixture(autouse=True)
def _enable_route(monkeypatch):
    monkeypatch.setattr(settings, "first_person_mode", "retrieval_only")
    monkeypatch.setattr(settings, "first_person_route_enabled", True)
    from app.api.first_person import _pipeline

    _pipeline.cache_clear()  # a pipeline cached by one test must not leak into the next
    yield
    _pipeline.cache_clear()


def test_first_person_route_disabled_by_mode(monkeypatch):
    monkeypatch.setattr(settings, "first_person_mode", "disabled")
    resp = client.post("/api/first-person/query", json={"query": "What is suffering?"})
    assert resp.status_code == 404
    assert "disabled" in resp.json()["detail"]


def test_first_person_route_disabled_by_flag(monkeypatch):
    """(g) flag off -> 404, even when first_person_mode is enabled."""
    monkeypatch.setattr(settings, "first_person_route_enabled", False)
    resp = client.post("/api/first-person/query", json={"query": "What is suffering?"})
    assert resp.status_code == 404


def test_route_calls_real_embedding_method_via_autospec():
    """(b) an autospec'd EmbeddingService rejects a nonexistent method call.

    This is the regression test for the original defect: the old route
    called embedder.embed_query(), which does not exist on EmbeddingService.
    create_autospec raises AttributeError for any method not on the real class.
    """
    mock_embedding = create_autospec(EmbeddingService, instance=True)
    mock_embedding.encode_single_full_async.return_value = {"dense": [0.1] * 1024, "sparse": {}}

    class _FakeContainer:
        embedding = mock_embedding
        guardrails = _PassRail()

    app.dependency_overrides[get_container_async] = lambda: _FakeContainer()
    try:
        with patch("app.api.first_person.FirstPersonPipeline") as mock_pipeline_cls:
            mock_pipeline = mock_pipeline_cls.return_value
            mock_pipeline.execute.return_value = FirstPersonPipelineResult(
                answer_text="ok",
                citations=[],
                status="abstained",
                is_direct_answer=False,
                latency_ms=1.0,
            )
            resp = client.post(
                "/api/first-person/query",
                json={"query": "What is suffering?", "teacher_id": "preethaji"},
            )
        assert resp.status_code == 200
        mock_embedding.encode_single_full_async.assert_called_once_with("What is suffering?")
    finally:
        app.dependency_overrides.pop(get_container_async, None)


def test_route_embedder_failure_is_503():
    mock_embedding = create_autospec(EmbeddingService, instance=True)
    mock_embedding.encode_single_full_async.side_effect = RuntimeError("boom")

    class _FakeContainer:
        embedding = mock_embedding
        guardrails = _PassRail()

    app.dependency_overrides[get_container_async] = lambda: _FakeContainer()
    try:
        resp = client.post("/api/first-person/query", json={"query": "What is suffering?"})
        assert resp.status_code == 503
        assert "boom" not in resp.text
    finally:
        app.dependency_overrides.pop(get_container_async, None)


def test_route_missing_collection_is_503():
    mock_embedding = create_autospec(EmbeddingService, instance=True)

    async def _encode(_text):
        return {"dense": [0.1] * 1024, "sparse": {}}

    mock_embedding.encode_single_full_async.side_effect = _encode

    class _FakeContainer:
        embedding = mock_embedding
        guardrails = _PassRail()

    app.dependency_overrides[get_container_async] = lambda: _FakeContainer()
    try:
        with patch("app.api.first_person.FirstPersonPipeline") as mock_pipeline_cls:
            mock_pipeline = mock_pipeline_cls.return_value
            mock_pipeline.execute.side_effect = RuntimeError("Collection `x` doesn't exist")
            resp = client.post("/api/first-person/query", json={"query": "What is suffering?"})
        assert resp.status_code == 503
        assert "doesn't exist" not in resp.text
        assert resp.json()["detail"] == "First-person retrieval unavailable"
    finally:
        app.dependency_overrides.pop(get_container_async, None)


def test_first_person_route_success():
    mock_embedding = create_autospec(EmbeddingService, instance=True)

    async def _encode(_text):
        return {"dense": [0.1] * 1024, "sparse": {}}

    mock_embedding.encode_single_full_async.side_effect = _encode

    class _FakeContainer:
        embedding = mock_embedding
        guardrails = _PassRail()

    app.dependency_overrides[get_container_async] = lambda: _FakeContainer()
    try:
        with patch("app.api.first_person.FirstPersonPipeline") as mock_pipeline_cls:
            mock_pipeline = mock_pipeline_cls.return_value
            mock_pipeline.execute.return_value = FirstPersonPipelineResult(
                answer_text='"Suffering is resistance to what is."\n— Sri Preethaji (vid1, 10s)',
                citations=[
                    {
                        "video_id": "vid1",
                        "start_ms": 10000,
                        "end_ms": 15000,
                        "timestamp_seconds": 10,
                        "speaker": "Sri Preethaji",
                        "teacher_id": "preethaji",
                        "transcript_hash": "a" * 64,
                        "verbatim_text": "Suffering is resistance to what is.",
                        "source_url": "https://youtube.com/watch?v=vid1",
                        "video_url": "https://youtube.com/watch?v=vid1",
                        "text_snippet": "Suffering is resistance to what is.",
                        "confidence": 0.9,
                        "is_verbatim": True,
                        "provenance_kind": "speech_turn_clip",
                        "caption_status": "auto_transcript",
                    }
                ],
                status="success",
                is_direct_answer=True,
                latency_ms=25.0,
            )
            resp = client.post(
                "/api/first-person/query",
                json={"query": "What is suffering?", "teacher_id": "preethaji"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["is_direct_answer"] is True
        assert len(data["citations"]) == 1
        assert data["citations"][0]["speaker"] == "Sri Preethaji"
        assert data["citations"][0]["timestamp_seconds"] == 10
    finally:
        app.dependency_overrides.pop(get_container_async, None)


def test_first_person_route_rejects_empty_query():
    resp = client.post("/api/first-person/query", json={"query": ""})
    assert resp.status_code == 422  # Pydantic validation error


def test_pipeline_factory_wires_a_real_redis_client_from_settings_url():
    """Regression: the route used to hard-code redis_client=None, so the exact
    cache never ran. redis.from_url() connects lazily -- constructing it here
    must not perform any socket I/O (no event-loop blocking, no live Redis
    write), it only needs to exist so the pipeline's cache calls have somewhere
    to go."""
    import redis as redis_lib

    from app.api.first_person import _pipeline

    pipeline = _pipeline(settings.first_person_collection, None)
    assert pipeline._redis is not None
    assert isinstance(pipeline._redis, redis_lib.Redis)


def test_pipeline_factory_degrades_to_no_cache_when_redis_construction_fails(monkeypatch):
    """A bad REDIS_URL (the only way construction itself can raise) must
    degrade to no cache, never a 500 at request time."""
    import app.api.first_person as first_person_module

    def _boom(*args, **kwargs):
        raise ValueError("bad redis url")

    monkeypatch.setattr(first_person_module.redis, "from_url", _boom)
    first_person_module._pipeline.cache_clear()
    try:
        pipeline = first_person_module._pipeline(settings.first_person_collection, None)
        assert pipeline._redis is None
    finally:
        first_person_module._pipeline.cache_clear()


# --- 2026-09-27: query translation + per-citation gloss ---------------------------

_HI_QUERY = "प्रेम क्या है?"
_CITATION = {
    "point_id": "p1",
    "video_id": "v1",
    "start_ms": 1000,
    "end_ms": 9000,
    "speaker": "Sri Preethaji",
    "verbatim_text": "Love is a state within you.",
}


class _FakeTranslation:
    def __init__(self, delay_s: float = 0.0):
        self.calls = []
        self.delay_s = delay_s

    async def translate_text(self, *, text, source_lang, target_lang):
        import asyncio

        self.calls.append((text, source_lang, target_lang))
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        return {"en": "What is love?", "hi": "प्रेम आपके भीतर की एक अवस्था है।"}[target_lang]


def _route_with(translation, body):
    mock_embedding = create_autospec(EmbeddingService, instance=True)
    mock_embedding.encode_single_full_async.return_value = {"dense": [0.1] * 1024, "sparse": {}}

    class _FakeContainer:
        embedding = mock_embedding
        guardrails = _PassRail()

    _FakeContainer.translation = translation
    app.dependency_overrides[get_container_async] = lambda: _FakeContainer()
    try:
        with patch("app.api.first_person.FirstPersonPipeline") as mock_pipeline_cls:
            mock_pipeline = mock_pipeline_cls.return_value
            mock_pipeline.execute.return_value = FirstPersonPipelineResult(
                answer_text="ok",
                citations=[dict(_CITATION)],
                status="weak_match",
                is_direct_answer=False,
                latency_ms=1.0,
            )
            resp = client.post("/api/first-person/query", json=body)
        return resp, mock_embedding, mock_pipeline
    finally:
        app.dependency_overrides.pop(get_container_async, None)


def test_non_english_query_is_embedded_in_english_and_both_forms_reach_pipeline():
    translation = _FakeTranslation()
    resp, embedding, pipeline = _route_with(translation, {"query": _HI_QUERY})
    assert resp.status_code == 200
    embedding.encode_single_full_async.assert_called_once_with("What is love?")
    kwargs = pipeline.execute.call_args.kwargs
    assert kwargs["query"] == _HI_QUERY  # cache key + safety checks see the seeker's words
    assert kwargs["retrieval_query"] == "What is love?"


def test_language_adds_gloss_and_never_replaces_verbatim():
    translation = _FakeTranslation()
    resp, _, _ = _route_with(translation, {"query": "What is love?", "language": "hi"})
    cit = resp.json()["citations"][0]
    assert cit["verbatim_text"] == "Love is a state within you."
    assert cit["translated_text"] == "प्रेम आपके भीतर की एक अवस्था है।"
    assert cit["translated_language"] == "hi"


def test_query_translation_timeout_embeds_raw_question(monkeypatch):
    monkeypatch.setattr(settings, "first_person_translation_timeout_s", 0.05)
    resp, embedding, _ = _route_with(
        _FakeTranslation(delay_s=1.0), {"query": _HI_QUERY + " (timeout)"}
    )
    assert resp.status_code == 200
    embedding.encode_single_full_async.assert_called_once_with(_HI_QUERY + " (timeout)")
