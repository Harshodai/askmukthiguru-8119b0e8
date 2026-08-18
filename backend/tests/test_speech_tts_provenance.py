"""
Tests for Speech TTS Provenance & Audio Watermarking Integration (Phase 4).
"""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import Response

from app.api.speech import SpeechTTSRequest, text_to_speech_endpoint
from services.watermarking_service import WatermarkingService


@pytest.mark.asyncio
@patch("app.api.speech.settings")
@patch("app.api.speech.httpx.AsyncClient")
async def test_text_to_speech_endpoint_provenance_and_watermarking(mock_client_cls, mock_settings):
    """
    Verify text_to_speech_endpoint:
    1. Calls Sarvam TTS API
    2. Tags the audio payload with ID3v2 provenance metadata
    3. Returns watermarked base64 audio and provenance dictionary
    """
    mock_settings.sarvam_api_key = "sk_live_valid_key_12345678"

    # Dummy raw audio bytes (MP3 frame header)
    raw_audio_bytes = b"\xff\xfb\x90\x44" + b"\x00" * 128
    raw_b64 = base64.b64encode(raw_audio_bytes).decode("ascii")

    # Mock HTTP response from Sarvam
    mock_resp = MagicMock(spec=Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"audios": [raw_b64]}

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client_cls.return_value = mock_client

    request = MagicMock()
    req = SpeechTTSRequest(
        text="Peace begins within the silence of your own heart.",
        target_language_code="hi",
        speaker="shubh",
    )
    user = {"id": "user-test-789", "email": "test@example.com"}
    container = MagicMock()
    container.neo4j_driver = None

    result = await text_to_speech_endpoint(
        request=request,
        req=req,
        user=user,
        container=container,
    )

    assert "audio" in result
    assert "provenance" in result

    # Verify provenance dictionary
    prov = result["provenance"]
    assert prov["modality"] == "synthetic_audio"
    assert prov["origin_type"] == "ai_generated"
    assert prov["risk_tier"] == "transparency_art50"
    assert prov["agent"]["model_name"] == "bulbul:v3"
    assert "EU AI Act Article 50" in prov["disclosure_statement"]
    assert prov["metadata"]["language_code"] == "hi-IN"
    assert prov["metadata"]["speaker"] == "shubh"

    # Verify returned audio has ID3 tags injected
    tagged_audio_bytes = base64.b64decode(result["audio"])
    assert len(tagged_audio_bytes) > len(raw_audio_bytes)
    tags = WatermarkingService.extract_audio_provenance(tagged_audio_bytes)
    assert tags.get("AI_GENERATED") == "true"
    assert tags.get("AI_MODEL") == "bulbul:v3"
    assert tags.get("PROVENANCE_ID") == prov["artifact_id"]
