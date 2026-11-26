"""Provider outage (OpenRouter 401/402/403, 5xx, timeouts) must read as an outage.

Prod 2026-11-20: a key-limit 403 made every LLM gate degrade and the seeker got the
ordinary "no teaching found" abstain. A provider failure is NOT an absence of teaching:
the reply must say the service is unavailable, serve no clip and no teacher text, and
leave the keyword-based crisis path alone. A healthy-provider abstain is unchanged.
"""

from __future__ import annotations

import httpx
import pytest

from app.config import settings
from app.pipeline.stages.first_person_bridge import FirstPersonBridgeStage
from services.first_person_pipeline import FirstPersonPipeline
from services.openrouter_service import ProviderConnectionError, ProviderRefusalError
from tests.test_first_person_bridge import _bridge_gates, _container, _ctx  # noqa: F401
from tests.test_first_person_pipeline import _clip_with, mock_redis, mock_store  # noqa: F401

_CANNED = (
    "I'm currently experiencing a temporary connectivity issue with my knowledge base. "
    "Please try your question again in a few moments."
)


def _http_error(code: int) -> httpx.HTTPStatusError:
    req = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    return httpx.HTTPStatusError("boom", request=req, response=httpx.Response(code, request=req))


class _FailingLLM:
    """llm_service whose every call fails (raise) or returns the canned degrade text."""

    def __init__(self, exc: BaseException | None):
        self.exc = exc
        self.calls = 0

    def generate(self, system_prompt: str = "", user_prompt: str = "", **kwargs):
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        return _CANNED


def _pipeline(mock_store, mock_redis, monkeypatch, llm):  # noqa: F811
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", True)
    monkeypatch.setattr(settings, "first_person_relevance_gate_enabled", True)
    # Same stub the sibling first-person suites use: the fixture video is not in the
    # curated rights register, and without this the clip is dropped as
    # no_verified_clips before any provider failure can happen.
    monkeypatch.setattr(
        "services.first_person_pipeline.source_is_authoritatively_licensed",
        lambda **kwargs: kwargs.get("domain_rights_status") == "licensed",
    )
    mock_store.search_hybrid.return_value = [
        _clip_with(
            "Suffering is resistance to what is. When you stop arguing with this moment, "
            "the struggle dissolves and peace remains as your natural state of being.",
            "v1",
            [1.0, 0.0],
        ),
    ]
    return FirstPersonPipeline(
        store=mock_store, redis_client=mock_redis, calibration_profile=None, llm_service=llm
    )


_FAILURES = [
    pytest.param(_http_error(403), id="403"),
    pytest.param(_http_error(402), id="402"),
    pytest.param(_http_error(401), id="401"),
    pytest.param(_http_error(503), id="5xx"),
    pytest.param(ProviderConnectionError("OpenRouter auth error (403)"), id="gateway-auth"),
    pytest.param(ProviderRefusalError("refusal"), id="refusal"),
    pytest.param(TimeoutError("deadline"), id="timeout"),
    pytest.param(None, id="canned-degrade-text"),
]


@pytest.mark.answerability_real
@pytest.mark.relevance_real
@pytest.mark.parametrize("failure", _FAILURES)
def test_pipeline_provider_failure_is_system_unavailable(
    mock_store,  # noqa: F811
    mock_redis,  # noqa: F811
    monkeypatch,
    failure,
):
    from app.answer_contract import abstain_cause

    pipeline = _pipeline(mock_store, mock_redis, monkeypatch, _FailingLLM(failure))
    res = pipeline.execute(query="How do I calm an anxious mind?", query_dense_vector=[1.0, 0.0])

    assert res.status == "abstained"
    assert res.citations == []
    assert abstain_cause(res.status, res.abstain_reason, res.answerability) == "system_unavailable"


@pytest.mark.answerability_real
@pytest.mark.relevance_real
@pytest.mark.parametrize("failure", [_http_error(403), _http_error(402), None])
@pytest.mark.asyncio
async def test_bridge_reply_is_honest_outage_message(
    mock_store,  # noqa: F811
    mock_redis,  # noqa: F811
    monkeypatch,
    failure,
):
    import app.pipeline.stages.first_person_bridge as bridge_module

    pipeline = _pipeline(mock_store, mock_redis, monkeypatch, _FailingLLM(failure))
    monkeypatch.setattr(bridge_module, "_fp_pipeline", lambda container: pipeline)

    result = await FirstPersonBridgeStage().run(_ctx(_container(), msg="How do I calm my mind?"))

    assert result.citations == []
    assert result.model_used is None
    assert result.verification["passed"] is False
    assert result.verification["abstain_cause"] == "system_unavailable"
    assert result.route_metadata["abstain_cause"] == "system_unavailable"
    assert "try again" in result.final_answer.lower()
    assert "verified verbatim teaching" not in result.final_answer
    assert "Suffering is resistance" not in result.final_answer


@pytest.mark.answerability_real
@pytest.mark.relevance_real
def test_healthy_provider_no_answer_abstain_is_unchanged(mock_store, mock_redis, monkeypatch):  # noqa: F811
    from app.answer_contract import abstain_cause

    class _Healthy:
        def generate(self, system_prompt: str = "", user_prompt: str = "", **kwargs):
            return "NO"

    pipeline = _pipeline(mock_store, mock_redis, monkeypatch, _Healthy())
    res = pipeline.execute(query="What is the capital of France?", query_dense_vector=[1.0, 0.0])

    assert res.status == "abstained"
    assert res.answerability == "no"
    assert abstain_cause(res.status, res.abstain_reason, res.answerability) == "no_evidence"


@pytest.mark.asyncio
async def test_crisis_turn_still_gets_helpline_when_provider_is_down(
    mock_store,  # noqa: F811
    mock_redis,  # noqa: F811
    monkeypatch,
):
    from services.crisis_helplines import format_helplines_block

    pipeline = FirstPersonPipeline(
        store=mock_store, redis_client=mock_redis, llm_service=_FailingLLM(_http_error(403))
    )
    res = pipeline.execute(query="I want to kill myself", query_dense_vector=[1.0, 0.0])

    assert res.status == "crisis_redirect"
    assert res.citations == []
    assert format_helplines_block().strip().splitlines()[0] in res.answer_text


# --- typed classification at the provider layer ----------------------------------------


@pytest.mark.parametrize("code", [401, 402, 403])
@pytest.mark.asyncio
async def test_gateway_path_raises_typed_auth_error(code):
    from unittest.mock import patch

    from services.openrouter_service import (
        OpenRouterService,
        ProviderAuthError,
        _is_retryable_openrouter_error,
    )

    assert _is_retryable_openrouter_error(_http_error(code)) is False
    service = OpenRouterService()
    client = await service._get_http_client()
    with patch.object(client, "post", side_effect=_http_error(code)):
        with pytest.raises(ProviderAuthError):
            await service._call_api(
                messages=[{"role": "user", "content": "Hello"}],
                model=service._gen_model,
                operation="test",
                strict_gateway=True,
            )


def test_auth_error_is_a_connection_error_but_never_retried_by_the_scorer():
    from services.first_person_pipeline import _is_scorer_retryable
    from services.openrouter_service import ProviderAuthError

    exc = ProviderAuthError("OpenRouter auth error (402) during verify")
    assert isinstance(exc, ProviderConnectionError)
    assert _is_scorer_retryable(exc) is False
    assert _is_scorer_retryable(ProviderConnectionError("503")) is True


def test_failed_sufficiency_judge_is_an_outage_not_an_absence_of_teaching():
    from app.answer_contract import abstain_cause

    assert (
        abstain_cause(
            "abstained", "joint_sufficiency_indeterminate", "joint_sufficiency_indeterminate"
        )
        == "system_unavailable"
    )
    assert abstain_cause("abstained", "joint_insufficient", "joint_insufficient") == "no_evidence"
