"""B23 (2026-09-12 latency audit): rewrite_query was the only CRAG helper still
calling the main model while every sibling (decompose_query, batch grader,
faithfulness check, HyDE) uses the fast model -- measured at ~20-25s/call,
~40% of a failing comparative query's latency.

rag_rewrite_query_fast_model (default False) lets this be A/B tested without
changing default generation behavior until a rewrite-quality regression check
is run (docs/RUTHLESS_PRODUCTION_EXECUTION.md B23). Both LLM service classes
need the same branch: OllamaService (LLM_PROVIDER=ollama) and
SarvamCloudService (LLM_PROVIDER=sarvam_cloud, the live default per
CLAUDE.md) are separate, non-inheriting implementations -- an earlier version
of this fix only patched OllamaService and had zero effect on the live
sarvam_cloud deployment. This pins both classes' branches: default False must
still call the main model (byte-identical old behavior), True must route to
the fast model instead.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from services.ollama_service import OllamaService
from services.openrouter_service import OpenRouterService
from services.sarvam_service import SarvamCloudService


def _ollama_svc():
    settings.ollama_cloud_only = False
    return OllamaService()


def _sarvam_svc(monkeypatch):
    monkeypatch.setattr(settings, "sarvam_api_key", "test-key")
    monkeypatch.setattr(settings, "sarvam_cloud_model", "sarvam-105b")
    monkeypatch.setattr(settings, "sarvam_cloud_classify_model", "sarvam-105b")
    monkeypatch.setattr(settings, "llm_max_retries", 1)
    return SarvamCloudService()


@pytest.mark.asyncio
async def test_ollama_rewrite_query_uses_main_model_by_default():
    svc = _ollama_svc()
    settings.rag_rewrite_query_fast_model = False
    with patch.object(svc, "generate", new=AsyncMock(return_value="rewritten")) as mock_generate, \
         patch.object(svc, "_generate_fast", new=AsyncMock(return_value="rewritten")) as mock_fast:
        result = await svc.rewrite_query("original query")

    assert result == "rewritten"
    mock_generate.assert_awaited_once()
    mock_fast.assert_not_awaited()


@pytest.mark.asyncio
async def test_ollama_rewrite_query_uses_fast_model_when_flag_enabled():
    svc = _ollama_svc()
    settings.rag_rewrite_query_fast_model = True
    try:
        with patch.object(svc, "generate", new=AsyncMock(return_value="rewritten")) as mock_generate, \
             patch.object(svc, "_generate_fast", new=AsyncMock(return_value="rewritten")) as mock_fast:
            result = await svc.rewrite_query("original query")

        assert result == "rewritten"
        mock_fast.assert_awaited_once()
        mock_generate.assert_not_awaited()
    finally:
        settings.rag_rewrite_query_fast_model = False


@pytest.mark.asyncio
async def test_sarvam_rewrite_query_uses_main_model_by_default(monkeypatch):
    svc = _sarvam_svc(monkeypatch)
    settings.rag_rewrite_query_fast_model = False
    with patch.object(svc, "generate", new=AsyncMock(return_value="rewritten")) as mock_generate, \
         patch.object(svc, "_generate_fast", new=AsyncMock(return_value="rewritten")) as mock_fast:
        result = await svc.rewrite_query("original query")

    assert result == "rewritten"
    mock_generate.assert_awaited_once()
    mock_fast.assert_not_awaited()


@pytest.mark.asyncio
async def test_sarvam_rewrite_query_uses_fast_model_when_flag_enabled(monkeypatch):
    svc = _sarvam_svc(monkeypatch)
    settings.rag_rewrite_query_fast_model = True
    try:
        with patch.object(svc, "generate", new=AsyncMock(return_value="rewritten")) as mock_generate, \
             patch.object(svc, "_generate_fast", new=AsyncMock(return_value="rewritten")) as mock_fast:
            result = await svc.rewrite_query("original query")

        assert result == "rewritten"
        mock_fast.assert_awaited_once()
        mock_generate.assert_not_awaited()
    finally:
        settings.rag_rewrite_query_fast_model = False


def _openrouter_svc(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(settings, "openrouter_generation_model", "deepseek/deepseek-chat")
    monkeypatch.setattr(settings, "openrouter_generation_model_fallback", "meta-llama/llama-3.3-70b-instruct")
    monkeypatch.setattr(settings, "openrouter_classify_model", "meta-llama/llama-3.1-8b-instruct")
    monkeypatch.setattr(settings, "openrouter_fast_model", "meta-llama/llama-3.1-8b-instruct")
    monkeypatch.setattr(settings, "openrouter_policy_id", "test-policy")
    monkeypatch.setattr(settings, "openrouter_enforce_model_policy", False)
    return OpenRouterService()


@pytest.mark.asyncio
async def test_openrouter_rewrite_query_uses_main_model_by_default(monkeypatch):
    svc = _openrouter_svc(monkeypatch)
    settings.rag_rewrite_query_fast_model = False
    with patch.object(svc, "generate", new=AsyncMock(return_value="rewritten")) as mock_generate, \
         patch.object(svc, "_generate_fast", new=AsyncMock(return_value="rewritten")) as mock_fast:
        result = await svc.rewrite_query("original query")

    assert result == "rewritten"
    mock_generate.assert_awaited_once()
    mock_fast.assert_not_awaited()


@pytest.mark.asyncio
async def test_openrouter_rewrite_query_uses_fast_model_when_flag_enabled(monkeypatch):
    svc = _openrouter_svc(monkeypatch)
    settings.rag_rewrite_query_fast_model = True
    try:
        with patch.object(svc, "generate", new=AsyncMock(return_value="rewritten")) as mock_generate, \
             patch.object(svc, "_generate_fast", new=AsyncMock(return_value="rewritten")) as mock_fast:
            result = await svc.rewrite_query("original query")

        assert result == "rewritten"
        mock_fast.assert_awaited_once()
        mock_generate.assert_not_awaited()
    finally:
        settings.rag_rewrite_query_fast_model = False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
