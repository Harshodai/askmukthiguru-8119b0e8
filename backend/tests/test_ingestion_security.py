"""
Comprehensive Ingestion Security & GraphRAG Traversal Safety Tests (Phase 4).

Tests:
  1. SSRF Defenses:
     - Loopback literals (127.0.0.1, localhost, [::1], 0.0.0.0)
     - Decimal, hex, and octal IP forms (2130706433, 0x7f000001, 0177.0.0.1, 0x7f.1)
     - Private and link-local IPs (10.0.0.1, 192.168.1.1, 172.16.0.1, 169.254.169.254, fe80::1)
     - DNS rebinding: hostnames resolving to private/internal IPs
     - Redirects to private/loopback IPs
  2. Oversized Streaming Download Abort:
     - Download aborts immediately when bytes exceed max limit and cleans up temp file.
  3. Disallowed Schemes:
     - file://, ftp://, gopher://, javascript:, data:
  4. Temporary File Cleanup Verification:
     - Validates temp files are cleaned up on success, failure, oversized abort, and exceptions.
  5. GraphRAG Traversal Bounding & Concurrency:
     - Concurrency semaphore limit
     - Per-traversal deadline timeout
     - Aggregate deadline timeout, subtask cancellation, and safe partial recovery
"""

from __future__ import annotations

import asyncio
import os
import socket
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from ingest.social_media_loader import (
    MAX_INGEST_RESPONSE_BYTES,
    download_streaming_file,
    ingest_social_media,
    is_social_media_url,
    resolve_and_validate_hostname,
    validate_safe_url,
)
from services.graphrag_fusion import (
    ContextItem,
    FusedContext,
    GraphRAGFusion,
    reciprocal_rank_fusion,
)


# ---------------------------------------------------------------------------
# 1. SSRF Defenses & Scheme Validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "url, expected_error_substring",
    [
        # Loopback literals
        ("http://127.0.0.1/video.mp4", "prohibited IP"),
        ("http://127.0.0.2:8080/video.mp4", "prohibited IP"),
        ("http://localhost/video.mp4", "localhost"),
        ("http://[::1]/video.mp4", "prohibited IP"),
        ("http://0.0.0.0/video.mp4", "prohibited IP"),
        # Decimal, hex, octal forms
        ("http://2130706433/video.mp4", "prohibited IP"),  # 127.0.0.1 decimal
        ("http://0x7f000001/video.mp4", "prohibited IP"),  # 127.0.0.1 hex
        ("http://0177.0.0.1/video.mp4", "prohibited IP"),  # 127.0.0.1 octal
        ("http://0x7f.1/video.mp4", "prohibited IP"),      # 127.0.0.1 mixed
        # Private & Cloud Metadata
        ("http://10.0.0.1/video.mp4", "prohibited IP"),
        ("http://192.168.1.1/video.mp4", "prohibited IP"),
        ("http://172.16.0.1/video.mp4", "prohibited IP"),
        ("http://169.254.169.254/latest/meta-data/", "prohibited IP"),
        ("http://[fe80::1]/video.mp4", "prohibited IP"),
        ("http://[fc00::1]/video.mp4", "prohibited IP"),
        # Disallowed schemes
        ("file:///etc/passwd", "Disallowed scheme"),
        ("ftp://example.com/video.mp4", "Disallowed scheme"),
        ("gopher://127.0.0.1/", "Disallowed scheme"),
        ("javascript:alert(1)", "Disallowed scheme"),
        ("data:text/plain;base64,SGVsbG8=", "Disallowed scheme"),
        # Embedded credentials
        ("http://user:password@example.com/video.mp4", "embedded credentials"),
    ],
)
def test_ssrf_and_scheme_rejections(url: str, expected_error_substring: str):
    is_safe, reason = validate_safe_url(url)
    assert not is_safe, f"Expected URL '{url}' to be rejected, but it passed"
    assert expected_error_substring.lower() in reason.lower(), f"Expected '{expected_error_substring}' in '{reason}'"


def test_dns_rebinding_rejection():
    """Verify that a hostname resolving to a private/loopback IP is blocked."""
    # Mock socket.getaddrinfo to simulate a hostname resolving to 127.0.0.1
    fake_addrinfo = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))
    ]
    with patch("socket.getaddrinfo", return_value=fake_addrinfo):
        is_safe, reason = validate_safe_url("http://attacker-rebinding.com/video.mp4")
        assert not is_safe
        assert "resolved to prohibited ip" in reason.lower() or "prohibited ip" in reason.lower()


def test_valid_public_dns_resolution():
    """Verify that a hostname resolving to a public IP passes validation."""
    fake_addrinfo = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))
    ]
    with patch("socket.getaddrinfo", return_value=fake_addrinfo):
        is_safe, reason = validate_safe_url("http://example.com/video.mp4")
        assert is_safe
        assert reason == ""


# ---------------------------------------------------------------------------
# 2. Redirect to Private IP & Oversized Streaming Download Abort
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_redirect_to_private_ip_aborts_download():
    """Verify that a redirect to a private IP (e.g. 169.254.169.254) is blocked during streaming."""
    fake_addrinfo = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))
    ]

    with patch("socket.getaddrinfo", return_value=fake_addrinfo):
        # Mock httpx response that redirects to 169.254.169.254
        mock_resp = MagicMock()
        mock_resp.status_code = 302
        mock_resp.headers = {"Location": "http://169.254.169.254/latest/meta-data/"}
        mock_resp.aclose = AsyncMock()

        mock_client = MagicMock()
        mock_client.build_request.return_value = MagicMock()
        mock_client.send = AsyncMock(return_value=mock_resp)

        mock_client_ctx = MagicMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client_ctx):
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                dest_path = tmp.name

            try:
                with pytest.raises(ValueError, match="SSRF blocked URL"):
                    await download_streaming_file(
                        "http://example.com/redirect",
                        dest_path,
                    )
                # Ensure destination file was removed on failure
                assert not os.path.exists(dest_path)
            finally:
                if os.path.exists(dest_path):
                    os.unlink(dest_path)


@pytest.mark.asyncio
async def test_oversized_streaming_download_aborts_and_cleans_up():
    """Verify that a streaming download exceeding max_bytes aborts immediately and cleans up file."""
    fake_addrinfo = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))
    ]

    with patch("socket.getaddrinfo", return_value=fake_addrinfo):
        async def fake_aiter_bytes(chunk_size=65536):
            # Yield 2MB chunks up to 10MB (when limit is 5MB)
            for _ in range(5):
                yield b"X" * (2 * 1024 * 1024)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.aiter_bytes = fake_aiter_bytes
        mock_resp.aclose = AsyncMock()

        mock_client = MagicMock()
        mock_client.build_request.return_value = MagicMock()
        mock_client.send = AsyncMock(return_value=mock_resp)

        mock_client_ctx = MagicMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client_ctx):

            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                dest_path = tmp.name

            try:
                # Limit to 5MB max
                max_bytes = 5 * 1024 * 1024
                with pytest.raises(ValueError, match="Response size .* exceeds limit"):
                    await download_streaming_file(
                        "http://example.com/huge-file.mp4",
                        dest_path,
                        max_bytes=max_bytes,
                    )
                # Verify file was cleaned up on oversized abort
                assert not os.path.exists(dest_path)
            finally:
                if os.path.exists(dest_path):
                    os.unlink(dest_path)


# ---------------------------------------------------------------------------
# 3. Ingest Social Media Error Handling & Temp File Teardown
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ingest_social_media_ssrf_blocked_returns_dict():
    """Verify ingest_social_media returns graceful error dict on SSRF block."""
    result = await ingest_social_media("http://127.0.0.1/audio.mp4")
    assert result["text"] == ""
    assert result["method"] == "blocked_ssrf"
    assert "Security validation failed" in result["error"]


@pytest.mark.asyncio
async def test_ingest_social_media_tempdir_cleanup_on_exception():
    """Verify temporary files are cleaned up when download or transcription raises exception."""
    fake_addrinfo = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))
    ]

    created_dirs = []
    real_temp_dir = tempfile.TemporaryDirectory

    class TrackedTempDir(real_temp_dir):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created_dirs.append(self.name)

    with patch("socket.getaddrinfo", return_value=fake_addrinfo), \
         patch("tempfile.TemporaryDirectory", new=TrackedTempDir):

        # Mock yt_dlp so YoutubeDL raises an error
        yt_dlp_mock = MagicMock()
        yt_dlp_mock.YoutubeDL.side_effect = RuntimeError("yt-dlp failed")
        with patch.dict("sys.modules", {"yt_dlp": yt_dlp_mock}):
            res = await ingest_social_media("https://www.instagram.com/reel/test/")
            assert res["text"] == ""
            assert "error" in res

        # Ensure any created temp directories were fully deleted
        assert created_dirs
        for d in created_dirs:
            assert not os.path.exists(d), f"Temporary directory {d} was not cleaned up!"


# ---------------------------------------------------------------------------
# 4. GraphRAG Traversal Bounding & Concurrency Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_graphrag_concurrency_semaphore():
    """Verify that GraphRAGFusion limits concurrent retrieve calls to max_concurrency."""
    max_concurrent_observed = 0
    current_concurrent = 0
    lock = asyncio.Lock()

    async def slow_vector(q, k):
        nonlocal max_concurrent_observed, current_concurrent
        async with lock:
            current_concurrent += 1
            if current_concurrent > max_concurrent_observed:
                max_concurrent_observed = current_concurrent
        await asyncio.sleep(0.05)
        async with lock:
            current_concurrent -= 1
        return [{"id": "v1", "text": "vector result", "score": 0.9, "source": "doc:1"}]

    async def noop_entities(q):
        return []

    async def noop_graph(uris, hops):
        return []

    # Configure max concurrency of 2
    fusion = GraphRAGFusion(
        slow_vector,
        noop_entities,
        noop_graph,
        max_concurrency=2,
        per_traversal_timeout=5.0,
        total_timeout=10.0,
    )

    # Launch 6 concurrent retrievals
    tasks = [asyncio.create_task(fusion.retrieve(f"q_{i}")) for i in range(6)]
    results = await asyncio.gather(*tasks)

    assert len(results) == 6
    assert max_concurrent_observed <= 2, f"Expected concurrency <= 2, got {max_concurrent_observed}"


@pytest.mark.asyncio
async def test_graphrag_per_traversal_timeout():
    """Verify that a slow vector search or graph traversal times out gracefully without crashing."""
    async def hanging_vector(q, k):
        await asyncio.sleep(10.0)  # Hang longer than per_traversal_timeout
        return [{"id": "v1", "text": "should never arrive", "score": 0.9}]

    async def fast_entities(q):
        return ["https://askmukthiguru.org/concept/peace"]

    async def fast_graph(uris, hops):
        return [{"uri": uris[0], "text": "Inner peace is stillness", "relation": "DEFINES", "hop": 1}]

    fusion = GraphRAGFusion(
        hanging_vector,
        fast_entities,
        fast_graph,
        per_traversal_timeout=0.1,  # 100ms per traversal timeout
        total_timeout=2.0,
    )

    ctx = await fusion.retrieve("What is peace?")
    # Vector timed out, but graph succeeded -> safe partial recovery
    assert isinstance(ctx, FusedContext)
    assert len(ctx.items) >= 1
    assert any("Inner peace is stillness" in it.text for it in ctx.items)


@pytest.mark.asyncio
async def test_graphrag_aggregate_deadline_and_subtask_cancellation():
    """Verify that when aggregate deadline expires, subtasks are cancelled and partial results returned."""
    vector_cancelled = False
    graph_cancelled = False

    async def fast_vector(q, k):
        await asyncio.sleep(0.01)
        return [{"id": "v1", "text": "Breath calms mind", "score": 0.9, "source": "doc:1"}]

    async def hanging_entities(q):
        nonlocal graph_cancelled
        try:
            await asyncio.sleep(10.0)
            return ["uri:test"]
        except asyncio.CancelledError:
            graph_cancelled = True
            raise

    async def noop_graph(uris, hops):
        return []

    fusion = GraphRAGFusion(
        fast_vector,
        hanging_entities,
        noop_graph,
        per_traversal_timeout=10.0,
        total_timeout=0.1,  # 100ms aggregate deadline
    )

    ctx = await fusion.retrieve("test question")
    assert isinstance(ctx, FusedContext)
    # The hanging graph task should have received cancellation
    assert graph_cancelled is True
    # Fast vector completed before aggregate deadline and was safely recovered
    assert any("Breath calms mind" in it.text for it in ctx.items)
