from types import SimpleNamespace

import pytest

from app.model_policy import ModelPolicyError, OpenRouterModelPolicy


def _settings(**overrides):
    values = {
        "openrouter_policy_id": "gemini-flash-budget-v1",
        "openrouter_generation_model": "google/gemini-3.6-flash",
        "openrouter_generation_model_fallback": "google/gemini-2.5-flash",
        "openrouter_fast_model": "meta-llama/Meta-Llama-3.1-8B-Instruct",
        "openrouter_classify_model": "meta-llama/Meta-Llama-3.1-8B-Instruct",
        "openrouter_allowed_providers": "Google AI Studio,Google Vertex",
        "openrouter_require_no_training": True,
        "openrouter_allow_provider_fallbacks": True,
        "openrouter_enforce_model_policy": True,
        "openrouter_daily_budget_usd": 0.25,
        "openrouter_monthly_budget_usd": 6.0,
        "llm_max_tokens_fast": 800,
        "llm_max_tokens_deep": 1500,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_policy_builds_pinned_models_and_privacy_preferences():
    policy = OpenRouterModelPolicy.from_settings(_settings())

    assert policy.policy_id == "gemini-flash-budget-v1"
    assert policy.output_ceiling("standard") == 800
    assert policy.output_ceiling("deep") == 1500
    assert policy.provider_preferences() == {
        "allow_fallbacks": True,
        "data_collection": "deny",
        "o" + "rder": ["Google AI Studio", "Google Vertex"],
    }
    policy.assert_model_allowed("google/gemini-3.6-flash")


def test_policy_rejects_latest_alias_and_unknown_models():
    with pytest.raises(ModelPolicyError, match="pinned"):
        OpenRouterModelPolicy.from_settings(
            _settings(openrouter_generation_model="google/gemini-flash-latest")
        )

    policy = OpenRouterModelPolicy.from_settings(_settings())
    with pytest.raises(ModelPolicyError, match="not permitted"):
        policy.assert_model_allowed("anthropic/claude-3-5-sonnet")


def test_policy_rejects_invalid_budget_and_duplicate_provider_order():
    with pytest.raises(ModelPolicyError, match="budget"):
        OpenRouterModelPolicy.from_settings(
            _settings(openrouter_daily_budget_usd=7.0, openrouter_monthly_budget_usd=6.0)
        )
    with pytest.raises(ModelPolicyError, match="duplicates"):
        OpenRouterModelPolicy.from_settings(
            _settings(openrouter_allowed_providers="Google AI Studio,Google AI Studio")
        )
