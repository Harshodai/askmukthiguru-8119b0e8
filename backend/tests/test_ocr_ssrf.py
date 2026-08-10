"""
OCR SSRF protections (P1-SEC-2): DNS-rebinding-safe resolution + 25MB download cap.

Pure unit tests — no network or Docker. DNS resolution and the httpx client
are mocked; the SSRF-guarding network backend is exercised directly so the
connection-time pinning behavior is verified against real code.
"""

import socket
from unittest.mock import patch

import httpx
import pytest

from services import ocr_service
from services.ocr_service import SSRFBlockingNetworkBackend


# getaddrinfo returns 5-tuples: (family, type, proto, canonname, sockaddr)
def _addrinfo(ip: str) -> list:
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 443))]


class _RecordingBackend:
    """Fake parent network backend: records the host it was asked to connect to."""

    def __init__(self):
        self.connected_hosts = []

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        self.connected_hosts.append(host)
        return object()


class _FakeClient:
    """Async context manager standing in for httpx.AsyncClient (no network)."""

    def __init__(self, response: httpx.Response):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def get(self, url, **kwargs):
        return self._response


def _image_response(url: str, headers: dict, content: bytes) -> httpx.Response:
    return httpx.Response(200, headers=headers, content=content, request=httpx.Request("GET", url))


@pytest.mark.asyncio
async def test_private_ip_rejected():
    """Loopback resolution must be rejected at connection time."""
    backend = SSRFBlockingNetworkBackend(parent=_RecordingBackend())
    with patch("services.ocr_service.socket.getaddrinfo", return_value=_addrinfo("127.0.0.1")):
        with pytest.raises(ValueError, match="private/internal"):
            await backend.connect_tcp("evil.example.com", 443)


@pytest.mark.asyncio
async def test_metadata_endpoint_rejected():
    """Cloud metadata endpoint (link-local) must be rejected at connection time."""
    backend = SSRFBlockingNetworkBackend(parent=_RecordingBackend())
    with patch("services.ocr_service.socket.getaddrinfo", return_value=_addrinfo("169.254.169.254")):
        with pytest.raises(ValueError, match="private/internal"):
            await backend.connect_tcp("evil.example.com", 443)


@pytest.mark.asyncio
async def test_dns_rebinding_rejected():
    """First resolution public, second private (classic rebinding): the connection
    pins the first public IP and DNS is resolved exactly once — the window where
    a second resolution could land on a private address never opens."""
    parent = _RecordingBackend()
    backend = SSRFBlockingNetworkBackend(parent=parent)
    with patch(
        "services.ocr_service.socket.getaddrinfo",
        side_effect=[_addrinfo("93.184.216.34"), _addrinfo("169.254.169.254")],
    ) as getaddrinfo:
        await backend.connect_tcp("example.com", 443)
    assert parent.connected_hosts == ["93.184.216.34"]
    assert getaddrinfo.call_count == 1


@pytest.mark.asyncio
async def test_large_download_rejected():
    """A declared Content-Length above the 25MB cap must abort the download."""
    response = _image_response(
        "https://example.com/image.png",
        {"Content-Type": "image/png", "Content-Length": str(100 * 1024 * 1024)},
        b"x",
    )
    with (
        patch("services.ocr_service.httpx.AsyncClient", return_value=_FakeClient(response)),
        patch.object(ocr_service.OCRService, "_extract_from_file", return_value={"error": "unexpected success path"}),
    ):
        result = await ocr_service.OCRService().extract_text_from_url("https://example.com/image.png")
    assert result["error"]
    assert "too large" in result["error"].lower()


@pytest.mark.asyncio
async def test_stream_cap_enforced():
    """A stream without Content-Length must be cut off once the cap is exceeded."""
    response = _image_response(
        "https://example.com/image.png",
        {"Content-Type": "image/png"},
        b"x" * (8192 * 3),
    )
    with (
        patch("services.ocr_service.httpx.AsyncClient", return_value=_FakeClient(response)),
        patch("services.ocr_service.MAX_IMAGE_BYTES", 8192),
        patch.object(ocr_service.OCRService, "_extract_from_file", return_value={"error": "unexpected success path"}),
    ):
        result = await ocr_service.OCRService().extract_text_from_url("https://example.com/image.png")
    assert result["error"]
    assert "too large" in result["error"].lower()


@pytest.mark.asyncio
async def test_octet_stream_rejected_without_opt_in():
    """application/octet-stream must be rejected unless the caller opts in."""
    response = _image_response(
        "https://example.com/image.bin",
        {"Content-Type": "application/octet-stream"},
        b"x",
    )
    with (
        patch("services.ocr_service.httpx.AsyncClient", return_value=_FakeClient(response)),
        patch.object(ocr_service.OCRService, "_extract_from_file", return_value={"error": "unexpected success path"}),
    ):
        result = await ocr_service.OCRService().extract_text_from_url("https://example.com/image.bin")
    assert "does not point to an image" in result["error"]
