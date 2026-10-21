"""Regression tests for source-verified breath teaching and truthful graph status."""

from __future__ import annotations

import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.config import settings


def _citation(text: str, **overrides) -> dict:
    citation = {
        "video_id": "video123",
        "start_ms": 12000,
        "end_ms": 26000,
        "verbatim_text": text,
        "transcript_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "is_verbatim": True,
        "speaker": "Sri Krishnaji",
        "speaker_verified": False,
        "channel": "unknown-source",
        "source_url": "https://www.youtube.com/watch?v=video123&t=12s",
    }
    citation.update(overrides)
    return citation


@pytest.mark.asyncio
async def test_breath_teaching_uses_verified_clip_and_never_generates_fallback(monkeypatch):
    from app.api import chat as chat_api
    from app.api import first_person as first_person_api

    monkeypatch.setattr(settings, "first_person_route_enabled", True)
    monkeypatch.setattr(settings, "first_person_mode", "retrieval_only")
    monkeypatch.setattr(settings, "first_person_collection", "first_person_test")

    quote = "Breathe gently and let the exhale soften the body."
    pipeline_result = SimpleNamespace(
        status="weak_match",
        is_direct_answer=False,
        citations=[_citation(quote)],
        latency_ms=5.0,
    )
    pipeline = MagicMock()
    pipeline.execute.side_effect = [
        pipeline_result,
        SimpleNamespace(
            status="abstained", is_direct_answer=False, citations=[], latency_ms=2.0
        ),
    ]
    monkeypatch.setattr(first_person_api, "_pipeline", lambda *args, **kwargs: pipeline)
    monkeypatch.setattr(first_person_api, "_english_query", AsyncMock(side_effect=lambda q, c: q))
    monkeypatch.setattr(first_person_api, "_output_rail_passes", AsyncMock(return_value=True))

    embedding = SimpleNamespace(
        encode_single_full_async=AsyncMock(return_value={"dense": [0.1, 0.2], "sparse": {}})
    )
    container = SimpleNamespace(
        embedding=embedding,
        serene_mind=None,
        openrouter=None,
        nim=None,
        ollama=None,
    )
    request = MagicMock()
    handler = getattr(chat_api.get_breath_teaching, "__wrapped__", chat_api.get_breath_teaching)

    response = await handler(request, "serene_mind", {"id": "user-1"}, container)

    assert quote in response["teaching"]
    assert "Related, not a direct answer" in response["teaching"]
    # The name is not promoted when this clip has no verified-speaker flag.
    assert "Sri Krishnaji" not in response["teaching"]
    assert "unverified clip" in response["teaching"]
    pipeline.execute.assert_called_once()
    assert pipeline.execute.call_args.kwargs["max_clips"] == 1
    assert pipeline.execute.call_args.kwargs["cache_bypass"] is False

    # Reuse the pipeline-owned exact cache: its hit path rechecks clip integrity,
    # speaker eligibility, and current point servability before returning a quote.
    # The route must not layer a second response cache over that contract.
    with pytest.raises(HTTPException) as exc:
        await handler(request, "serene_mind", {"id": "user-1"}, container)
    assert exc.value.status_code == 503
    assert pipeline.execute.call_count == 2
    assert embedding.encode_single_full_async.await_count == 2


@pytest.mark.asyncio
async def test_breath_teaching_rejects_missing_or_invalid_evidence(monkeypatch):
    from app.api import chat as chat_api
    from app.api import first_person as first_person_api

    monkeypatch.setattr(settings, "first_person_route_enabled", True)
    monkeypatch.setattr(settings, "first_person_mode", "retrieval_only")
    monkeypatch.setattr(settings, "first_person_collection", "first_person_test")

    pipeline = MagicMock()
    pipeline.execute.return_value = SimpleNamespace(
        status="abstained", is_direct_answer=False, citations=[], latency_ms=2.0
    )
    monkeypatch.setattr(first_person_api, "_pipeline", lambda *args, **kwargs: pipeline)
    monkeypatch.setattr(first_person_api, "_english_query", AsyncMock(side_effect=lambda q, c: q))
    embedding = SimpleNamespace(
        encode_single_full_async=AsyncMock(return_value={"dense": [0.1], "sparse": {}})
    )
    container = SimpleNamespace(
        embedding=embedding, serene_mind=None, openrouter=None, nim=None, ollama=None
    )
    handler = getattr(chat_api.get_breath_teaching, "__wrapped__", chat_api.get_breath_teaching)

    with pytest.raises(HTTPException) as exc:
        await handler(MagicMock(), "box", {"id": "user-1"}, container)

    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_breath_teaching_rejects_unknown_technique(monkeypatch):
    from app.api import chat as chat_api

    handler = getattr(chat_api.get_breath_teaching, "__wrapped__", chat_api.get_breath_teaching)
    with pytest.raises(HTTPException) as exc:
        await handler(MagicMock(), "arbitrary-fallback", {"id": "user-1"}, SimpleNamespace())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_concept_graph_does_not_return_mock_nodes_when_unconfigured(monkeypatch):
    from app.api import chat as chat_api

    monkeypatch.setattr(settings, "neo4j_uri", "")
    with pytest.raises(HTTPException) as exc:
        await chat_api.get_concept_graph(
            container=SimpleNamespace(),
            user={"id": "admin-1", "is_superuser": True},
        )
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_concept_graph_returns_unavailable_when_driver_is_down(monkeypatch):
    from app.api import chat as chat_api

    monkeypatch.setattr(settings, "neo4j_uri", "bolt://graph.example:7687")
    with pytest.raises(HTTPException) as exc:
        await chat_api.get_concept_graph(
            container=SimpleNamespace(neo4j_driver=None),
            user={"id": "admin-1", "is_superuser": True},
        )
    assert exc.value.status_code == 503
