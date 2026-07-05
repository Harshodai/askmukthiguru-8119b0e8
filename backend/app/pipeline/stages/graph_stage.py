"""Graph stage — LangGraph execution (fast / standard / deep).

Body extracted verbatim from PipelineCoordinator._run_graph. The coalescer
stays on the coordinator and is reached via ``ctx.coordinator.coalescer``;
the graph facade (``container.<variant>_graph``) via ``ctx.container``.
Never short-circuits — writes ctx.graph_result / ctx.graph_latency.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import random
import time
from typing import TYPE_CHECKING

from app.config import settings
from app.context import correlation_id_var
from app.orchestrator_utils import get_expected_keywords, select_graph_for_query
from langgraph.errors import GraphRecursionError
from rag.graph import create_initial_state
from rag.timeout_utils import TimeoutBudget, budget_var

from app.pipeline.stages.base import Stage
from app.pipeline.result import PipelineResult  # noqa: F401  (re-export hint)

if TYPE_CHECKING:
    from app.pipeline.stages.context import PipelineContext

logger = logging.getLogger(__name__)


class GraphStage(Stage):
    """Run the LangGraph pipeline via the selected graph strategy facade."""

    name = "langgraph"

    async def run(self, ctx: "PipelineContext") -> PipelineResult | None:
        # ponytail: body of _run_graph verbatim (self -> ctx.coordinator / ctx.container)
        user_msg_en = ctx.state["user_msg_en"]
        chat_history_en = ctx.state["chat_history_en"]
        meditation_step = ctx.meditation_step
        lang_detection = ctx.state.get("lang_detection")
        memory_context = ctx.state.get("memory_context", "")
        proactive_data = ctx.proactive_data or ctx.state.get("proactive_serene_mind")
        chat_body = ctx.request
        stream_queue = ctx.stream_queue
        container = ctx.container
        coalescer = ctx.coordinator.coalescer

        async def run():
            assistant = getattr(chat_body, "assistant", None)
            initial_state = create_initial_state(
                question=user_msg_en,
                chat_history=chat_history_en,
                meditation_step=meditation_step,
                request_id=correlation_id_var.get(),
                assistant_slug=getattr(assistant, "slug", None),
                knowledge_tags=list(getattr(assistant, "knowledge_tags", []) or []),
                assistant_system_prompt=getattr(assistant, "system_prompt", None),
            )
            initial_state["detected_language"] = lang_detection.primary.value if lang_detection else "en"
            initial_state["memory_context"] = memory_context
            initial_state["expected_keywords"] = get_expected_keywords(user_msg_en)
            if proactive_data:
                initial_state["proactive_serene_mind"] = proactive_data

            if settings.ab_testing_enabled and random.random() < settings.ab_testing_ratio:
                initial_state["ab_model"] = "krutrim"
            else:
                initial_state["ab_model"] = "primary"

            budget = TimeoutBudget(total_budget=settings.pipeline_timeout)
            token = budget_var.set(budget)

            # Pre-classify intent before graph selection for fast-path routing
            from rag.nodes.on_device_intent import classify_with_reason
            on_device_result = classify_with_reason(user_msg_en)
            detected_intent = on_device_result[0] if on_device_result else None
            if detected_intent:
                initial_state["intent"] = detected_intent
                # Pre-fill query_tier from on-device classifier
                # Uses is None check because create_initial_state always sets query_tier=None.
                if initial_state.get("query_tier") is None:
                    initial_state["query_tier"] = "tier2_simple" if detected_intent in ("CASUAL", "FACTUAL", "DISTRESS", "MEDITATION") else "tier3_complex"

            # Kill #7: reuse query tier already determined by CacheCheckStage to avoid
            # a redundant select_graph_for_query call. Falls back to calling it only
            # if the cache stage didn't run (e.g., cache disabled).
            tier_for_graph = initial_state.get("query_tier", "standard")
            if ctx.detected_query_tier is not None:
                # Fast path: CacheCheckStage already ran select_graph_for_query — reuse result.
                graph_variant = ctx.detected_query_tier
            else:
                graph_variant = await select_graph_for_query(
                    user_msg_en,
                    container=container,
                    detected_intent=detected_intent,
                    query_tier=tier_for_graph,
                )
            # Only set query_tier if on-device didn't already set it
            if "query_tier" not in initial_state or initial_state.get("query_tier") is None:
                initial_state["query_tier"] = graph_variant

            selected_graph = getattr(container, f"{graph_variant}_graph")
            try:
                config = {"recursion_limit": 60}
                if stream_queue:
                    config["configurable"] = {"stream_queue": stream_queue}
                return await selected_graph.ainvoke(initial_state, config=config)
            except GraphRecursionError as e:
                logger.warning(f"Graph recursion limit reached ({e}). Returning fallback response.")
                return {
                    **initial_state,
                    "final_answer": "The Guru needs broader context to answer this question. Please try rephrasing.",
                    "intent": "QUERY",
                    "citations": [],
                }
            finally:
                budget_var.reset(token)

        history_hash = hashlib.md5(str([m["content"] for m in chat_history_en[-4:]]).encode()).hexdigest()[:8]
        start_lat = time.time()
        try:
            result = await asyncio.wait_for(
                coalescer.get_or_run(f"{lang_detection.primary.value if lang_detection else 'en'}:{user_msg_en}:{history_hash}", run),
                timeout=settings.pipeline_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(f"Pipeline outer timeout ({settings.pipeline_timeout}s) exceeded. Returning graceful fallback.")
            fallback = {
                "final_answer": "The Guru took too long to respond. Please try again.",
                "intent": "QUERY",
                "citations": [],
            }
            ctx.graph_result = fallback
            ctx.graph_latency = int((time.time() - start_lat) * 1000)
            ctx.final_answer = fallback["final_answer"]
            ctx.intent = fallback["intent"]
            ctx.med_step = 0
            ctx.citations = []
            return None
        ctx.graph_result = result
        ctx.graph_latency = int((time.time() - start_lat) * 1000)

        # ponytail: post-graph field extraction from execute() verbatim
        final_answer = result.get("final_answer") or "The Guru is unable to answer this question. Please try again."
        intent = result.get("intent", "CASUAL")
        if intent == "FACTUAL":
            intent = "QUERY"
        ctx.final_answer = final_answer
        ctx.intent = intent
        ctx.med_step = result.get("meditation_step", 0)
        ctx.citations = result.get("citations", [])
        return None