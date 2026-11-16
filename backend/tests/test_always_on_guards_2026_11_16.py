"""Safety/privacy/spend guards that have no off switch (U3, 2026-11-16)."""

from types import SimpleNamespace

import pytest

from app.config import Settings
from app.model_policy import OpenRouterModelPolicy
from app.openrouter_budget import OpenRouterBudgetGuard
from services import fp_fail_closed
from services.llm_budget_guard import LLMBudgetGuard

REMOVED = (
    "fp_fail_closed_enabled",
    "openrouter_budget_fail_closed",
    "llm_budget_fail_closed",
    "openrouter_require_no_training",
)


@pytest.mark.parametrize("name", REMOVED)
def test_flag_fields_are_gone(name):
    assert name not in Settings.model_fields


def test_openrouter_budget_guard_fails_closed_without_flag():
    s = SimpleNamespace(redis_url="redis://x", openrouter_budget_guard_enabled=True)
    policy = SimpleNamespace(daily_budget_usd=1.0, monthly_budget_usd=2.0)
    assert OpenRouterBudgetGuard.from_settings(s, policy)._fail_closed is True


def test_llm_budget_guard_fails_closed_without_flag():
    assert LLMBudgetGuard.from_settings(SimpleNamespace(), "sarvam")._fail_closed is True


def test_model_policy_always_denies_training():
    s = SimpleNamespace(
        openrouter_policy_id="p",
        openrouter_generation_model="deepseek/deepseek-chat",
        openrouter_generation_model_fallback="meta-llama/llama-3.3-70b-instruct",
        openrouter_fast_model="meta-llama/llama-3.1-8b-instruct",
        openrouter_classify_model="meta-llama/llama-3.1-8b-instruct",
        openrouter_allowed_providers="DeepSeek",
        openrouter_daily_budget_usd=1.0,
        openrouter_monthly_budget_usd=2.0,
        llm_max_tokens_fast=800,
        llm_max_tokens_deep=1500,
    )
    policy = OpenRouterModelPolicy.from_settings(s)
    assert policy.require_no_training is True
    assert policy.provider_preferences()["data_collection"] == "deny"


def test_teaching_generation_closed_unless_llm_fallback_on(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "first_person_llm_fallback_enabled", False)
    assert fp_fail_closed.teaching_generation_allowed() is False
