"""
Unit 16 — A/B Testing Framework

Provides a lightweight, stateless A/B testing framework for LLM model and
prompt variant experiments. No external dependencies required.

Design:
  - ``ABTestConfig``: dataclass defining an experiment (variants, weights, metrics)
  - ``ABTestRouter``: deterministic variant assignment by user_id hash
  - ``ABTestResult``: structured result with variant metadata for logging
  - Experiments stored in YAML config (hot-reloadable with Unit 17)
  - Results logged to the compliance audit log and Prometheus metrics

Supported experiment types:
  1. Model experiments: route to different LLM models (e.g., sarvam vs gemma3)
  2. Prompt experiments: route to different system prompt variants
  3. Temperature experiments: vary generation temperature

Assignment is deterministic: same user_id always gets same variant
(consistent UX within a session/user while allowing population analysis).

Usage::

    from services.ab_testing import ABTestRouter, ABTestConfig

    router = ABTestRouter()
    router.register(ABTestConfig(
        name="model_test_v1",
        variants=["gemma3:12b", "llama3.2:3b"],
        weights=[0.7, 0.3],
        experiment_type="model",
    ))

    variant = router.assign("user-uuid-1234", "model_test_v1")
    # variant → "gemma3:12b" or "llama3.2:3b"
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from app.sanitization import sanitize_log_input

logger = logging.getLogger(__name__)


@dataclass
class ABTestConfig:
    """Configuration for a single A/B experiment.

    Args:
        name: Unique experiment name (e.g., "model_test_v1").
        variants: List of variant identifiers (model names, prompt IDs, etc.)
        weights: Relative weights for each variant (must sum to 1.0 ± 0.01).
        experiment_type: "model" | "prompt" | "temperature" | "custom".
        description: Human-readable experiment description.
        enabled: If False, always returns variants[0] (control).
        start_time: Unix timestamp when the experiment starts (default: now).
        end_time: Optional Unix timestamp when the experiment ends.
    """

    name: str
    variants: list[str]
    weights: list[float]
    experiment_type: str = "model"
    description: str = ""
    enabled: bool = True
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None

    def __post_init__(self):
        if len(self.variants) != len(self.weights):
            raise ValueError(
                f"ABTestConfig '{self.name}': variants and weights must have the same length"
            )
        total = sum(self.weights)
        if not (0.99 <= total <= 1.01):
            raise ValueError(
                f"ABTestConfig '{self.name}': weights must sum to ~1.0 (got {total:.3f})"
            )

    @property
    def is_active(self) -> bool:
        """True if the experiment is enabled and within its time window."""
        if not self.enabled:
            return False
        now = time.time()
        if now < self.start_time:
            return False
        if self.end_time and now > self.end_time:
            return False
        return True

    @property
    def control(self) -> str:
        """Return the control variant (always first)."""
        return self.variants[0]


@dataclass
class ABTestResult:
    """Result of a variant assignment for logging and metrics."""

    experiment_name: str
    user_id: str
    variant: str
    variant_index: int
    is_control: bool
    experiment_type: str
    assignment_hash: str  # For audit/verification


class ABTestRouter:
    """Deterministic A/B test router using user_id-based hashing.

    Guarantees:
    - Same user_id always maps to the same variant for a given experiment.
    - Variant assignment is instant (O(1), no DB lookup).
    - Experiments are independent of each other.
    """

    def __init__(self) -> None:
        self._experiments: dict[str, ABTestConfig] = {}

    def register(self, config: ABTestConfig) -> None:
        """Register an experiment configuration."""
        self._experiments[config.name] = config
        logger.info(
            f"ABTestRouter: registered experiment '{config.name}' "
            f"({len(config.variants)} variants, type={config.experiment_type})"
        )

    def unregister(self, experiment_name: str) -> None:
        """Remove an experiment (e.g., after conclusion)."""
        self._experiments.pop(experiment_name, None)

    def assign(self, user_id: str, experiment_name: str) -> ABTestResult:
        """Deterministically assign a user to a variant.

        Args:
            user_id: The authenticated user's ID (Supabase UUID or similar).
            experiment_name: The experiment to look up.

        Returns:
            ABTestResult with the assigned variant.
            Falls back to control variant if experiment not found or inactive.
        """
        config = self._experiments.get(experiment_name)

        if config is None:
            logger.debug(
                "ABTestRouter: unknown experiment '%s'; using fallback",
                sanitize_log_input(experiment_name),
            )
            return ABTestResult(
                experiment_name=experiment_name,
                user_id=user_id,
                variant="__unknown__",
                variant_index=0,
                is_control=True,
                experiment_type="unknown",
                assignment_hash="",
            )

        if not config.is_active:
            logger.debug(
                "ABTestRouter: experiment '%s' inactive; using control",
                sanitize_log_input(experiment_name),
            )
            return ABTestResult(
                experiment_name=experiment_name,
                user_id=user_id,
                variant=config.control,
                variant_index=0,
                is_control=True,
                experiment_type=config.experiment_type,
                assignment_hash="",
            )

        # Hash(user_id + salt + experiment_name) -> uniform float in [0, 1)
        raw = f"{user_id}:{self._salt}:{experiment_name}".encode("utf-8")
        hash_hex = hashlib.sha256(raw).hexdigest()
        hash_int = int(hash_hex[:8], 16)
        scale = hash_int / 0xFFFFFFFF

        # Cumulative weight lookup
        cumulative = 0.0
        selected_variant = config.variants[-1]  # fallback
        selected_index = len(config.variants) - 1

        for i, (variant, weight) in enumerate(zip(config.variants, config.weights)):
            cumulative += weight
            if scale < cumulative:
                selected_variant = variant
                selected_index = i
                break

        is_control = selected_variant == config.control

        logger.debug(
            "ABTestRouter: user='%s' experiment='%s' scale=%.4f -> variant='%s' (control=%s)",
            sanitize_log_input(user_id),
            sanitize_log_input(experiment_name),
            scale,
            sanitize_log_input(selected_variant),
            is_control,
        )

        return ABTestResult(
            experiment_name=experiment_name,
            user_id=user_id,
            variant=selected_variant,
            variant_index=selected_index,
            is_control=is_control,
            experiment_type=config.experiment_type,
            assignment_hash=hash_hex[:16],
        )

    def list_experiments(self) -> list[dict]:
        """Return summary of all registered experiments."""
        return [
            {
                "name": c.name,
                "type": c.experiment_type,
                "variants": c.variants,
                "weights": c.weights,
                "active": c.is_active,
                "description": c.description,
            }
            for c in self._experiments.values()
        ]


# -----------------------------------------------------------------------
# Global singleton + default experiments
# -----------------------------------------------------------------------

_ab_router: Optional[ABTestRouter] = None


def get_ab_router() -> ABTestRouter:
    """Return the global ABTestRouter singleton, initializing default experiments."""
    global _ab_router
    if _ab_router is None:
        _ab_router = ABTestRouter()
        _register_default_experiments(_ab_router)
    return _ab_router


def _register_default_experiments(router: ABTestRouter) -> None:
    """Register the baseline A/B experiments for production."""
    # Model experiment: test different classification models
    router.register(
        ABTestConfig(
            name="classifier_model_v1",
            variants=["meta-llama/Meta-Llama-3.1-8B-Instruct", "anthropic/claude-3.5-haiku"],
            weights=[0.8, 0.2],
            experiment_type="model",
            description="Test claude-3.5-haiku for classification tasks (20% of traffic)",
        )
    )

    # Temperature experiment: test higher temperature for creative responses
    router.register(
        ABTestConfig(
            name="temperature_casual_v1",
            variants=["0.1", "0.3"],
            weights=[0.9, 0.1],
            experiment_type="temperature",
            description="Test higher temperature for casual responses (10% of traffic)",
        )
    )
