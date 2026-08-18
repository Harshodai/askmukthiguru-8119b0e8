"""Regression coverage for awaitable service shutdown methods."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.lifecycle import close_container_async


@pytest.mark.asyncio
async def test_async_service_close_is_awaited() -> None:
    closed: list[str] = []

    async def close_krutrim() -> None:
        closed.append("krutrim")

    container = SimpleNamespace(
        rag_graph=None,
        ingestion=None,
        guardrails=None,
        ocr=None,
        ollama=None,
        embedding=None,
        qdrant=None,
        user_profile=None,
        krutrim=SimpleNamespace(close=close_krutrim),
        _neo4j_driver=None,
    )

    await close_container_async(container)

    assert closed == ["krutrim"]
