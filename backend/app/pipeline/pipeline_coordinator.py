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
import hashlib
import logging
import re
import time
import uuid
from typing import Any

from app.config import settings
from app.dependencies import ServiceContainer
from app.metrics import SEARCH_LATENCY_MS
from app.orchestrator_utils import cache_language_key
from app.pipeline.result import PipelineResult
from app.pipeline.stages import PipelineContext, StageRunner, build_default_pipeline
from app.telemetry.publisher import TelemetryPublisher
from rag.memory import normalize_session_id
from services.health_monitor import HealthMonitor
from services.hot_cache import hot_cache
from services.turboquant_cache import TurboQuantCache, get_shared_vector_cache

logger = logging.getLogger(__name__)


def _query_token(query: str) -> str:
    """Non-reversible 8-char token for log correlation — never logs raw user content."""
    return hashlib.sha256(query.encode()).hexdigest()[:8]


class PipelineCoordinator:
    """Core pipeline shared between sync and streaming orchestrators."""

    def __init__(self, container: ServiceContainer) -> None:
        self.container = container
        self.telemetry = TelemetryPublisher()
        self.coalescer = container.coalescer
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
        cache_key = self._build_context_aware_cache_key(user_msg, preferred_lang, chat_body_messages)
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
            )

        # Cache-hit results are built with latency_ms=0; apply the real elapsed time.
        if result.cache_hit:
            return result.with_latency(int((time.time() - start_time) * 1000))
        return result

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
        """Emit a StageCompleted telemetry event."""
        latency_ms = int((time.time_ns() - start_ns) / 1_000_000) if start_ns else 0
        await self.telemetry.stage_complete(
            name, trace_id, latency_ms=latency_ms, status=status, error_type=error_type, metadata=metadata
        )

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
    ) -> str:
        """Build cache key that handles follow-up questions."""
        base_key = cache_language_key(user_msg, preferred_lang)

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
                prev_hash = hashlib.md5(last_user_msg.encode()).hexdigest()[:8]
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
                enc = embedder.encode_single_full(query_text)
                emb = enc.get("dense")
                if hasattr(emb, "tolist"):
                    return emb.tolist()
                return emb
            elif hasattr(embedder, "encode"):
                result = embedder.encode(query_text)
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
        """Check if the circuit breaker is open for the active provider."""
        underlying = self.container.ollama
        if hasattr(underlying, "_service"):
            underlying = underlying._service
        circuit = getattr(underlying, "_circuit", None) or getattr(underlying, "_circuit_breaker", None)
        return circuit is not None and not circuit.can_execute()

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

        return {
            "faithfulness": result.get("faithfulness_score", 0.0) if is_rag else 1.0,
            "hallucination_flag": not result.get("is_faithful") if (is_rag and result.get("is_faithful") is not None) else False,
            "judge_reasoning": result.get("verification_reason", "") if is_rag else "",
            "confidence_score": confidence,
        }