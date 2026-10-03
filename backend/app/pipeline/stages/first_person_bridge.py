"""FirstPersonBridgeStage — serve hash-verified teacher clips inside main chat.

Task 2 of ``.claude/tasks/world_class_production_elevation_and_docker_redeploy.md``.

Placement (plug-and-play cutover, plan
``.claude/tasks/langgraph_plug_play_pipelines_plan.md``): the bridge runs
INSIDE the LangGraph as the ``first_person`` pipeline module — dispatched by
the entry router in ``rag/pipeline_registry.py`` after the whole outer safety
lane (kill_switch → … → BoundedComparisonShortCircuitStage) and before every
general graph node. When the node claims the request, GraphStage returns the
bridge's ``PipelineResult`` and the stage chain short-circuits — skipping
GraphStage's downstream stages (TranslationStage, ToneAdapterStage,
OutputGuardrailStage, MemoryStage, CacheUpdateStage, ResultAssemblyStage)
exactly as the pre-cutover stage did, so this module re-applies the two rails
those skipped stages would have run, explicitly:

* **Translation policy** (sub-task 5): a living teacher's words are NEVER
  translated. Only the weaver's framing/glue goes through
  ``_translate_cached`` with ``translation_timeout_s`` (default 5s,
  fail-open). Quotes stay verbatim in their original language.
* **Output rail**: the same ``container.guardrails.check_output`` English
  phrase list ``OutputGuardrailStage`` runs, applied here to the
  pre-translation English answer (identical rationale: the rail is an English
  regex list). A blocked answer falls through to GraphStage — it is never
  served from this path.

Zero-generation invariant: ``answer_text`` is produced by
``FirstPersonPipeline`` → ``QuoteWeaverService`` (selection-only,
``QuoteWeaverAssertionGate``-validated). This stage never generates,
paraphrases, reorders, or synthesizes text; it gates, translates glue, and
packages.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import TYPE_CHECKING, Any

from app.config import settings
from app.orchestrator_utils import _translate_cached
from app.pipeline.result import PipelineResult
from app.pipeline.stages.base import Stage
from app.release_manifest import get_release_manifest
from app.route_taxonomy import RoutingProvenance, record_routing_decision

if TYPE_CHECKING:
    from app.pipeline.stages.context import PipelineContext

logger = logging.getLogger(__name__)

# Spans that must never enter a translation call: the verbatim quote itself,
# the bold speaker label (a name, not prose), the markdown link (its URL would
# be mangled), and any bare URL.
_PROTECTED_PATTERNS: tuple[str, ...] = (
    r"\*\*[^*\n]+\*\*",
    r"\[[^\]\n]*\]\(https?://[^)\s]+\)",
    r"https?://\S+",
)

# Glue worth translating must contain real words; rule lines, separators and
# punctuation-only runs are passed through untouched.
_HAS_WORDS_RE = re.compile(r"[A-Za-z]{3,}")


def _split_glue_and_quotes(text: str, verbatim_quotes: list[str]) -> list[tuple[bool, str]]:
    """Split an assembled answer into (protected, segment) runs.

    ``protected=True`` marks text that must be served byte-for-byte: the
    teacher's verbatim clip text, speaker labels, and links.
    """
    quotes = sorted({q for q in verbatim_quotes if q}, key=len, reverse=True)
    parts = [re.escape(q) for q in quotes] + list(_PROTECTED_PATTERNS)
    master = re.compile("(" + "|".join(parts) + ")")
    segments: list[tuple[bool, str]] = []
    pos = 0
    for match in master.finditer(text):
        if match.start() > pos:
            segments.append((False, text[pos : match.start()]))
        segments.append((True, match.group(0)))
        pos = match.end()
    if pos < len(text):
        segments.append((False, text[pos:]))
    return segments


async def _translate_glue_only(
    text: str,
    verbatim_quotes: list[str],
    container: Any,
    target_lang: str,
) -> str:
    """Sub-task 5 — translate framing/glue only; quotes are never translated.

    Translating a living teacher's words would be an alteration, so quote
    spans never reach the translator. Each glue segment is translated
    concurrently with the shared ``translation_timeout_s`` budget and fails
    open: a timeout or provider error keeps the English glue rather than
    blocking or dropping the answer.
    """
    service = getattr(container, "translation", None)
    if service is None or not target_lang:
        logger.warning("[FirstPersonBridge] No translation service; serving English glue.")
        return text
    segments = _split_glue_and_quotes(text, verbatim_quotes)
    glue_positions = [
        i
        for i, (protected, segment) in enumerate(segments)
        if not protected and _HAS_WORDS_RE.search(segment)
    ]
    if not glue_positions:
        return text
    timeout = float(getattr(settings, "translation_timeout_s", 5.0) or 5.0)

    async def _one(segment: str) -> str | None:
        try:
            translated = await _translate_cached(
                service,
                text=segment,
                source_lang="en",
                target_lang=target_lang,
                timeout=timeout,
            )
        except TimeoutError:
            logger.warning(
                "[FirstPersonBridge] Glue translation timed out after %.1fs; "
                "keeping English glue (fail-open)",
                timeout,
            )
            return None
        except Exception as exc:
            logger.warning(
                "[FirstPersonBridge] Glue translation failed; keeping English glue: %s", exc
            )
            return None
        if isinstance(translated, str) and translated.strip():
            return translated
        return None

    results = await asyncio.gather(*(_one(segments[i][1]) for i in glue_positions))
    for position, translated in zip(glue_positions, results):
        if translated:
            protected, _segment = segments[position]
            segments[position] = (protected, translated)
    return "".join(segment for _protected, segment in segments)


def _eligible_citations(citations: object) -> list[dict]:
    """Sub-task 1 — eligibility exclusion: teacher voice is voice-verified only.

    Clips reach here exclusively from ``FirstPersonPipeline.execute()``
    against the pinned first-person collection (``first_person_collection``,
    e.g. ``first_person_v7``), where the sha256 integrity gate, the
    content-quality gate, and the voice census have already run. This filter
    restates that contract at the chat boundary: a citation must prove it is
    a verbatim clip (``is_verbatim``), carry its own resolvable http(s)
    pointer, and carry the exact text it quotes.

    The chat corpus ``spiritual_wisdom_contextual`` (61% machine-rewritten)
    and OKF summaries may NEVER render as teacher speech — they have no clip
    contract, so they cannot pass here, and this stage never queries the chat
    corpus or OKF for answer text (no ``_resolve_speaker`` involvement
    either: ``rag/nodes/citation_extractor.py`` is untouched).
    """
    if not isinstance(citations, list):
        return []
    eligible: list[dict] = []
    for citation in citations:
        if not isinstance(citation, dict):
            continue
        if citation.get("is_verbatim") is not True:
            continue
        url = str(citation.get("source_url") or citation.get("url") or "")
        if not url.startswith(("http://", "https://")):
            continue
        if not str(citation.get("verbatim_text") or "").strip():
            continue
        eligible.append(citation)
    return eligible


def _sparse_vector(raw: object) -> dict | None:
    """Qdrant sparse payload shape (``{indices, values}``), or None."""
    if not isinstance(raw, dict) or not raw:
        return None
    try:
        return {"indices": [int(k) for k in raw], "values": [float(v) for v in raw.values()]}
    except (TypeError, ValueError):
        return None


def _dense_vector(encoded: object, expected_dimension: int) -> list[float] | None:
    """Validate the embedding contract; anything else means no bridge."""
    if not isinstance(encoded, dict):
        return None
    dense = encoded.get("dense")
    if hasattr(dense, "tolist"):
        dense = dense.tolist()
    if not isinstance(dense, (list, tuple)) or len(dense) != int(expected_dimension):
        return None
    try:
        return [float(value) for value in dense]
    except (TypeError, ValueError):
        return None


def _fp_pipeline(container: Any) -> Any:
    """One FirstPersonPipeline per process (calibration profile loaded once).

    Lazy import: ``app.api.first_person`` owns the shared ``_pipeline``
    lru_cache, and importing the API module at stage-import time would drag
    routers/limiters into the pipeline package.
    """
    from app.api.first_person import _pipeline

    llm_service = (
        getattr(container, "openrouter", None)
        or getattr(container, "nim", None)
        or getattr(container, "ollama", None)
    )
    rerank_embedding = (
        container.embedding if getattr(settings, "first_person_rerank_enabled", False) else None
    )
    return _pipeline(
        settings.first_person_collection,
        getattr(container, "serene_mind", None),
        rerank_embedding,
        llm_service,
    )


class FirstPersonBridgeStage(Stage):
    """Bridge a calibrated first-person direct answer into main chat.

    Sub-task 6 (safety ordering): reached after ``InputGuardrailStage`` and
    ``DistressStage`` — the outer safety lane — so an acute self-harm probe
    is already answered by the distress lane and this never runs for it.
    Sub-task 8 (degradation): any exception — and every non-direct outcome —
    logs and returns ``None`` so GraphStage runs exactly as today.

    Plug-and-play cutover note: the stage is no longer part of
    ``build_default_pipeline``; the bridge now runs inside the LangGraph as
    the ``first_person`` pipeline module (rag/pipeline_registry.py →
    rag/nodes/first_person.py). This class remains the single implementation
    home and the compatibility entry point — the graph node and the entry
    router reach it through ``run_first_person_bridge`` and
    ``first_person_bridge_enabled`` at the bottom of this module, so stage
    and node can never drift apart.
    """

    name = "first_person_bridge"

    @staticmethod
    def _enabled() -> bool:
        """Kill-switch + inherited first-person route gates (sub-task 8)."""
        if not getattr(settings, "first_person_chat_bridge_enabled", True):
            return False
        # Inherit the route's own gates: when the first-person route is off,
        # the chat bridge must not become a second, ungated serving path.
        if not getattr(settings, "first_person_route_enabled", False):
            return False
        if str(getattr(settings, "first_person_mode", "disabled")).strip().lower() == "disabled":
            return False
        return True

    async def run(self, ctx: PipelineContext) -> PipelineResult | None:
        if not self._enabled():
            return None
        try:
            return await self._bridge(ctx)
        except Exception:
            # Sub-task 8: fail open to the graph path. Never let bridge
            # infrastructure (embedding, Redis, Qdrant, translation) take the
            # chat request down — today's behavior is the fallback.
            logger.exception("[FirstPersonBridge] Bridge failed; falling through to GraphStage.")
            return None

    async def _bridge(self, ctx: PipelineContext) -> PipelineResult | None:
        query = str(getattr(ctx, "user_msg", "") or "").strip()
        if not query:
            return None
        state = getattr(ctx, "state", None) or {}
        # RequestStateStage already produced the English query (its own
        # bounded translation); never pay for a second one here.
        retrieval_query = str(state.get("user_msg_en") or query)
        container = ctx.container

        try:
            encoded = await container.embedding.encode_single_full_async(retrieval_query)
        except Exception as exc:
            # Embedding is bridge infrastructure, not chat infrastructure:
            # GraphStage performs its own retrieval embedding, so a failure
            # here only means "no bridge" (kept at DEBUG — the embedding
            # service logs its own errors).
            logger.debug("[FirstPersonBridge] Query embed unavailable; no bridge: %s", exc)
            return None
        dense = _dense_vector(encoded, settings.embedding_dimension)
        if dense is None:
            # Includes mocked/test containers: no vector contract, no bridge.
            logger.debug("[FirstPersonBridge] Dense vector contract not met; no bridge.")
            return None
        sparse = _sparse_vector(encoded.get("sparse") if isinstance(encoded, dict) else None)

        user_lang = str(getattr(ctx, "preferred_lang", "") or getattr(ctx, "language", "") or "en")
        pipeline = _fp_pipeline(container)
        result = await asyncio.to_thread(
            pipeline.execute,
            query=query,
            query_dense_vector=dense,
            query_sparse_vector=sparse,
            teacher_id="both",
            max_clips=3,
            retrieval_query=retrieval_query,
            language=user_lang,
        )

        # Calibrated gate: the pipeline's own is_direct decision (fitted
        # profile threshold — never an invented number) plus a real success
        # status. weak_match / abstained / error / crisis all fall through —
        # unless the owner's FP-primary switch is off: with
        # first_person_llm_fallback_enabled=false a decline stays inside
        # first-person (honest static abstain, zero generation) so the
        # generating graph never improvises a "teaching". Two carve-outs
        # always fall through: crisis_redirect (safety must keep flowing to
        # distress handling) and imperative meditation requests (product
        # flow, not teaching).
        status = str(getattr(result, "status", "") or "")
        if status != "success" or not getattr(result, "is_direct_answer", False):
            if status != "crisis_redirect" and not getattr(
                settings, "first_person_llm_fallback_enabled", True
            ):
                from rag.meditation import is_meditation_imperative

                if not is_meditation_imperative(query):
                    return await self._abstain(ctx, status)
            logger.debug(
                "[FirstPersonBridge] No direct answer (status=%s); GraphStage runs.",
                status or "unknown",
            )
            return None

        citations = _eligible_citations(getattr(result, "citations", None))
        answer = str(getattr(result, "answer_text", "") or "").strip()
        if not answer or not citations:
            logger.debug("[FirstPersonBridge] No servable verbatim answer; GraphStage runs.")
            return None

        # Sub-task 2 (verbatim-only assembly): the served answer must contain
        # the exact clip text it cites. Anything assembled by paraphrase fails
        # this check and falls through instead of being rendered as teacher
        # speech (zero generation here — text passes through byte-for-byte).
        verbatim_quotes = [
            str(c.get("verbatim_text") or "").strip()
            for c in citations
            if str(c.get("verbatim_text") or "").strip()
        ]
        if not any(quote in answer for quote in verbatim_quotes):
            logger.warning(
                "[FirstPersonBridge] Answer text does not contain its cited clip text; "
                "refusing to serve it as teacher voice."
            )
            return None

        # Sub-task 4 (quote preservation): this answer never reaches
        # format_final_answer / _unquote_unverifiable_spans (the bridge
        # returns before GraphStage), so nothing downstream re-processes the
        # quotes. Nothing here strips them either.

        # Output rail — explicit re-application of the stage this short-circuit
        # skips. Moderate the English answer, exactly like OutputGuardrailStage
        # does for Indic seekers (the rail is an English literal-phrase list).
        guardrails = getattr(container, "guardrails", None)
        if guardrails is None:
            logger.warning("[FirstPersonBridge] No output rail available; GraphStage runs.")
            return None
        output_check = await guardrails.check_output(answer)
        if isinstance(output_check, dict) and output_check.get("blocked"):
            logger.info(
                "[FirstPersonBridge] Output rail blocked bridge answer (reason=%s); "
                "falling through to GraphStage.",
                output_check.get("reason"),
            )
            return None

        # Sub-task 5: quotes never translated — only glue, fail-open.
        if getattr(ctx, "is_indic", False):
            answer = await _translate_glue_only(
                answer,
                verbatim_quotes,
                container,
                str(getattr(ctx, "preferred_lang", "") or ""),
            )

        record_routing_decision(
            ctx,
            RoutingProvenance(
                layer="FIRST_PERSON_BRIDGE",
                decision="first_person_bridge",
                method="calibrated_is_direct",
                confidence=1.0,
                reason="Verbatim first-person clip short-circuit (zero generation)",
                latency_ms=round(float(getattr(result, "latency_ms", 0.0) or 0.0), 2),
            ),
        )
        logger.info(
            "FIRST_PERSON_BRIDGE_SERVED trace_id=%s clips=%d pipeline_latency_ms=%.1f cached=%s",
            getattr(ctx, "trace_id", "unknown"),
            len(citations),
            float(getattr(result, "latency_ms", 0.0) or 0.0),
            bool(getattr(result, "cached", False)),
        )
        return PipelineResult(
            final_answer=answer,
            intent="QUERY",
            trace_id=getattr(ctx, "trace_id", ""),
            latency_ms=int((time.time() - getattr(ctx, "start_time", time.time())) * 1000),
            # No model generated this text: selection-only, assertion-gated.
            model_used=None,
            model_provider=None,
            route_decision="first_person_bridge",
            query_tier="fast",
            citations=citations,
            # No LLM faithfulness grade ran on this path. None means "not
            # computed" — never a fabricated number (see tests/test_grounding).
            faithfulness_score=None,
            hallucination_flag=False,
            # Every citation is a sha256 + voice-census verified clip from the
            # first-person collection; `speaker` is named for that reason only.
            citations_verified=True,
            verification={
                "passed": True,
                "method": "first_person_verbatim_clip_gate",
                "citations_verified": True,
            },
            release_manifest=get_release_manifest().to_dict(),
            route_metadata={
                "requested_variant": "first_person",
                "selected_variant": "verbatim_clip_bridge",
                "decision_method": "calibrated_is_direct",
                "first_person_collection": str(getattr(settings, "first_person_collection", "")),
                "clips_served": len(citations),
                "pipeline_latency_ms": round(float(getattr(result, "latency_ms", 0.0) or 0.0), 2),
                "pipeline_cached": bool(getattr(result, "cached", False)),
                "routing_chain": list(getattr(ctx, "routing_chain", [])),
            },
        )

    async def _abstain(self, ctx: PipelineContext, status: str) -> PipelineResult:
        """Ask-1 FP-primary abstain — static text, no LLM, no fall-through.

        first_person_llm_fallback_enabled=false: the bridge declined (no
        verbatim teaching matched, or the clip store errored) and the owner
        has switched the general LLM path off. Answer with an honest static
        message instead of letting the generating graph improvise one —
        teachings come straight from the gurus or not at all.
        """
        if status == "error":
            answer = "I couldn't reach my teaching library just now. Please try again in a moment."
            method = "first_person_store_unavailable"
        else:
            answer = (
                "I don't have a verified verbatim teaching that directly "
                "answers this, and I'd rather say so than improvise one. "
                "Try rephrasing, or ask about a specific teaching or practice."
            )
            method = "first_person_no_match_abstain"

        # The abstain is static, but an Indic seeker still deserves localized
        # glue: an empty quote list makes the whole message glue, translated
        # under the same bounded budget, fail-open to English.
        if getattr(ctx, "is_indic", False):
            answer = await _translate_glue_only(
                answer,
                [],
                ctx.container,
                str(getattr(ctx, "preferred_lang", "") or ""),
            )

        record_routing_decision(
            ctx,
            RoutingProvenance(
                layer="FIRST_PERSON_BRIDGE",
                decision="first_person_abstain",
                method=method,
                confidence=1.0,
                reason=(
                    f"FP declined (status={status or 'unknown'}); general LLM fallback disabled"
                ),
                latency_ms=0.0,
            ),
        )
        logger.info(
            "FIRST_PERSON_BRIDGE_ABSTAIN trace_id=%s status=%s reason=llm_fallback_disabled",
            getattr(ctx, "trace_id", "unknown"),
            status or "unknown",
        )
        return PipelineResult(
            final_answer=answer,
            intent="QUERY",
            trace_id=getattr(ctx, "trace_id", ""),
            latency_ms=int((time.time() - getattr(ctx, "start_time", time.time())) * 1000),
            # Static text: no model generated it, so no model/provider claim.
            model_used=None,
            model_provider=None,
            route_decision="first_person_abstain",
            query_tier="fast",
            citations=[],
            # Not computed — never a fabricated number (see tests/test_grounding).
            faithfulness_score=None,
            hallucination_flag=False,
            citations_verified=True,
            verification={
                "passed": True,
                "method": method,
                "citations_verified": True,
            },
            release_manifest=get_release_manifest().to_dict(),
            route_metadata={
                "requested_variant": "first_person",
                "selected_variant": "no_match_abstain",
                "decision_method": method,
                "decline_status": status or "unknown",
                "llm_fallback_enabled": False,
                "routing_chain": list(getattr(ctx, "routing_chain", [])),
            },
        )


# ---------------------------------------------------------------------------
# Shared entries for the plug-and-play wiring. The class above remains the
# single implementation; these two functions are the named seams the entry
# registry (rag/pipeline_registry.py) and the graph node
# (rag/nodes/first_person.py) bind to, so the flag check and the fail-open
# contract exist exactly once.
# ---------------------------------------------------------------------------


def first_person_bridge_enabled() -> bool:
    """Live kill-switch: chat-bridge flag + inherited first-person route gates."""
    return FirstPersonBridgeStage._enabled()


async def run_first_person_bridge(ctx: PipelineContext) -> PipelineResult | None:
    """Run the bridge fail-open — shared by the stage shim and the graph node."""
    return await FirstPersonBridgeStage().run(ctx)
