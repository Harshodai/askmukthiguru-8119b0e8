"""
Mukthi Guru — Centralized HTTP Client Pool

Provides a global AsyncClient with connection limits, shared across all
services that make outbound HTTP calls (Ollama, Sarvam, OCR, Auth).

Usage:
    from services.http_client_pool import get_client, aclose, lifespan

    # In service code
    client = get_client()
    resp = await client.get(url)

    # In FastAPI lifespan
    @asynccontextmanager
    async def lifespan(app):
        yield
        await aclose()
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

from anyio import Lock as AsyncLock
import httpx

logger = logging.getLogger(__name__)

# Global singleton
_client: Optional[httpx.AsyncClient] = None
_lock = AsyncLock()

from app.config import settings

_max_conn = settings.http_pool_max_connections
_max_keep = settings.http_pool_max_keepalive

DEFAULT_LIMITS = httpx.Limits(
    max_connections=_max_conn,
    max_keepalive_connections=_max_keep,
)



async def get_client() -> httpx.AsyncClient:
    """Get or create the global AsyncClient."""
    global _client
    if _client is None:
        async with _lock:
            if _client is None:
                _client = httpx.AsyncClient(limits=DEFAULT_LIMITS, timeout=30.0)
                logger.info(f"HTTP client pool initialized (max_connections={_max_conn}, keepalive={_max_keep})")
    return _client


async def aclose() -> None:
    """Close the global AsyncClient. Call on application shutdown."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
        logger.info("HTTP client pool closed")


@asynccontextmanager
async def lifespan(app):
    """FastAPI lifespan context manager."""
    try:
        yield
    finally:
        await aclose()
