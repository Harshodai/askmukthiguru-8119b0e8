"""AskMukthiGuru Engine 1: Fast Intake, Safety Kernel & Unified Personalization.

Provides deterministic zero-I/O safety preemption (<2ms), 5-tier short-circuiting (<5ms),
and unified parallel user personalization hydration (<15ms).
"""

from app.intake.personalization_coordinator import (
    UnifiedPersonalizationCoordinator,
    UnifiedUserPersonalizationContext,
)
from app.intake.safety_kernel import FastSafetyKernel, SafetyVerdict
from app.intake.short_circuit import FastShortCircuitCascade, ShortCircuitResult

__all__ = [
    "FastSafetyKernel",
    "SafetyVerdict",
    "FastShortCircuitCascade",
    "ShortCircuitResult",
    "UnifiedPersonalizationCoordinator",
    "UnifiedUserPersonalizationContext",
]
