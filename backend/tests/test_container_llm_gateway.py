"""Tests for One LLM Gateway & container.ollama rename (T7-03 / CQ-002, CQ-014, AI-005).

Verifies:
1. ServiceContainer exposes `llm` as the canonical provider and `ollama` as a backward-compatible alias.
2. Mutating container.ollama updates container.llm and vice versa.
3. LLMGateway provides `generate_fast` for latency-critical paths.
4. LLMGateway provides `stream` as an async generator over tokens.
"""

from unittest.mock import MagicMock

import pytest

from app.coalescer import _InMemoryCoalescer
from app.container import ServiceContainer
from services.llm_gateway import LLMGateway


class _FakeProvider:
    def __init__(self, name="fake"):
        self.name = name
        self.calls: list[dict] = []

    async def generate(self, system_prompt, user_prompt, context="", **kwargs):
        self.calls.append({"system": system_prompt, "user": user_prompt, **kwargs})
        return f"{self.name}:{user_prompt}"

    async def generate_fast(self, system_prompt, user_prompt, context="", **kwargs):
        self.calls.append({"fast": True, "system": system_prompt, "user": user_prompt, **kwargs})
        return f"{self.name}:fast:{user_prompt}"

    async def generate_stream(self, system_prompt, user_prompt, context="", **kwargs):
        for word in user_prompt.split():
            yield f"{word} "


@pytest.mark.asyncio
async def test_container_llm_and_ollama_property():
    container = ServiceContainer.__new__(ServiceContainer)
    mock_llm = MagicMock()
    container.llm = mock_llm

    # Reading ollama returns llm
    assert container.ollama is mock_llm

    # Writing ollama updates llm
    new_mock = MagicMock()
    container.ollama = new_mock
    assert container.llm is new_mock
    assert container.ollama is new_mock


@pytest.mark.asyncio
async def test_llm_gateway_generate_fast():
    provider = _FakeProvider("provider")
    coalescer = _InMemoryCoalescer(ttl=5.0)
    gw = LLMGateway(primary=provider, coalescer=coalescer)

    res = await gw.generate_fast("sys", "fast question")
    assert res == "provider:fast:fast question"
    assert len(provider.calls) == 1
    assert provider.calls[0]["fast"] is True


@pytest.mark.asyncio
async def test_llm_gateway_stream():
    provider = _FakeProvider("provider")
    coalescer = _InMemoryCoalescer(ttl=5.0)
    gw = LLMGateway(primary=provider, coalescer=coalescer)

    chunks = []
    async for chunk in gw.stream("sys", "peace and stillness"):
        chunks.append(chunk)

    assert "".join(chunks).strip() == "peace and stillness"
