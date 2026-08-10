"""Tone adapter stage — guru voice transform with citation re-grounding.

Runs after citation resolution (graph output) and translation, before
OutputGuardrailStage so output moderation gates the final voice-adapted text.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from app.pipeline.stages.base import Stage
from services.citation_service import resolve

if TYPE_CHECKING:
    from app.pipeline.result import PipelineResult
    from app.pipeline.stages.context import PipelineContext

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 15.0


class ToneAdapterStage(Stage):
    """Transform the final answer into the guru voice, then re-verify citations.

    If the transform drops citation markers, the remaining citations no longer
    match the adapted text — clear them and zero the faithfulness score so
    un-grounded claims are never presented as sourced.
    """

    name = "tone_adapter"

    def __init__(self) -> None:
        self._adapter: Any = None

    def _get_adapter(self, container: Any) -> Any:
        """Lazy-init GuruToneAdapterNode — created once per stage instance."""
        if self._adapter is None:
            from rag.nodes.guru_tone_adapter import GuruToneAdapterNode

            self._adapter = GuruToneAdapterNode(
                llm_service=getattr(container, "llm_gateway", None),
                guru_brain_service=getattr(container, "guru_brain_service", None),
                guru_kg_service=getattr(container, "guru_kg_service", None),
            )
        return self._adapter

    async def run(self, ctx: "PipelineContext") -> "PipelineResult | None":
        pre_cited = resolve(ctx.final_answer, ctx.citations).citation_count

        assistant = getattr(ctx.request, "assistant", None)
        state_input = {
            "question": ctx.user_msg,
            "final_answer": ctx.final_answer,
            "guru_name": getattr(assistant, "slug", None),
            "request_id": ctx.trace_id,
        }
        try:
            res_state = await asyncio.wait_for(
                self._get_adapter(ctx.container).transform_tone(state_input),
                timeout=_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            logger.warning(f"ToneAdapterStage: transform failed ({exc}); keeping original answer.")
            return None

        transformed = res_state.get("final_answer") if isinstance(res_state, dict) else res_state
        if transformed and len(transformed.strip()) > 20:
            ctx.final_answer = transformed.strip()

        post_cited = resolve(ctx.final_answer, ctx.citations).citation_count
        if post_cited < pre_cited and ctx.citations:
            logger.warning(
                f"ToneAdapterStage: adapted answer lost {pre_cited - post_cited} citation(s); "
                "clearing citations and faithfulness."
            )
            ctx.citations = []
            if ctx.graph_result:
                ctx.graph_result["faithfulness_score"] = 0.0
        return None


if __name__ == "__main__":
    import asyncio
    from unittest.mock import MagicMock

    from app.pipeline.stages.context import PipelineContext

    class _NoopAdapter:
        def __init__(self, **kwargs):
            pass

        async def transform_tone(self, state_input):
            return {"final_answer": state_input["final_answer"]}

    async def _self_check() -> None:
        import rag.nodes.guru_tone_adapter as gta

        orig = gta.GuruToneAdapterNode
        gta.GuruToneAdapterNode = _NoopAdapter
        try:
            ctx = PipelineContext(
                container=MagicMock(),
                coordinator=MagicMock(),
                request=MagicMock(),
                user_msg="what is presence",
                final_answer="Presence arises from steadiness. [[CITE:1]]",
                citations=[{"id": "d1", "source_url": "u1"}],
                graph_result={"faithfulness_score": 0.9},
            )
            res = await ToneAdapterStage().run(ctx)
            assert res is None
            assert ctx.final_answer == "Presence arises from steadiness. [[CITE:1]]"
            assert ctx.citations, "citations must survive a faithful transform"
            print("ToneAdapterStage self-check OK")
        finally:
            gta.GuruToneAdapterNode = orig

    asyncio.run(_self_check())