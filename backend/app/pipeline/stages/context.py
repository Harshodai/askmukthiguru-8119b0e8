"""PipelineContext — mutable working state shared across stages.

Replaces threading kwargs through the stage chain. Stages read inputs from
ctx and write outputs back to ctx; the coordinator helpers (``_embed_query``,
``_is_circuit_open``, ``_build_context_aware_cache_key``, ``_ensure_vector_cache``,
``_circuit_open_result``, metadata builders) stay on the coordinator and are
reachable via ``ctx.coordinator`` so stages call them without reimplementation.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from app.pipeline.result import PipelineResult


@dataclass
class PipelineContext:
    """All state flowing through the stage pipeline."""

    # --- Inputs (set once by coordinator.execute) ---
    container: Any  # ServiceContainer
    coordinator: Any  # PipelineCoordinator (private helpers)
    request: Any  # ChatRequest / ChatStreamRequest body
    user_msg: str = ""
    preferred_lang: str = "en"
    meditation_step: int = 0
    session_id: str | None = None
    user: dict | None = None
    is_benchmark: bool = False
    stream_queue: asyncio.Queue | None = None

    # --- Trace / timing ---
    trace_id: str = ""
    start_time: float = 0.0

    # --- Cache precomputation ---
    cache_key: str = ""
    query_for_embedding: str = ""
    is_indic: bool = False
    user_id: str = "anonymous"
    stable_session_id: str = "anonymous"
    chat_body_messages: list = field(default_factory=list)

    # --- Working state (mutated by stages) ---
    state: dict = field(default_factory=dict)
    cached_result: PipelineResult | None = None
    assessment: Any = None  # DistressAssessment | None
    has_distress_keywords: bool = False
    proactive_data: dict | None = None
    graph_result: dict | None = None
    graph_latency: int = 0
    final_answer: str = ""
    intent: str = "CASUAL"
    med_step: int = 0
    citations: list = field(default_factory=list)
    input_check: dict | None = None
    output_check: dict | None = None
    is_blocked: bool = False

    # --- Final output ---
    result: PipelineResult | None = None

    # --- Per-stage telemetry (set by stages, read by StageRunner) ---
    last_stage_status: str = "success"
    last_stage_metadata: dict | None = None

    # --- Query tier (set by CacheCheckStage, reused by GraphStage to avoid double LLM call) ---
    detected_query_tier: str | None = None