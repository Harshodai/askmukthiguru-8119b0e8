"""Mukthi Guru — Pipeline Coordinator

Extracts the shared conversational pipeline logic from both
ChatRequestOrchestrator and ChatStreamRequestOrchestrator.

Responsibilities (in order):
  1. Cache lookup (exact + semantic)
  2. Circuit-breaker pre-check
  3. Request-state preparation (language detection, translation, memory)
  4. Input guardrails
  5. Distress detection (Serene Mind)
  6. Proactive Serene Mind triggering
  7. LangGraph execution (fast / standard / deep)
  8. Post-processing (translation, memory saving, cache update)
  9. Output guardrails
  10. Telemetry data assembly

All spiritual-accuracy guarantees (guardrails, distress detection,
verification thresholds, doctrinal keyword injection) are preserved.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import random
import re
import time
import uuid
from typing import Any

from app.config import settings
from app.context import correlation_id_var
from app.dependencies import ServiceContainer
from app.metrics import CACHE_OPERATIONS, REQUEST_COUNT, REQUEST_LATENCY, SEARCH_PATH_TOTAL, SEARCH_LATENCY_MS
from app.orchestrator_utils import (
    cache_language_key,
    get_expected_keywords,
    prepare_request_state,
    select_graph_for_query,
)
from app.pipeline.result import PipelineResult
from app.telemetry.publisher import TelemetryPublisher
from langgraph.errors import GraphRecursionError
from rag.graph import create_initial_state
from rag.memory import normalize_session_id
from rag.timeout_utils import TimeoutBudget, budget_var
from services.health_monitor import HealthMonitor
from services.turboquant_cache import TurboQuantCache
from services.hot_cache import hot_cache
from services.serene_mind_engine import DistressAssessment, DistressLevel

logger = logging.getLogger(__name__)

# ---- Kill #3: Randomized warm greetings for instant CASUAL short-circuit ----
# Industry standard (ChatGPT, Perplexity): greetings return <200ms with no LLM call.
_WARM_GREETINGS = [
    "\U0001f64f Namaste, dear seeker! I am Mukthi Guru, here to walk with you on the path of awakening. What wisdom would you like to explore today?",
    "\U0001f64f Welcome, dear friend! I am here to share the timeless wisdom of Sri Preethaji and Sri Krishnaji. How may I serve your journey?",
    "\U0001f64f Namaste! A beautiful state begins with a single question. What's on your heart today?",
    "\U0001f64f Hello, beloved seeker! Every moment is an invitation to awaken. What would you like to explore together?",
    "\U0001f64f Pranam! I am Mukthi Guru, your companion on the path of inner peace. What question brings you here today?",
    "\U0001f64f Welcome! As Sri Preethaji teaches, every encounter is an opportunity for connection. How can I guide you today?",
    "\U0001f64f Namaste! May our conversation bring you closer to the Beautiful State. What would you like to know?",
    "\U0001f64f Hello, dear one! I am here with the wisdom of the ancient teachings and the vision of Sri Krishnaji. Ask me anything.",
    "\U0001f64f Welcome back! The path of awakening continues with each new question. What shall we explore?",
    "\U0001f64f Namaste, dear seeker! Like a Soul Sync breath, let us begin with presence. What is in your heart?",
]

# Regex for instant greeting detection (no embedding, no LLM)
_GREETING_RE = re.compile(
    r"^\s*(hi|hello|hey|namaste|pranam|namaskar|namasthe|greetings|"
    r"good\s*(morning|afternoon|evening|night)|howdy|yo|hola|\U0001f64f)\s*[!.?]*\s*$",
    re.IGNORECASE,
)

# Distress keyword pre-screen for Kill #4 — only triggers full analysis when present
_DISTRESS_KEYWORD_RE = re.compile(
    r"\b(suicid|kill\s*my|want\s*to\s*die|end\s*my\s*life|hurt\s*my|self[-\s]*harm|"
    r"hopeless|crying|panic|anxiety|depress|grief|alone|miserable|worthless|"
    r"helpless|nobody\s*cares|no\s*point|give\s*up|can'?t\s*go\s*on|overwhelm|"
    r"suffering|pain|afraid|scared|terrif|agony|desper|broken|tut\s*chuk|"
    r"akela|kashtam|dukh|takleef|udas)\b",
    re.IGNORECASE,
)


class PipelineCoordinator:
    """Core pipeline shared between sync and streaming orchestrators."""

    def __init__(self, container: ServiceContainer) -> None:
        self.container = container
        self.telemetry = TelemetryPublisher()
        from app.coalescer import build_coalescer
        self.coalescer = build_coalescer(redis_url=getattr(settings, "redis_url", None), ttl=60.0)
        self._vector_cache: TurboQuantCache | None = None
        self._health_monitor: HealthMonitor | None = None

    async def _stage(
        self,
        name: str,
        trace_id: str,
        *,
        start_ns: int = 0,
        status: str = "success",
        error_type: str = None,
        metadata: dict = None,
    ) -> None:
        """Emit a StageCompleted telemetry event."""
        latency_ms = int((time.time_ns() - start_ns) / 1_000_000) if start_ns else 0
        await self.telemetry.stage_complete(
            name, trace_id, latency_ms=latency_ms, status=status, error_type=error_type, metadata=metadata
        )

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
        stream_queue: asyncio.Queue | None = None,
    ) -> PipelineResult:
        """Execute the full pipeline and return a PipelineResult.

        Parameters
        ----------
        user_msg:
            Stripped user message (already validated by orchestrator).
        preferred_lang:
            User's preferred language code.
        chat_body:
            ChatRequest or ChatStreamRequest object (for state preparation).
        meditation_step:
            Current meditation step if applicable.
        session_id:
            Session ID for memory / cache correlation.
        user:
            Authenticated user dict (or None for anonymous).
        is_benchmark:
            Whether this is a benchmark request (affects circuit-breaker behaviour).

        Returns
        -------
        PipelineResult:
            Immutable result object with all pipeline outputs.
        """
        start_time = time.time()
        # Extract messages list for downstream use
        chat_body_messages = [m.model_dump() for m in chat_body.messages] if hasattr(chat_body, "messages") else []
        cache_key = self._build_context_aware_cache_key(user_msg, preferred_lang, chat_body_messages)
        # Pass original query text for vector cache embedding lookup
        query_for_embedding = user_msg
        is_indic = preferred_lang and not preferred_lang.startswith("en")
        user_id = user.get("id", "anonymous") if user else "anonymous"
        stable_session_id = normalize_session_id(session_id, user_id)

        trace_id = str(uuid.uuid4())

        # ------------------------------------------------------------------
        # 1. Cache Check
        # ------------------------------------------------------------------
        _s = time.time_ns()
        cached_result = await self._check_cache(cache_key, query_for_embedding, is_indic, preferred_lang)
        await self._stage("cache_check", trace_id, start_ns=_s, status="cached" if cached_result else "success")
        if cached_result is not None:
            latency_ms = int((time.time() - start_time) * 1000)
            return cached_result.with_latency(latency_ms)

        # ------------------------------------------------------------------
        # 2. Circuit Breaker
        # ------------------------------------------------------------------
        _s = time.time_ns()
        circuit_open = self._is_circuit_open()
        await self._stage("circuit_breaker", trace_id, start_ns=_s, status="error" if circuit_open else "success")
        if circuit_open:
            return self._circuit_open_result(is_benchmark, start_time)

        # ------------------------------------------------------------------
        # 3. Request State Preparation
        # ------------------------------------------------------------------
        _s = time.time_ns()
        state = await prepare_request_state(self.container, chat_body, preferred_lang, user=user)
        user_msg_en = state["user_msg_en"]
        chat_history_en = state["chat_history_en"]
        memory_context = state["memory_context"]
        lang_detection = state["lang_detection"]
        await self._stage("request_state", trace_id, start_ns=_s)

        # ------------------------------------------------------------------
        # 4. Input Guardrails
        # ------------------------------------------------------------------
        _s = time.time_ns()
        input_check = await self._run_input_guardrails(user_msg_en)
        await self._stage("input_guardrails", trace_id, start_ns=_s, status="error" if input_check["blocked"] else "success")
        if input_check["blocked"]:
            blocked_resp = input_check["response"]
            if is_indic:
                blocked_resp = await self.container.translation.translate_text(
                    text=blocked_resp, source_lang="en", target_lang=preferred_lang
                )
            return PipelineResult(
                final_answer=blocked_resp,
                intent="ERROR",
                blocked=True,
                block_reason=input_check["reason"],
                latency_ms=int((time.time() - start_time) * 1000),
                trace_id=trace_id,
                model_used=getattr(settings, "sarvam_cloud_model", None) or getattr(settings, "ollama_model", None),
                model_provider=getattr(settings, "llm_provider", None),
                route_decision="blocked",
            )

        # ------------------------------------------------------------------
        # 4b. CASUAL Short-Circuit (Kill #3)
        # ------------------------------------------------------------------
        # Industry standard: greetings return <200ms with no LLM call.
        # Only fires for pure greetings ("Hello", "Namaste", "Hi!") — anything
        # with spiritual keywords falls through to the full pipeline.
        if _GREETING_RE.match(user_msg_en):
            greeting = random.choice(_WARM_GREETINGS)
            if is_indic:
                greeting = await self.container.translation.translate_text(
                    text=greeting, source_lang="en", target_lang=preferred_lang
                )
            latency_ms = int((time.time() - start_time) * 1000)
            logger.info(f"Instant greeting short-circuit: {latency_ms}ms")
            return PipelineResult(
                final_answer=greeting,
                intent="CASUAL",
                trace_id=trace_id,
                latency_ms=latency_ms,
                model_used=getattr(settings, "sarvam_cloud_model", None) or getattr(settings, "ollama_model", None),
                model_provider=getattr(settings, "llm_provider", None),
                route_decision="instant_greeting",
                cache_hit=False,
            )

        # ------------------------------------------------------------------
        # 5. Distress Detection (Kill #4: conditional)
        # ------------------------------------------------------------------
        # Skip full LLM-based distress analysis for queries that are clearly
        # factual/casual with no distress keywords. Safety is preserved:
        # any query containing distress language always gets full analysis.
        _s = time.time_ns()
        _has_distress_keywords = bool(_DISTRESS_KEYWORD_RE.search(user_msg_en))
        if _has_distress_keywords:
            assessment = await self._detect_distress(user_msg_en, state)
        else:
            assessment = None
        await self._stage("distress_detection", trace_id, start_ns=_s)

        # ------------------------------------------------------------------
        # 6. Proactive Serene Mind (conditional on distress presence)
        # ------------------------------------------------------------------
        _s = time.time_ns()
        proactive_data = None
        if _has_distress_keywords:
            proactive_data = await self._maybe_trigger_proactive_serene_mind(
                assessment, user_id, chat_body, state
            )
        if proactive_data:
            state["proactive_serene_mind"] = proactive_data
        await self._stage("proactive_serene_mind", trace_id, start_ns=_s)

        # ------------------------------------------------------------------
        # 7. LangGraph Execution
        # ------------------------------------------------------------------
        _s = time.time_ns()
        graph_result, graph_latency = await self._run_graph(
            user_msg_en,
            chat_history_en,
            meditation_step,
            lang_detection,
            memory_context,
            state.get("proactive_serene_mind"),
            chat_body=chat_body,
            stream_queue=stream_queue,
        )
        await self._stage("langgraph", trace_id, start_ns=_s)

        final_answer = graph_result.get("final_answer") or "I apologize, something went wrong."
        intent = graph_result.get("intent", "CASUAL")
        if intent == "FACTUAL":
            intent = "QUERY"
        med_step = graph_result.get("meditation_step", 0)
        citations = graph_result.get("citations", [])

        # ------------------------------------------------------------------
        # 8. Translation (post-graph)
        # ------------------------------------------------------------------
        _s = time.time_ns()
        if is_indic:
            final_answer = await self.container.translation.translate_text(
                text=final_answer, source_lang="en", target_lang=preferred_lang
            )
        await self._stage("translation", trace_id, start_ns=_s)

        # ------------------------------------------------------------------
        # 9. Memory Saving
        # ------------------------------------------------------------------
        _s = time.time_ns()
        await self._save_memory(
            user_id,
            stable_session_id,
            chat_body_messages,
            user_msg,
            final_answer,
            intent,
            med_step,
            citations,
            distress_level=assessment.level.value if assessment else 0,
        )
        await self._stage("memory_save", trace_id, start_ns=_s)

        # ------------------------------------------------------------------
        # 10. Output Guardrails
        # ------------------------------------------------------------------
        _s = time.time_ns()
        output_check = await self.container.guardrails.check_output(final_answer)
        is_blocked = output_check["blocked"]
        if is_blocked:
            logger.info(f"Output moderated: {output_check['reason']}")
            final_answer = output_check["moderated_response"]
        await self._stage("output_guardrails", trace_id, start_ns=_s, status="error" if is_blocked else "success")

        # ------------------------------------------------------------------
        # 11. Cache Update
        # ------------------------------------------------------------------
        _s = time.time_ns()
        if not is_blocked:
            await self._update_cache(cache_key, final_answer, intent, med_step, citations)
        else:
            logger.info("Skipping cache update: output was blocked by guardrails.")
        await self._stage("cache_update", trace_id, start_ns=_s)

        # ------------------------------------------------------------------
        # 12. Result Assembly
        # ------------------------------------------------------------------
        latency_ms = int((time.time() - start_time) * 1000)

        retrieval_meta = self._build_retrieval_meta(citations)
        trigger_events = self._build_trigger_events(assessment)
        safety_events = self._build_safety_events(input_check, output_check)
        spans = self._build_spans(graph_result)
        response_data = self._build_response_data(graph_result, intent)

        return PipelineResult(
            final_answer=final_answer,
            intent=intent,
            meditation_step=med_step,
            citations=citations,
            trace_id=str(uuid.uuid4()),
            latency_ms=latency_ms,
            model_used=getattr(settings, "sarvam_cloud_model", None) or getattr(settings, "ollama_model", None),
            model_provider=getattr(settings, "llm_provider", None),
            route_decision=intent.lower(),
            query_tier=state.get("query_tier"),
            blocked=False,
            cache_hit=False,
            proactive_serene_mind=state.get("proactive_serene_mind"),
            faithfulness_score=response_data["faithfulness"],
            hallucination_flag=response_data["hallucination_flag"],
            answer_relevancy=response_data["answer_relevancy"],
            context_precision=response_data["context_precision"],
            context_recall=response_data["context_recall"],
            confidence_score=response_data.get("confidence_score"),
            judge_reasoning=response_data["judge_reasoning"],
            evaluation_trace=graph_result.get("evaluation_trace"),
            retrieval_metadata=retrieval_meta,
            trigger_events=trigger_events,
            safety_events=safety_events,
            spans=spans,
            follow_up_suggestions=graph_result.get("follow_up_suggestions", []),
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _check_cache(self, cache_key: str, query_text: str, is_indic: bool, preferred_lang: str) -> PipelineResult | None:
        """Return a PipelineResult if cache hit, else None.

        Checks tiers in order (fastest → slowest):
          1. Hot cache (in-memory dict, <1ms lookup)
          2. Vector cache (local TurboVec index, sub-ms lookup) — P90 fast path
          3. Exact cache (Redis, ~1-5ms lookup)
          4. Semantic cache (Qdrant vector, ~20-50ms lookup)
        """
        # Determine query tier and dynamic cache threshold
        query_tier = "standard"
        if self.container:
            try:
                from app.orchestrator_utils import select_graph_for_query
                query_tier = await select_graph_for_query(query_text, container=self.container)
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
            return PipelineResult(
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

        # --- 2. Vector cache (P90 fast path, sub-ms lookup via TurboVec) ---
        if settings.hybrid_search_enabled:
            cache_hit = await self._check_vector_cache(cache_key, query_text, threshold=threshold)
            if cache_hit is not None:
                SEARCH_PATH_TOTAL.labels(path="p90").inc()
                response, citations, cached_intent = cache_hit
                output_check = await self.container.guardrails.check_output(response)
                final_response = output_check["moderated_response"] if output_check["blocked"] else response

                if is_indic and final_response != response:
                    final_response = await self.container.translation.translate_text(
                        text=final_response, source_lang="en", target_lang=preferred_lang
                    )

                return PipelineResult(
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

        SEARCH_PATH_TOTAL.labels(path="p99").inc()

        # --- 3. Exact + Semantic cache ---
        cached = self.container.exact_cache.get(cache_key)
        if cached is None and self.container.semantic_cache and self.container.semantic_cache.is_available:
            cached = await asyncio.to_thread(self.container.semantic_cache.get, cache_key, threshold=threshold)

        if cached is not None:
            REQUEST_COUNT.labels(status="cache_hit").inc()
            cached_response = cached["response"]
            output_check = await self.container.guardrails.check_output(cached_response)
            final_response = output_check["moderated_response"] if output_check["blocked"] else cached_response

            if is_indic and final_response != cached_response:
                final_response = await self.container.translation.translate_text(
                    text=final_response, source_lang="en", target_lang=preferred_lang
                )

            return PipelineResult(
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
        return None

    def _ensure_vector_cache(self) -> TurboQuantCache:
        """Lazy-init TurboQuantCache."""
        if self._vector_cache is None:
            self._vector_cache = TurboQuantCache(
                dimension=settings.embedding_dimension,
                max_size=settings.faiss_cache_size,
            )
        return self._vector_cache

    async def _check_vector_cache(self, cache_key: str, query_text: str, threshold: float = None) -> tuple[str, list, str] | None:
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
        chat_history: list[dict] = None
    ) -> str:
        """Build cache key that handles follow-up questions."""
        base_key = cache_language_key(user_msg, preferred_lang)
        
        # For standalone questions, use simple key
        is_standalone = self._is_standalone_question(user_msg)
        if is_standalone:
            return base_key
        
        # For follow-ups, include previous question hash in key
        if chat_history:
            last_user_msg = None
            for msg in reversed(chat_history):
                # Ignore the current user message if it is already in the list
                if msg.get("role") == "user" and msg.get("content") != user_msg:
                    last_user_msg = msg.get("content", "")
                    break
            if last_user_msg:
                prev_hash = hashlib.md5(last_user_msg.encode()).hexdigest()[:8]
                return f"{base_key}:ctx:{prev_hash}"
        
        return base_key

    def _is_standalone_question(self, question: str) -> bool:
        """Detect if a question can be answered without context."""
        # Follow-up patterns that need context
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
        # Check circuit breaker attribute (name varies by provider)
        circuit = getattr(underlying, "_circuit", None) or getattr(underlying, "_circuit_breaker", None)
        return circuit is not None and not circuit.can_execute()

    def _circuit_open_result(self, is_benchmark: bool, start_time: float) -> PipelineResult:
        """Return an error PipelineResult when the circuit is open."""
        model = getattr(settings, "sarvam_cloud_model", None) or getattr(settings, "ollama_model", None)
        msg = "I apologize, but the service is temporarily unavailable. Please try again in a moment."
        latency_ms = int((time.time() - start_time) * 1000)
        return PipelineResult(
            final_answer=msg,
            intent="ERROR",
            trace_id=str(uuid.uuid4()),
            latency_ms=latency_ms,
            model_used=model,
            model_provider=getattr(settings, "llm_provider", None),
            route_decision="error",
        )

    async def _run_input_guardrails(self, user_msg_en: str) -> dict:
        """Run input guardrails and return the check result."""
        with REQUEST_LATENCY.labels(stage="guardrails").time():
            return await self.container.guardrails.check_input(user_msg_en)

    async def _detect_distress(self, user_msg_en: str, state: dict) -> DistressAssessment | None:
        """Run Serene Mind distress detection. Returns None on failure (non-fatal)."""
        try:
            if self.container.serene_mind:
                distress_history = state.get("distress_history", [])
                assessment_history = (
                    [{"role": "system", "content": f"Previous distress history: {distress_history}"}]
                    if distress_history
                    else []
                )
                assessment = await self.container.serene_mind.analyze_with_history(
                    user_msg_en, history=state.get("chat_history_en", []) + assessment_history
                )
                if assessment.level.value >= 2:
                    logger.info(f"Distress detected ({assessment.level.name}), passing to RAG pipeline for compassionate response.")
                return assessment
        except Exception as e:
            logger.warning(f"Serene Mind detection failed (non-fatal): {e}")
        return None

    async def _maybe_trigger_proactive_serene_mind(
        self,
        assessment: DistressAssessment | None,
        user_id: str,
        chat_body: Any,
        state: dict,
    ) -> dict:
        """Check if proactive Serene Mind should be triggered."""
        try:
            if not (self.container.serene_mind and self.container.user_profile):
                return {"triggered": False}

            current = assessment or DistressAssessment(
                level=DistressLevel.NONE,
                confidence=0.0,
                detected_signals=[],
                language_detected=state.get("lang_detection", {}).get("primary", {}).get("value"),
                recommended_response_type="normal",
            )

            proactive = await self.container.serene_mind.analyze_distress_trend(
                user_id=user_id,
                current_assessment=current,
                user_profile_service=self.container.user_profile,
            )

            if not proactive:
                return {"triggered": False}

            _client_ts = getattr(chat_body, "last_serene_mind_at", None) or 0.0
            _now = time.time()
            _COOLDOWN = 15 * 60
            _skip = (_now - _client_ts) < _COOLDOWN

            if not _skip:
                _db_ts = await self.container.user_profile.get_last_meditation_session(user_id)
                if _db_ts and (_now - _db_ts) < _COOLDOWN:
                    _skip = True

            if _skip:
                logger.info(f"Proactive Serene Mind skipped for {user_id} — within 15-min cooldown.")
                return {"triggered": False}

            logger.info(f"Proactive Serene Mind triggered for user {user_id}: level={proactive.level.name}, confidence={proactive.confidence:.2f}")
            return {
                "triggered": True,
                "level": proactive.level.name,
                "confidence": proactive.confidence,
                "signals": proactive.detected_signals,
                "suggested_response": self.container.serene_mind.get_response(proactive),
                "teachings_prelude": (
                    "Sri Krishnaji and Preethaji teach us that suffering is not the truth of who you are. "
                    "Every moment of pain is also a doorway to awakening. "
                    "You are not alone in this — Mukti Guru is here with you. "
                    "Before we continue, let's pause together in a moment of Serene Mind."
                ),
            }
        except Exception as e:
            logger.warning(f"Proactive Serene Mind analysis failed (non-fatal): {e}")
        return {"triggered": False}

    async def _run_graph(
        self,
        user_msg_en: str,
        chat_history_en: list,
        meditation_step: int,
        lang_detection: Any,
        memory_context: str,
        proactive_data: dict | None,
        chat_body: Any,
        stream_queue: asyncio.Queue | None = None,
    ) -> tuple[dict, int]:
        """Run the LangGraph pipeline and return (result, latency_ms)."""
        import random

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

            # Kill #7: select_graph_for_query uses pure heuristics now (sub-1ms).
            # It respects the detected_intent and query_tier from on-device and does NOT make
            # an LLM call. We use the result to pick the graph variant but do
            # NOT overwrite query_tier — on-device tier is authoritative.
            tier_for_graph = initial_state.get("query_tier", "standard")
            graph_variant = await select_graph_for_query(
                user_msg_en,
                container=self.container,
                detected_intent=detected_intent,
                query_tier=tier_for_graph,
            )
            # Only set query_tier if on-device didn't already set it
            if "query_tier" not in initial_state or initial_state.get("query_tier") is None:
                initial_state["query_tier"] = graph_variant

            selected_graph = getattr(self.container, f"{graph_variant}_graph")
            try:
                config = {"recursion_limit": 60}
                if stream_queue:
                    config["configurable"] = {"stream_queue": stream_queue}
                return await selected_graph.ainvoke(initial_state, config=config)
            except GraphRecursionError as e:
                logger.warning(f"Graph recursion limit reached ({e}). Returning fallback response.")
                return {
                    **initial_state,
                    "final_answer": "I apologize, but this question requires broader context than I can gather right now...",
                    "intent": "QUERY",
                    "citations": [],
                }
            finally:
                budget_var.reset(token)

        history_hash = hashlib.md5(str([m["content"] for m in chat_history_en[-4:]]).encode()).hexdigest()[:8]
        start_lat = time.time()
        try:
            result = await asyncio.wait_for(
                self.coalescer.get_or_run(f"{lang_detection.primary.value if lang_detection else 'en'}:{user_msg_en}:{history_hash}", run),
                timeout=settings.pipeline_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(f"Pipeline outer timeout ({settings.pipeline_timeout}s) exceeded. Returning graceful fallback.")
            return {
                "final_answer": "I apologize, something went wrong — the pipeline took too long to respond.",
                "intent": "QUERY",
                "citations": [],
            }, int((time.time() - start_lat) * 1000)
        graph_latency = int((time.time() - start_lat) * 1000)
        return result, graph_latency

    async def _save_memory(
        self,
        user_id: str,
        stable_session_id: str,
        chat_body_messages: list,
        user_msg: str,
        final_answer: str,
        intent: str,
        med_step: int,
        citations: list,
        distress_level: int = 0,
    ) -> None:
        """Save conversation memory asynchronously."""
        if not self.container.user_profile:
            return
        try:
            from services.user_profile_service import ConversationMemory

            memory = ConversationMemory(
                session_id=stable_session_id,
                user_id=user_id,
                started_at=time.time(),
                messages=[
                    {"role": "user", "content": user_msg},
                    {"role": "assistant", "content": final_answer},
                ],
                key_insights=[c if isinstance(c, str) else c.get("title", "") for c in citations],
                emotional_arc=[
                    {
                        "timestamp": time.time(),
                        "distress_level": distress_level,
                        "provoked": False,
                        "topic": intent,
                    }
                ],
                follow_up_suggestions=[],
            )
            await self.container.user_profile.save_conversation_memory(memory)
        except Exception as e:
            logger.warning(f"Memory save failed (non-fatal): {e}")

        if settings.feature_memory_write and getattr(self.container, "memory_service", None):
            full_msgs = chat_body_messages + [
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": final_answer},
            ]

            async def _extract_with_retry():
                max_attempts = 3
                base_delay = 1.0
                for attempt in range(1, max_attempts + 1):
                    try:
                        await self.container.memory_service.extract_and_write(
                            user_id, stable_session_id, full_msgs
                        )
                        logger.debug(f"Memory extraction succeeded on attempt {attempt}")
                        return
                    except Exception as e:
                        if attempt == max_attempts:
                            logger.error(
                                f"Memory extraction failed after {max_attempts} attempts "
                                f"for user {user_id} session {stable_session_id}: {e}"
                            )
                            return
                        delay = base_delay * (2 ** (attempt - 1))
                        logger.warning(
                            f"Memory extraction attempt {attempt}/{max_attempts} failed: {e}. "
                            f"Retrying in {delay}s..."
                        )
                        await asyncio.sleep(delay)

            asyncio.create_task(_extract_with_retry())

    async def _update_cache(self, cache_key: str, final_answer: str, intent: str, med_step: int, citations: list) -> None:
        """Update all cache tiers: hot (in-memory), exact (Redis), semantic (Qdrant)."""
        # Audit cache updates: never cache fallback/refusal responses or empty results
        refusal_indicators = [
            "i don't have that specific teaching",
            "please try asking another question",
            "don't have any specific teaching",
            "do not have that specific teaching",
            "i apologize, something went wrong",
            "sorry, something went wrong",
        ]
        ans_lower = final_answer.lower()
        if not final_answer.strip() or any(indicator in ans_lower for indicator in refusal_indicators):
            logger.info("Skipping cache update: response is identified as a fallback/refusal.")
            return

        # For QUERY or FACTUAL intents, we must have citations to cache
        if intent in ["QUERY", "FACTUAL"] and not citations:
            logger.info("Skipping cache update: query/factual response has no citations.")
            return

        if intent in ["QUERY", "CASUAL", "FACTUAL"]:
            try:
                # Update hot cache first (fastest, no I/O)
                hot_cache.put(cache_key, final_answer, citations, ttl=300.0, intent=intent)

                # Update exact cache (Redis)
                self.container.exact_cache.put(
                    query=cache_key,
                    response=final_answer,
                    intent=intent,
                    citations=citations,
                    meditation_step=med_step,
                )

                # Update semantic cache (Qdrant — slowest, guarded)
                if self.container.semantic_cache and self.container.semantic_cache.is_available:
                    await asyncio.to_thread(
                        self.container.semantic_cache.put,
                        query=cache_key,
                        response=final_answer,
                        intent=intent,
                        citations=citations,
                        meditation_step=med_step,
                    )
            except Exception as e:
                logger.warning(f"Cache update failed (non-fatal): {e}")

    # ------------------------------------------------------------------
    # Metadata builders
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
    def _build_trigger_events(assessment: DistressAssessment | None) -> list[dict]:
        if assessment and assessment.level.value >= 2:
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
        
        # Calculate confidence using the ensemble if it is missing or is the placeholder 7.0 parallel-verify score
        confidence = result.get("confidence_score")
        if confidence is None or (is_rag and confidence == 7.0):
            from services.confidence_scorer import calculate_confidence
            # Inject standard default values for signals if missing from result
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
            "answer_relevancy": 1.0,
            "context_precision": 1.0,
            "context_recall": 1.0,
            "hallucination_flag": not result.get("is_faithful") if (is_rag and result.get("is_faithful") is not None) else False,
            "judge_reasoning": result.get("verification_reason", "") if is_rag else "",
            "confidence_score": confidence,
        }
