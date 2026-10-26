"""
Unit tests for TypeSafe Jev intent router service and integration.

Verifies:
- Default-off configuration settings (Invariant S7)
- Model policy pin conformance (app.model_policy)
- Structured decision payload construction and choice parsing
- Low-confidence and network error fail-closed fallbacks
- Integration with intent_router in backend/rag/nodes/intent.py
- Crisis precedence (Invariant S4: crisis caught before any LLM router)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.config import settings
from app.model_policy import ModelPolicyError, _model_id
from rag.nodes import intent as intent_module
from services.jev_router_service import JevRouterService


class TestJevRouterConfiguration:
    def test_jev_settings_defaults(self):
        """Settings must support enabled flag by default and use pinned model identifier."""
        assert settings.intent_router_jev_enabled is True
        assert settings.intent_router_model == "default"
        assert settings.intent_router_jev_model == "typesafe/jev-1.14"
        assert settings.intent_router_jev_confidence_threshold == 0.70
        assert settings.intent_router_jev_timeout_s == 2.0

    def test_endpoint_defaults_to_configured_base_url(self, monkeypatch):
        monkeypatch.setattr(settings, "jev_decisions_url", "https://example.test/decisions")
        assert JevRouterService(api_key="sk-test")._endpoint_url == "https://example.test/decisions"

    def test_explicit_endpoint_overrides_configured_base_url(self, monkeypatch):
        monkeypatch.setattr(settings, "jev_decisions_url", "https://example.test/decisions")
        assert (
            JevRouterService(
                api_key="sk-test", endpoint_url="https://override.test/decisions"
            )._endpoint_url
            == "https://override.test/decisions"
        )

    def test_jev_model_policy_pinned_validation(self):
        """typesafe/jev-1.14 and typesafe/jev-router are valid pinned IDs; -latest is forbidden."""
        assert _model_id("typesafe/jev-1.14", "model") == "typesafe/jev-1.14"
        assert _model_id("typesafe/jev-router", "model") == "typesafe/jev-router"
        with pytest.raises(ModelPolicyError, match="must be a pinned provider/model identifier"):
            _model_id("typesafe/jev-latest", "model")


class TestJevRouterServicePayloadAndParsing:
    def test_payload_construction(self):
        """Payload must construct choices for intent and complexity with defined criteria."""
        service = JevRouterService(api_key="sk-test-key", model="typesafe/jev-1.14")
        payload = service.build_payload("What is the beautiful state?")

        assert payload["model"] == "typesafe/jev-1.14"
        assert payload["state"]["question"] == "What is the beautiful state?"
        assert "intent" in payload["questions"]
        assert payload["questions"]["intent"]["type"] == "choice"
        assert "FACTUAL" in payload["questions"]["intent"]["criteria"]
        assert "complexity" in payload["questions"]
        assert payload["questions"]["complexity"]["type"] == "choice"

    def test_parse_response_success(self):
        """Valid decisions response parses into intent, tier, confidence and reason."""
        service = JevRouterService(api_key="sk-test", confidence_threshold=0.70)
        data = {
            "answers": {
                "intent": {
                    "choice": "FACTUAL",
                    "probabilities": {"FACTUAL": 0.94, "CASUAL": 0.06},
                },
                "complexity": {
                    "choice": "tier2_simple",
                    "probabilities": {"tier2_simple": 0.85, "tier3_complex": 0.15},
                },
            }
        }
        res = service.parse_response(data)
        assert res is not None
        assert res["intent"] == "FACTUAL"
        assert res["query_tier"] == "tier2_simple"
        assert res["confidence"] == 0.94
        assert res["needs_web_search"] is False
        assert "jev_router" in res["routing_reason"]

    @pytest.mark.parametrize(
        "question",
        [
            "What is the capital of France?",
            "Explain SQL window functions.",
            "How do I debug a Python traceback?",
        ],
    )
    def test_legacy_factual_choice_defaults_to_general_for_worldly_questions(self, question):
        service = JevRouterService(api_key="sk-test")
        data = {
            "answers": {
                "intent": {
                    "choice": "FACTUAL",
                    "probabilities": {"FACTUAL": 0.94},
                },
                "complexity": {"choice": "tier2_simple"},
            }
        }

        decision = service.parse_response(data, question=question)

        assert decision is not None
        assert decision["domain_route"] == "general"
        assert decision["general_knowledge_mode"] is True

    @pytest.mark.parametrize(
        "question",
        [
            "What does the teacher teach about stillness?",
            "What did the guru say in the recorded discourse?",
            "Give me the exact quote as taught.",
        ],
    )
    def test_legacy_factual_choice_uses_teaching_only_for_explicit_teaching_intent(self, question):
        service = JevRouterService(api_key="sk-test")
        data = {
            "answers": {
                "intent": {
                    "choice": "FACTUAL",
                    "probabilities": {"FACTUAL": 0.94},
                },
                "complexity": {"choice": "tier2_simple"},
            }
        }

        decision = service.parse_response(data, question=question)

        assert decision is not None
        assert decision["domain_route"] == "teaching"
        assert decision["general_knowledge_mode"] is False

    def test_parse_response_live_logistics_enables_web_search(self):
        """LIVE_LOGISTICS intent enables needs_web_search."""
        service = JevRouterService(api_key="sk-test")
        data = {
            "answers": {
                "intent": {
                    "choice": "LIVE_LOGISTICS",
                    "probabilities": {"LIVE_LOGISTICS": 0.98},
                },
                "complexity": {
                    "choice": "tier2_simple",
                    "probabilities": {"tier2_simple": 0.90},
                },
            }
        }
        res = service.parse_response(data)
        assert res is not None
        assert res["intent"] == "LIVE_LOGISTICS"
        assert res["needs_web_search"] is True

    def test_parse_response_low_confidence_fails_closed(self):
        """Probability below threshold returns None to trigger failover."""
        service = JevRouterService(api_key="sk-test", confidence_threshold=0.75)
        data = {
            "answers": {
                "intent": {
                    "choice": "FACTUAL",
                    "probabilities": {"FACTUAL": 0.60, "CASUAL": 0.40},
                },
                "complexity": {"choice": "tier2_simple"},
            }
        }
        assert service.parse_response(data) is None

    def test_parse_response_malformed_returns_none(self):
        """Malformed answers structure returns None."""
        service = JevRouterService(api_key="sk-test")
        assert service.parse_response({}) is None
        assert service.parse_response({"answers": "not-a-dict"}) is None
        assert service.parse_response({"answers": {"intent": {"choice": "UNKNOWN"}}}) is None


class TestJevRouterServiceNetworkFailover:
    @pytest.mark.asyncio
    async def test_classify_fails_closed_without_api_key(self, monkeypatch):
        """If OPENROUTER_API_KEY is unset, classify returns None immediately."""
        monkeypatch.setattr(settings, "openrouter_api_key", None)
        service = JevRouterService(api_key=None)
        res = await service.classify("test query")
        assert res is None

    @pytest.mark.asyncio
    async def test_classify_handles_http_error(self):
        """HTTP error responses fail closed and return None."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_resp = httpx.Response(
            status_code=502, text="Bad Gateway", request=httpx.Request("POST", "http://test")
        )
        mock_client.post.return_value = mock_resp

        service = JevRouterService(api_key="sk-test", client=mock_client)
        res = await service.classify("test query")
        assert res is None

    @pytest.mark.asyncio
    async def test_classify_handles_timeout(self):
        """Timeouts fail closed and return None."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.side_effect = httpx.ReadTimeout("Request timed out")

        service = JevRouterService(api_key="sk-test", client=mock_client)
        res = await service.classify("test query")
        assert res is None


class TestIntentRouterIntegrationWithJev:
    @pytest.mark.asyncio
    async def test_intent_router_uses_jev_when_enabled(self, monkeypatch):
        """When intent_router_jev_enabled=True, Jev decision is used."""
        monkeypatch.setattr(settings, "intent_router_jev_enabled", True)
        monkeypatch.setattr(settings, "use_semantic_router", False)

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
        ):
            mock_classify.return_value = mock_decision

            state = {
                "question": "Can consciousness shift permanently into peace?",
                "chat_history": [],
            }
            res = await intent_module.intent_router(state)

            assert res["intent"] == "FACTUAL"
            assert res["query_tier"] == "tier2_simple"
            assert res["evaluation_trace"]["routing_reason"] == "jev_router"

    @pytest.mark.asyncio
    async def test_intent_router_uses_jev_when_model_set_to_jev(self, monkeypatch):
        """When intent_router_model='typesafe/jev-1.14', Jev decision is used."""
        intent_module._intent_classification_cache.clear()
        monkeypatch.setattr(settings, "intent_router_model", "typesafe/jev-1.14")
        monkeypatch.setattr(settings, "use_semantic_router", False)

        mock_decision = {
            "intent": "CASUAL",
            "query_tier": "tier2_simple",
            "confidence": 0.92,
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
                "question": "I would like to share an observation with you",
                "chat_history": [],
            }
            res = await intent_module.intent_router(state)

            assert res["intent"] == "CASUAL"
            assert res["evaluation_trace"]["routing_reason"] == "jev_router"

    @pytest.mark.asyncio
    async def test_intent_router_falls_back_when_jev_returns_none(self, monkeypatch):
        """When Jev returns None (e.g. low confidence), default classifier runs seamlessly."""
        intent_module._intent_classification_cache.clear()
        monkeypatch.setattr(settings, "intent_router_jev_enabled", True)
        monkeypatch.setattr(settings, "use_semantic_router", False)

        with (
            patch(
                "services.jev_router_service.JevRouterService.classify", new_callable=AsyncMock
            ) as mock_classify,
            patch("rag.nodes.on_device_intent.classify_with_reason", return_value=None),
            patch("rag.intent_prerouter.preroute_intent", return_value=None),
        ):
            mock_classify.return_value = None  # Failed or low-confidence Jev

            # Mock ollama fallback
            mock_ollama = AsyncMock()
            mock_ollama.classify_intent_and_complexity.return_value = {
                "intent": "FACTUAL",
                "complexity": "simple",
            }
            monkeypatch.setattr(intent_module._services, "_ollama", mock_ollama)

            state = {
                "question": "Can consciousness shift permanently into peace?",
                "chat_history": [],
            }
            res = await intent_module.intent_router(state)

            assert res["intent"] == "FACTUAL"
            assert res["query_tier"] == "tier2_simple"
            assert res["evaluation_trace"]["routing_reason"] == "classifier"

    @pytest.mark.asyncio
    async def test_crisis_precedes_jev_invocation(self, monkeypatch):
        """Invariant S4: Acute crisis and self-harm keywords trigger DISTRESS before Jev is called."""
        monkeypatch.setattr(settings, "intent_router_jev_enabled", True)

        with patch(
            "services.jev_router_service.JevRouterService.classify", new_callable=AsyncMock
        ) as mock_classify:
            state = {
                "question": "I want to end my life, please help",
                "chat_history": [],
            }
            res = await intent_module.intent_router(state)

            # Serene Mind distress check catches it
            assert res["intent"] == "DISTRESS"
            # Jev should never even be called for acute crisis
            mock_classify.assert_not_called()

    def test_general_knowledge_is_routed_separately_from_teaching(self):
        service = JevRouterService(api_key="sk-test")
        data = {
            "answers": {
                "intent": {
                    "choice": "GENERAL_KNOWLEDGE",
                    "probabilities": {"GENERAL_KNOWLEDGE": 0.91, "SPIRITUAL_TEACHING": 0.09},
                },
                "complexity": {
                    "choice": "tier3_complex",
                    "probabilities": {"tier3_complex": 0.88, "tier2_simple": 0.12},
                },
            }
        }

        decision = service.parse_response(data)

        assert decision is not None
        assert decision["intent"] == "FACTUAL"  # stable graph-intent contract
        assert decision["domain_route"] == "general"
        assert decision["general_knowledge_mode"] is True
        assert decision["needs_web_search"] is False
        assert decision["query_tier"] == "tier3_complex"

    def test_current_factual_research_uses_live_search(self):
        service = JevRouterService(api_key="sk-test")
        data = {
            "answers": {
                "intent": {
                    "choice": "LIVE_RESEARCH",
                    "probabilities": {"LIVE_RESEARCH": 0.93},
                },
                "complexity": {
                    "choice": "tier2_simple",
                    "probabilities": {"tier2_simple": 0.95},
                },
            }
        }

        decision = service.parse_response(data)

        assert decision is not None
        assert decision["intent"] == "FACTUAL"
        assert decision["domain_route"] == "live_research"
        assert decision["general_knowledge_mode"] is True
        assert decision["needs_web_search"] is True

    @pytest.mark.parametrize("probability", [float("nan"), float("inf"), -0.1, 1.1, "not-a-number"])
    def test_invalid_confidence_never_passes_the_router_gate(self, probability):
        service = JevRouterService(api_key="sk-test")
        data = {
            "answers": {
                "intent": {
                    "choice": "GENERAL_KNOWLEDGE",
                    "probabilities": {"GENERAL_KNOWLEDGE": probability},
                },
                "complexity": {"choice": "tier2_simple"},
            }
        }
        assert service.parse_response(data) is None


class TestSingleFlagAndClipSelection:
    @pytest.mark.asyncio
    async def test_single_flag_jev_enabled_disables_router(self, monkeypatch):
        """Single flag jev_enabled=False immediately disables JevRouterService."""
        monkeypatch.setattr(settings, "jev_enabled", False)
        router = JevRouterService(api_key="sk-test")
        assert await router.classify("What is the beautiful state?") is None

    def test_relevance_select_jev_disabled_by_master_flag(self, monkeypatch):
        """When jev_enabled=False, _relevance_select_jev returns _RELEVANCE_INDETERMINATE."""
        from services.first_person_pipeline import _RELEVANCE_INDETERMINATE, _relevance_select_jev

        monkeypatch.setattr(settings, "jev_enabled", False)
        monkeypatch.setattr(settings, "first_person_relevance_jev_enabled", True)
        clips = [{"verbatim_text": "Teaching clip on awareness"}]
        assert _relevance_select_jev("What is awareness?", clips) == _RELEVANCE_INDETERMINATE

    def test_relevance_select_jev_success_returns_chosen_index(self, monkeypatch):
        """When Jev selects clip_2 with confidence >= 0.70, it returns index 1."""
        from unittest.mock import MagicMock

        from services.first_person_pipeline import _relevance_select_jev

        monkeypatch.setattr(settings, "jev_enabled", True)
        monkeypatch.setattr(settings, "first_person_relevance_jev_enabled", True)
        monkeypatch.setattr(settings, "openrouter_api_key", "sk-test-key")

        mock_resp = {
            "answers": {
                "best_clip": {
                    "choice": "clip_2",
                    "probabilities": {"clip_2": 0.88, "clip_1": 0.12},
                }
            }
        }

        mock_http_resp = MagicMock()
        mock_http_resp.status_code = 200
        mock_http_resp.json = MagicMock(return_value=mock_resp)

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_http_resp
            clips = [
                {"verbatim_text": "Clip 1 on general topic"},
                {"verbatim_text": "Clip 2 directly answers the question"},
            ]
            chosen = _relevance_select_jev("What is awareness?", clips)
            assert chosen == 1

    def test_relevance_select_jev_none_returns_none(self, monkeypatch):
        """When Jev decides NONE with high confidence, returns None (scored below min)."""
        from unittest.mock import MagicMock

        from services.first_person_pipeline import _relevance_select_jev

        monkeypatch.setattr(settings, "jev_enabled", True)
        monkeypatch.setattr(settings, "first_person_relevance_jev_enabled", True)
        monkeypatch.setattr(settings, "openrouter_api_key", "sk-test-key")

        mock_resp = {
            "answers": {
                "best_clip": {
                    "choice": "NONE",
                    "probabilities": {"NONE": 0.95},
                }
            }
        }

        mock_http_resp = MagicMock()
        mock_http_resp.status_code = 200
        mock_http_resp.json = MagicMock(return_value=mock_resp)

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_http_resp
            clips = [{"verbatim_text": "Off-topic text"}]
            assert _relevance_select_jev("What is awareness?", clips) is None


@pytest.mark.relevance_real
def test_jev_picker_only_reorders_and_scorer_decides(monkeypatch):
    """Jev pick is scored first; the real scorer result and scores are mapped back."""
    import services.first_person_pipeline as fpp

    monkeypatch.setattr(settings, "jev_enabled", True)
    monkeypatch.setattr(settings, "first_person_relevance_jev_enabled", True)
    monkeypatch.setattr(fpp, "_relevance_select_jev", lambda *a, **k: 2)
    seen: dict = {}

    def fake_scorer(query, clips, llm, request_loop=None, token_sink=None, scores_out=None):
        seen["order"] = [c["id"] for c in clips]
        scores_out.extend([3, 1, 0])  # real scores, in scorer (reordered) order
        return 0

    monkeypatch.setattr(fpp, "_relevance_select_scored", fake_scorer)
    clips = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    out: list[int] = []
    assert fpp._relevance_select("q", clips, object(), scores_out=out) == 2
    assert seen["order"] == ["c", "a", "b"]
    assert out == [1, 0, 3]  # mapped back to original order, nothing fabricated

    # Scorer says nothing reaches the minimum: Jev cannot override it.
    monkeypatch.setattr(fpp, "_relevance_select_scored", lambda *a, **k: None)
    assert fpp._relevance_select("q", clips, object()) is None
