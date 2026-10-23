"""Unit tests for Model Strategy, TypeSafe Jev Routing, Prompt Caching, and Multilingual Reranker.

Covers:
1. TypeSafe Jev structured router wiring, default/config enablement, and clean fallback
   to fast classifiers (Qwen2.5-1.5B-Instruct / Llama-3.1-8b-instruct).
2. Sarvam models on OpenRouter (sarvamai/sarvam-m) and Sarvam Cloud API.
3. Prompt caching headers (X-OpenRouter-Cache, HTTP-Referer, X-Title) and prefix caching
   discount calculations (DeepSeek-V3 80% discount: $0.14 input, $0.028 cached input).
4. Cost-effective model presets (DeepSeek-V3, Gemini Flash, Sarvam-M).
5. Multilingual Reranker (Alibaba-NLP/gte-multilingual-reranker-base) ONNX INT8 support.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from app.config import settings
from app.model_policy import OpenRouterModelPolicy
from rag.nodes import intent as intent_module
from services.llm.factory import LLMProviderFactory
from services.llm.openrouter_provider import OpenRouterProvider
from services.onnx_reranker import (
    _GTE_MULTILINGUAL_RERANKER_ID,
    _ONNX_RERANKER_MODEL_ID,
    _SUPPORTED_ONNX_RERANKERS,
    OnnxReranker,
)
from services.openrouter_service import (
    _OPENROUTER_CACHED_INPUT_RATES_PER_MILLION,
    _OPENROUTER_FALLBACK_RATES_PER_MILLION,
    OpenRouterService,
)
from services.reranker_service import RerankerService


@pytest.fixture(autouse=True)
def _disable_budget_guard(monkeypatch):
    """Disable budget guard to avoid Redis connections in isolated tests."""
    monkeypatch.setattr(settings, "openrouter_budget_guard_enabled", False)


# ============================================================================
# 1. TypeSafe Jev Structured Router & Fast Classifier Fallback
# ============================================================================


class TestJevRouterWiringAndFallback:
    def test_jev_enabled_by_default(self):
        """intent_router_jev_enabled should be enabled by default or configurable via config."""
        assert settings.intent_router_jev_enabled is True
        assert settings.intent_router_jev_model == "typesafe/jev-1.14"
        assert settings.intent_router_jev_confidence_threshold == 0.70

    @pytest.mark.asyncio
    async def test_jev_success_routes_directly(self, monkeypatch):
        """When Jev succeeds with high confidence, intent is classified without LLM fallback."""
        intent_module._intent_classification_cache.clear()
        monkeypatch.setattr(settings, "intent_router_jev_enabled", True)
        monkeypatch.setattr(settings, "use_semantic_router", False)
        monkeypatch.setattr(settings, "openrouter_api_key", "sk-test-mock-key")

        mock_decision = {
            "intent": "FACTUAL",
            "query_tier": "tier2_simple",
            "confidence": 0.95,
            "needs_web_search": False,
            "model": "typesafe/jev-1.14",
            "routing_reason": "jev_router_typesafe/jev-1.14",
        }

        with (
            patch(
                "services.jev_router_service.JevRouterService.classify", new_callable=AsyncMock
            ) as mock_classify,
            patch("rag.nodes.on_device_intent.classify_with_reason", return_value=None),
            patch("rag.intent_prerouter.preroute_intent", return_value=None),
        ):
            mock_classify.return_value = mock_decision
            state = {
                "question": "Can consciousness shift permanently into peace?",
                "messages": [],
                "chat_history": [],
            }
            res = await intent_module.intent_router(state)

            assert res["intent"] == "FACTUAL"
            assert res["query_tier"] == "tier2_simple"
            assert res["evaluation_trace"]["routing_reason"] == "jev_router"
            mock_classify.assert_awaited_once_with(
                "Can consciousness shift permanently into peace?"
            )

    @pytest.mark.asyncio
    async def test_jev_low_confidence_falls_back_to_fast_classifier(self, monkeypatch):
        """When Jev confidence is below threshold (< 0.70), it cleanly falls back to fast classifier."""
        intent_module._intent_classification_cache.clear()
        monkeypatch.setattr(settings, "intent_router_jev_enabled", True)
        monkeypatch.setattr(settings, "use_semantic_router", False)
        monkeypatch.setattr(settings, "openrouter_api_key", "sk-test-mock-key")

        mock_fast_classifier = AsyncMock()
        mock_fast_classifier.classify_intent_and_complexity.return_value = {
            "intent": "FACTUAL",
            "complexity": "simple",
        }
        mock_fast_classifier.model = "meta-llama/llama-3.1-8b-instruct"

        with (
            patch(
                "services.jev_router_service.JevRouterService.classify", new_callable=AsyncMock
            ) as mock_classify,
            patch("rag.nodes.on_device_intent.classify_with_reason", return_value=None),
            patch("rag.intent_prerouter.preroute_intent", return_value=None),
            patch.object(intent_module._services, "_ollama", mock_fast_classifier),
        ):
            # Jev returns None due to low confidence check in service
            mock_classify.return_value = None

            state = {
                "question": "Can consciousness shift permanently into peace?",
                "messages": [],
                "chat_history": [],
            }
            res = await intent_module.intent_router(state)

            assert res["intent"] == "FACTUAL"
            assert res["query_tier"] == "tier2_simple"
            assert res["evaluation_trace"]["routing_reason"] == "classifier"
            mock_fast_classifier.classify_intent_and_complexity.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_jev_network_failure_cleanly_falls_back(self, monkeypatch):
        """When Jev encounters a network error/exception, fallback to fast classifier is seamless."""
        intent_module._intent_classification_cache.clear()
        monkeypatch.setattr(settings, "intent_router_jev_enabled", True)
        monkeypatch.setattr(settings, "use_semantic_router", False)
        monkeypatch.setattr(settings, "openrouter_api_key", "sk-test-mock-key")

        mock_fast_classifier = AsyncMock()
        mock_fast_classifier.classify_intent_and_complexity.return_value = {
            "intent": "CASUAL",
            "complexity": "simple",
        }
        mock_fast_classifier.model = "qwen/qwen-2.5-1.5b-instruct"

        with (
            patch(
                "services.jev_router_service.JevRouterService.classify",
                side_effect=TimeoutError("Request timed out"),
            ),
            patch("rag.nodes.on_device_intent.classify_with_reason", return_value=None),
            patch("rag.intent_prerouter.preroute_intent", return_value=None),
            patch.object(intent_module._services, "_ollama", mock_fast_classifier),
        ):
            state = {
                "question": "I would like to share a casual observation with you",
                "messages": [],
                "chat_history": [],
            }
            res = await intent_module.intent_router(state)

            assert res["intent"] == "CASUAL"
            assert res["evaluation_trace"]["routing_reason"] == "classifier"
            mock_fast_classifier.classify_intent_and_complexity.assert_awaited_once()


# ============================================================================
# 2. Sarvam Models via OpenRouter & Sarvam Cloud API
# ============================================================================


class TestSarvamModelSupport:
    def test_sarvam_rates_registered_in_openrouter(self):
        """sarvamai/sarvam-m must have fallback accounting rates registered."""
        assert "sarvamai/sarvam-m" in _OPENROUTER_FALLBACK_RATES_PER_MILLION
        rate = _OPENROUTER_FALLBACK_RATES_PER_MILLION["sarvamai/sarvam-m"]
        assert rate[0] > 0.0  # input rate
        assert rate[1] > 0.0  # output rate

    def test_sarvam_model_in_openrouter_policy(self, monkeypatch):
        """OpenRouterModelPolicy must validate and allow sarvamai/sarvam-m."""
        monkeypatch.setattr(settings, "openrouter_generation_model", "sarvamai/sarvam-m")
        monkeypatch.setattr(
            settings, "openrouter_generation_model_fallback", "deepseek/deepseek-chat"
        )
        monkeypatch.setattr(settings, "openrouter_fast_model", "meta-llama/llama-3.1-8b-instruct")
        monkeypatch.setattr(
            settings, "openrouter_classify_model", "meta-llama/llama-3.1-8b-instruct"
        )

        policy = OpenRouterModelPolicy.from_settings(settings)
        policy.assert_model_allowed("sarvamai/sarvam-m")
        assert "sarvamai/sarvam-m" in policy.allowed_models

    def test_sarvam_m_preset_resolution(self, monkeypatch):
        """Setting openrouter_model_preset to 'sarvam-m' resolves generation and classification models."""
        monkeypatch.setattr(settings, "llm_provider", "openrouter")
        monkeypatch.setattr(settings, "openrouter_model_preset", "sarvam-m")

        assert settings.model_for_generation == "sarvamai/sarvam-m"
        assert settings.model_for_classification == "meta-llama/llama-3.1-8b-instruct"

    def test_llm_provider_factory_sarvam_cloud_and_openrouter(self):
        """LLMProviderFactory creates appropriate adapters for sarvam_cloud and openrouter."""
        with patch("services.llm_factory.LLMServiceFactory.create") as mock_factory:
            mock_factory.return_value = MagicMock()
            provider_sarvam = LLMProviderFactory.create_provider("sarvam_cloud")
            assert provider_sarvam is not None

            provider_openrouter = LLMProviderFactory.create_provider("openrouter")
            assert isinstance(provider_openrouter, OpenRouterProvider)


# ============================================================================
# 3. Prompt Caching & Cost-Effective Model Suite
# ============================================================================


class TestPromptCachingAndCostSuite:
    def test_openrouter_prompt_caching_config_defaults(self):
        """Prompt caching and identification headers must be enabled by default."""
        assert settings.openrouter_cache_enabled is True
        assert settings.openrouter_prompt_caching_enabled is True
        assert settings.openrouter_http_referer == "https://askmukthiguru.com"
        assert settings.openrouter_x_title == "AskMukthiGuru"

    def test_deepseek_prompt_caching_rate_discount(self):
        """DeepSeek prefix caching discount must be calculated (80% discount: $0.14 -> $0.028)."""
        model = "deepseek/deepseek-chat"
        assert model in _OPENROUTER_FALLBACK_RATES_PER_MILLION
        assert model in _OPENROUTER_CACHED_INPUT_RATES_PER_MILLION

        # Uncached cost: 1,000,000 in, 0 out = $0.14
        uncached_cost = OpenRouterService._fallback_cost(1_000_000, 0, model, cached_tokens=0)
        assert pytest.approx(uncached_cost, 0.001) == 0.14

        # Fully cached input cost: 1,000,000 in (all cached), 0 out = $0.028
        cached_cost = OpenRouterService._fallback_cost(1_000_000, 0, model, cached_tokens=1_000_000)
        assert pytest.approx(cached_cost, 0.001) == 0.028

        # 50% cached: 500k regular ($0.07) + 500k cached ($0.014) = $0.084
        half_cost = OpenRouterService._fallback_cost(1_000_000, 0, model, cached_tokens=500_000)
        assert pytest.approx(half_cost, 0.001) == 0.084

    def test_cost_effective_presets_defined(self):
        """Cost-effective presets (deepseek-v3, gemini-flash, sarvam-m) must be defined."""
        presets = settings.OPENROUTER_PRESETS
        assert "deepseek-v3" in presets
        assert "gemini-flash" in presets
        assert "sarvam-m" in presets

        assert presets["deepseek-v3"]["generation"] == "deepseek/deepseek-chat"
        assert presets["gemini-flash"]["generation"] == "google/gemini-2.0-flash-001"
        assert presets["sarvam-m"]["generation"] == "sarvamai/sarvam-m"

    @pytest.mark.asyncio
    async def test_openrouter_cache_headers_sent_in_api_call(self, monkeypatch):
        """_call_api must attach X-OpenRouter-Cache header when enabled."""
        monkeypatch.setattr(settings, "openrouter_api_key", "sk-mock-key")
        monkeypatch.setattr(settings, "openrouter_cache_enabled", True)

        service = OpenRouterService()
        captured_headers = {}

        class MockResponse:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "choices": [{"message": {"content": "Response content"}}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 50},
                }

        class MockClient:
            async def post(self, url, json=None, headers=None, **kwargs):
                nonlocal captured_headers
                captured_headers = headers or {}
                return MockResponse()

        async def mock_get_client(self):
            return MockClient()

        monkeypatch.setattr(OpenRouterService, "_get_http_client", mock_get_client)

        await service.generate("System prompt", "User query")
        assert captured_headers.get("X-OpenRouter-Cache") == "true"

    @pytest.mark.asyncio
    async def test_prompt_caching_switch_actually_disables_cache_control(self, monkeypatch):
        """Turning prompt caching off must stop cache_control markup and the beta header."""
        import json as _json

        monkeypatch.setattr(settings, "openrouter_api_key", "sk-mock-key")
        monkeypatch.setattr(settings, "openrouter_generation_model", "anthropic/claude-3-5-sonnet")
        monkeypatch.setattr(settings, "openrouter_prompt_caching_enabled", False)

        service = OpenRouterService()
        captured = {}

        class MockResponse:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "choices": [{"message": {"content": "Response content"}}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 50},
                }

        class MockClient:
            async def post(self, url, json=None, headers=None, **kwargs):
                captured["payload"] = json
                captured["headers"] = headers or {}
                return MockResponse()

        async def mock_get_client(self):
            return MockClient()

        monkeypatch.setattr(OpenRouterService, "_get_http_client", mock_get_client)

        await service.generate("System prompt", "User query")

        assert "anthropic-beta" not in captured["headers"]
        assert "cache_control" not in _json.dumps(captured["payload"])

    def test_openrouter_preset_reaches_generation_and_fast_models(self, monkeypatch):
        """A selected preset must drive the adapter's actual model attributes."""
        monkeypatch.setattr(settings, "openrouter_api_key", "sk-mock-key")

        monkeypatch.setattr(settings, "openrouter_model_preset", "gemini-flash")
        gemini = OpenRouterService()
        assert gemini._gen_model == "google/gemini-2.0-flash-001"
        # _generate_fast() calls self._cls_model; the preset's classification
        # role is what a "fast" selection has to reach.
        assert gemini._cls_model == "google/gemini-2.0-flash-001"

        monkeypatch.setattr(settings, "openrouter_model_preset", "sarvam-m")
        sarvam = OpenRouterService()
        assert sarvam._gen_model == "sarvamai/sarvam-m"
        assert sarvam._cls_model == "meta-llama/llama-3.1-8b-instruct"
        assert sarvam._gen_model_fallback == "deepseek/deepseek-chat"

    def test_openrouter_individual_settings_used_without_preset(self, monkeypatch):
        """With no preset selected, per-role settings keep their own values."""
        monkeypatch.setattr(settings, "openrouter_api_key", "sk-mock-key")
        monkeypatch.setattr(settings, "openrouter_model_preset", "")
        monkeypatch.setattr(settings, "openrouter_generation_model", "deepseek/deepseek-chat")
        monkeypatch.setattr(
            settings, "openrouter_classify_model", "meta-llama/llama-3.1-8b-instruct"
        )

        service = OpenRouterService()
        assert service._gen_model == "deepseek/deepseek-chat"
        assert service._cls_model == "meta-llama/llama-3.1-8b-instruct"


# ============================================================================
# 4. Multilingual Reranker (Alibaba-NLP/gte-multilingual-reranker-base)
# ============================================================================


class TestMultilingualRerankerSupport:
    def test_gte_multilingual_reranker_in_registry(self):
        """Alibaba-NLP/gte-multilingual-reranker-base and its aliases must be in supported registry."""
        assert _GTE_MULTILINGUAL_RERANKER_ID in _SUPPORTED_ONNX_RERANKERS
        assert "gte-multilingual-reranker-base" in _SUPPORTED_ONNX_RERANKERS
        assert "onnx-community/gte-multilingual-reranker-base" in _SUPPORTED_ONNX_RERANKERS
        assert _ONNX_RERANKER_MODEL_ID in _SUPPORTED_ONNX_RERANKERS

    def test_unvetted_reranker_model_fails_closed(self):
        """Unvetted model IDs must be rejected fail-closed to prevent arbitrary repo execution."""
        with pytest.raises(ValueError, match="Refusing to load unvetted reranker model id"):
            OnnxReranker(model_id="malicious/arbitrary-unvetted-reranker")

    def test_reranker_service_model_resolution_for_gte(self, monkeypatch):
        """RerankerService fallback correctly routes to gte-multilingual-reranker-base."""
        monkeypatch.setattr(settings, "reranker_backend", "onnx_int8")
        monkeypatch.setattr(
            settings, "reranker_onnx_model", "Alibaba-NLP/gte-multilingual-reranker-base"
        )

        service = RerankerService()
        with patch("services.onnx_reranker.OnnxReranker") as mock_onnx:
            service._load_fallback()
            mock_onnx.assert_called_once_with(model_id="Alibaba-NLP/gte-multilingual-reranker-base")
            assert service._reranker_outputs_probs is True

    def test_predict_scoring_supports_multilingual_inputs(self):
        """OnnxReranker.predict handles multilingual Indic pairs and output array formatting."""
        # Mock session and tokenizer
        reranker = OnnxReranker.__new__(OnnxReranker)
        reranker._batch_size = 8
        reranker._has_token_type_ids = False

        mock_session = MagicMock()
        # Mock logits: 3 pairs -> logits shape (3, 1)
        mock_session.run.return_value = [np.array([[2.0], [0.0], [-2.0]])]
        reranker._session = mock_session

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": np.zeros((3, 16), dtype=np.int64),
            "attention_mask": np.ones((3, 16), dtype=np.int64),
        }
        reranker._tokenizer = mock_tokenizer

        # Multilingual Indic pairs: Tamil, Telugu, Hindi
        pairs = [
            ("தியானம் என்றால் என்ன?", "தியானம் என்பது அமைதி."),
            ("ధ్యానం అంటే ఏమిటి?", "ధ్యానం అంతర్గత శాంతిని ఇస్తుంది."),
            ("ध्यान क्या है?", "ध्यान मन की शांति है।"),
        ]

        scores = reranker.predict(pairs)
        assert len(scores) == 3
        # Sigmoid check
        assert scores[0] > 0.8  # sigmoid(2.0) ~ 0.88
        assert 0.45 < scores[1] < 0.55  # sigmoid(0.0) == 0.5
        assert scores[2] < 0.2  # sigmoid(-2.0) ~ 0.12
