"""
Tests for EU AI Act Compliance & Provenance Framework (Phases 1, 2, 3, 4).

Covers:
1. Phase 1: Schema validation, enums, models, and W3C PROV-O JSON-LD serialization.
2. Phase 2: Audio ID3 tagging, zero-width text watermarking, and HTTP headers.
3. Phase 3: Neo4j ontology recording, graph traversal, and compliance statistics.
4. Phase 4: ChatResponse integration, TTS speech tagging, and compliance endpoints.
"""

from __future__ import annotations

import base64
import datetime as _dt
import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.compliance import router as compliance_router
from app.dependencies import get_container
from app.main import app
from app.schemas.compliance_provenance import (
    AIProvenanceManifest,
    ArtifactModality,
    EUComplianceRiskTier,
    GroundingSourceReference,
    OriginType,
    SoftwareAgentDescriptor,
)
from app.schemas import ChatResponse
from services.provenance_ontology_service import (
    ProvenanceOntologyService,
    get_provenance_ontology_service,
)
from services.watermarking_service import WatermarkingService


# ---------------------------------------------------------------------------
# 1. Phase 1: Schema & W3C PROV-O JSON-LD Tests
# ---------------------------------------------------------------------------


def test_provenance_enums():
    """Verify all required enum values exist."""
    assert OriginType.HUMAN_GENERATED.value == "human_generated"
    assert OriginType.AI_ASSISTED.value == "ai_assisted"
    assert OriginType.AI_GENERATED.value == "ai_generated"

    assert ArtifactModality.TEXT_CHAT.value == "text_chat"
    assert ArtifactModality.SYNTHETIC_AUDIO.value == "synthetic_audio"
    assert ArtifactModality.USER_MEMORY.value == "user_memory"
    assert ArtifactModality.KNOWLEDGE_GRAPH_NODE.value == "knowledge_graph_node"
    assert ArtifactModality.VECTOR_EMBEDDING.value == "vector_embedding"
    assert ArtifactModality.DOCUMENT_EXPORT.value == "document_export"

    assert EUComplianceRiskTier.MINIMAL_RISK.value == "minimal_risk"
    assert EUComplianceRiskTier.TRANSPARENCY_ART50.value == "transparency_art50"
    assert EUComplianceRiskTier.SPECIFIC_CAUTION.value == "specific_caution"


def test_ai_provenance_manifest_creation_and_json_ld():
    """Verify manifest creation and W3C PROV-O JSON-LD structure."""
    source1 = GroundingSourceReference(
        source_id="chunk-42",
        source_type="spiritual_wisdom",
        title="Discourse on Inner Awakening",
        url="https://example.com/discourse-42",
        snippet_hash="sha256:abcd1234",
        score=0.95,
    )
    agent = SoftwareAgentDescriptor(
        agent_id="askmukthiguru-v1",
        name="AskMukthiGuru AI",
        version="1.2.0",
        model_name="meta-llama/llama-3.1-8b-instruct",
        provider="openrouter",
        role="Spiritual Guide",
        system_prompt_hash="sha256:prompt123",
    )

    manifest = AIProvenanceManifest(
        artifact_id="urn:uuid:12345678-1234-5678-1234-567812345678",
        modality=ArtifactModality.TEXT_CHAT,
        origin_type=OriginType.AI_GENERATED,
        risk_tier=EUComplianceRiskTier.TRANSPARENCY_ART50,
        agent=agent,
        sources=[source1],
        content_hash="sha256:content999",
        watermark_signature="sig:zw-001",
        session_id="sess-xyz",
        user_id_hash="sha256:user123",
    )

    json_ld = manifest.to_json_ld()

    assert json_ld["@id"] == "urn:uuid:12345678-1234-5678-1234-567812345678"
    assert "@context" in json_ld
    assert isinstance(json_ld["@context"], dict)
    assert "prov" in json_ld["@context"]
    assert "euaiact" in json_ld["@context"]
    assert json_ld["euaiact:riskTier"] == "transparency_art50"
    assert json_ld["euaiact:originType"] == "ai_generated"

    # Verify PROV-O agent association
    prov_agent = json_ld["prov:wasAttributedTo"]
    assert prov_agent["@id"] == "urn:agent:askmukthiguru-v1"
    assert prov_agent["schema:model"] == "meta-llama/llama-3.1-8b-instruct"

    # Verify PROV-O activity & used sources
    prov_act = json_ld["prov:wasGeneratedBy"]
    assert prov_act["@type"] == "prov:Activity"
    assert len(prov_act["prov:used"]) == 1
    assert prov_act["prov:used"][0]["@id"] == "https://example.com/discourse-42"
    assert prov_act["prov:used"][0]["schema:score"] == 0.95


# ---------------------------------------------------------------------------
# 2. Phase 2: Watermarking Service Tests
# ---------------------------------------------------------------------------


def test_audio_provenance_injection_and_extraction():
    """Verify audio ID3 tagging and metadata extraction without corruption."""
    manifest = AIProvenanceManifest(
        artifact_id="urn:uuid:audio-test-001",
        modality=ArtifactModality.SYNTHETIC_AUDIO,
        origin_type=OriginType.AI_GENERATED,
        risk_tier=EUComplianceRiskTier.TRANSPARENCY_ART50,
        agent=SoftwareAgentDescriptor(
            agent_id="sarvam-tts",
            name="Sarvam Bulbul TTS",
            model_name="bulbul:v3",
            provider="sarvam",
        ),
        disclosure_statement="Art. 50 disclosure for synthetic speech",
    )

    # Simulated audio payload (e.g. MP3 frames)
    dummy_mp3_payload = b"\xff\xfb\x90\x44" + b"\x00" * 256

    watermarked = WatermarkingService.inject_audio_provenance(
        audio_bytes=dummy_mp3_payload,
        manifest=manifest,
        format="mp3",
    )

    assert len(watermarked) > len(dummy_mp3_payload)
    assert watermarked.startswith(b"ID3")

    tags = WatermarkingService.extract_audio_provenance(watermarked)
    assert tags.get("AI_GENERATED") == "true"
    assert tags.get("AI_MODEL") == "bulbul:v3"
    assert tags.get("PROVENANCE_ID") == "urn:uuid:audio-test-001"
    assert tags.get("EU_AI_ACT_DISCLOSURE") == "Art. 50 disclosure for synthetic speech"


def test_audio_provenance_wav_handling():
    """Verify WAV audio RIFF id3 chunk injection."""
    manifest = AIProvenanceManifest(
        artifact_id="urn:uuid:wav-test-001",
        modality=ArtifactModality.SYNTHETIC_AUDIO,
        origin_type=OriginType.AI_GENERATED,
    )

    # Minimal dummy RIFF WAVE payload
    riff_header = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
    watermarked = WatermarkingService.inject_audio_provenance(
        audio_bytes=riff_header,
        manifest=manifest,
        format="wav",
    )

    assert watermarked.startswith(b"RIFF")
    assert b"WAVE" in watermarked
    assert b"id3 " in watermarked

    tags = WatermarkingService.extract_audio_provenance(watermarked)
    assert tags.get("AI_GENERATED") == "true"
    assert tags.get("PROVENANCE_ID") == "urn:uuid:wav-test-001"


def test_text_watermarking_encode_decode():
    """Verify invisible zero-width unicode text watermarking roundtrip."""
    text = "The nature of consciousness is peace and spacious presence."
    manifest = AIProvenanceManifest(
        artifact_id="urn:uuid:text-007",
        origin_type=OriginType.AI_GENERATED,
        agent=SoftwareAgentDescriptor(model_name="meta-llama/llama-3.1-8b-instruct"),
    )

    watermarked = WatermarkingService.encode_text_watermark(text, manifest)

    # Visible text is unchanged
    assert text in watermarked
    assert len(watermarked) > len(text)

    # Decode watermark
    decoded = WatermarkingService.decode_text_watermark(watermarked)
    assert decoded is not None
    assert decoded["origin_type"] == "ai_generated"
    assert decoded["artifact_id"] == "urn:uuid:text-007"
    assert decoded["model_name"] == "meta-llama/llama-3.1-8b-instruct"

    # Strip watermark
    stripped = WatermarkingService.strip_text_watermark(watermarked)
    assert stripped == text


def test_text_watermarking_corrupted_or_missing():
    """Verify robust handling of text without watermark or corrupted data."""
    plain_text = "Plain text without any watermarking."
    assert WatermarkingService.decode_text_watermark(plain_text) is None

    # Partial / corrupted zero-width chars
    corrupted = plain_text + "\u200d\u200b\u200d\u200b\u200c\u200d\u200c\u200d"
    assert WatermarkingService.decode_text_watermark(corrupted) is None


def test_http_provenance_headers():
    """Verify standard EU AI Act Article 50 HTTP headers."""
    manifest = AIProvenanceManifest(
        artifact_id="urn:uuid:http-hdr-01",
        origin_type=OriginType.AI_GENERATED,
        risk_tier=EUComplianceRiskTier.TRANSPARENCY_ART50,
        agent=SoftwareAgentDescriptor(model_name="bulbul:v3"),
    )

    headers = WatermarkingService.build_http_provenance_headers(manifest)
    assert headers["X-AI-Generated"] == "true"
    assert headers["X-AI-Origin"] == "ai_generated"
    assert headers["X-AI-Model"] == "bulbul:v3"
    assert "EU-AI-Act-Art50" in headers["X-AI-Compliance"]
    assert headers["X-AI-Provenance-ID"] == "urn:uuid:http-hdr-01"


# ---------------------------------------------------------------------------
# 3. Phase 3: Provenance Ontology Service Tests
# ---------------------------------------------------------------------------


def test_provenance_ontology_service_memory_fallback():
    """Verify ontology service stores and searches records via memory fallback."""
    service = ProvenanceOntologyService()

    manifest1 = AIProvenanceManifest(
        artifact_id="urn:uuid:ont-001",
        origin_type=OriginType.AI_GENERATED,
        risk_tier=EUComplianceRiskTier.TRANSPARENCY_ART50,
        agent=SoftwareAgentDescriptor(
            agent_id="agent-1",
            name="AskMukthiGuru AI",
            model_name="meta-llama/llama-3.1-8b-instruct",
            provider="openrouter",
        ),
        sources=[
            GroundingSourceReference(source_id="src-1", title="Four Sacred Secrets"),
        ],
    )

    service.record_provenance(manifest1, prompt_hash="sha256:prompt001", latency_ms=120.5)

    # Retrieve JSON-LD manifest
    ld = service.get_provenance_manifest("urn:uuid:ont-001")
    assert ld is not None
    assert ld["@id"] == "urn:uuid:ont-001"
    assert ld["euaiact:originType"] == "ai_generated"

    # Search provenance
    search_res = service.search_provenance(origin_type="ai_generated")
    assert len(search_res) == 1
    assert search_res[0]["artifact_id"] == "urn:uuid:ont-001"
    assert search_res[0]["model_name"] == "meta-llama/llama-3.1-8b-instruct"

    # Search with non-matching model
    empty_res = service.search_provenance(model_name="non-existent-model")
    assert len(empty_res) == 0

    # Get compliance stats
    stats = service.get_eu_compliance_stats()
    assert stats["total_artifacts"] == 1
    assert stats["origin_breakdown"]["ai_generated"] == 1
    assert stats["article_50_disclosure_rate"] == 1.0


# ---------------------------------------------------------------------------
# 4. Phase 4: API & Integration Tests
# ---------------------------------------------------------------------------


def test_chat_response_schema_with_provenance():
    """Verify ChatResponse accepts and serializes provenance_manifest."""
    manifest = AIProvenanceManifest(
        artifact_id="urn:uuid:chat-resp-001",
        origin_type=OriginType.AI_GENERATED,
    )
    resp = ChatResponse(
        response="Namaste seeker.",
        provenance_manifest=manifest,
    )

    dumped = resp.model_dump()
    assert dumped["response"] == "Namaste seeker."
    assert dumped["provenance_manifest"] is not None
    assert dumped["provenance_manifest"]["artifact_id"] == "urn:uuid:chat-resp-001"


@pytest.fixture
def mock_service_container():
    """Create a mock service container to avoid live Qdrant/Neo4j connections during API tests."""
    mock_container = MagicMock()
    mock_container.neo4j_driver = None
    mock_container.compliance_logger = MagicMock()
    mock_container.compliance_logger.list_sessions_for_user.return_value = []
    return mock_container


@pytest.fixture
def test_app():
    """Create isolated FastAPI test app with compliance router attached."""
    from fastapi import FastAPI
    from app.api.compliance import _require_admin

    app = FastAPI()
    app.dependency_overrides[_require_admin] = lambda: {"user_id": "test-admin", "is_superuser": True}
    app.include_router(compliance_router)
    return app


@pytest.mark.asyncio
async def test_compliance_status_endpoint(test_app, mock_service_container):
    """Test GET /api/compliance/eu-ai-act/status."""
    test_app.dependency_overrides[get_container] = lambda: mock_service_container
    try:
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            response = await client.get("/api/compliance/eu-ai-act/status")
            assert response.status_code == 200
            data = response.json()
            assert data["status"].lower() == "compliant"
            assert "Regulation (EU) 2024/1689" in data["regulation"]
            assert data["article_50_compliance"]["synthetic_content_marking"] is True
            assert "supported_risk_tiers" in data
            assert "transparency_art50" in data["supported_risk_tiers"]
    finally:
        test_app.dependency_overrides.pop(get_container, None)


@pytest.mark.asyncio
async def test_compliance_provenance_search_and_manifest_endpoints(test_app, mock_service_container):
    """Test /api/compliance/provenance/search and /manifest/{artifact_id} endpoints."""
    test_app.dependency_overrides[get_container] = lambda: mock_service_container
    try:
        # Seed a record in ontology service
        prov_service = get_provenance_ontology_service()
        test_manifest = AIProvenanceManifest(
            artifact_id="urn:uuid:e2e-artifact-42",
            origin_type=OriginType.AI_GENERATED,
            risk_tier=EUComplianceRiskTier.TRANSPARENCY_ART50,
            agent=SoftwareAgentDescriptor(model_name="bulbul:v3"),
        )
        prov_service.record_provenance(test_manifest)

        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            # Search
            search_resp = await client.get(
                "/api/compliance/provenance/search",
                params={"origin_type": "ai_generated"},
            )
            assert search_resp.status_code == 200
            search_data = search_resp.json()
            assert search_data["count"] >= 1
            assert any(r["artifact_id"] == "urn:uuid:e2e-artifact-42" for r in search_data["results"])

            # Fetch manifest by ID
            manifest_resp = await client.get(
                "/api/compliance/provenance/manifest/urn:uuid:e2e-artifact-42"
            )
            assert manifest_resp.status_code == 200
            manifest_data = manifest_resp.json()
            assert manifest_data["@id"] == "urn:uuid:e2e-artifact-42"
            assert manifest_data["euaiact:originType"] == "ai_generated"

            # Fetch 404 for non-existent artifact
            not_found_resp = await client.get(
                "/api/compliance/provenance/manifest/urn:uuid:does-not-exist"
            )
            assert not_found_resp.status_code == 404
    finally:
        test_app.dependency_overrides.pop(get_container, None)


# ---------------------------------------------------------------------------
# 5. Phase 5: Backfill Script & Classifier Tests
# ---------------------------------------------------------------------------


def test_qdrant_classification_heuristics():
    """Verify classification logic accurately distinguishes human teachings from AI summaries."""
    from scripts.ops.eu_ai_act_backfill import (
        backfill_database,
        backfill_neo4j,
        backfill_qdrant,
        classify_qdrant_point_payload,
    )

    # 1. Primary human source discourse
    human_point = {
        "text": "Living in the beautiful state transforms all actions.",
        "source_url": "https://youtube.com/watch?v=preethaji-talk",
        "title": "The Four Sacred Secrets",
        "speaker": "Sri Preethaji",
        "chunk_index": 1,
    }
    origin, update = classify_qdrant_point_payload(human_point)
    assert origin == "human_generated"
    assert update["origin_type"] == "human_generated"
    assert update["provenance_schema_version"] == "1.0"
    assert "compliance_tagged_at" in update

    # 2. AI Synthesized cluster summary
    ai_point = {
        "text": "Comprehensive synthesis of emotional wellness practices.",
        "is_summary": True,
        "cluster_id": 105,
        "doc_type": "summary",
    }
    origin_ai, update_ai = classify_qdrant_point_payload(ai_point)
    assert origin_ai == "ai_generated"
    assert update_ai["origin_type"] == "ai_generated"


def test_backfill_dry_run_qdrant_mock():
    """Verify backfill_qdrant dry-run mode with mocked client."""
    from scripts.ops.eu_ai_act_backfill import backfill_qdrant

    mock_rec_1 = MagicMock()
    mock_rec_1.id = "p-1"
    mock_rec_1.payload = {
        "text": "Meditation discourse",
        "source_url": "https://ekam.org",
    }

    mock_rec_2 = MagicMock()
    mock_rec_2.id = "p-2"
    mock_rec_2.payload = {
        "text": "Cluster summary",
        "is_summary": True,
    }

    with patch("qdrant_client.QdrantClient") as MockQdrantClient:
        mock_client = MockQdrantClient.return_value
        mock_client.scroll.return_value = ([mock_rec_1, mock_rec_2], None)

        result = backfill_qdrant(
            collection="spiritual_wisdom",
            batch_size=10,
            dry_run=True,
            limit=10,
        )

        assert result["status"] == "success"
        assert result["scanned"] == 2
        assert result["human_generated"] == 1
        assert result["ai_generated"] == 1
        assert result["updated"] == 0
        assert result["dry_run"] is True


def test_backfill_database_and_neo4j_dry_run():
    """Verify backfill database and Neo4j functions execute cleanly in dry-run mode."""
    from scripts.ops.eu_ai_act_backfill import backfill_database, backfill_neo4j

    db_res = backfill_database(dry_run=True)
    assert db_res["dry_run"] is True
    assert db_res["status"] in ("success", "simulated")

    neo_res = backfill_neo4j(dry_run=True)
    assert neo_res["dry_run"] is True
    assert neo_res["status"] in ("success", "warning", "skipped")
