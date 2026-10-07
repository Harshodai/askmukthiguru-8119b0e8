"""Pipeline builder — ordered list of default stages.

Order keeps request validation and safety ahead of provider availability:
  kill_switch → cache_check → request_state → input_guardrails → circuit_breaker →
  doctrine_cache → casual_short_circuit → distress → bounded_comparison →
  graph → meditation_gen → translation → tone_adapter →
  output_guardrails → memory_save → cache_update → result_assembly

kill_switch runs first, ahead of cache, on purpose (PLAN.md Phase A5): a
tripped switch must never be bypassable by a cache entry computed before it
was flipped, and it must not depend on any other stage's state.

First-person is no longer a stage (plug-and-play cutover, plan
langgraph_plug_play_pipelines_plan.md): it runs INSIDE GraphStage as the
registry-dispatched ``first_person`` pipeline module
(rag/pipeline_registry.py). It still sits after this whole safety lane and
before every general graph node, and with FIRST_PERSON_CHAT_BRIDGE_ENABLED
off the entry router never enters it — the request takes the general graph
exactly as before.
"""

from __future__ import annotations

from app.pipeline.stages.base import Stage
from app.pipeline.stages.cache_stage import CacheCheckStage, CacheUpdateStage
from app.pipeline.stages.distress_stage import DistressStage
from app.pipeline.stages.doctrine_cache_stage import DoctrineCacheStage
from app.pipeline.stages.glue_stages import (
    BoundedComparisonShortCircuitStage,
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
from app.pipeline.stages.kill_switch_stage import KillSwitchStage
from app.pipeline.stages.meditation_gen_stage import MeditationGenStage
from app.pipeline.stages.memory_stage import MemoryStage
from app.pipeline.stages.tone_adapter_stage import ToneAdapterStage


def build_default_pipeline() -> list[Stage]:
    """Return the ordered default stage chain for a chat request."""
    stages: list[Stage] = [
        KillSwitchStage(),
        CacheCheckStage(),
        RequestStateStage(),
        InputGuardrailStage(),
        CircuitBreakerStage(),
        DoctrineCacheStage(),
        CasualShortCircuitStage(),
        DistressStage(),
        BoundedComparisonShortCircuitStage(),
    ]
    # First-person routing moved inside GraphStage (plug-and-play cutover):
    # the entry router in rag/pipeline_registry.py dispatches to the
    # "first_person" module when its live kill-switch is on, so the flag no
    # longer changes which stages exist — only which graph node runs first.
    stages.extend(
        [
            GraphStage(),
            MeditationGenStage(),
            TranslationStage(),
            ToneAdapterStage(),
            OutputGuardrailStage(),
            MemoryStage(),
            CacheUpdateStage(),
            ResultAssemblyStage(),
        ]
    )
    return stages
