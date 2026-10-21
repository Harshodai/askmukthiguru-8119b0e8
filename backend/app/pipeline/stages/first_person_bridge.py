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
  regex list). A blocked answer declines — ``None`` (GraphStage runs) with the
  fallback on, static abstain in first-person-only mode (default) — it is
  never served from this path.

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
from rag.resolve_followup import _get_last_user_message, _is_heuristic_followup
from services.user_profile_service import _is_persistable_user_id

if TYPE_CHECKING:
    from app.pipeline.stages.context import PipelineContext

logger = logging.getLogger(__name__)

# DistressLevel.MODERATE; an int so this module stays import-light.
_DISTRESS_DECLINE_LEVEL = 2

_PRACTICE_HOWTO_RE = re.compile(
    r"\b(how|steps?|guide|teach me|instructions?)\b.{0,40}"
    r"\b(soul\s*sync|serene\s*mind|meditat\w*|breath\w*)",
    re.IGNORECASE,
)

# Question shapes one verbatim clip cannot answer: a contrast, a root cause or
# "why", a personal how-to (heal / overcome / repair ...), or a multi-part
# question. Live 2026-10-05 (audits/scenarios-2026-10-05/): each of these was
# served a topic-matched clip that did not answer the exact question. They go
# to GraphStage's grounded synthesis, which is labelled as synthesis. "Why do
# you ..." asks the teachers their own reason, which a clip can answer.
_SYNTHESIS_SHAPE_RE = re.compile(
    r"\bdifference\s+between\b|\bdiffer(?:s|ent)?\s+from\b|\bvs\b\.?|\bversus\b"
    r"|\bcompar\w*|\bcontrast\w*"
    r"|\broot\s+causes?\b|\bwhat\s+causes?\b|\bwhy\s+(?:do|does|am)\b(?!\s+you\b)"
    # "is X the only cause", "the cause of" (2026-10-05, live rt3)
    r"|\b(?:only|real|main|true)\s+causes?\b|\bthe\s+causes?\s+of\b"
    r"|\bhow\s+(?:(?:can|do|should|could)\s+(?:i|we)|to)\b.{0,40}?"
    r"\b(?:heal|overcome|stop|deal|let\s+go|repair|fix|forgive|cope|handle|get\s+over"
    r"|break\s+free|release|reconcile|move\s+on)\b"
    r"|,\s*and\s+(?:how|what|why|when|where|which|can|should|is|are|do|does)\b"
    r"|\?[^?]+\?",
    re.IGNORECASE,
)

# Strong references to in-flight memory writes to prevent garbage collection before execution
_FP_MEMORY_WRITE_TASKS: set[asyncio.Task] = set()


def _dispatch_fp_memory(
    ctx: PipelineContext,
    final_answer: str,
    citations: list[dict],
) -> None:
    """Asynchronously persist memory for first-person turns to prevent memory blackout.

    FirstPersonBridgeStage short-circuits GraphStage, which skips MemoryStage.
    This helper dispatches canonical memory extraction and outbox enqueueing as
    non-blocking background tasks with strong reference retention.
    """
    if getattr(ctx, "incognito", False):
        return

    user_id = getattr(ctx, "user_id", None)
    if not user_id or not _is_persistable_user_id(user_id):
        return

    container = getattr(ctx, "container", None)
    if container is None:
        return

    from services.tenant_context import TenantContext

    tenant_id = TenantContext.get()
    stable_session_id = getattr(ctx, "stable_session_id", "") or ""
    user_msg = getattr(ctx, "user_msg", "") or ""
    chat_body_messages = getattr(ctx, "chat_body_messages", []) or []

    # 1. Canonical memory write (extractor/judge/resolver -> canonical_memories)
    canonical_integration = getattr(container, "canonical_memory_integration", None)
    if (
        getattr(settings, "memory_write", False)
        and canonical_integration is not None
        and final_answer
    ):

        async def _canonical_write() -> None:
            try:
                _outbox = getattr(container, "memory_outbox", None)
                if _outbox is None:
                    return
                _consent = await _outbox.active_consent(user_id=user_id, tenant_id=tenant_id)
                if not _consent:
                    return
                await asyncio.wait_for(
                    canonical_integration.post_response_memory(
                        user_id=user_id,
                        query=user_msg,
                        response=final_answer,
                        session_id=stable_session_id,
                        session_messages=chat_body_messages,
                    ),
                    timeout=float(getattr(settings, "canonical_memory_write_timeout", 30.0)),
                )
                logger.info(
                    "[FirstPersonBridge] Canonical memory write completed for verbatim turn"
                )
            except TimeoutError:
                logger.warning(
                    "[FirstPersonBridge] Canonical memory write timed out for verbatim turn"
                )
            except Exception as exc:
                logger.warning("[FirstPersonBridge] Canonical memory write failed: %s", exc)

        _task = asyncio.create_task(_canonical_write(), name="fp_memory:canonical")
        _FP_MEMORY_WRITE_TASKS.add(_task)
        _task.add_done_callback(_FP_MEMORY_WRITE_TASKS.discard)

    # 2. Outbox memory write (for Second Brain personal graph & legacy extraction)
    if getattr(settings, "feature_memory_write", False):
        outbox = getattr(container, "memory_outbox", None)
        if outbox is not None:

            async def _outbox_write() -> None:
                try:
                    consent = await outbox.active_consent(user_id=user_id, tenant_id=tenant_id)
                    if not consent:
                        return
                    await outbox.enqueue(
                        user_id=user_id,
                        tenant_id=tenant_id,
                        session_id=stable_session_id,
                        consent_receipt_id=consent.get("id"),
                        payload={
                            "user_message": user_msg,
                            "assistant_answer": final_answer,
                            "prior_messages": chat_body_messages,
                            "citations": citations,
                            "intent": "QUERY",
                            "med_step": None,
                            "distress_level": 0,
                        },
                    )
                    logger.info("[FirstPersonBridge] Outbox memory enqueued for verbatim turn")
                except Exception as exc:
                    logger.warning("[FirstPersonBridge] Outbox memory enqueue failed: %s", exc)

            _otask = asyncio.create_task(_outbox_write(), name="fp_memory:outbox")
            _FP_MEMORY_WRITE_TASKS.add(_otask)
            _otask.add_done_callback(_FP_MEMORY_WRITE_TASKS.discard)


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


# Static abstain copy per Indic language (2026-10-16, outside-audit I18N-001). The bridge used to
# send the English abstain through an LLM glue translation: 6-8 s extra, and a Hindi result that
# kept English words ("teaching या practice"). AI-written, NOT native-speaker reviewed (task list
# A12/E-7); English words and Latin letters are deliberately absent.
_STATIC_ABSTAIN = {
    "hi": "मेरे पास ऐसा कोई प्रमाणित शब्दशः उपदेश नहीं है जो सीधे इसका उत्तर दे। कुछ गढ़कर कहने से बेहतर है कि मैं यह स्पष्ट कहूँ। कृपया प्रश्न दूसरे शब्दों में पूछें, या किसी विशेष उपदेश या साधना के बारे में पूछें।",
    "ta": "இதற்கு நேரடியாகப் பதிலளிக்கும் சரிபார்க்கப்பட்ட, சொல்லுக்குச் சொல் உபதேசம் என்னிடம் இல்லை. எதையும் கற்பனையாகச் சொல்வதை விட இதை வெளிப்படையாகச் சொல்வதே சரி. தயவுசெய்து வேறு வார்த்தைகளில் கேளுங்கள், அல்லது ஒரு குறிப்பிட்ட உபதேசம் அல்லது பயிற்சி பற்றிக் கேளுங்கள்.",
    "te": "దీనికి నేరుగా సమాధానం ఇచ్చే ధృవీకరించిన, పదానికి పదం ఉపదేశం నా వద్ద లేదు. ఏదో కల్పించి చెప్పడం కంటే ఇదే స్పష్టంగా చెప్పడం మంచిది. దయచేసి వేరే మాటల్లో అడగండి, లేదా ఒక నిర్దిష్ట ఉపదేశం లేదా సాధన గురించి అడగండి.",
    "kn": "ಇದಕ್ಕೆ ನೇರವಾಗಿ ಉತ್ತರಿಸುವ ಪರಿಶೀಲಿತ, ಪದಶಃ ಉಪದೇಶ ನನ್ನ ಬಳಿ ಇಲ್ಲ. ಏನನ್ನೋ ಕಲ್ಪಿಸಿ ಹೇಳುವುದಕ್ಕಿಂತ ಇದನ್ನು ಸ್ಪಷ್ಟವಾಗಿ ಹೇಳುವುದೇ ಉತ್ತಮ. ದಯವಿಟ್ಟು ಬೇರೆ ಮಾತುಗಳಲ್ಲಿ ಕೇಳಿ, ಅಥವಾ ಒಂದು ನಿರ್ದಿಷ್ಟ ಉಪದೇಶ ಅಥವಾ ಸಾಧನೆಯ ಬಗ್ಗೆ ಕೇಳಿ.",
    "mr": "यावर थेट उत्तर देणारा पडताळलेला, शब्दशः उपदेश माझ्याकडे नाही. काहीतरी रचून सांगण्यापेक्षा हे स्पष्ट सांगणे योग्य आहे. कृपया प्रश्न वेगळ्या शब्दांत विचारा, किंवा एखाद्या विशिष्ट उपदेशाबद्दल किंवा साधनेबद्दल विचारा.",
}


# COPY PENDING OWNER APPROVAL -------------------------------------------------
# A25 (2026-10-19): the only user-visible copy this backend half adds for the
# abstain related-clips affordance. Deliberately minimal and neutral — the owner
# approves user-visible copy and the frontend owns presentation, so these may be
# rewritten or dropped freely. ABSTAIN_RELATED_HEADING reuses the repo's existing
# "Related, not a direct answer" vocabulary (no new brand voice). The faculty
# affordance ships as a boolean only: no seeker-facing "ask a faculty member"
# entry point exists in the repo, and none may be invented.
ABSTAIN_RELATED_HEADING = "Related, not a direct answer"
ABSTAIN_FACULTY_PROMPT = "Ask a faculty member"
# -----------------------------------------------------------------------------


def _abstain_related_payload(related: list[dict] | None) -> dict:
    """Route-metadata block for the A25 abstain related-clips affordance.

    Returns ``{}`` when the feature is off or there is nothing to offer, so the
    abstain payload is byte-identical to before. Only ever called for an abstain
    that did NOT come from a safety/blocked reason (the pipeline attaches
    ``related_clips`` exclusively on a below-min relevance abstain).
    """
    if not related or not getattr(
        settings, "first_person_abstain_related_clips_enabled", False
    ):
        return {}
    topics: list[str] = []
    seen: set[str] = set()
    for entry in related:
        if not isinstance(entry, dict):
            continue
        for topic in entry.get("topics") or []:
            if isinstance(topic, str) and topic.strip() and topic.lower() not in seen:
                seen.add(topic.lower())
                topics.append(topic.strip())
    return {
        "related_clips": related,
        # Same vocabulary as the served weak-match label; never an answer claim.
        "related_clips_heading": ABSTAIN_RELATED_HEADING,
        "related_topics": topics,
        # Affordance flag only. No faculty URL is invented (see COPY block).
        "ask_faculty_available": True,
        "ask_faculty_prompt": ABSTAIN_FACULTY_PROMPT,
    }


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


def _distress_compassion_framing(ctx: PipelineContext) -> str:
    """The compassion copy a MODERATE-distress turn keeps.

    Owner decision 2026-10-19 (``first_person_distress_serve_clip_enabled``):
    MODERATE distress keeps its framing *and* gains the clip, so this returns
    the same copy the graph's distress lane serves, from the same two sources
    (``rag/nodes/intent.py::handle_distress``): the Serene Mind engine's
    graduated template for this assessment, else the static clinician-reviewed
    distress copy. Static text only — never generated here.
    """
    assessment = getattr(ctx, "assessment", None)
    serene_mind = getattr(getattr(ctx, "container", None), "serene_mind", None)
    if assessment is not None and serene_mind is not None:
        try:
            template = serene_mind.get_response(assessment)
        except Exception as exc:  # noqa: BLE001 — fall back to the static copy
            logger.warning("[FirstPersonBridge] Serene Mind template unavailable: %s", exc)
        else:
            if isinstance(template, str) and template.strip():
                return template
    from rag.meditation import get_distress_response

    return get_distress_response()


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
        # speaker_verified is a PROVENANCE CLAIM, so it is copied from the stored clip
        # and never inferred: a teacher-owned channel (or the pipeline's allowlist gate)
        # says where the video came from, not whose voice is in this span. Live
        # 2026-10-11: 79% of clips carry no voice verification, yet the old stamp
        # published speaker_verified=True for them. The UI still labels by its own
        # channel rule (resolveAttributionLabel); the boolean stays honest.
        # is_verbatim is not speaker verification (L-PROVENANCE-ISVERBATIM-1).
        # Keep provenance only for speakers currently registered in
        # gurus.yaml. Adding a teacher must not require a code edit here.
        from services.guru_registry import allowed_speaker_labels

        eligible.append(
            {**citation, "speaker_verified": True}
            if citation.get("speaker_verified") is True
            and citation.get("speaker") in allowed_speaker_labels()
            else citation
        )
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
    logs and declines. With the fallback on, a decline returns ``None`` so
    GraphStage runs exactly as before; in first-person-only mode (default
    since RP-A4, 2026-10-13) the decline is a static abstain and the
    generating graph never improvises a teaching. Three early paths still
    return ``None`` in both modes — empty query (no-op), SEVERE+ distress
    and imperative meditation (intended carve-outs that keep flowing).
    MODERATE distress is the fourth early path and still declines unless the
    owner has set ``first_person_distress_serve_clip_enabled``, which keeps the
    compassion framing and adds the clip (owner decision 2026-10-19).

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
            # Sub-task 8: never let bridge infrastructure (embedding, Redis,
            # Qdrant, translation) take the chat request down. With the
            # fallback on, _decline returns None and GraphStage runs; in
            # first-person-only mode (default) the decline is a static abstain.
            logger.exception("[FirstPersonBridge] Bridge failed; declining.")
            return await self._decline(ctx, "error")

    async def _decline(
        self,
        ctx: PipelineContext,
        status: str,
        boundaries: list[str] | None = None,
        compassion: bool = False,
        related: list[dict] | None = None,
    ) -> PipelineResult | None:
        """Hand off to the generating graph, or (first-person-only) abstain statically.

        Imperative meditation requests keep their templated product flow either way.
        ``compassion`` (owner decision 2026-10-19) marks a MODERATE-distress turn whose
        clip did not clear the gates: with the generating graph switched off the abstain
        becomes the distress lane's compassion copy, never the "no verified teaching"
        message a distressed seeker must not receive.
        ``related`` (A25) is the pipeline's related-clip offer for a below-min abstain;
        it is ignored on every non-abstain decline.
        """
        if getattr(settings, "first_person_llm_fallback_enabled", False):
            return None
        from rag.meditation import is_meditation_imperative

        if is_meditation_imperative(str(getattr(ctx, "user_msg", "") or "")):
            return None
        return await self._abstain(
            ctx,
            status,
            boundaries,
            compassion=compassion,
            related=await self._safe_related(ctx, related, compassion),
        )

    async def _safe_related(
        self,
        ctx: PipelineContext,
        related: list[dict] | None,
        distress_compassion: bool,
    ) -> list[dict] | None:
        """A25: output-rail-filter the abstain related clips before they are offered.

        A distressed (MODERATE-compassion) turn never offers related clips, and every
        remaining clip's ``text_snippet`` must pass the same output rail the served
        answer passes (``guardrails.check_output``). Clips that fail — or that have no
        rail to check against — are dropped; an all-dropped list becomes ``None`` so
        the abstain payload stays byte-identical to the feature-off case.
        """
        if not related or distress_compassion:
            return None
        guardrails = getattr(getattr(ctx, "container", None), "guardrails", None)
        if guardrails is None:
            return None
        kept: list[dict] = []
        for clip in related:
            if not isinstance(clip, dict):
                continue
            snippet = clip.get("text_snippet")
            check = await guardrails.check_output(snippet if isinstance(snippet, str) else "")
            if isinstance(check, dict) and check.get("blocked"):
                continue
            kept.append(clip)
        return kept or None

    async def _bridge(self, ctx: PipelineContext) -> PipelineResult | None:
        query = str(getattr(ctx, "user_msg", "") or "").strip()
        if not query:
            return None
        # A grieving or distressed seeker (DistressStage: MODERATE and up)
        # needs the compassionate path, not a clip picked by topic match --
        # live 2026-10-05, "my mother died" was served a clip about the
        # suffering state. SEVERE+ never reaches here (DistressStage
        # pre-empts); this covers MODERATE.
        #
        # Owner decision 2026-10-19 (first_person_distress_serve_clip_enabled):
        # exactly MODERATE keeps the compassion framing AND serves the clip the
        # normal path below would have served, through the same gates. Measured
        # reason: a SINGLE emotion keyword ("fear", "anxiety", ...) made 15 of
        # 150 benign on-topic questions MODERATE, and 14 of those had clips
        # waiting. SEVERE/CRISIS still decline completely — no clip, ever.
        level = getattr(getattr(ctx, "assessment", None), "level", None)
        level_value = int(getattr(level, "value", 0) or 0)
        distress_compassion = bool(
            level_value == _DISTRESS_DECLINE_LEVEL
            and getattr(settings, "first_person_distress_serve_clip_enabled", False)
        )
        if level_value >= _DISTRESS_DECLINE_LEVEL and not distress_compassion:
            logger.info("[FirstPersonBridge] Distress level %s; GraphStage runs.", level)
            return None
        if distress_compassion:
            logger.info(
                "[FirstPersonBridge] Distress level %s; serving the matching clip under "
                "the compassion framing (first_person_distress_serve_clip_enabled).",
                level,
            )
        # Guided practices (Soul Sync, Serene Mind) are step-by-step; one clip
        # is not the steps. A request to do one, or to learn how, goes to the
        # graph's meditation/teaching path (live 2026-10-05: no Soul Sync steps).
        from rag.meditation import is_meditation_imperative

        if is_meditation_imperative(query):
            logger.info("[FirstPersonBridge] Guided-practice request; GraphStage runs.")
            return None
        if _PRACTICE_HOWTO_RE.search(query) and getattr(
            settings, "first_person_llm_fallback_enabled", False
        ):
            # "How do I practice X?" -> the graph's teaching path. In first-person-only
            # mode it continues below (clip or static abstain): live 2026-10-11 this
            # carve-out was the one path that let deepseek-chat generate a "teaching".
            logger.info("[FirstPersonBridge] Guided-practice request; GraphStage runs.")
            return None
        # A clip cannot carry the relationship safety boundary
        # (OutputGuardrailStage appends it on the graph path), so a
        # relationship-repair question never takes the bridge.
        from guardrails.lightweight_handler import (
            needs_addiction_support_boundary,
            needs_relationship_safety_boundary,
        )

        fp_only = not getattr(settings, "first_person_llm_fallback_enabled", False)
        boundaries: list[str] = []
        needs_rel = needs_relationship_safety_boundary(query)
        needs_add = needs_addiction_support_boundary(query)
        if _SYNTHESIS_SHAPE_RE.search(query) or needs_rel or needs_add:
            if not fp_only:
                logger.info(
                    "[FirstPersonBridge] Question needs synthesis, not one clip; GraphStage runs."
                )
                return None
            # First-person-only: never hand the question to the generating graph.
            # Serve a clip and carry the same safety boundary the graph path appends.
            from guardrails.lightweight_handler import (
                RELATIONSHIP_SAFETY_BOUNDARY,
                addiction_support_boundary,
            )

            if needs_rel:
                boundaries.append(RELATIONSHIP_SAFETY_BOUNDARY)
            if needs_add:
                boundaries.append(addiction_support_boundary())
        state = getattr(ctx, "state", None) or {}
        # RequestStateStage already produced the English query (its own
        # bounded translation); never pay for a second one here.
        retrieval_query = str(state.get("user_msg_en") or query)

        # Conversational Follow-Up Resolution (CQR / Anaphora):
        chat_history = getattr(ctx, "chat_body_messages", None) or []
        if chat_history and _is_heuristic_followup(retrieval_query, chat_history):
            last_user = _get_last_user_message(chat_history)
            if last_user:
                retrieval_query = f"{last_user} — {retrieval_query}"
                logger.info("[FirstPersonBridge] Resolved follow-up query to: %s", retrieval_query)

        container = ctx.container

        try:
            encoded = await container.embedding.encode_single_full_async(retrieval_query)
        except Exception as exc:
            # Embedding is bridge infrastructure, not chat infrastructure:
            # GraphStage performs its own retrieval embedding, so a failure
            # here only means "no bridge" (kept at DEBUG — the embedding
            # service logs its own errors).
            logger.debug("[FirstPersonBridge] Query embed unavailable; no bridge: %s", exc)
            return await self._decline(ctx, "error", compassion=distress_compassion)
        dense = _dense_vector(encoded, settings.embedding_dimension)
        if dense is None:
            # Includes mocked/test containers: no vector contract, no bridge.
            logger.debug("[FirstPersonBridge] Dense vector contract not met; no bridge.")
            return await self._decline(ctx, "error", compassion=distress_compassion)
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
            # The chat cache stages honour both flags; the first-person exact
            # cache is a cache too, so it must honour them the same way.
            cache_bypass=(
                getattr(ctx, "cache_bypass", False) is True
                or getattr(ctx, "incognito", False) is True
            ),
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
        is_direct = bool(getattr(result, "is_direct_answer", False))
        # A25: the pipeline attaches related_clips ONLY on a below-min relevance
        # abstain (never on crisis_redirect, answerability_withheld/topic_blocked,
        # or a served result), so an empty/absent value keeps the abstain payload
        # byte-identical and off-topic/safety turns carry nothing.
        related = getattr(result, "related_clips", None) or None
        # Opt-in (first_person_serve_weak_match): the pipeline already ran the
        # answerability gate on this clip, so a gated weak_match is servable under
        # its honest "Related, not a direct answer" label. The getattr default
        # matches the declared default (True); real Settings always carries it.
        serve_weak = status == "weak_match" and bool(
            getattr(settings, "first_person_serve_weak_match", True)
        )
        if (status != "success" or not is_direct) and not serve_weak:
            if status != "crisis_redirect" and not getattr(
                settings, "first_person_llm_fallback_enabled", False
            ):
                from rag.meditation import is_meditation_imperative

                if not is_meditation_imperative(query):
                    return await self._abstain(
                        ctx,
                        status,
                        boundaries,
                        compassion=distress_compassion,
                        related=await self._safe_related(ctx, related, distress_compassion),
                    )
            logger.debug(
                "[FirstPersonBridge] No direct answer (status=%s); GraphStage runs.",
                status or "unknown",
            )
            return None

        citations = _eligible_citations(getattr(result, "citations", None))
        answer = str(getattr(result, "answer_text", "") or "").strip()
        if not answer or not citations:
            logger.debug("[FirstPersonBridge] No servable verbatim answer; declining.")
            return await self._decline(
                ctx, status, boundaries, compassion=distress_compassion, related=related
            )

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
            return await self._decline(ctx, status, boundaries, compassion=distress_compassion)

        # Sub-task 4 (quote preservation): this answer never reaches
        # format_final_answer / _unquote_unverifiable_spans (the bridge
        # returns before GraphStage), so nothing downstream re-processes the
        # quotes. Nothing here strips them either.

        # Output rail — explicit re-application of the stage this short-circuit
        # skips. Moderate the English answer, exactly like OutputGuardrailStage
        # does for Indic seekers (the rail is an English literal-phrase list).
        guardrails = getattr(container, "guardrails", None)
        if guardrails is None:
            logger.warning("[FirstPersonBridge] No output rail available; declining.")
            return await self._decline(ctx, status, boundaries, compassion=distress_compassion)
        output_check = await guardrails.check_output(answer)
        if isinstance(output_check, dict) and output_check.get("blocked"):
            logger.info(
                "[FirstPersonBridge] Output rail blocked bridge answer (reason=%s); declining.",
                output_check.get("reason"),
            )
            return await self._decline(ctx, status, boundaries, compassion=distress_compassion)

        if distress_compassion:
            # Distress-lane parity (rag/nodes/intent.py::handle_distress): a clip that
            # talks about dying, quitting life or rock bottom is omitted ENTIRELY for a
            # distressed seeker — a verbatim clip is never edited sentence-by-sentence.
            # The compassion framing is served instead. This is the exact class the
            # 2026-10-05 MODERATE decline existed to stop; serving the clip additively
            # must not reopen it.
            from rag.nodes.intent import _contains_hazardous_distress_sentence

            if _contains_hazardous_distress_sentence(answer):
                logger.warning(
                    "[FirstPersonBridge] Distress clip carries a hazardous sentence; "
                    "serving the compassion framing only."
                )
                return await self._abstain(ctx, status, boundaries, compassion=True)
            # Owner decision 2026-10-19: the seeker keeps the compassion framing
            # (the same graduated template the graph's distress lane serves) AND
            # the clip. Added after the output rail, exactly like the safety
            # boundaries below: it is the distress lane's own reviewed copy, not
            # generated text, so the English literal-phrase rail does not gate it.
            # Before glue translation, so an Indic seeker gets localized compassion
            # copy while the teacher's words stay verbatim.
            framing = _distress_compassion_framing(ctx)
            if framing.strip():
                answer = f"{framing}\n\n{answer}"

        if boundaries:
            # Appended after the output rail so safety text can never be blocked,
            # before glue translation so Indic seekers get it localized.
            answer = answer + "\n\n" + "\n\n".join(boundaries)

        if distress_compassion:
            # Distress lane invariant: every distress answer ends with a human
            # support line, unless a helpline block is already present.
            from services.crisis_helplines import ensure_support_line

            answer = ensure_support_line(answer)
            # Distress-lane parity, defense-in-depth: the graph's distress handler
            # returns straight to END, so it re-runs this persona/constitutional
            # check itself (rag/nodes/intent.py::handle_distress). The bridge
            # short-circuits even earlier, so the same check runs here — on a hit the
            # clip is dropped and the reviewed compassion copy is served instead.
            from rag.nodes.verification import check_persona_adherence

            violation = check_persona_adherence(answer)
            if violation:
                logger.warning(
                    "[FirstPersonBridge] Compassion+clip answer failed the persona guard "
                    "(%s); serving the compassion framing only.",
                    violation,
                )
                return await self._abstain(ctx, status, boundaries, compassion=True)

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
                method="calibrated_is_direct" if is_direct else "weak_match_opt_in",
                confidence=1.0 if is_direct else 0.0,
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
        # Dispatches consented canonical memory and outbox persistence asynchronously
        _dispatch_fp_memory(ctx, answer, citations)
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
                # False = weak_match served under the "Related, not a direct answer" label.
                "direct": is_direct,
            },
            release_manifest=get_release_manifest().to_dict(),
            route_metadata={
                "requested_variant": "first_person",
                "selected_variant": "verbatim_clip_bridge",
                "decision_method": "calibrated_is_direct" if is_direct else "weak_match_opt_in",
                "first_person_collection": str(getattr(settings, "first_person_collection", "")),
                "clips_served": len(citations),
                "pipeline_latency_ms": round(float(getattr(result, "latency_ms", 0.0) or 0.0), 2),
                "pipeline_cached": bool(getattr(result, "cached", False)),
                "routing_chain": list(getattr(ctx, "routing_chain", [])),
                "audio_playback_clip": getattr(result, "audio_playback_clip", None),
                "audio_playback_clips": getattr(result, "audio_playback_clips", []) or [],
                "detected_concepts": getattr(result, "detected_concepts", []),
                "atma_vichara_inquiry": getattr(result, "atma_vichara_inquiry", None),
                "practice_recommendation": getattr(result, "practice_recommendation", None),
                # Owner decision 2026-10-19: this clip was served under the MODERATE
                # distress compassion framing (additive, opt-in flag).
                "distress_compassion_framing": distress_compassion,
            },
        )

    async def _abstain(
        self,
        ctx: PipelineContext,
        status: str,
        boundaries: list[str] | None = None,
        compassion: bool = False,
        related: list[dict] | None = None,
    ) -> PipelineResult:
        """Ask-1 FP-primary abstain — static text, no LLM, no fall-through.

        first_person_llm_fallback_enabled=false: the bridge declined (no
        verbatim teaching matched, or the clip store errored) and the owner
        has switched the general LLM path off. Answer with an honest static
        message instead of letting the generating graph improvise one —
        teachings come straight from the gurus or not at all.

        ``compassion`` (owner decision 2026-10-19): a MODERATE-distress turn whose
        clip did not clear the gates. The honest "no verified teaching" message is
        still true, but it is the wrong thing to hand a distressed seeker, so the
        distress lane's own compassion copy is served instead — static, zero
        generation, no citations, no fabricated content.

        ``related`` (A25, ``first_person_abstain_related_clips_enabled``): the
        pipeline's bounded, explicitly-related clip offer for a below-min relevance
        abstain. Rides ``route_metadata.related_clips`` only; it never becomes a
        citation and never changes the abstain text. ``None``/``[]`` (every safety,
        blocked and crisis turn) leaves the payload byte-identical.
        """
        related_block = _abstain_related_payload(related)
        if compassion:
            answer = _distress_compassion_framing(ctx)
            from services.crisis_helplines import ensure_support_line

            answer = ensure_support_line(answer)
            method = "first_person_distress_compassion"
        elif status == "error":
            answer = "I couldn't reach my teaching library just now. Please try again in a moment."
            method = "first_person_store_unavailable"
        else:
            answer = (
                "I don't have a verified verbatim teaching that directly "
                "answers this, and I'd rather say so than improvise one. "
                "Try rephrasing, or ask about a specific teaching or practice."
            )
            method = "first_person_no_match_abstain"

        if boundaries:
            # A relationship/addiction question must carry its safety line even when
            # no clip is served (live 2026-10-11: a drinking-habit question got a bare
            # "no verified teaching" with no support pointer).
            answer = answer + "\n\n" + "\n\n".join(boundaries)

        # The abstain is static, but an Indic seeker still deserves localized
        # glue: an empty quote list makes the whole message glue, translated
        # under the same bounded budget, fail-open to English.
        static = _STATIC_ABSTAIN.get(str(getattr(ctx, "preferred_lang", "") or "").lower())
        if compassion:
            # The native-script "no verified verbatim teaching" copy does not apply
            # here (a clip was searched for and this is the compassion fallback), so
            # only the translation branch runs.
            if getattr(ctx, "is_indic", False):
                answer = await _translate_glue_only(
                    answer,
                    [],
                    ctx.container,
                    str(getattr(ctx, "preferred_lang", "") or ""),
                )
        elif getattr(ctx, "is_indic", False) and static and status != "error" and not boundaries:
            answer = static  # no LLM call, no English words
        elif getattr(ctx, "is_indic", False):
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
                # Owner decision 2026-10-19: the abstain is the distress compassion
                # copy because the flag was on and this turn was MODERATE.
                "distress_compassion_framing": compassion,
                "routing_chain": list(getattr(ctx, "routing_chain", [])),
                # A25: empty {} unless the flag is on, the pipeline offered
                # related clips, and this abstain is not a safety/blocked turn.
                **related_block,
            },
        )


# ---------------------------------------------------------------------------
# Shared entries for the plug-and-play wiring. The class above remains the
# single implementation; these two functions are the named seams the entry
# registry (rag/pipeline_registry.py) and the graph node
# (rag/nodes/first_person.py) bind to, so the flag check and the decline
# contract exist exactly once.
# ---------------------------------------------------------------------------


def first_person_bridge_enabled() -> bool:
    """Live kill-switch: chat-bridge flag + inherited first-person route gates."""
    return FirstPersonBridgeStage._enabled()


async def run_first_person_bridge(ctx: PipelineContext) -> PipelineResult | None:
    """Run the bridge fail-open — shared by the stage shim and the graph node."""
    return await FirstPersonBridgeStage().run(ctx)
