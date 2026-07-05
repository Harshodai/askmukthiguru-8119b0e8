"""Cache stages — exact/semantic/vector cache lookup and post-graph cache update.

Bodies extracted verbatim from PipelineCoordinator._check_cache /
_update_cache / _check_vector_cache. Helpers (_check_vector_cache,
_ensure_vector_cache, _embed_query) stay on the coordinator and are
reached via ``ctx.coordinator``.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING

from app.config import settings
from app.metrics import CACHE_OPERATIONS, REQUEST_COUNT, SEARCH_LATENCY_MS, SEARCH_PATH_TOTAL
from app.pipeline.result import PipelineResult
from app.pipeline.stages.base import Stage
from services.hot_cache import hot_cache

if TYPE_CHECKING:
    from app.pipeline.stages.context import PipelineContext

logger = logging.getLogger(__name__)


class CacheCheckStage(Stage):
    """Cache lookup across hot / vector / exact / semantic tiers.

    Short-circuits the pipeline with a PipelineResult on hit, returns None on miss.
    """

    name = "cache_check"

    async def run(self, ctx: "PipelineContext") -> PipelineResult | None:
        cache_key = ctx.cache_key
        query_text = ctx.query_for_embedding
        is_indic = ctx.is_indic
        preferred_lang = ctx.preferred_lang
        container = ctx.container

        # Determine query tier and dynamic cache threshold.
        # Store result on ctx so GraphStage can reuse it — avoids redundant LLM classification.
        query_tier = "standard"
        if container:
            try:
                from app.orchestrator_utils import select_graph_for_query

                query_tier = await select_graph_for_query(query_text, container=container)
                ctx.detected_query_tier = query_tier  # cache for GraphStage
            except Exception as e:
                logger.warning(f"Failed to determine query tier for cache check: {e}")

        _CACHE_THRESHOLDS = {
            "fast": 0.82,
            "tier2_simple": 0.85,
            "standard": 0.87,
            "tier3_complex": 0.92,
            "deep": 0.92,
        }
        threshold = _CACHE_THRESHOLDS.get(query_tier, settings.semantic_cache_similarity)

        # --- 1. Hot cache (sub-millisecond) ---
        hot_hit = hot_cache.get(cache_key)
        if hot_hit is not None:
            response, citations, cached_intent = hot_hit
            if cached_intent.upper() in ("CASUAL", "GREETING"):
                return None
            CACHE_OPERATIONS.labels(cache_type="hot", result="hit").inc()
            result = PipelineResult(
                final_answer=response,
                intent=cached_intent,
                meditation_step=0,
                citations=citations,
                trace_id=str(uuid.uuid4()),
                latency_ms=0,
                model_used=getattr(settings, "sarvam_cloud_model", None) or getattr(settings, "ollama_model", None),
                model_provider=getattr(settings, "llm_provider", None),
                route_decision="hot_cache",
                cache_hit=True,
            )
            ctx.last_stage_status = "cached"
            return result

        # --- 2. Vector cache (P90 fast path, sub-ms lookup via TurboVec) ---
        if settings.hybrid_search_enabled:
            cache_hit = await ctx.coordinator._check_vector_cache(cache_key, query_text, threshold=threshold)
            if cache_hit is not None:
                SEARCH_PATH_TOTAL.labels(path="p90").inc()
                response, citations, cached_intent = cache_hit
                output_check = await container.guardrails.check_output(response)
                final_response = output_check["moderated_response"] if output_check["blocked"] else response

                if is_indic and final_response != response:
                    final_response = await container.translation.translate_text(
                        text=final_response, source_lang="en", target_lang=preferred_lang
                    )

                result = PipelineResult(
                    final_answer=final_response,
                    intent=cached_intent,
                    meditation_step=0,
                    citations=citations,
                    trace_id=str(uuid.uuid4()),
                    latency_ms=0,
                    model_used=getattr(settings, "sarvam_cloud_model", None) or getattr(settings, "ollama_model", None),
                    model_provider=getattr(settings, "llm_provider", None),
                    route_decision="vector_cache_p90",
                    cache_hit=True,
                )
                ctx.last_stage_status = "cached"
                return result

        SEARCH_PATH_TOTAL.labels(path="p99").inc()

        # --- 3. Exact + Semantic cache ---
        cached = container.exact_cache.get(cache_key)
        if cached is None and container.semantic_cache and container.semantic_cache.is_available:
            cached = await asyncio.to_thread(container.semantic_cache.get, cache_key, threshold=threshold)

        if cached is not None:
            REQUEST_COUNT.labels(status="cache_hit").inc()
            cached_response = cached["response"]
            output_check = await container.guardrails.check_output(cached_response)
            final_response = output_check["moderated_response"] if output_check["blocked"] else cached_response

            if is_indic and final_response != cached_response:
                final_response = await container.translation.translate_text(
                    text=final_response, source_lang="en", target_lang=preferred_lang
                )

            result = PipelineResult(
                final_answer=final_response,
                intent=cached.get("intent"),
                meditation_step=cached.get("meditation_step", 0),
                citations=cached.get("citations", []),
                trace_id=str(uuid.uuid4()),
                latency_ms=0,
                model_used=getattr(settings, "sarvam_cloud_model", None) or getattr(settings, "ollama_model", None),
                model_provider=getattr(settings, "llm_provider", None),
                route_decision="semantic_cache",
                cache_hit=True,
            )
            ctx.last_stage_status = "cached"
            return result
        return None


class CacheUpdateStage(Stage):
    """Post-graph cache update across hot / exact / semantic tiers. Never short-circuits."""

    name = "cache_update"

    async def run(self, ctx: "PipelineContext") -> PipelineResult | None:
        cache_key = ctx.cache_key
        final_answer = ctx.final_answer
        intent = ctx.intent
        med_step = ctx.med_step
        citations = ctx.citations
        container = ctx.container

        # Audit cache updates: never cache fallback/refusal responses, empty results, blocked responses, or errors
        if ctx.is_blocked or ctx.last_stage_status == "error":
            logger.info("Skipping cache update: response was blocked by guardrails or has a stage error status.")
            return None

        if intent in ["ERROR", "SAFETY_VIOLATION", "ADVERSARIAL", "DISTRESS"]:
            logger.info(f"Skipping cache update: intent '{intent}' is not cacheable.")
            return None

        refusal_indicators = [
            "i don't have that specific teaching",
            "please try asking another question",
            "don't have any specific teaching",
            "do not have that specific teaching",
            "the guru is unable",
            "sorry, something went wrong",
        ]
        ans_lower = final_answer.lower()
        if not final_answer.strip() or any(indicator in ans_lower for indicator in refusal_indicators):
            logger.info("Skipping cache update: response is identified as a fallback/refusal.")
            return None

        # For QUERY or FACTUAL intents, we must have citations to cache
        if intent in ["QUERY", "FACTUAL"] and not citations:
            logger.info("Skipping cache update: query/factual response has no citations.")
            return None

        if intent in ["QUERY", "CASUAL", "FACTUAL"]:
            try:
                # Update hot cache first (fastest, no I/O)
                hot_cache.put(cache_key, final_answer, citations, ttl=300.0, intent=intent)

                # Update exact cache (Redis)
                container.exact_cache.put(
                    query=cache_key,
                    response=final_answer,
                    intent=intent,
                    citations=citations,
                    meditation_step=med_step,
                )

                # Update semantic cache (Qdrant — slowest, guarded)
                if container.semantic_cache and container.semantic_cache.is_available:
                    await asyncio.to_thread(
                        container.semantic_cache.put,
                        query=cache_key,
                        response=final_answer,
                        intent=intent,
                        citations=citations,
                        meditation_step=med_step,
                    )
            except Exception as e:
                logger.warning(f"Cache update failed (non-fatal): {e}")
        return None