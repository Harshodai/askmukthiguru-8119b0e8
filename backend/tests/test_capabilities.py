"""Regression coverage for truthful capability reporting."""

from __future__ import annotations

from types import SimpleNamespace

from app.api.capabilities import build_capability_manifest
from app.config import settings


def test_manifest_exposes_policy_disabled_features(monkeypatch) -> None:
    monkeypatch.setattr(settings, "feature_memory_write", False)
    monkeypatch.setattr(settings, "web_search_enabled", False)
    monkeypatch.setattr(settings, "queue_enabled", False)
    container = SimpleNamespace(
        qdrant=object(),
        embedding=object(),
        ollama=object(),
        standard_graph=object(),
        lightrag_degraded=False,
        web_search=object(),
        job_queue=object(),
    )

    manifest = build_capability_manifest(container)

    assert manifest["schema_version"] == 1
    assert manifest["features"]["chat_generation"] == "available"
    assert manifest["features"]["retrieval"] == "available"
    assert manifest["features"]["memory_write"] == "disabled_by_policy"
    assert manifest["features"]["live_information"] == "disabled_by_policy"
    assert manifest["features"]["request_queue"] == "disabled_by_policy"
    assert manifest["features"]["support_attachments"] == "disabled_by_policy"
    assert manifest["features"]["waitlist"] == "disabled_by_policy"


def test_manifest_reports_chat_queue_when_enabled_and_available(monkeypatch) -> None:
    monkeypatch.setattr(settings, "queue_enabled", True)
    container = SimpleNamespace(
        qdrant=object(),
        embedding=object(),
        ollama=object(),
        standard_graph=object(),
        lightrag_degraded=False,
        web_search=None,
        job_queue=object(),
    )

    manifest = build_capability_manifest(container)

    assert manifest["features"]["request_queue"] == "available"


def test_manifest_reports_enabled_but_missing_dependency_as_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(settings, "knowledge_graph_query_enabled", True)
    container = SimpleNamespace(
        qdrant=object(),
        embedding=object(),
        ollama=object(),
        standard_graph=None,
        lightrag_degraded=True,
        web_search=None,
        job_queue=None,
    )

    manifest = build_capability_manifest(container)

    assert manifest["features"]["knowledge_graph"] == "unavailable"


def test_manifest_reports_waitlist_dependency(monkeypatch) -> None:
    monkeypatch.setattr(settings, "waitlist_enabled", True)
    unavailable = SimpleNamespace(
        qdrant=object(),
        embedding=object(),
        ollama=object(),
        standard_graph=object(),
        lightrag_degraded=False,
        web_search=object(),
        job_queue=object(),
        supabase_client=None,
    )
    available = SimpleNamespace(**{**unavailable.__dict__, "supabase_client": object()})

    assert build_capability_manifest(unavailable)["features"]["waitlist"] == "unavailable"
    assert build_capability_manifest(available)["features"]["waitlist"] == "available"


def test_manifest_exposes_composer_capabilities_without_claiming_server_voice():
    container = SimpleNamespace(
        qdrant=object(),
        embedding=object(),
        ollama=object(),
        standard_graph=object(),
        lightrag_degraded=False,
        web_search=None,
        job_queue=None,
        serene_mind=None,
    )
    features = build_capability_manifest(container)["features"]
    assert features["serene_mind"] == "unavailable"
    assert features["guided_meditation"] == "available"
    assert features["text_attachments"] == "available"
    assert features["voice_input"] == "available"
