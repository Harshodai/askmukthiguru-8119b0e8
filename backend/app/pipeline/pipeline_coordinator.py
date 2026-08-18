"""Mukthi Guru — Pipeline Coordinator (thin)

The pipeline is composed of pure-function Stages (see ``app.pipeline.stages``).
``execute()`` builds a ``PipelineContext``, runs the stage chain via
``StageRunner``, and returns the result. Stage method bodies were extracted
verbatim into the stage classes — this file retains only:

  * the public ``execute()`` entrypoint (signature unchanged so
    ``orchestrator.py`` / ``stream_orchestrator.py`` need no changes)
  * private helpers stages reach through ``ctx.coordinator``:
    ``_check_vector_cache``, ``_ensure_vector_cache``, ``_embed_query``,
    ``_is_circuit_open``, ``_circuit_open_result``,
    ``_build_context_aware_cache_key``, ``_is_standalone_question``
  * metadata builders used by ``ResultAssemblyStage``:
    ``_build_retrieval_meta``, ``_build_trigger_events``,
    ``_build_safety_events``, ``_build_spans``, ``_build_response_data``
  * the ``_stage`` telemetry helper (used by ``StageRunner``)

All spiritual-accuracy guarantees (guardrails, distress detection,
verification thresholds, doctrinal keyword injection) are preserved —
the stage bodies are verbatim moves, not rewrites.
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import logging
import re
import time
import uuid
from typing import Any

from app.config import settings
from app.dependencies import ServiceContainer
from app.metrics import SEARCH_LATENCY_MS, SLO_CHAT_LATENCY
from app.orchestrator_utils import cache_language_key
from app.pipeline.result import PipelineResult
from app.pipeline.stages import PipelineContext, StageRunner, build_default_pipeline
from app.release_manifest import get_release_manifest
from rag.memory import normalize_session_id
from services.health_monitor import HealthMonitor
from services.hot_cache import hot_cache
from services.tenant_context import TenantContext
from services.turboquant_cache import TurboQuantCache, get_shared_vector_cache
from services.user_profile_service import _is_persistable_user_id

logger = logging.getLogger(__name__)


def _query_token(query: str) -> str:
    """Non-reversible 8-char token for log correlation — never logs raw user content."""
    return hashlib.sha256(query.encode()).hexdigest()[:8]


class PipelineCoordinator:
    """Core pipeline shared between sync and streaming orchestrators."""

    def __init__(self, container: ServiceContainer) -> None:
        self.container = container
        self.coalescer = getattr(container, "coalescer", None)
        self._vector_cache: TurboQuantCache | None = None
        self._health_monitor: HealthMonitor | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute(
        self,
        *,
        user_msg: str,
        preferred_lang: str,
        chat_body: Any,
        meditation_step: int = 0,
        session_id: str | None = None,
        user: dict | None = None,
        is_benchmark: bool = False,
        stream_queue: Any | None = None,
    ) -> PipelineResult:
        """Execute the full stage pipeline and return a PipelineResult.

        Signature is identical to the pre-refactor version, so
        ``orchestrator.py`` and ``stream_orchestrator.py`` need no changes.
        """
        start_time = time.time()
        chat_body_messages = (
            [m.model_dump() for m in chat_body.messages] if hasattr(chat_body, "messages") else []
        )
        assistant = getattr(chat_body, "assistant", None)
        assistant_slug = getattr(assistant, "slug", None)
        assistant_system_prompt = getattr(assistant, "system_prompt", None)
        assistant_knowledge_tags = list(getattr(assistant, "knowledge_tags", []) or [])
        assistant_config_present = bool(assistant_slug) or bool(assistant_system_prompt) or bool(
            assistant_knowledge_tags
        )
        response_preferences = getattr(chat_body, "response_preferences", None)
        response_preferences_data = (
            response_preferences.model_dump(mode="json")
            if hasattr(response_preferences, "model_dump")
            else {}
        )
        cache_key = self._build_context_aware_cache_key(
            user_msg,
            preferred_lang,
            chat_body_messages,
            assistant_slug,
            assistant_system_prompt,
            assistant_knowledge_tags,
            response_preferences_data,
        )
        is_indic = bool(preferred_lang) and not preferred_lang.startswith("en")
        user_id = user.get("id", "anonymous") if user else "anonymous"
        stable_session_id = normalize_session_id(session_id, user_id)
        trace_id = str(uuid.uuid4())

        ctx = PipelineContext(
            container=self.container,
            coordinator=self,
            request=chat_body,
            user_msg=user_msg,
            preferred_lang=preferred_lang,
            meditation_step=meditation_step,
            session_id=session_id,
            user=user,
            is_benchmark=is_benchmark,
            stream_queue=stream_queue,
            trace_id=trace_id,
            start_time=start_time,
            cache_key=cache_key,
            query_for_embedding=user_msg,
            is_indic=is_indic,
            user_id=user_id,
            stable_session_id=stable_session_id,
            chat_body_messages=chat_body_messages,
            assistant_config_present=assistant_config_present,
            incognito=bool(getattr(chat_body, "incognito", False)),
        )

        # Pre-stage personalization probe: CacheCheckStage is stage #1 while
        # RequestStateStage (which builds state.memory_context via
        # prepare_user_memory) runs later in the chain, so ctx.state is empty at
        # cache-lookup time. The flag must be computed here, BEFORE the chain,
        # or the cache read guard would silently degrade to dead code again.
        ctx.personalization_eligible = (
            False if ctx.incognito else await self._compute_personalization_eligible(user_id)
        )

        try:
            result = await asyncio.wait_for(
                StageRunner.run(build_default_pipeline(), ctx, coordinator=self),
                timeout=settings.pipeline_timeout + 60,
            )
        except asyncio.TimeoutError:
            logger.error(
                "Pipeline timed out for user %s: query_token='%s' trace='%s'",
                user_id, _query_token(user_msg), trace_id,
            )
            latency_ms = int((time.time() - start_time) * 1000)
            return PipelineResult(
                final_answer="The Guru took too long to respond. Please try again.",
                intent="TIMEOUT", trace_id=trace_id, latency_ms=latency_ms,
                model_used=None, model_provider=None, route_decision="timeout",
                release_manifest=get_release_manifest().to_dict(),
            )
        except Exception:
            logger.exception(
                "Pipeline crashed for user %s: query_token='%s' trace='%s'",
                user_id, _query_token(user_msg), trace_id,
            )
            latency_ms = int((time.time() - start_time) * 1000)
            return PipelineResult(
                final_answer="The Guru encountered an error. Please try again.",
                intent="ERROR", trace_id=trace_id, latency_ms=latency_ms,
                model_used=None, model_provider=None, route_decision="error",
                release_manifest=get_release_manifest().to_dict(),
            )

        if result is None:
            # ponytail: defensive — ResultAssemblyStage is terminal, but guard anyway
            latency_ms = int((time.time() - start_time) * 1000)
            return PipelineResult(
                final_answer="The Guru is unable to answer this question. Please try again.",
                intent="ERROR",
                trace_id=str(uuid.uuid4()),
                latency_ms=latency_ms,
                model_used=None,  # error fallback — no model produced this text
                model_provider=None,
                route_decision="error",
                release_manifest=get_release_manifest().to_dict(),
            )

        if result.release_manifest is None:
            result = dataclasses.replace(result, release_manifest=get_release_manifest().to_dict())

        # Cache-hit results are built with latency_ms=0; apply the real elapsed time.
        if result.cache_hit:
            latency_ms = int((time.time() - start_time) * 1000)
            res = result.with_latency(latency_ms)
            SLO_CHAT_LATENCY.labels(tier=(res.route_decision or "standard")).observe(latency_ms / 1000.0)
            return res

        SLO_CHAT_LATENCY.labels(tier=(result.route_decision or "standard")).observe(time.time() - start_time)
        return result

    # ------------------------------------------------------------------
    # Pre-stage personalization probe (consumed by the cache stage guards)
    # ------------------------------------------------------------------

    async def _compute_personalization_eligible(self, user_id: str) -> bool:
        """Request-level personalization probe, run BEFORE the stage chain.

        CacheCheckStage is stage #1; RequestStateStage (which builds
        state.memory_context via prepare_user_memory) runs later, so ctx.state
        is empty at cache-lookup time. The cache guards therefore key off this
        flag. The signal mirrors prepare_user_memory's own guards: anonymous /
        non-persistable user ids never receive memory_context (early returns),
        while a persistable user is eligible when any memory source holds data.
        Conservative on error/timeout: a failed probe returns True so a
        personalized query can never be replayed from the shared cache.
        """
        if not _is_persistable_user_id(user_id):
            return False
        try:
            return await asyncio.wait_for(self._probe_has_memory(user_id), timeout=0.200)
        except Exception as exc:
            # Conservative: a failed probe returns True so a personalized query
            # can never be replayed from the shared cache — but the swallowed
            # failure must stay visible in logs.
            logger.debug(
                "Personalization probe failed for user %s, returning conservative True: %s",
                user_id, exc,
            )
            return True

    async def _probe_has_memory(self, user_id: str) -> bool:
        """True if any probed memory source holds data for ``user_id``.

        user_profile.get_recent_memories and memory_service.get_core are the
        two side-effect-free, bounded probes. SecondBrainService.unlock() is
        deliberately NOT probed: it provisions a vault for vaultless users as a
        side effect, which a cache fast path must not trigger. A
        second-brain-only user is a theoretical residual gap (MemoryStage
        writes conversation memories alongside brain notes); the write guard's
        state-based fallback still covers that case.
        """
        profile_service = getattr(self.container, "user_profile", None)
        if profile_service is not None:
            try:
                if await profile_service.get_recent_memories(user_id, limit=1):
                    return True
            except Exception as exc:
                # a failed probe cannot prove absence
                logger.debug(
                    "user_profile.get_recent_memories probe failed for user %s, "
                    "treating as has-memory: %s", user_id, exc,
                )
                return True
        memory_service = getattr(self.container, "memory_service", None)
        if memory_service is not None:
            try:
                if await memory_service.get_core(user_id):
                    return True
            except Exception as exc:
                # a failed probe cannot prove absence
                logger.debug(
                    "memory_service.get_core probe failed for user %s, "
                    "treating as has-memory: %s", user_id, exc,
                )
                return True
        return False

    # ------------------------------------------------------------------
    # Telemetry helper (used by StageRunner)
    # ------------------------------------------------------------------

    async def _stage(
        self,
        name: str,
        trace_id: str,
        *,
        start_ns: int = 0,
        status: str = "success",
        error_type: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """No-op: the per-stage event-bus (events.py/publisher.py/sinks.py) was
        deleted as dead code -- every configured sink discarded the event, so
        this call did nothing on every request. Kept as a no-op because
        StageRunner calls it unconditionally after every stage."""
        return None

    # ------------------------------------------------------------------
    # Private helpers (called by stages via ctx.coordinator)
    # ------------------------------------------------------------------

    def _ensure_vector_cache(self) -> TurboQuantCache:
        """Bind the process-wide vector cache (this coordinator is rebuilt per request)."""
        if self._vector_cache is None:
            self._vector_cache = get_shared_vector_cache()
        return self._vector_cache

    async def _check_vector_cache(
        self, cache_key: str, query_text: str, threshold: float | None = None
    ) -> tuple[str, list, str] | None:
        """Check vector cache. Returns (response, citations, intent) or None."""
        vcache = self._ensure_vector_cache()
        if vcache.size == 0:
            return None

        embedding = await self._embed_query(query_text)
        if embedding is None:
            return None

        target_threshold = threshold if threshold is not None else settings.semantic_cache_similarity
        results = vcache.search(
            query_embedding=embedding,
            top_k=1,
            threshold=target_threshold,
        )
        if not results:
            return None

        best = results[0]
        meta = best["metadata"]
        score = best["score"]
        SEARCH_LATENCY_MS.labels(path="p90").observe(float(score))
        return (
            meta.get("response", ""),
            meta.get("citations", []),
            meta.get("intent", "QUERY"),
        )

    def _build_context_aware_cache_key(
        self,
        user_msg: str,
        preferred_lang: str,
        chat_history: list[dict] | None = None,
        assistant_slug: str | None = None,
        assistant_system_prompt: str | None = None,
        assistant_knowledge_tags: list[str] | None = None,
        response_preferences: dict | None = None,
    ) -> str:
        """Build cache key that handles follow-up questions.

        The key is prefixed with the active tenant so answers never bleed
        across tenants: the hot/exact/semantic/vector caches are all
        process- or Redis-wide, and without a tenant scope one tenant's
        generic answer would be served to every other tenant. TenantContext
        defaults to "default" (legacy single-tenant) for anonymous requests.

        A custom assistant persona changes the answer to the same question, so
        its configuration is part of the key. There is no server-side persona
        registry to validate a client-supplied ``assistant`` against, so the
        cache stages bypass the shared tiers entirely for such requests (see
        ``assistant_config_present`` on PipelineContext). The key still carries
        a bounded SHA-256 fingerprint of the effective assistant configuration
        (slug + system_prompt + knowledge_tags — never the raw prompt text) so
        any non-guarded cache use can never reuse results across different
        effective configurations. Absent assistant config keeps the legacy key
        unchanged.
        """
        tenant = TenantContext.get() or "default"
        manifest = get_release_manifest()
        persona = ""
        if assistant_slug or assistant_system_prompt or assistant_knowledge_tags:
            config_text = "|".join(
                [
                    assistant_slug or "",
                    assistant_system_prompt or "",
                    ",".join(sorted(assistant_knowledge_tags or [])),
                ]
            )
            config_fp = hashlib.sha256(config_text.encode("utf-8")).hexdigest()[:16]
            persona = f":asst:{config_fp}"
        preference_scope = ""
        if response_preferences:
            preference_fp = hashlib.sha256(
                json.dumps(response_preferences, sort_keys=True).encode("utf-8")
            ).hexdigest()[:12]
            preference_scope = f":pref:{preference_fp}"
        if ":" in manifest.release_id or ":" in manifest.policy_version:
            scope_digest = hashlib.sha256(
                f":rel:{manifest.release_id}:pol:{manifest.policy_version}".encode("utf-8")
            ).hexdigest()[:16]
            release_scope = f":rel:{scope_digest}"
        else:
            release_scope = f":rel:{manifest.release_id}:pol:{manifest.policy_version}"
        base_key = f"tenant:{tenant}{release_scope}{persona}{preference_scope}:{cache_language_key(user_msg, preferred_lang)}"

        is_standalone = self._is_standalone_question(user_msg)
        if is_standalone:
            return base_key

        if chat_history:
            last_user_msg = None
            for msg in reversed(chat_history):
                if msg.get("role") == "user" and msg.get("content") != user_msg:
                    last_user_msg = msg.get("content", "")
                    break
            if last_user_msg:
                prev_hash = hashlib.md5(last_user_msg.encode(), usedforsecurity=False).hexdigest()[:8]
                return f"{base_key}:ctx:{prev_hash}"

        return base_key

    def _is_standalone_question(self, question: str) -> bool:
        """Detect if a question can be answered without context."""
        follow_up_patterns = [
            r"^(tell me )?more( about it)?",
            r"^(can you )?(elaborate|explain)( more| further)?",
            r"^(what )?(about|do you mean)",
            r"^(why|how) (is that|so)\?",
            r"^(go on|continue|and then|what else)",
            r"^(can you )?(give|provide) (an )?example",
            r"^(that )?(sounds|seems) (good|interesting|helpful)",
            r"^(yes|yeah|sure|ok|okay)(,? (please|go ahead))?",
            r"^(what|how) (about|does) (that|it) (work|mean)",
        ]
        question_lower = question.lower().strip()
        for pattern in follow_up_patterns:
            if re.match(pattern, question_lower):
                return False
        return True

    async def _embed_query(self, query_text: str) -> list[float] | None:
        """Compute embedding for a query text."""
        try:
            embedder = getattr(self.container, "embedding", None)
            if embedder is None:
                return None
            if hasattr(embedder, "encode_single_full"):
                enc = await asyncio.to_thread(embedder.encode_single_full, query_text)
                emb = enc.get("dense")
                if hasattr(emb, "tolist"):
                    return emb.tolist()
                return emb
            elif hasattr(embedder, "encode"):
                result = await asyncio.to_thread(embedder.encode, query_text)
                if isinstance(result, dict):
                    return result.get("dense") or result.get("embedding")
                if hasattr(result, "tolist"):
                    return result.tolist()
                return result
            return None
        except Exception:
            logger.warning("Failed to compute query embedding for vector cache", exc_info=True)
            return None

    def _is_circuit_open(self) -> bool:
        """Check if the circuit breaker is open for the active provider.

        P1-BE-4: uses the public ``LLMProvider.is_circuit_open()`` probe
        (services/llm/base.py) instead of traversing provider internals like
        ``_service._circuit``, which breaks silently on refactors. Providers
        without a circuit report False (never open) by default.
        """
        provider = self.container.ollama
        if not hasattr(provider, "is_circuit_open"):
            # Unknown/legacy provider shape — treat as not open (fail-open,
            # same behavior as a provider without a breaker).
            return False
        try:
            result = provider.is_circuit_open()
            # Strict literal-bool test: real providers return plain bools.
            # Mock doubles (AsyncMock auto-attributes) return non-bool truthy
            # objects that must never trip the breaker.
            return result is True
        except Exception as e:
            # A throwing probe must not take the pipeline down — degrade to
            # not-open and surface the state loss in logs.
            logger.warning(f"is_circuit_open() probe failed, treating circuit as closed: {e}")
            return False

    def _circuit_open_result(self, is_benchmark: bool, start_time: float) -> PipelineResult:
        """Return an error PipelineResult when the circuit is open."""
        model = getattr(settings, "sarvam_cloud_model", None) or getattr(settings, "ollama_model", None)
        msg = "The Guru is unable to answer this question. Please try again."
        latency_ms = int((time.time() - start_time) * 1000)
        return PipelineResult(
            final_answer=msg,
            intent="ERROR",
            trace_id=str(uuid.uuid4()),
            latency_ms=latency_ms,
            model_used=model,
            model_provider=getattr(settings, "llm_provider", None),
            route_decision="error",
            blocked=True,
            block_reason="circuit_breaker_open",
            release_manifest=get_release_manifest().to_dict(),
        )

    # ------------------------------------------------------------------
    # Metadata builders (called by ResultAssemblyStage)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_retrieval_meta(citations: list) -> dict | None:
        if not citations:
            return None
        return {
            "chunk_ids": [c.get("id") if isinstance(c, dict) else "" for c in citations],
            "source_docs": [c.get("source_url") if isinstance(c, dict) else c for c in citations],
            "scores": [c.get("score", 0.0) if isinstance(c, dict) else 1.0 for c in citations],
            "top_k": len(citations),
            "hit": len(citations) > 0,
        }

    @staticmethod
    def _build_trigger_events(assessment: Any) -> list[dict]:
        if assessment and getattr(assessment, "level", None) and assessment.level.value >= 2:
            return [
                {
                    "name": "DISTRESS",
                    "metadata": {
                        "level": assessment.level.name,
                        "confidence": assessment.confidence,
                        "signals": assessment.detected_signals,
                    },
                }
            ]
        return []

    @staticmethod
    def _build_safety_events(input_check: dict, output_check: dict) -> list[dict]:
        events = []
        if input_check.get("blocked"):
            events.append({
                "event_type": "INPUT_GUARDRAIL",
                "decision": "BLOCKED",
                "reason": input_check.get("reason") or "Harmful input detected",
            })
        if output_check.get("blocked"):
            events.append({
                "event_type": "OUTPUT_GUARDRAIL",
                "decision": "BLOCKED",
                "reason": output_check.get("reason") or "Harmful output detected",
            })
        return events

    @staticmethod
    def _build_spans(result: dict) -> list[dict]:
        metrics = result.get("metrics")
        if not metrics:
            return []
        return [
            {"span_name": name, "start_ms": 0, "duration_ms": int(duration * 1000)}
            for name, duration in metrics.items()
        ]

    @staticmethod
    def _build_response_data(result: dict, intent: str) -> dict:
        is_rag = intent == "QUERY"

        confidence = result.get("confidence_score")
        if confidence is None or (is_rag and confidence == 7.0):
            from services.confidence_scorer import calculate_confidence
            conf_state = {
                "faithfulness_score": result.get("faithfulness_score", 1.0 if not is_rag else 0.0),
                "verification": result.get("verification") or {
                    "passed": result.get("is_faithful", True),
                    "cove_pass_ratio": 1.0 if result.get("is_faithful", True) else 0.0,
                },
                "reranked_docs": result.get("reranked_docs") or result.get("documents") or [],
                "citations": result.get("citations") or [],
                "evaluation_trace": result.get("evaluation_trace") or {},
            }
            confidence = calculate_confidence(conf_state)

        # A retrieval failure (no_context) is not a faithful answer and not a
        # hallucination — there was nothing to be faithful to. Emit NULL so it
        # is excluded from the faithfulness percentile instead of recorded as
        # 1.0, which had a retrieval outage reading as a perfect answer.
        no_context = is_rag and bool(result.get("no_context"))
        return {
            "faithfulness": None if no_context else (result.get("faithfulness_score", 0.0) if is_rag else 1.0),
            "hallucination_flag": not result.get("is_faithful") if (is_rag and result.get("is_faithful") is not None) else False,
            "judge_reasoning": result.get("verification_reason", "") if is_rag else "",
            "confidence_score": confidence,
            "node_timings": result.get("node_timings", {}),
        }