"""P1-BE-8: audio size cap is enforced BEFORE decode/transcribe.

The STT endpoint must reject oversized uploads with 413 before any bytes
reach Sarvam or the local Whisper fallback. A hostile 30MB upload must never
be fully buffered + transcribed — the cap rejects first.
"""

import tempfile
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import UploadFile

from app.api.speech import speech_to_text_endpoint

_OVERSIZED = b"x" * (30 * 1024 * 1024)


def _make_upload(size: int | None, content: bytes = b"") -> UploadFile:
    spool = tempfile.SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b")
    spool.write(content)
    spool.seek(0)
    f = UploadFile(filename="rec.webm", headers={"content-type": "audio/webm"}, file=spool)
    f.size = size
    return f


@pytest.mark.asyncio
@patch("app.api.speech.transcribe_with_whisper")
@patch("app.api.speech.httpx.AsyncClient")
async def test_oversized_upload_rejected_before_decode(mock_httpx, mock_whisper):
    request = AsyncMock()
    # request.headers is real code's Mapping-like, sync .get(). AsyncMock makes
    # every attribute access recursively async, so request.headers.get(...)
    # returns an unawaited coroutine instead of a string -- is_benchmark_request()
    # then compares that coroutine against a real str in hmac.compare_digest and
    # raises TypeError instead of returning False (surfaces only when
    # settings.enable_test_auth happens to be True, e.g. leaked from another
    # test's unpatched settings mutation -- security_utils.py's own docstring
    # warns about that pattern). A plain dict has the right sync .get().
    request.headers = {}
    container = AsyncMock()

    upload = _make_upload(30 * 1024 * 1024, _OVERSIZED)

    with pytest.raises(Exception) as exc_info:
        await speech_to_text_endpoint(
            request=request,
            file=upload,
            language_code="en-IN",
            model="saaras:v3",
            user={"id": "u1"},
            container=container,
        )
    assert exc_info.value.status_code == 413

    mock_whisper.assert_not_called()
    mock_httpx.assert_not_called()
    assert upload.file.tell() == 0, "file must not be read before the cap rejects"
    await upload.close()


@pytest.mark.asyncio
@patch("app.api.speech.transcribe_with_whisper")
async def test_oversized_body_with_unknown_size_rejected_before_decode(mock_whisper):
    """Content-Length absent (file.size None) — bounded read must 413 anyway."""
    request = AsyncMock()
    # request.headers is real code's Mapping-like, sync .get(). AsyncMock makes
    # every attribute access recursively async, so request.headers.get(...)
    # returns an unawaited coroutine instead of a string -- is_benchmark_request()
    # then compares that coroutine against a real str in hmac.compare_digest and
    # raises TypeError instead of returning False (surfaces only when
    # settings.enable_test_auth happens to be True, e.g. leaked from another
    # test's unpatched settings mutation -- security_utils.py's own docstring
    # warns about that pattern). A plain dict has the right sync .get().
    request.headers = {}
    container = AsyncMock()

    upload = _make_upload(None, _OVERSIZED)

    with pytest.raises(Exception) as exc_info:
        await speech_to_text_endpoint(
            request=request,
            file=upload,
            language_code="en-IN",
            model="saaras:v3",
            user={"id": "u1"},
            container=container,
        )
    assert exc_info.value.status_code == 413

    mock_whisper.assert_not_called()
    await upload.close()
