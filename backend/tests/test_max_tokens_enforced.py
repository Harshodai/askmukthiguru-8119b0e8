"""P1-AI-1 tests — max_tokens + stop sequences enforced on every LLM call.

Covers the LLM gateway (fast/deep route ceilings, caller-capping, streaming,
verify) and the SRS flashcard call. Fakes only — no network, no real
providers, mirroring tests/test_llm_gateway.py and tests/test_srs_service.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.coalescer import _InMemoryCoalescer
from app.config import settings
from services.llm_gateway import LLMGateway


class _RecordingProvider:
    """LLMProvider-shaped fake that records kwargs per call."""

    def __init__(self, name="rec"):
        self.name = name
        self.calls: list[dict] = []

    async def generate(self, system_prompt, user_prompt, context="", **kwargs):
        self.calls.append({"system_prompt": system_prompt, "user_prompt": user_prompt, **kwargs})
        return f"{self.name}:{user_prompt}"

    async def generate_stream(self, system_prompt, user_prompt, context="", **kwargs):
        self.calls.append({"system_prompt": system_prompt, "user_prompt": user_prompt, **kwargs})
        yield "chunk"

    async def verify_answer(self, *, answer: str, context: str, **kwargs):
        self.calls.append({"answer": answer, "context": context, **kwargs})
        return {"is_faithful": True, "passed": True, "confidence": 8.0, "details": "ok"}


def _gateway(primary, **kw) -> LLMGateway:
    coalescer = kw.pop("coalescer", None) or _InMemoryCoalescer(ttl=5.0)
    return LLMGateway(primary=primary, coalescer=coalescer, **kw)


@pytest.fixture
def fast_deep_ceilings(monkeypatch):
    """Pin the config ceilings so assertions do not depend on .env values."""
    monkeypatch.setattr(settings, "llm_max_tokens_fast", 800)
    monkeypatch.setattr(settings, "llm_max_tokens_deep", 1500)


@pytest.mark.asyncio
async def test_gateway_fast_route_defaults_to_fast_ceiling(fast_deep_ceilings):
    """A caller that passes no max_tokens must get the fast ceiling, never None."""
    primary = _RecordingProvider()
    gw = _gateway(primary)

    await gw.generate("sys", "hi", task="standard")

    assert primary.calls[0]["max_tokens"] == 800


@pytest.mark.asyncio
async def test_gateway_deep_route_defaults_to_deep_ceiling(fast_deep_ceilings):
    """deep task must default to the deep ceiling, not the fast one."""
    primary = _RecordingProvider()
    gw = _gateway(primary)

    await gw.generate("sys", "hi", task="deep")

    assert primary.calls[0]["max_tokens"] == 1500


@pytest.mark.asyncio
async def test_gateway_caps_caller_requested_max_tokens(fast_deep_ceilings):
    """A caller requesting more than the route ceiling must be capped down (min)."""
    primary = _RecordingProvider()
    gw = _gateway(primary)

    await gw.generate("sys", "hi", task="standard", max_tokens=4000)

    assert primary.calls[0]["max_tokens"] == 800


@pytest.mark.asyncio
async def test_gateway_keeps_smaller_caller_max_tokens(fast_deep_ceilings):
    """A caller requesting less than the ceiling keeps its smaller value."""
    primary = _RecordingProvider()
    gw = _gateway(primary)

    await gw.generate("sys", "hi", task="deep", max_tokens=300)

    assert primary.calls[0]["max_tokens"] == 300


@pytest.mark.asyncio
async def test_gateway_streaming_route_enforces_max_tokens(fast_deep_ceilings):
    """The uncached streaming path must be bounded just like generate()."""
    primary = _RecordingProvider()
    gw = _gateway(primary)

    chunks = [c async for c in gw.generate_stream("sys", "hi", task="standard", use_cache=False)]

    assert chunks == ["chunk"]
    assert primary.calls[0]["max_tokens"] == 800


@pytest.mark.asyncio
async def test_gateway_verify_answer_is_bounded(fast_deep_ceilings):
    """verify_answer must pass a bounded max_tokens, never an unbounded call."""
    primary = _RecordingProvider()
    gw = _gateway(primary)

    result = await gw.verify_answer(answer="a", context="c")

    assert result["is_faithful"] is True
    assert primary.calls[0]["max_tokens"] == min(settings.llm_max_tokens_fast, 512)


@pytest.mark.asyncio
async def test_srs_flashcard_generation_passes_max_tokens_400():
    """The SRS flashcard LLM call must carry max_tokens=400 (short JSON output)."""
    mock_supabase = MagicMock()
    mock_ollama = AsyncMock()
    mock_ollama.generate.return_value = (
        '[{"question": "Q1?", "answer": "A1"}, {"question": "Q2?", "answer": "A2"}]'
    )
    mock_insert_resp = MagicMock()
    mock_insert_resp.data = [{"id": "card-1"}, {"id": "card-2"}]
    mock_supabase.table.return_value.insert.return_value.execute = MagicMock(
        return_value=mock_insert_resp
    )

    from services.srs_service import SRSService

    service = SRSService(mock_supabase, mock_ollama)
    cards = await service.generate_cards_from_notebook_item(
        "user-1", query="What is breath awareness?", answer="Focus on the breath.", source_id="n1"
    )

    assert len(cards) == 2
    kwargs = mock_ollama.generate.call_args.kwargs
    assert kwargs["max_tokens"] == 400


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-q"]))


@pytest.mark.asyncio
async def test_gateway_secondary_verify_keeps_the_bounded_token_ceiling(fast_deep_ceilings):
    """Fallback verification must receive the same bounded token ceiling."""
    primary = _RecordingProvider("primary")
    primary.verify_answer = AsyncMock(side_effect=RuntimeError("primary unavailable"))
    secondary = _RecordingProvider("secondary")
    gw = _gateway(
        primary,
        secondary=secondary,
        cross_provider_fallback_enabled=True,
    )

    result = await gw.verify_answer(answer="a", context="c")

    assert result["is_faithful"] is True
    assert secondary.calls[0]["max_tokens"] == min(settings.llm_max_tokens_fast, 512)
