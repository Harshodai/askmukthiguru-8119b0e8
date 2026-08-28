"""Server-authoritative OpenRouter model and provider policy.

The policy keeps model, provider-privacy, token-ceiling, and budget configuration
out of browser-controlled request data. Cost guards consume the same contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class ModelPolicyError(ValueError):
    """Raised when a model or provider request violates the active policy."""


def _model_id(value: str, field_name: str) -> str:
    model = (value or "").strip()
    if (
        not model
        or model.endswith("/latest")
        or model.endswith(":latest")
        or model.rsplit("/", 1)[-1].endswith("-latest")
    ):
        raise ModelPolicyError(
            f"{field_name} must be a pinned provider/model identifier, not a latest alias"
        )
    return model


def _optional_model_id(value: str, field_name: str) -> str | None:
    model = (value or "").strip()
    return _model_id(model, field_name) if model else None


def _provider_list(value: str) -> tuple[str, ...]:
    providers = tuple(item.strip() for item in (value or "").split(",") if item.strip())
    if len(set(providers)) != len(providers):
        raise ModelPolicyError("openrouter_allowed_providers contains duplicates")
    return providers


def _provider_sort(value: str) -> str | None:
    sort = (value or "").strip().lower()
    if not sort:
        return None
    if sort not in {"latency", "throughput", "price"}:
        raise ModelPolicyError("openrouter_provider_sort must be latency, throughput, price, or empty")
    return sort


def _provider_partition(value: str) -> str:
    partition = (value or "model").strip().lower()
    if partition not in {"model", "none"}:
        raise ModelPolicyError("openrouter_provider_partition must be model or none")
    return partition


@dataclass(frozen=True)
class OpenRouterModelPolicy:
    """Validated immutable policy used for every OpenRouter request."""

    policy_id: str
    generation_model: str
    generation_fallback_model: str | None
    fast_model: str
    classify_model: str
    allowed_providers: tuple[str, ...]
    provider_sort: str | None
    provider_partition: str
    preferred_max_latency_p90: float
    preferred_min_throughput_p90: float
    require_no_training: bool
    allow_provider_fallbacks: bool
    enforce_model_allowlist: bool
    max_tokens_fast: int
    max_tokens_deep: int
    daily_budget_usd: float
    monthly_budget_usd: float

    @classmethod
    def from_settings(cls, settings: Any) -> OpenRouterModelPolicy:
        policy_id = (getattr(settings, "openrouter_policy_id", "") or "").strip()
        if not policy_id:
            raise ModelPolicyError("openrouter_policy_id is required")
        policy = cls(
            policy_id=policy_id,
            generation_model=_model_id(
                settings.openrouter_generation_model, "openrouter_generation_model"
            ),
            generation_fallback_model=_optional_model_id(
                settings.openrouter_generation_model_fallback,
                "openrouter_generation_model_fallback",
            ),
            fast_model=_model_id(settings.openrouter_fast_model, "openrouter_fast_model"),
            classify_model=_model_id(
                settings.openrouter_classify_model, "openrouter_classify_model"
            ),
            allowed_providers=_provider_list(getattr(settings, "openrouter_allowed_providers", "")),
            provider_sort=_provider_sort(getattr(settings, "openrouter_provider_sort", "")),
            provider_partition=_provider_partition(
                getattr(settings, "openrouter_provider_partition", "model")
            ),
            preferred_max_latency_p90=float(
                getattr(settings, "openrouter_preferred_max_latency_p90", 0.0)
            ),
            preferred_min_throughput_p90=float(
                getattr(settings, "openrouter_preferred_min_throughput_p90", 0.0)
            ),
            require_no_training=bool(getattr(settings, "openrouter_require_no_training", True)),
            allow_provider_fallbacks=bool(
                getattr(settings, "openrouter_allow_provider_fallbacks", True)
            ),
            enforce_model_allowlist=bool(
                getattr(settings, "openrouter_enforce_model_policy", True)
            ),
            max_tokens_fast=int(settings.llm_max_tokens_fast),
            max_tokens_deep=int(settings.llm_max_tokens_deep),
            daily_budget_usd=float(getattr(settings, "openrouter_daily_budget_usd", 10.0)),
            monthly_budget_usd=float(getattr(settings, "openrouter_monthly_budget_usd", 100.0)),
        )
        policy.validate()
        return policy

    def validate(self) -> None:
        if (
            self.generation_fallback_model
            and self.generation_model == self.generation_fallback_model
        ):
            raise ModelPolicyError("generation fallback model must differ from primary model")
        if self.max_tokens_fast < 1 or self.max_tokens_deep < self.max_tokens_fast:
            raise ModelPolicyError("OpenRouter token ceilings are invalid")
        if self.provider_sort is None and (
            self.preferred_max_latency_p90 > 0 or self.preferred_min_throughput_p90 > 0
        ):
            raise ModelPolicyError(
                "OpenRouter performance thresholds require openrouter_provider_sort"
            )
        if self.daily_budget_usd <= 0 or self.monthly_budget_usd < self.daily_budget_usd:
            raise ModelPolicyError("OpenRouter daily/monthly budget configuration is invalid")

    @property
    def allowed_models(self) -> frozenset[str]:
        return frozenset(
            {
                self.generation_model,
                self.generation_fallback_model,
                self.fast_model,
                self.classify_model,
            }
        )

    def assert_model_allowed(self, model: str) -> None:
        if self.enforce_model_allowlist and model not in self.allowed_models:
            raise ModelPolicyError(
                f"model '{model}' is not permitted by OpenRouter policy '{self.policy_id}'"
            )

    def output_ceiling(self, operation: str) -> int:
        if operation in {"deep", "complex", "verify"}:
            return self.max_tokens_deep
        return self.max_tokens_fast

    def provider_preferences(self) -> dict[str, Any]:
        """Build the OpenRouter provider payload without exposing secrets."""
        preferences: dict[str, Any] = {"allow_fallbacks": self.allow_provider_fallbacks}
        if self.require_no_training:
            preferences["data_collection"] = "deny"
        if self.allowed_providers:
            preferences["order"] = list(self.allowed_providers)
        if self.provider_sort:
            preferences["sort"] = {
                "by": self.provider_sort,
                "partition": self.provider_partition,
            }
        if self.preferred_max_latency_p90 > 0:
            preferences["preferred_max_latency"] = {"p90": self.preferred_max_latency_p90}
        if self.preferred_min_throughput_p90 > 0:
            preferences["preferred_min_throughput"] = {
                "p90": self.preferred_min_throughput_p90
            }
        return preferences
