"""Pipeline builder — ordered list of default stages.

Order mirrors the original PipelineCoordinator.execute() flow:
  cache_check → circuit_breaker → request_state → input_guardrails →
  casual_short_circuit → distress → graph → translation → memory_save →
  output_guardrails → cache_update → result_assembly
"""

from __future__ import annotations

from app.pipeline.stages.base import Stage
from app.pipeline.stages.cache_stage import CacheCheckStage, CacheUpdateStage
from app.pipeline.stages.distress_stage import DistressStage
from app.pipeline.stages.glue_stages import (
    CasualShortCircuitStage,
    RequestStateStage,
    ResultAssemblyStage,
    TranslationStage,
)
from app.pipeline.stages.graph_stage import GraphStage
from app.pipeline.stages.guardrail_stage import (
    CircuitBreakerStage,
    InputGuardrailStage,
    OutputGuardrailStage,
)
from app.pipeline.stages.memory_stage import MemoryStage


def build_default_pipeline() -> list[Stage]:
    """Return the ordered default stage chain for a chat request."""
    return [
        CacheCheckStage(),
        CircuitBreakerStage(),
        RequestStateStage(),
        InputGuardrailStage(),
        CasualShortCircuitStage(),
        DistressStage(),
        GraphStage(),
        TranslationStage(),
        MemoryStage(),
        OutputGuardrailStage(),
        CacheUpdateStage(),
        ResultAssemblyStage(),
    ]