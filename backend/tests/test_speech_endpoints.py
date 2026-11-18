"""Tests for enhanced speech endpoints (STT and TTS) supporting flexible form fields and optional auth."""
from __future__ import annotations

import base64
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import UploadFile
from httpx import Response

from app.api.speech import SpeechTTSRequest, speech_to_text_endpoint, text_to_speech_endpoint


def _make_upload(content: bytes = b"RIFF....WAVEfmt ", filename: str = "voice.webm") -> UploadFile:
    spool = tempfile.SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b")
    spool.write(content)
    spool.seek(0)
    return UploadFile(filename=filename, headers={"content-type": "audio/webm"}, file=spool)


@pytest.mark.asyncio
@patch("app.api.speech.transcribe_with_whisper")
@patch("app.api.speech.httpx.AsyncClient")
async def test_stt_accepts_file_param_anonymous(mock_httpx, mock_whisper):
    """STT must accept anonymous user and return both transcript and text."""
    mock_whisper.return_value = "What is suffering?"
    mock_client = AsyncMock()
    mock_client.post.side_effect = Exception("Sarvam offline")
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_httpx.return_value = mock_client

    request = MagicMock()
    request.headers = {}
    request.client.host = "127.0.0.1"

    upload = _make_upload(b"some audio data")
    result = await speech_to_text_endpoint(
        request=request,
        file=upload,
        audio=None,
        language_code="en-IN",
        user=None,  # anonymous user
    )

    assert result["transcript"] == "What is suffering?"
    assert result["text"] == "What is suffering?"
    assert result["language_code"] == "en-IN"


@pytest.mark.asyncio
@patch("app.api.speech.transcribe_with_whisper")
@patch("app.api.speech.httpx.AsyncClient")
async def test_stt_accepts_audio_param_anonymous(mock_httpx, mock_whisper):
    """STT must accept 'audio' parameter for compatibility with legacy audio clients."""
    mock_whisper.return_value = "How to find peace?"
    mock_client = AsyncMock()
    mock_client.post.side_effect = Exception("Sarvam offline")
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_httpx.return_value = mock_client

    request = MagicMock()
    request.headers = {}
    request.client.host = "127.0.0.1"

    upload = _make_upload(b"some audio data")
    result = await speech_to_text_endpoint(
        request=request,
        file=None,
        audio=upload,
        language="hi-IN",
        user=None,
    )

    assert result["transcript"] == "How to find peace?"
    assert result["text"] == "How to find peace?"


@pytest.mark.asyncio
@patch("app.api.speech.settings")
@patch("app.api.speech.httpx.AsyncClient")
async def test_tts_accepts_anonymous_user(mock_client_cls, mock_settings):
    """TTS must accept anonymous user requests within IP rate limits."""
    mock_settings.sarvam_api_key = "sk_live_valid_key_12345678"

    raw_audio_bytes = b"\xff\xfb\x90\x44" + b"\x00" * 64
    raw_b64 = base64.b64encode(raw_audio_bytes).decode("ascii")

    mock_resp = MagicMock(spec=Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"audios": [raw_b64]}

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client_cls.return_value = mock_client

    request = MagicMock()
    request.headers = {}
    request.client.host = "127.0.0.1"

    req = SpeechTTSRequest(text="Peace is within you.", target_language_code="en-IN", speaker="priya")
    res = await text_to_speech_endpoint(request=request, req=req, user=None)

    assert "audio_base64" in res
    assert res["format"] == "mp3"
