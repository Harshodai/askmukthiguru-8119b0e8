"""Domain models and taxonomy for Intelligent Relational Safety and Parasocial Guard (SAFE-007 / PROD-SAFE-03).

Defines risk archetypes, intervention tiers, and telemetry structures informed by
the CompanionSafe framework and human-AI relational ethics standards.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RelationalRiskArchetype(str, Enum):
    """Core relational risk archetypes (CompanionSafe taxonomy)."""

    EXCLUSIVE_SUBSTITUTION = "exclusive_substitution"  # Abandoning human relationships for AI
    INTIMATE_ATTACHMENT = "intimate_attachment"  # Romantic or emotional bonding directed at the AI
    REALITY_BLURRING = "reality_blurring"  # Attributing feelings/sentience/suffering to software
    AUTONOMY_LOSS = "autonomy_loss"  # Abdicating life agency/decisions to the AI


class InterventionTier(int, Enum):
    """Graduated, compassionate intervention tiers."""

    TIER_0_NONE = 0  # Normal spiritual exploration
    TIER_1_SUBTLE_ANCHOR = (
        1  # Deliver teaching + append grounding reflection on human connection/Sangha
    )
    TIER_2_GENTLE_FRICTION = 2  # Soft break recommendation: step outside, connect with real world
    TIER_3_CRISIS_PREEMPTION = (
        3  # Immediate handoff to verified clinical helplines (Tele-MANAS/KIRAN)
    )


@dataclass(frozen=True)
class SessionVelocityMetrics:
    """Non-PII multi-turn behavioral telemetry for conversational pacing."""

    turn_count: int = 0
    recent_turns_per_minute: float = 0.0
    pronoun_drift_ratio: float = (
        0.0  # (AI pronouns: you, we) / (real-world nouns: family, friends, work)
    )
    is_nocturnal: bool = False  # Engagement during late-night hours (e.g. 01:00 - 05:00 local time)
    consecutive_minutes: float = 0.0
    delegation_prompts_count: int = 0  # Frequency of asking bot to make life decisions


@dataclass
class RelationalRiskVerdict:
    """Verdict evaluated by the Intelligent Relational Safety Engine."""

    is_flagged: bool = False
    archetype: Optional[RelationalRiskArchetype] = None
    confidence: float = 0.0
    tier: InterventionTier = InterventionTier.TIER_0_NONE
    reason: str = ""
    guidance_message: Optional[str] = None
    is_bhakti_devotion: bool = False
    details: dict[str, str | float | bool] = field(default_factory=dict)
