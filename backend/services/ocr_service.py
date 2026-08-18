"""
Mukthi Guru — OCR Service

Design Patterns:
  - Adapter Pattern: Wraps EasyOCR behind a simple interface
  - Lazy Loading: EasyOCR reader initialized on first call (heavy model)
  - Strategy Pattern: URL vs file path input handling
  - Thread-safe: Reader initialization uses a lock

Supports: English, Hindi, Telugu (configurable via OCR_LANGUAGES env var)
Runs on CPU to leave GPU free for the LLM.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import socket
import tempfile
import threading
import typing
from urllib.parse import urlparse

import httpcore
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Mirror speech.py's 25MB upload cap: images larger than this are rejected
# to prevent disk-exhaustion DoS via an unbounded download stream.
MAX_IMAGE_BYTES = 25 * 1024 * 1024


def _resolve_public_ip(hostname: str) -> str | None:
    """
    Resolve a hostname once and return the first public IP address.

    Raises ValueError if any resolved address is private, loopback, reserved,
    or link-local (e.g. 169.254.169.254 metadata endpoint). Returns None if
    the hostname cannot be resolved.
    """
    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return None
    public_ip = None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
            raise ValueError(f"URL resolves to a private/internal address: {ip}")
        if public_ip is None:
            public_ip = str(ip)
    return public_ip


class SSRFBlockingNetworkBackend(httpcore.AsyncNetworkBackend):
    """
    httpcore network backend that closes the DNS-rebinding (TOCTOU) window.

    The hostname is resolved exactly once inside ``connect_tcp``, validated
    against private/loopback/reserved/link-local ranges, and the connection is
    pinned to the first public IP — httpx never re-resolves the hostname, so a
    second resolution (e.g. to 169.254.169.254) cannot be observed by the
    caller. TLS certificate verification still runs against the original
    hostname (httpcore passes the request's SNI hostname to ``start_tls``).
    """

    def __init__(self, parent: httpcore.AsyncNetworkBackend | None = None) -> None:
        self._parent = parent or httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: typing.Iterable[tuple] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        if not host:
            raise ValueError("URL has no hostname")
        ip = _resolve_public_ip(host)
        if ip is None:
            raise ValueError(f"Cannot resolve hostname: {host}")
        return await self._parent.connect_tcp(
            ip, port, timeout=timeout, local_address=local_address, socket_options=socket_options
        )

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: typing.Iterable[tuple] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        return await self._parent.connect_unix_socket(path, timeout=timeout, socket_options=socket_options)

    async def sleep(self, seconds: float) -> None:
        return await self._parent.sleep(seconds)


class SSRFBlockingTransport(httpx.AsyncHTTPTransport):
    """
    AsyncHTTPTransport whose connection pool uses the SSRF-guarding network
    backend, so every hostname is resolved and validated at connection time.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        limits = kwargs.get("limits", httpx.Limits())
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=httpx.create_ssl_context(
                verify=kwargs.get("verify", True),
                cert=kwargs.get("cert", None),
                trust_env=kwargs.get("trust_env", True),
            ),
            max_connections=limits.max_connections,
            max_keepalive_connections=limits.max_keepalive_connections,
            keepalive_expiry=limits.keepalive_expiry,
            http1=kwargs.get("http1", True),
            http2=kwargs.get("http2", False),
            retries=kwargs.get("retries", 0),
            local_address=kwargs.get("local_address", None),
            uds=kwargs.get("uds", None),
            network_backend=SSRFBlockingNetworkBackend(),
            socket_options=kwargs.get("socket_options", None),
        )


class OCRService:
    """
    Extract text from images using EasyOCR.

    Lazy-loaded: The EasyOCR reader (~200MB) is only loaded when
    the first OCR request comes in. This saves memory if OCR is never used.

    Thread-safe: Uses a lock around reader initialization to prevent
    double-loading in concurrent request scenarios.
    """

    def __init__(self) -> None:
        """Initialize with None reader — will be loaded on first use."""
        self._reader = None
        self._reader_lock = threading.Lock()
        self._languages = settings.ocr_languages_list
        logger.info(f"OCR service initialized (lazy load). Languages: {self._languages}")

    def _ensure_reader(self) -> None:
        """
        Lazy-load the EasyOCR reader on first use.

        Thread-safe: Double-checked locking ensures only one reader is created
        even if multiple threads call this concurrently.
        """
        if self._reader is not None:
            return
        with self._reader_lock:
            if self._reader is None:
                import easyocr

                logger.info(f"Loading EasyOCR reader for: {self._languages}")
                self._reader = easyocr.Reader(
                    self._languages,
                    gpu=False,  # CPU only — GPU reserved for LLM
                    model_storage_directory="/app/.cache/easyocr",
                )
                logger.info("EasyOCR reader loaded")

    async def extract_text_from_url(self, image_url: str, allow_octet_stream: bool = False) -> dict:
        """
        Download an image from URL and extract text via OCR.

        Args:
            image_url: HTTP(S) URL to an image (JPG, PNG, WEBP)
            allow_octet_stream: Accept ``application/octet-stream`` responses
                (off by default — only explicit callers may opt in)

        Returns:
            Dict with 'text', 'source_url', 'content_type', 'confidence'

        SSRF note: connections go through ``SSRFBlockingTransport``, which
        resolves the hostname once and pins the socket to the first public IP
        at connection time. The legacy separate check-then-connect pattern had
        a DNS-rebinding (TOCTOU) window — it is gone.
        """
        logger.info(f"OCR: downloading {image_url}")

        # SSRF protection: validate URL scheme and block private/internal addresses
        parsed = urlparse(image_url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")
        tmp_path = None

        try:
            async with httpx.AsyncClient(transport=SSRFBlockingTransport(), timeout=30.0) as client:
                response = await client.get(image_url, timeout=30.0)
                response.raise_for_status()

                # Validate content type
                content_type = response.headers.get("content-type", "")
                base_type = content_type.split(";")[0].strip().lower()
                if not base_type.startswith("image/") and not (
                    allow_octet_stream and base_type == "application/octet-stream"
                ):
                    raise ValueError(f"URL does not point to an image: {content_type}")

                # Reject oversized downloads before streaming begins
                content_length = response.headers.get("content-length", "")
                if content_length.isdigit() and int(content_length) > MAX_IMAGE_BYTES:
                    raise ValueError(f"Image too large. Maximum size is {MAX_IMAGE_BYTES // (1024 * 1024)}MB.")

                # Save to temp file for EasyOCR, enforcing the cap mid-stream too
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    tmp_path = tmp.name
                    total = 0
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        total += len(chunk)
                        if total > MAX_IMAGE_BYTES:
                            raise ValueError(
                                f"Image too large. Maximum size is {MAX_IMAGE_BYTES // (1024 * 1024)}MB."
                            )
                        tmp.write(chunk)

            # Run ML inference in a separate thread so we don't block the asyncio event loop
            return await asyncio.to_thread(self._extract_from_file, tmp_path, image_url)

        except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as e:
            logger.error(f"Failed to download/validate image: {e}")
            return {
                "text": "",
                "source_url": image_url,
                "content_type": "image",
                "confidence": 0.0,
                "error": str(e),
            }
        finally:
            # Clean up temp file regardless of success/failure
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    async def extract_text_from_file(self, file_path: str) -> dict:
        """
        Extract text from a local image file.

        Args:
            file_path: Path to image file

        Returns:
            Dict with 'text', 'source_url', 'content_type', 'confidence'
        """
        # Run ML inference in a separate thread
        return await asyncio.to_thread(self._extract_from_file, file_path, f"file://{file_path}")

    def _extract_from_file(self, file_path: str, source_url: str = "") -> dict:
        """
        Internal: Run EasyOCR on a file path.

        Returns structured result with text and confidence score.
        """
        self._ensure_reader()

        try:
            results = self._reader.readtext(file_path, detail=1)

            # results = [(bbox, text, confidence), ...]
            texts = []
            confidences = []
            for _bbox, text, conf in results:
                if text.strip():
                    texts.append(text.strip())
                    confidences.append(conf)

            combined_text = " ".join(texts)
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

            logger.info(
                f"OCR extracted {len(texts)} text segments, avg confidence: {avg_confidence:.2f}"
            )

            return {
                "text": combined_text,
                "source_url": source_url,
                "content_type": "image",
                "confidence": avg_confidence,
            }

        except Exception as e:
            logger.error(f"OCR extraction failed: {e}")
            return {
                "text": "",
                "source_url": source_url,
                "content_type": "image",
                "confidence": 0.0,
                "error": str(e),
            }

    def health_check(self) -> bool:
        """Check if EasyOCR can be imported (don't load the model for health check)."""
        import importlib.util

        return importlib.util.find_spec("easyocr") is not None
