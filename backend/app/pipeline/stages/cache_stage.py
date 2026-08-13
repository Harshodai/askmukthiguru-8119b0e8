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
from app.constants import is_graceful_degradation
from app.metrics import CACHE_OPERATIONS, REQUEST_COUNT, SEARCH_LATENCY_MS, SEARCH_PATH_TOTAL
from app.pipeline.result import PipelineResult
from app.pipeline.stages.base import Stage
from services.hot_cache import hot_cache

if TYPE_CHECKING:
    from app.pipeline.stages.context import PipelineContext

logger = logging.getLogger(__name__)


def _is_personalization_eligible(ctx: "PipelineContext") -> bool:
    """Single source of truth for the personalization-eligibility predicate.

    A query is personalization-eligible when the request carries this user's
    ``memory_context`` (core facts + recent turns). The shared caches key on
    (language, message) only, so an eligible query must never read from or
    write to them. Used by both CacheCheckStage (read guard) and
    CacheUpdateStage (write guard) so the two sides can never drift.

    Primary signal is the request-level ``personalization_eligible`` flag on
    the PipelineContext, populated by PipelineCoordinator.execute() BEFORE the
    stage chain (CacheCheckStage runs before RequestStateStage, so
    ``state.memory_context`` is empty at lookup time). The state-based check is
    kept as a fallback so direct-stage callers (unit tests) and the write
    guard's later-in-chain view agree with the same source of truth.
    """
    return bool(
        ctx.personalization_eligible
        or (ctx.state and ctx.state.get("memory_context"))
    )


def _is_assistant_config_present(ctx: "PipelineContext") -> bool:
    """Single source of truth for the assistant-configuration bypass predicate.

    True when the request carries client-supplied assistant configuration
    (slug / system_prompt / knowledge_tags). There is no server-side persona
    registry to validate it against, so the shared caches must neither read
    nor write for these requests: a stale answer generated under one
    effective configuration must never be replayed for a different one.
    Populated by PipelineCoordinator.execute() BEFORE the stage chain, same
    as ``personalization_eligible``.
    """
    return bool(ctx.assistant_config_present)


async def _invalidate_shared_entries(container, cache_key: str) -> None:
    """Purge previously-cached SHARED entries for ``cache_key``.

    Called when a response was personalization-sensitive (write guard's
    skipped path): a stale entry written earlier by a non-personalized answer
    would otherwise keep shadowing personalization — the next seeker with
    memory would be served it straight from the shared cache. Delete every
    tier that exposes a per-key API: hot (exact-key invalidate) and semantic
    (per-query invalidate). The Redis exact tier and the vector tier expose
    no per-key delete from this module (only nuclear ``invalidate_all`` /
    ``clear``), so they are intentionally skipped rather than nuked; their
    TTLs bound the staleness window.
    """
    try:
        hot_cache.invalidate(cache_key)
    except Exception as e:
        logger.debug("[cache stage] hot-cache invalidation failed: %s", e)

    semantic = getattr(container, "semantic_cache", None)
    if semantic is not None and getattr(semantic, "is_available", False):
        invalidate = getattr(semantic, "invalidate_by_query", None)
        if callable(invalidate):
            try:
                await asyncio.to_thread(invalidate, cache_key)
            except Exception as e:
                logger.debug("[cache stage] semantic-cache invalidation failed: %s", e)


class CacheCheckStage(Stage):
    """Cache lookup across hot / vector / exact / semantic tiers.

    Short-circuits the pipeline with a PipelineResult on hit, returns None on miss.
    """

    name = "cache_check"

    async def run(self, ctx: "PipelineContext") -> PipelineResult | None:
        if ctx.incognito:
            logger.debug("Cache read skipped for incognito request")
            return None
        cache_key = ctx.cache_key
        query_text = ctx.query_for_embedding
        is_indic = ctx.is_indic
        preferred_lang = ctx.preferred_lang
        container = ctx.container

        # Read-side guard (mirror of CacheUpdateStage's write guard below): a query
        # personalized with this user's memory_context must never be served a generic
        # cached answer. The shared caches key on (language, message) only, so without
        # this guard a memory-context query could replay another seeker's generic answer.
        # The eligibility flag is populated by PipelineCoordinator.execute() BEFORE the
        # stage chain: CacheCheckStage runs ahead of RequestStateStage, so
        # state.memory_context would otherwise still be empty here — this guard was
        # dead code at lookup time and a personalized query could be served a generic
        # shared-cache answer written by another user. The predicate's state fallback
        # keeps direct-stage callers and the write guard consistent with the same flag.
        # INVARIANT: the eligibility guard MUST run before any shared-cache read; never
        # return a shared entry for a personalization-eligible query. It sits above every
        # lookup tier below (hot / vector / exact / semantic) on purpose — moving it
        # below any of them would reintroduce the cross-user replay.
        if _is_personalization_eligible(ctx):
            logger.debug("cache hit skipped: memory_context present")
            return None

        # Read-side guard for client-supplied assistant configuration: without a
        # server-side persona registry the effective system prompt / retrieval
        # scope cannot be validated, so a shared-cache entry written under one
        # configuration must never be replayed for another. Sits above every
        # lookup tier below (hot / vector / exact / semantic) on purpose.
        if _is_assistant_config_present(ctx):
            logger.debug("cache hit skipped: client-supplied assistant configuration present")
            return None

        # Out-of-corpus logistics queries must bypass the cache entirely. "upcoming programs
        # from Ekam" and "what is Ekam" embed close, so the semantic cache would otherwise
        # serve a teaching answer for a logistics question (and vice-versa). Skipping the
        # cache forces the query to intent_router's deterministic honest short-circuit
        # (intent.py:_is_logistics_query → LIVE_LOGISTICS).
        try:
            from rag.nodes.intent import _is_logistics_query
            if query_text and _is_logistics_query(query_text):
                logger.info("CacheCheck: logistics query — bypassing cache for the honest short-circuit.")
                return None
        except Exception as _e:
            logger.debug("[cache stage] suppressed non-critical error: %s", _e)

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
                model_used=None,  # cached response — no model ran this request
                model_provider=None,
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
                    model_used=None,  # cached response — no model ran this request
                    model_provider=None,
                    route_decision="vector_cache_p90",
                    cache_hit=True,
                )
                ctx.last_stage_status = "cached"
                return result

        SEARCH_PATH_TOTAL.labels(path="p99").inc()

        # --- 3. Exact + Semantic cache ---
        cached = await asyncio.to_thread(container.exact_cache.get, cache_key)
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
                model_used=None,  # cached response — no model ran this request
                model_provider=None,
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
        if ctx.incognito:
            logger.debug("Cache write skipped for incognito request")
            return None
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

        # P1-BE-3: never cache a known-unfaithful answer — a hallucinated
        # response must not be replayed to every seeker with the same query.
        # The faithfulness verdict lives on ctx.graph_result (the LangGraph
        # generation node's output — generation.py:1795), NOT on ctx.state:
        # GraphStage copies only answer/intent/citations into ctx, so
        # ctx.state would carry no verdict at all. When no verdict was written
        # (non-RAG / no-context / fallback paths), keep the legacy behavior.
        graph_result = ctx.graph_result or {}
        verdict_present = any(
            key in graph_result for key in ("is_faithful", "faithfulness_score", "citations_verified")
        )
        if verdict_present:
            if graph_result.get("is_faithful") is False:
                logger.info("Skipping cache update: answer failed faithfulness verification.")
                return None
            faithfulness_score = graph_result.get("faithfulness_score")
            if faithfulness_score is not None and faithfulness_score < settings.cove_compulsory_threshold:
                logger.info(
                    "Skipping cache update: faithfulness score %.2f below cache threshold %.2f.",
                    faithfulness_score,
                    settings.cove_compulsory_threshold,
                )
                return None
            if graph_result.get("is_faithful") is None and not graph_result.get("citations_verified", False):
                # P1-AI-2 semantics: is_faithful None means the verifier was
                # legitimately skipped (fast tier), NOT that the answer failed —
                # but a cited-but-unverified answer (citations_verified=False)
                # must not be cached either: it has no grounding evidence and
                # would be replayed verbatim on the next identical query.
                logger.info("Skipping cache update: faithfulness unverified and citations not verified.")
                return None

        if intent in ["ERROR", "SAFETY_VIOLATION", "ADVERSARIAL", "DISTRESS"]:
            logger.info(f"Skipping cache update: intent '{intent}' is not cacheable.")
            return None

        # cache_key is (language, message) only — no user_id, no tenant_id — and every
        # tier below (hot, exact, semantic, vector) is process- or Redis-wide. But
        # context_engineer conditions the answer on this user's memory_context (core
        # facts + recent turns). Caching such an answer would replay one seeker's
        # private context to the next person who asks the same question.
        # Mirror of CacheCheckStage's read guard above — both sides share the
        # _is_personalization_eligible predicate (single source of truth), driven by
        # the request-level personalization_eligible flag populated before the chain.
        if _is_personalization_eligible(ctx):
            logger.info("Skipping cache update: response was personalized with user memory_context.")
            # A stale SHARED entry for this key (written earlier by a non-personalized
            # answer) must not survive the personalized response: it would be served to
            # the next memory-bearing seeker straight from the cache, shadowing their
            # personalization. Purge it on the skip path so a later shared lookup can
            # never serve a stale cross-user answer.
            await _invalidate_shared_entries(container, cache_key)
            return None

        # Mirror of CacheCheckStage's read guard: a response generated under a
        # client-supplied assistant configuration must never enter the shared
        # tiers — it could be replayed for a request with a different effective
        # configuration. The config fingerprint in cache_key means no stale
        # shared entry shares this key, so no invalidation is needed.
        if _is_assistant_config_present(ctx):
            logger.info("Skipping cache update: response used client-supplied assistant configuration.")
            return None

        if not isinstance(final_answer, str):
            logger.warning("Skipping cache update: final_answer is %s, not str", type(final_answer).__name__)
            return None

        refusal_indicators = [
            "i don't have that specific teaching",
            "please try asking another question",
            "don't have any specific teaching",
            "do not have that specific teaching",
            "the guru is unable",
            "sorry, something went wrong",
            # Live logistics response (intent.py:LIVE_LOGISTICS).
            # It is cheap to regenerate and MUST NOT be cached: the semantic cache would
            # otherwise replay it for teaching queries about Ekam (e.g. "what is Ekam?").
            "i don't have current schedules",
        ]
        ans_lower = final_answer.lower()
        if (
            not final_answer.strip()
            or is_graceful_degradation(final_answer)
            or any(indicator in ans_lower for indicator in refusal_indicators)
        ):
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
                await asyncio.to_thread(
                    container.exact_cache.put,
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

                # Update local vector cache (P90 fast path). Previously this stage
                # never wrote to TurboQuantCache, so the P90 cache stayed empty and
                # every repeat/similar query missed.
                if getattr(settings, "hybrid_search_enabled", False):
                    try:
                        query_text = ctx.query_for_embedding or cache_key
                        embedding = await ctx.coordinator._embed_query(query_text)
                        if embedding is not None:
                            vcache = ctx.coordinator._ensure_vector_cache()
                            # ponytail: must run off the event loop, same as
                            # exact_cache/semantic_cache above — vcache.put() can
                            # trigger a full O(max_size) native index rebuild on
                            # eviction (turboquant_cache.py's _evict_if_full), and
                            # a blocking call here freezes the single worker
                            # process for every other in-flight request. Confirmed
                            # live 2026-07-25: this exact call stalled the process
                            # long enough to fail Railway's health check and
                            # trigger a container restart under benchmark load.
                            await asyncio.to_thread(
                                vcache.put,
                                embedding=embedding,
                                metadata={
                                    "response": final_answer,
                                    "citations": citations,
                                    "intent": intent,
                                    "meditation_step": med_step,
                                    "cache_key": cache_key,
                                },
                            )
                    except Exception as e:
                        logger.warning(f"Vector cache update failed (non-fatal): {e}")
            except Exception as e:
                logger.warning(f"Cache update failed (non-fatal): {e}")
        return None
