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
import uuid
from typing import TYPE_CHECKING, Any

from langgraph.errors import GraphRecursionError

from app.assistant_authorization import resolve_effective_assistant
from app.assistant_registry import resolve_assistant_scope
from app.config import settings
from app.orchestrator_utils import get_expected_keywords, select_graph_for_query
from app.pipeline.result import PipelineResult  # noqa: F401  (re-export hint)
from app.release_manifest import get_release_manifest
from app.pipeline.stages.base import Stage
from rag.graph import create_initial_state
from rag.timeout_utils import TimeoutBudget, budget_var

if TYPE_CHECKING:
    from app.pipeline.stages.context import PipelineContext

logger = logging.getLogger(__name__)


def _assistant_config_fingerprint(assistant: Any, *, is_authed: bool) -> str:
    """Bounded SHA-256 digest of the effective assistant configuration.

    Covers slug, the effective system prompt (M3 gate: dropped for
    unauthenticated requests AND when the slug is not on the server-side
    allowlist — InputGuardrailStage clears assistant.system_prompt in both
    cases before this runs), and knowledge_tags. Raw prompt text never enters
    the key — only the first 16 hex chars of the digest. Two requests with
    different effective configurations can never coalesce onto the same key.
    Non-str attrs (e.g. mocks in tests) degrade to "" and never raise.
    """
    slug = getattr(assistant, "slug", None)
    system_prompt = getattr(assistant, "system_prompt", None) if is_authed else None
    tags = getattr(assistant, "knowledge_tags", None)
    if not isinstance(tags, (list, tuple, set)):
        tags = []
    config_text = "|".join(
        [
            slug if isinstance(slug, str) else "",
            system_prompt if isinstance(system_prompt, str) else "",
            ",".join(sorted(t for t in tags if isinstance(t, str))),
        ]
    )
    return hashlib.sha256(config_text.encode("utf-8")).hexdigest()[:16]


def _attachment_context_from_request(request: object) -> str:
    """Return only validated string evidence from a chat request."""
    value = getattr(request, "attachment_context", None)
    return value if isinstance(value, str) else ""


def _coalesce_key(
    user_id: str,
    session_id: str,
    lang_code: str,
    user_msg_en: str,
    history_hash: str,
    config_fingerprint: str = "",
    meditation_step: int = 0,
    attachment_fingerprint: str = "",
) -> str:
    """Build the coalescer key for a graph run.

    P1-BE-7: the raw user message is never embedded — it is unbounded, may
    carry PII, and varies across locales. A bounded, deterministic SHA-256
    digest (first 16 hex chars) keeps coalescing semantics identical while
    keeping user text out of cache keys. The assistant-config fingerprint
    (also bounded) and meditation_step scope the key so runs under different
    effective assistant configurations or meditation steps never coalesce.
    """
    digest = hashlib.sha256(user_msg_en.encode("utf-8")).hexdigest()[:16]
    return (
        f"{user_id}:{session_id}:{lang_code}:{digest}:{history_hash}:"
        f"{config_fingerprint}:{meditation_step}:{attachment_fingerprint}"
    )


class GraphStage(Stage):
    """Run the LangGraph pipeline via the selected graph strategy facade."""

    name = "langgraph"

    async def run(self, ctx: PipelineContext) -> PipelineResult | None:
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
            _user = ctx.user or {}
            requested_slug = getattr(assistant, "slug", None)
            resolution = None
            if ctx.assistant_scope is not None and requested_slug:
                scope = ctx.assistant_scope
                _persona = getattr(assistant, "system_prompt", None)
            else:
                resolution = await resolve_effective_assistant(requested_slug, _user, container)
                if resolution is None and requested_slug:
                    logger.warning("Rejecting assistant without authorized scope: %r", requested_slug)
                    requested_slug = None
                    scope = resolve_assistant_scope(None)
                    if assistant is not None:
                        assistant.system_prompt = None
                        assistant.knowledge_tags = []
                    _persona = None
                elif resolution is not None:
                    requested_slug = resolution.slug
                    scope = resolution.scope
                    if assistant is not None:
                        assistant.system_prompt = resolution.system_prompt
                        assistant.knowledge_tags = list(resolution.knowledge_tags)
                    _persona = resolution.system_prompt
                else:
                    scope = resolve_assistant_scope(None)
                    _persona = None
            initial_state = create_initial_state(
                question=user_msg_en,
                chat_history=chat_history_en,
                meditation_step=meditation_step,
                # ctx.trace_id (not the HTTP correlation id) — this is the id that
                # becomes chat_queries.id (orchestrator.py/stream_orchestrator.py
                # pass result.trace_id as query_id) and ChatResponse.trace_id.
                # Node-level telemetry keys off GraphState["request_id"]
                # (_persist_trace_span writes trace_spans.query_id from it), so
                # seeding it from the correlation id instead — an unrelated
                # per-HTTP-request uuid4, truncated to 8 chars by default and
                # never reconciled with trace_id — made every trace_spans insert
                # fail the column's UUID NOT NULL constraint and get silently
                # swallowed, and even a full-length id would never join back to
                # its chat_queries row (production-audit finding OBS-1).
                request_id=ctx.trace_id,
                assistant_slug=requested_slug,
                knowledge_tags=list(getattr(assistant, "knowledge_tags", []) or []),
                assistant_system_prompt=_persona,
            )
            initial_state["corpus_id"] = scope.corpus_id
            initial_state["teacher_id"] = scope.teacher_id
            initial_state["detected_language"] = (
                lang_detection.primary.value if lang_detection else "en"
            )
            initial_state["memory_context"] = memory_context
            # Attachment evidence is a per-turn input, separate from personal memory.
            # The generation layer labels it as untrusted material and never persists it.
            attachment_context = _attachment_context_from_request(chat_body)
            initial_state["attachment_context"] = attachment_context or None
            initial_state["expected_keywords"] = get_expected_keywords(user_msg_en)
            if proactive_data:
                initial_state["proactive_serene_mind"] = proactive_data

            if settings.ab_testing_enabled and random.random() < settings.ab_testing_ratio:
                initial_state["ab_model"] = "krutrim"
            else:
                initial_state["ab_model"] = "primary"

            # Establish admission deadline propagation as remaining time budget
            elapsed_admission = (
                max(0.0, time.time() - ctx.start_time)
                if getattr(ctx, "start_time", 0.0) > 0
                else 0.0
            )
            remaining_budget = max(0.0, float(settings.pipeline_timeout) - elapsed_admission)
            budget = TimeoutBudget(total_budget=remaining_budget)
            token = budget_var.set(budget)

            # Reuse CacheCheckStage's preclassification when available. Direct
            # stage callers and cache-disabled requests still classify here.
            on_device_started = time.perf_counter()
            if ctx.preclassified_intent:
                on_device_result = (
                    ctx.preclassified_intent,
                    ctx.preclassified_tier or "standard",
                    ctx.preclassified_reason or "preclassified",
                )
            else:
                from rag.nodes.on_device_intent import classify_with_reason

                on_device_result = await asyncio.to_thread(classify_with_reason, user_msg_en)
            logger.info(
                "GRAPH_ROUTING_TIMING trace_id=%s phase=on_device_intent duration_ms=%.1f reused=%s",
                ctx.trace_id,
                (time.perf_counter() - on_device_started) * 1000,
                bool(ctx.preclassified_intent),
            )
            detected_intent = on_device_result[0] if on_device_result else None
            if detected_intent:
                initial_state["intent"] = detected_intent
                # Pre-fill query_tier from on-device classifier
                # Uses is None check because create_initial_state always sets query_tier=None.
                if initial_state.get("query_tier") is None:
                    initial_state["query_tier"] = (
                        "tier2_simple"
                        if detected_intent in ("CASUAL", "FACTUAL", "DISTRESS", "MEDITATION")
                        else "tier3_complex"
                    )

            # Kill #7: reuse query tier already determined by CacheCheckStage to avoid
            # a redundant select_graph_for_query call. Falls back to calling it only
            # if the cache stage didn't run (e.g., cache disabled).
            tier_for_graph = initial_state.get("query_tier", "standard")
            route_decision_method = "cache_tier_reuse"
            if ctx.detected_query_tier is not None and detected_intent != "DISTRESS":
                # Fast path: CacheCheckStage already ran select_graph_for_query — reuse result.
                # Honor the on-device classifier's fast-tier decision; the cache stage runs
                # before intent classification and can over-classify simple queries.
                #
                # Exception: a CacheCheckStage "deep" result comes from a deterministic
                # regex match (compare/contrast/difference between/relationship between —
                # see HEURISTIC_DEEP_PATTERNS), a stronger complexity signal than the
                # on-device classifier's coarse intent-based tier guess. Letting
                # tier_for_graph="tier2_simple" force "fast" here silently dropped
                # genuinely comparative/multi-hop queries onto the fast graph, which
                # skips grade_documents/verify_answer/extract_citations entirely.
                if ctx.detected_query_tier == "deep":
                    graph_variant = "deep"
                else:
                    graph_variant = (
                        ctx.detected_query_tier
                        if tier_for_graph not in ("fast", "tier2_simple")
                        else "fast"
                    )
            else:
                route_decision_method = "graph_selector"
                graph_selection_started = time.perf_counter()
                # A coarse factual tier is an admission hint, not a complexity
                # verdict. Let the selector inspect the full query shape so
                # comparison, temporal, multi-part, and deep cues can choose
                # the quality graph. Casual and meditation paths retain their
                # bounded tier2 route; distress is guarded below on the full
                # graph.
                selector_tier = tier_for_graph
                if detected_intent in ("FACTUAL", "QUERY") and selector_tier in (
                    "fast",
                    "tier2_simple",
                ):
                    selector_tier = None
                graph_variant = await select_graph_for_query(
                    user_msg_en,
                    container=container,
                    detected_intent=detected_intent,
                    query_tier=selector_tier,
                )
                logger.info(
                    "GRAPH_ROUTING_TIMING trace_id=%s phase=graph_selection variant=%s duration_ms=%.1f",
                    ctx.trace_id,
                    graph_variant,
                    (time.perf_counter() - graph_selection_started) * 1000,
                )

            # Explicit check to preserve full RAG/guardrail path for DISTRESS
            if detected_intent == "DISTRESS" and graph_variant == "fast":
                graph_variant = "standard"
                initial_state["query_tier"] = "standard"

            # Only set query_tier if on-device didn't already set it
            if "query_tier" not in initial_state or initial_state.get("query_tier") is None:
                initial_state["query_tier"] = graph_variant
            elif graph_variant != "fast" and initial_state["query_tier"] in (
                "fast",
                "tier2_simple",
            ):
                # Divergence guard: graph_variant is the tier CacheCheckStage's
                # intent-blind classifier actually resolved (it catches deep
                # patterns like "difference between" that the on-device
                # classifier's coarser FACTUAL/CASUAL guess misses). Every
                # in-graph gate (grade_documents, retrieval depth,
                # verify_answer) reads state["query_tier"], not graph_variant
                # -- left at "tier2_simple" it self-bypasses real grading and
                # verification even while running the standard/deep graph.
                # Promote to the tier matching the graph actually selected:
                # "deep" graph_variant means tier4_deep-gated logic
                # (deep_contradiction_gate, route_after_verification) must
                # see "tier4_deep", not the "standard" that was previously
                # used for both -- that silently downgraded deep queries out
                # of their own tier's extra verification pass.
                initial_state["query_tier"] = (
                    "tier4_deep" if graph_variant == "deep" else "standard"
                )

            selected_graph = getattr(container, f"{graph_variant}_graph")

            # Verify the fast_graph definition contains the distress/quality-gate nodes before allowing fast routing
            if graph_variant == "fast":
                required_nodes = ["handle_distress_check", "handle_distress"]
                if not hasattr(selected_graph, "nodes") or not all(
                    node in selected_graph.nodes for node in required_nodes
                ):
                    logger.warning(
                        "fast_graph is missing required distress/quality-gate nodes! Routing to standard graph instead."
                    )
                    graph_variant = "standard"
                    selected_graph = container.standard_graph
                    initial_state["query_tier"] = "standard"

            # This manifest is internal-only and intentionally contains enums,
            # booleans, and a release policy id—not prompts, memory, or graph state.
            policy_version = get_release_manifest().to_dict().get("policy_version", "unknown")
            ctx.route_metadata.update(
                {
                    "requested_variant": str(ctx.detected_query_tier or tier_for_graph)[:32],
                    "selected_variant": str(graph_variant)[:32],
                    "detected_cache_tier": str(ctx.detected_query_tier or "unknown")[:32],
                    "normalized_query_tier": str(initial_state.get("query_tier") or "unknown")[:32],
                    "on_device_intent": str(detected_intent or "unknown")[:32],
                    "decision_method": route_decision_method,
                    "policy_version": str(policy_version)[:128],
                }
            )
            try:
                import uuid

                user_id = ctx.user_id or str(uuid.uuid4())
                session_id = getattr(chat_body, "session_id", None) or str(uuid.uuid4())
                config = {
                    "recursion_limit": 60,
                    "configurable": {
                        "user_id": user_id,
                        "session_id": session_id,
                        **({"stream_queue": stream_queue} if stream_queue else {}),
                    },
                }
                graph_invoke_started = time.perf_counter()
                graph_result = await selected_graph.ainvoke(initial_state, config=config)
                logger.info(
                    "GRAPH_ROUTING_TIMING trace_id=%s phase=graph_invoke variant=%s duration_ms=%.1f",
                    ctx.trace_id,
                    graph_variant,
                    (time.perf_counter() - graph_invoke_started) * 1000,
                )
                return graph_result
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

        user_id = ctx.user_id or str(uuid.uuid4())
        session_id = getattr(chat_body, "session_id", None) or str(uuid.uuid4())
        history_hash = hashlib.md5(
            str([m["content"] for m in chat_history_en[-4:]]).encode(), usedforsecurity=False
        ).hexdigest()[:8]
        # Coalesce identity: bounded fingerprint of the effective assistant
        # configuration (M3 gate: system_prompt only for authenticated users)
        # plus meditation_step, so runs under different effective configurations
        # or steps never coalesce onto the same key. Raw prompt text never
        # enters the key — the fingerprint is a bounded digest.
        assistant = getattr(chat_body, "assistant", None)
        _user = ctx.user or {}
        _is_authed = (
            bool(_user.get("id"))
            and _user.get("id") != "anonymous"
            and not str(_user.get("id")).startswith("anon:")
            and not _user.get("is_anonymous")
        )
        config_fp = _assistant_config_fingerprint(assistant, is_authed=_is_authed)
        attachment_context = _attachment_context_from_request(chat_body)
        attachment_fp = hashlib.sha256(attachment_context.encode("utf-8")).hexdigest()[:16]
        elapsed_admission = (
            max(0.0, time.time() - ctx.start_time)
            if getattr(ctx, "start_time", 0.0) > 0
            else 0.0
        )
        remaining_timeout = max(0.0, float(settings.pipeline_timeout) - elapsed_admission)
        start_lat = time.time()
        try:
            # P1-BE-7: coalesce key carries a bounded digest, never raw user text.
            lang_code = lang_detection.primary.value if lang_detection else "en"
            if remaining_timeout <= 0.0:
                raise TimeoutError("Pipeline admission deadline expired before GraphStage execution")
            result = await asyncio.wait_for(
                coalescer.get_or_run(
                    _coalesce_key(
                        user_id,
                        session_id,
                        lang_code,
                        user_msg_en,
                        history_hash,
                        config_fp,
                        meditation_step,
                        attachment_fp,
                    ),
                    run,
                ),
                timeout=remaining_timeout,
            )
        except TimeoutError:
            logger.warning(
                f"Pipeline deadline ({remaining_timeout:.1f}s remaining of {settings.pipeline_timeout}s) exceeded. Returning graceful fallback."
            )
            fallback = {
                "final_answer": "The Guru took too long to respond. Please try again.",
                "intent": "TIMEOUT",
                "route_decision": "timeout",
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
        final_answer = (
            result.get("final_answer")
            or "The Guru is unable to answer this question. Please try again."
        )
        intent = result.get("intent", "CASUAL")
        if intent == "FACTUAL":
            intent = "QUERY"
        ctx.final_answer = final_answer
        ctx.intent = intent
        ctx.med_step = result.get("meditation_step", 0)
        ctx.citations = result.get("citations", [])
        return None
