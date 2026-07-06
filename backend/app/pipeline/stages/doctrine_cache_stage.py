"""Doctrine cache fast-path stage.

Checks DoctrineCache before running the heavy RAG graph pipeline.
If the query is a known doctrine question (exact or fuzzy match),
returns a pre-canned answer immediately, bypassing all downstream stages.
"""

from __future__ import annotations

import logging

from app.pipeline.result import PipelineResult
from app.pipeline.stages.base import Stage

logger = logging.getLogger(__name__)


class DoctrineCacheStage(Stage):
    """Fast-path stage using DoctrineCache for known spiritual questions."""

    name = "doctrine_cache"

    async def run(self, ctx) -> PipelineResult | None:  # noqa: ANN001  — ctx: PipelineContext
        doctrine_cache = getattr(ctx.container, "doctrine_cache", None) if ctx.container else None
        if doctrine_cache is None:
            return None

        answer = doctrine_cache.lookup(ctx.user_msg)
        if not answer:
            return None

        logger.info("DoctrineCache fast-path hit for: %s", ctx.user_msg[:60])
        # cache_hit=True also makes the coordinator patch in the real latency;
        # citations stay empty — the canned answer embeds its own source line,
        # and "doctrine-cache" is not a retrievable source.
        return PipelineResult(
            final_answer=answer,
            intent="doctrine",
            trace_id=getattr(ctx, "trace_id", "doctrine-hit"),
            latency_ms=0,
            citations=[],
            route_decision="doctrine_cache",
            cache_hit=True,
        )
