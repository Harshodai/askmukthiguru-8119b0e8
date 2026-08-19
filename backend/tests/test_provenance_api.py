"""Tests for EU AI Act Compliance API Endpoints and ChatResponse Provenance Serialization.

Verifies:
1. GET /api/compliance/eu-ai-act/status returns Article 50 transparency status.
2. GET /api/compliance/provenance/search filters and returns provenance manifests.
3. Provenance manifest serialization in ChatResponse schema.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.compliance import router as compliance_router
from app.schemas import (
    AIProvenanceManifest,
    ChatResponse,
    OriginType,
)


@pytest.fixture
def client():
    """Create test client with compliance router attached."""
    from app.api.compliance import _require_admin

    app = FastAPI()
    app.dependency_overrides[_require_admin] = lambda: {
        "user_id": "test-admin",
        "is_superuser": True,
    }
    app.include_router(compliance_router)
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. EU AI Act Status Endpoint Tests
# ---------------------------------------------------------------------------


def test_get_eu_ai_act_status(client):
    """Verify GET /api/compliance/eu-ai-act/status returns compliant transparency metadata."""
    response = client.get("/api/compliance/eu-ai-act/status")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "compliant"
    assert data["standard"] == "eu_ai_act_article_50"
    assert data["article_50_transparency_enabled"] is True
    assert data["watermarking_engine"] == "active"
    assert "zero_width_text" in data["watermarking_methods"]
    assert "audio_tag" in data["watermarking_methods"]
    assert "http_header" in data["watermarking_methods"]
    assert data["provenance_schema_version"] == "1.0"
    assert "human_generated" in data["supported_origin_types"]
    assert "ai_generated" in data["supported_origin_types"]
    assert "timestamp" in data


# ---------------------------------------------------------------------------
# 2. Provenance Search Endpoint Tests
# ---------------------------------------------------------------------------


def test_search_provenance_empty(client):
    """Verify search without params returns valid query envelope."""
    response = client.get("/api/compliance/provenance/search")
    assert response.status_code == 200

    data = response.json()
    assert data["count"] >= 0
    assert isinstance(data["results"], list)
    assert data["query"]["limit"] == 50


def test_search_provenance_with_content_id(client):
    """Verify search with content_id returns W3C PROV-O JSON-LD manifest."""
    response = client.get(
        "/api/compliance/provenance/search",
        params={"content_id": "msg-response-789", "origin_type": "ai_generated"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["count"] == 1
    assert len(data["results"]) == 1

    manifest_ld = data["results"][0]
    assert "@context" in manifest_ld
    assert "schema" in manifest_ld["@context"] or "prov" in manifest_ld["@context"]
    assert manifest_ld["identifier"] == "msg-response-789"
    assert manifest_ld["creativeWorkStatus"] == "AI-Generated"
    assert manifest_ld["originType"] == "ai_generated"
    assert manifest_ld["producer"]["@type"] == "SoftwareApplication"
    assert manifest_ld["compliance"]["standard"] == "eu_ai_act_article_50"


def test_search_provenance_human_authored(client):
    """Verify search with human_generated origin returns human-authored manifest."""
    response = client.get(
        "/api/compliance/provenance/search",
        params={"content_id": "discourse-33", "origin_type": "human_generated"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["count"] == 1
    manifest_ld = data["results"][0]
    assert manifest_ld["creativeWorkStatus"] == "Human-Authored"
    assert manifest_ld["originType"] == "human_generated"


# ---------------------------------------------------------------------------
# 3. ChatResponse Provenance Serialization Tests
# ---------------------------------------------------------------------------


def test_chat_response_serialization_with_provenance():
    """Verify ChatResponse model serializes ai_provenance and release_manifest."""
    manifest = AIProvenanceManifest(
        content_id="resp-12345",
        origin_type=OriginType.AI_GENERATED,
        model_name="meta-llama/llama-3.1-8b-instruct",
        model_provider="OpenRouter",
        source_urls=["https://youtube.com/watch?v=preethaji_meditation"],
        confidence_score=0.96,
        watermark_signature="SIG-WATERMARK-ZW-1",
    )

    chat_resp = ChatResponse(
        response="Observe the stillness within.",
        intent="meditation",
        grounding_state="grounded",
        ai_provenance=manifest.to_json_ld(),
        release_manifest={
            "release_id": "rel-2026-08-v1",
            "git_sha": "abc1234",
            "policy_version": "gemini-flash-budget-v1",
        },
    )

    dumped = chat_resp.model_dump()
    assert dumped["response"] == "Observe the stillness within."
    assert dumped["grounding_state"] == "grounded"
    assert dumped["ai_provenance"] is not None
    assert dumped["ai_provenance"]["identifier"] == "resp-12345"
    assert dumped["ai_provenance"]["creativeWorkStatus"] == "AI-Generated"
    assert dumped["ai_provenance"]["compliance"]["watermark"] == "SIG-WATERMARK-ZW-1"
    assert dumped["ai_provenance"]["compliance"]["confidence"] == 0.96
    assert dumped["release_manifest"]["release_id"] == "rel-2026-08-v1"


def test_chat_response_json_roundtrip_with_provenance():
    """Verify ChatResponse model JSON string serialization and deserialization."""
    manifest = AIProvenanceManifest(
        content_id="resp-abc",
        origin_type=OriginType.AI_GENERATED,
        model_name="sarvam-2b",
        model_provider="Sarvam",
    )

    original_resp = ChatResponse(
        response="శాంతి అంతరంగంలో ఉంటుంది.",
        language="te",
        ai_provenance=manifest.to_json_ld(),
    )

    json_str = original_resp.model_dump_json()
    assert '"identifier":"resp-abc"' in json_str or '"identifier": "resp-abc"' in json_str
    assert (
        '"creativeWorkStatus":"AI-Generated"' in json_str
        or '"creativeWorkStatus": "AI-Generated"' in json_str
    )

    # Deserialization check
    reconstructed = ChatResponse.model_validate_json(json_str)
    assert reconstructed.response == original_resp.response
    assert reconstructed.ai_provenance == manifest.to_json_ld()
