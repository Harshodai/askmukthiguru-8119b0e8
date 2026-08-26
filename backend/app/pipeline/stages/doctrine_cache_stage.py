"""Doctrine cache fast-path stage.

Checks DoctrineCache before running the heavy RAG graph pipeline.
If the query is a known doctrine question (exact or fuzzy match),
returns a pre-canned answer immediately, bypassing all downstream stages.
"""

from __future__ import annotations

import asyncio
import logging

from app.config import settings
from app.pipeline.result import PipelineResult
from app.pipeline.stages.base import Stage
from app.release_manifest import get_release_manifest

logger = logging.getLogger(__name__)


class DoctrineCacheStage(Stage):
    """Fast-path stage using DoctrineCache for known spiritual questions.

    Default disabled (DOCTRINE_CACHE_ENABLED=false): even with a curated,
    fully-cited FAQ file/table loaded, this bypasses retrieval and
    verification, which tanks ruthless benchmark scores. Enable only after
    curating a high-quality FAQ source — DoctrineCache.lookup() refuses to
    return any entry lacking structured citations, so there is no config-drift
    path back to an uncited answer (OH-P0-01).
    """

    name = "doctrine_cache"

    async def run(self, ctx) -> PipelineResult | None:  # noqa: ANN001  — ctx: PipelineContext
        if getattr(settings, "latency_benchmark_cache_disabled", False):
            logger.debug("Doctrine cache disabled for local latency benchmark")
            return None
        if not getattr(settings, "doctrine_cache_enabled", False):
            return None
        doctrine_cache = getattr(ctx.container, "doctrine_cache", None) if ctx.container else None
        if doctrine_cache is None:
            return None

        hit = doctrine_cache.lookup(ctx.user_msg)
        if not hit:
            return None
        answer = hit.answer
        citations = hit.citations

        # This stage short-circuits before TranslationStage ever runs (same
        # gap fixed in distress_stage.py's crisis-preemption path) — an Indic
        # user would otherwise get the canned English doctrine answer verbatim.
        if getattr(ctx, "is_indic", False):
            try:
                translation_timeout = max(1.0, settings.node_timeout_fast - 2.0)
                translated = await asyncio.wait_for(
                    ctx.container.translation.translate_text(
                        text=answer, source_lang="en", target_lang=ctx.preferred_lang
                    ),
                    timeout=translation_timeout,
                )
                answer = translated
            except TimeoutError:
                logger.warning(
                    "DoctrineCache translation timed out for Indic request; preserving English answer"
                )
            except Exception as e:
                logger.warning("DoctrineCache translation failed for Indic request: %s", e)

        logger.info("DoctrineCache fast-path hit for: %s", ctx.user_msg[:60])
        # cache_hit=True also makes the coordinator patch in the real latency.
        # citations come from the matched entry itself — DoctrineCache.lookup()
        # never returns an entry without them (audit finding OH-P0-01).
        return PipelineResult(
            final_answer=answer,
            intent="doctrine",
            trace_id=getattr(ctx, "trace_id", "doctrine-hit"),
            latency_ms=0,
            citations=citations,
            route_decision="doctrine_cache",
            cache_hit=True,
            release_manifest=get_release_manifest().to_dict(),
        )
