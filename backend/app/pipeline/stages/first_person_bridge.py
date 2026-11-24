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
import hashlib
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
from rag.resolve_followup import (
    FollowupResolution,
    _get_last_user_message,
    _is_heuristic_followup,
    followup_metadata,
    names_new_topic,
)
from services.first_person_public_projection import (
    public_editorial_set_metadata as _public_editorial_set_metadata,
)
from services.first_person_rights import source_is_authoritatively_licensed
from services.user_profile_service import _is_persistable_user_id

if TYPE_CHECKING:
    from app.pipeline.stages.context import PipelineContext

logger = logging.getLogger(__name__)

# DistressLevel.MODERATE; an int so this module stays import-light.
_DISTRESS_DECLINE_LEVEL = 2

# One-shot flag so "no provider can write a HyDE passage" is said once, not per request.
# A mutable cell, so the note needs no ``global`` statement.
_HYDE_PROVIDER_WARNED: dict[str, bool] = {"said": False}

# Deterministic in-memory HyDE caching to eliminate LLM jitter and timeouts (T-R1)
_HYDE_CACHE: dict[str, tuple[str, list[float], float]] = {}  # query_hash -> (hyde_text, vector, expiry)
_HYDE_CACHE_MAX_SIZE = 1000
_HYDE_CACHE_TTL_S = 86400.0 * 7  # 7 days


def _get_cached_hyde(query_hash: str) -> tuple[str, list[float]] | None:
    now = time.monotonic()
    entry = _HYDE_CACHE.get(query_hash)
    if entry:
        text, vec, expiry = entry
        if expiry > now:
            return text, vec
        _HYDE_CACHE.pop(query_hash, None)
    return None


def _set_cached_hyde(query_hash: str, text: str, vec: list[float]) -> None:
    if len(_HYDE_CACHE) >= _HYDE_CACHE_MAX_SIZE:
        oldest_key = next(iter(_HYDE_CACHE))
        _HYDE_CACHE.pop(oldest_key, None)
    _HYDE_CACHE[query_hash] = (text, vec, time.monotonic() + _HYDE_CACHE_TTL_S)


def _hyde_provider(container: Any) -> Any:
    """The container service that can write a HyDE passage, or ``None``.

    2026-11-11: this used to read ``container.ollama`` only. That attribute is a
    *deprecated alias for* ``container.llm`` on the real container, so it happened to
    work — but the signal was invisible and any container built without it (mocks, a
    provider wired under a different name) skipped HyDE in silence. Prefer the canonical
    provider, then the legacy aliases, and only accept an object that actually
    implements ``generate_hyde`` (including ``OpenRouterService``).
    """
    for attribute in ("llm", "openrouter", "nim", "ollama"):
        candidate = getattr(container, attribute, None)
        if candidate is not None and hasattr(candidate, "generate_hyde"):
            return candidate
    return None


_PRACTICE_HOWTO_RE = re.compile(
    r"\b(how|steps?|guide|teach me|instructions?)\b.{0,40}"
    r"\b(soul\s*sync|serene\s*mind|meditat\w*|breath\w*)",
    re.IGNORECASE,
)

_STEP_INSTRUCTION_RE = re.compile(
    r"\b(steps?|instructions?|step-by-step)\b.{0,50}\b(practice|soul\s*sync|serene\s*mind|meditat\w*)|\b(soul\s*sync|serene\s*mind)\b.{0,50}\b(steps?|instructions?|step-by-step)\b",
    re.IGNORECASE,
)

_DIFFERENCE_SYNTHESIS_RE = re.compile(
    r"\bdifference\s+between\b|\bdiffer(?:s|ent)?\s+from\b|\bdistinction\s+(?:between|from)\b|\bvs\b\.?|\bversus\b|\bcompar\w*|\bcontrast\w*",
    re.IGNORECASE,
)

_PROMISE_OR_OUTCOME_TRAP_RE = re.compile(
    r"\b(?:promise(?:\s+me)?|guarantee|will\s+definitely|definitely\s+(?:be\s+)?saved|cure\s+my)\b",
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


# Linear-time form (2026-11-16). The earlier `\w[\w\s]*` prefixes made a search
# quadratic: 0.94 s on an 8,000-character message, and the cap is 10,000. A
# leading `\w[\w\s]*` before `\s+` matches exactly when a single `\w` does, so
# dropping it keeps the verdict. Only the "both ... and" span is now bounded.
_COMPOUND_BOTH_SPAN_MAX = 200
_COMPOUND_QUESTION_RE = re.compile(
    rf"\bboth\s+\w[\w\s]{{0,{_COMPOUND_BOTH_SPAN_MAX}}}and\s+\w"
    r"|\w\s+as\s+well\s+as\s+\w"
    r"|—[^—]{3,80}(?:and|&)[^—]{3,80}—"
    r"|,\s*[^,]+,\s*(?:and|&)\s*"
    r"|\w(?:\s*,)?\s+and\s+(?:also|why|how|what|can|at\s+what|help|do|did|does|is|are|will|would)\b",
    re.IGNORECASE,
)


def _is_compound_question(text: str) -> bool:
    """Detect multi-part questions that likely require more than one clip or concept.

    Heuristic: compound questions have structural markers like:
    - Multiple question marks (e.g., 'What is X? And how does Y work?')
    - 'both X and Y' framing
    - 'X as well as Y' structure
    - Em-dash separating concepts ('X — A and B — why?')
    - Explicit enumeration ('two states', 'two aspects')
    - Coordinated question clauses ('..., and (also|why|how|what)')

    The shape is used to widen retrieval (``max_clips``), never to decide
    whether a clip may be served: that is the coverage decision's job.
    """
    if not text or not text.strip():
        return False
    if text.count("?") >= 2:
        return True
    return bool(_COMPOUND_QUESTION_RE.search(text))


def _serve_decision_for_result(
    *,
    query: str,
    answer_text: str,
    status: str,
    is_direct: bool,
    editorial_set: object,
    primary_mode: bool,
    serve_weak_match: bool,
):
    """Build the typed serve decision for one pipeline result.

    Imports are local so the bridge module stays import-light at startup (the
    stage is only constructed when the first-person variant is selected).
    """
    from domain.first_person_decision import resolve_serve_posture
    from services.first_person_content_assessment import assess_content
    from services.first_person_coverage import coverage_for_served_text

    editorial_dict = editorial_set if isinstance(editorial_set, dict) else None
    content_safety = str(editorial_dict.get("content_safety") or "") if editorial_dict else None
    covered_facets = editorial_dict.get("covered_facets") if editorial_dict else None
    if covered_facets and not isinstance(covered_facets, (list, tuple, set)):
        covered_facets = None

    coverage = coverage_for_served_text(
        query,
        answer_text,
        is_direct=is_direct,
        editorial_set=editorial_dict,
        semantic_facets=covered_facets,
    )
    assessment = assess_content(
        answer_text,
        query=query,
        content_safety=content_safety or None,
    )
    return resolve_serve_posture(
        pipeline_status=status,
        is_direct_answer=is_direct,
        coverage=coverage,
        assessment=assessment,
        primary_mode=primary_mode,
        serve_weak_match=serve_weak_match,
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
    # Attribution and sources lines name a speaker, a talk title and a video id,
    # none of which may be machine-translated (audit 2026-10-25, review R10).
    # Anchored to the start of a line: the legacy layout renders "— Speaker (id, 12s)",
    # the continuous layout "— Speaker · Title · ▶ 01:20" and "Sources: [1] ...".
    r"(?<![^\n])— [^\n]+",
    r"(?<![^\n])Sources: [^\n]+",
)

# Glue worth translating must contain real words; rule lines, separators and
# punctuation-only runs are passed through untouched.
_HAS_WORDS_RE = re.compile(r"[A-Za-z]{3,}")

# A served clip that itself raises self-harm gets the support line beside it, even
# when the seeker's question showed no distress (2026-10-31 grading: q019 opened
# with self-harm statistics and carried no notice). Whole words only; the clip is
# never edited.
# Question-side cue for the same notice. Deliberately wide in WHAT it matches (means near a
# person, cutting, overdose) because it only ever adds the support line: it never blocks,
# never reroutes, never edits a clip. Not a risk classifier; the distress engine owns that.
_QUESTION_SELF_HARM_CUE_RE = re.compile(
    r"\b(?:self[\s-]*harm\w*|self[\s-]*injur\w*|overdos\w+"
    r"|cut(?:ting|s)?\s+(?:myself|herself|himself|themselves|(?:my|her|his|their|your)\s+"
    r"(?:arms?|wrists?|legs?|thighs?|skin))"
    r"|(?:bottle|packet|strip|box)\s+of\s+(?:sleeping\s+)?(?:pills|tablets)"
    r"|(?:pills|tablets|rope|blade|razor|gun)\b[^.?!]{0,60}\b(?:staring|looking\s+at)"
    r"|(?:swallow|took|take)\w*\s+(?:all\s+)?(?:the\s+)?(?:pills|tablets))\b",
    re.IGNORECASE,
)
_CLIP_MENTIONS_SELF_HARM = re.compile(
    r"\b(?:self[\s-]*harm|suicid\w*|kill(?:ing)?\s+(?:my|your|him|her|them)self"
    r"|end(?:ing)?\s+(?:my|your|his|her|their|one'?s)\s+(?:own\s+)?life|take\s+(?:my|your|his|her|their|one'?s)\s+own\s+life"
    r"|thinking\s+of\s+dying|want(?:ing)?\s+to\s+die)\b",
    re.IGNORECASE,
)


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
    if not related or not getattr(settings, "first_person_abstain_related_clips_enabled", False):
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
        if citation.get("domain_rights_status") != "licensed":
            logger.info("[FirstPersonBridge] Dropping citation without canonical licensed status.")
            continue
        if citation.get("rights_cleared") is not True:
            logger.info("[FirstPersonBridge] Dropping citation without rights clearance.")
            continue
        if citation.get("first_person_eligible") is not True:
            logger.info("[FirstPersonBridge] Dropping citation not marked first-person eligible.")
            continue
        url = str(citation.get("source_url") or citation.get("url") or "")
        if not url.startswith(("http://", "https://")):
            continue
        if not source_is_authoritatively_licensed(
            source_url=url,
            video_id=citation.get("video_id"),
            domain_rights_status=citation.get("domain_rights_status"),
        ):
            logger.info("[FirstPersonBridge] Dropping citation not licensed in current register.")
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
        # Fail-closed invariant: unverified clips must NEVER be served to public users (UT-06)
        if getattr(settings, "first_person_require_speaker_verified", False):
            is_verified = (
                citation.get("speaker_verified") is True
                or citation.get("quality_status") == "verified_verbatim"
                or bool(citation.get("voice_verification_method"))
            )
            if not is_verified:
                logger.info(
                    "[FirstPersonBridge] Dropping citation without verified voice: %s",
                    citation.get("clip_id") or citation.get("point_id"),
                )
                continue
        from services.guru_registry import allowed_speaker_labels

        if citation.get("speaker") not in allowed_speaker_labels():
            logger.info(
                "[FirstPersonBridge] Dropping citation with unallowlisted speaker: %s",
                citation.get("speaker"),
            )
            continue

        eligible.append(
            {**citation, "speaker_verified": True}
            if citation.get("speaker_verified") is True
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


# Arabic/Urdu and the Indic blocks (Devanagari .. Sinhala). Latin text, punctuation and
# typographic quotes are not in these ranges.
_NON_LATIN_SCRIPT_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u0900-\u0DFF]")


def _retrieval_query_is_latin(text: str) -> bool:
    """True when the retrieval query carries no Indic/Arabic script (HyDE language gate)."""
    return not _NON_LATIN_SCRIPT_RE.search(text or "")


def _hint_reads_calm(ctx: Any, hint: str) -> bool:
    """True only when the distress assessor rates the hint NONE.

    The pipeline's crisis pre-check also reads the resolved retrieval query, so a
    hint carrying distress would make a follow-up turn redirect where it did not
    before the hint existed. Distress routing must not change without a clinician
    note, so such a hint is simply not merged: the turn behaves as it did before.
    Fails closed: no assessor, or an unreadable level, means the hint is not used.
    """
    serene_mind = getattr(getattr(ctx, "container", None), "serene_mind", None)
    if serene_mind is None:
        return False
    assessment = serene_mind.assess_distress(hint)
    if assessment is None:
        return True
    level = getattr(assessment, "level", None)
    value = getattr(level, "value", level)
    return isinstance(value, int) and not isinstance(value, bool) and value == 0


# Labelled assistant copy for a meta follow-up (rendered in safety_notices, never in
# the evidence body). It describes the selection; it never teaches.
_META_FOLLOWUP_NOTES = {
    "shorter": "You asked for something shorter, so this is a shorter passage for your earlier question.",
    "example": "You asked for an example; this passage was chosen for your earlier question.",
    "elaborate": "This passage goes back to your earlier question.",
    "ordinal": (
        "I can't see which item you mean from here, so this passage was chosen for "
        "your earlier question as a whole."
    ),
}


def _resolve_topic_shift(retrieval_query: str) -> FollowupResolution | None:
    """The question without an explicit topic-shift marker, else None.

    Flag ``first_person_topic_shift_enabled``, independent of the meta lane: dropping
    "Unrelated," is a mis-serve protection, not a meta behaviour. Deterministic; the
    marker is dropped and history is never prepended.
    """
    if not getattr(settings, "first_person_topic_shift_enabled", False):
        return None
    from rag.resolve_followup import FollowupResolution, strip_topic_shift

    shifted = strip_topic_shift(retrieval_query)
    if shifted is None:
        return None
    return FollowupResolution(
        retrieval_query=shifted,
        kind="topic_shift",
        reason_code="explicit_topic_shift_marker",
        history_used=False,
    )


def _resolve_meta_followup(
    retrieval_query: str, chat_history: list
) -> FollowupResolution | None:
    """Typed resolution for a meta follow-up, else None.

    Flag ``first_person_meta_followup_enabled``; deterministic, no LLM. A meta follow-up
    needs a prior user turn: that turn becomes the question that is retrieved and scored,
    so the scorer never judges clips against "say it shorter". An explicit topic shift is
    handled by :func:`_resolve_topic_shift`, before this; ``meta_followup_kind`` itself
    refuses a turn that carries a shift marker.
    """
    if not getattr(settings, "first_person_meta_followup_enabled", False):
        return None
    from rag.resolve_followup import FollowupResolution, meta_followup_kind, names_new_topic

    kind = meta_followup_kind(retrieval_query)
    if kind is None or not chat_history:
        return None
    if kind != "ordinal" and names_new_topic(retrieval_query):
        return None
    current = retrieval_query.strip()
    prior = next(
        (
            str(m.get("content") or "").strip()[:200]
            for m in reversed(chat_history)
            if isinstance(m, dict)
            and m.get("role") == "user"
            and str(m.get("content") or "").strip()
            and str(m.get("content") or "").strip() != current
            # A prior meta turn ("explain the second one") is not a question to retrieve.
            and meta_followup_kind(str(m.get("content") or "")) is None
        ),
        "",
    )
    if not prior:
        return None
    resolved = {
        "shorter": prior,
        "elaborate": prior,
        "example": f"{prior} — an example or story",
        "ordinal": f"{prior} — {current}",
    }[kind]
    return FollowupResolution(
        retrieval_query=resolved,
        kind=kind,
        reason_code=f"meta_{kind}_request",
        note=_META_FOLLOWUP_NOTES[kind],
        max_context_spans=1 if kind == "shorter" else None,
    )


_DIFFERENCE_RE = re.compile(
    r"\bdifference\s+between\s+(?P<a>[\w' -]{2,40}?)\s+and\s+(?P<b>[\w' -]{2,40}?)(?=[,?.;]|\s+and\s+|$)",
    re.IGNORECASE,
)
_PART_SPLIT_RE = re.compile(
    r"\?\s+(?=\S)"
    r"|,?\s+and\s+(?:then\s+|also\s+)?(?=(?:how|why|what|which|when|where|can|should|is|does|do)\b)",
    re.IGNORECASE,
)
_PART_REFERENT_RE = re.compile(r"\b(?:it|this|that|they|them|those|these|one)\b", re.IGNORECASE)
_MULTIPART_MAX_PARTS = 2
_PART_MIN_WORDS = 3


def _question_parts(question: str) -> list[str]:
    """At most two sub-questions of a multi-part question, else [] (deterministic).

    "difference between A and B" becomes "What is A?" / "What is B?"; otherwise the
    question splits on a second question mark or a coordinated question clause
    (", and then how ..."). A later part that only points back ("it", "that") keeps
    the first part as its context. Parts are the seeker's own words.
    """
    q = " ".join((question or "").split())
    m = _DIFFERENCE_RE.search(q)
    if m:
        a, b = m.group("a").strip(), m.group("b").strip()
        if a and b and a.lower() != b.lower():
            return [f"What is {a}?", f"What is {b}?"]
    pieces = [p.strip(" ,;") for p in _PART_SPLIT_RE.split(q) if p and p.strip(" ,;")]
    pieces = [p for p in pieces if len(p.split()) >= _PART_MIN_WORDS]
    if len(pieces) < 2:
        return []
    first, second = pieces[0], pieces[1]
    if _PART_REFERENT_RE.search(second):
        second = f"{first} — {second}"
    return [first, second][:_MULTIPART_MAX_PARTS]


async def _resolve_question_parts(container: Any, question: str) -> list[str]:
    """Resolve sub-questions of a multi-part question: deterministic regex first, then LLM decomposition."""
    parts = _question_parts(question)
    if len(parts) >= 2:
        return parts
    provider = _hyde_provider(container)
    if provider is not None and hasattr(provider, "decompose_query"):
        try:
            sub_queries = await asyncio.wait_for(provider.decompose_query(question), timeout=2.5)
            if isinstance(sub_queries, list):
                valid = [q.strip() for q in sub_queries if q and len(q.split()) >= _PART_MIN_WORDS]
                clean_q = " ".join((question or "").split()).lower().rstrip("?.!")
                distinct = [q for q in valid if " ".join(q.split()).lower().rstrip("?.!") != clean_q]
                if len(distinct) >= 2:
                    return distinct[:_MULTIPART_MAX_PARTS]
        except Exception as exc:
            logger.debug("[FirstPersonBridge] LLM query decomposition fell back to single query: %s", exc)
    return []


def _merge_part_results(results: list[Any]) -> Any:
    """One pipeline result from the served part results (citations in part order)."""
    from services.first_person_pipeline import FirstPersonPipelineResult

    served = [r for r in results if r is not None]

    def _all(attr: str) -> list:
        return [x for r in served for x in (getattr(r, attr, None) or [])]

    return FirstPersonPipelineResult(
        answer_text="\n\n".join(str(r.answer_text or "").strip() for r in served),
        citations=_all("citations"),
        status="success" if all(r.status == "success" for r in served) else "weak_match",
        is_direct_answer=all(bool(r.is_direct_answer) for r in served),
        latency_ms=max(float(getattr(r, "latency_ms", 0.0) or 0.0) for r in served),
        audio_playback_clips=_all("audio_playback_clips"),
        related_clips_heading=next(
            (h for r in served if (h := getattr(r, "related_clips_heading", None))), None
        ),
        fp_served=True,
    )


def _multipart_note(parts: list[str], served: list[bool]) -> str:
    """Labelled assistant copy naming which part each passage was chosen for."""
    shown = [p for p, ok in zip(parts, served) if ok]
    if len(shown) == len(parts):
        listed = " ".join(f"{i}. “{p}”" for i, p in enumerate(shown, 1))
        return (
            f"Your question has {len(parts)} parts, so each passage below was chosen for one "
            f"part, in order: {listed} The passages are not a combined answer."
        )
    return (
        f"I found a recorded passage for only one part of your question: “{shown[0]}”. "
        "I don't have a verified passage for the rest."
    )


async def _serve_question_parts(
    container: Any,
    pipeline: Any,
    parts: list[str],
    whole_question: str,
    **serve_kwargs: Any,
) -> tuple[Any, str] | None:
    """Serve each part through the full gate chain in parallel; None when no part serves.

    Flag ``first_person_multipart_enabled``. Each part is embedded and served exactly
    like a standalone question (no HyDE, to bound cost); only success/weak_match
    results with citations are kept.
    """
    from services.first_person_pipeline import serve_first_person

    async def _one(part: str) -> Any:
        try:
            encoded = await container.embedding.encode_single_full_async(part)
        except (RuntimeError, ValueError, TimeoutError, OSError) as exc:  # noqa: BLE001 - a part that cannot embed is not served
            logger.debug("[FirstPersonBridge] Part embed unavailable: %s", type(exc).__name__)
            return None
        dense = _dense_vector(encoded, settings.embedding_dimension)
        if dense is None:
            return None
        sparse = _sparse_vector(encoded.get("sparse") if isinstance(encoded, dict) else None)
        try:
            res = await serve_first_person(
                pipeline,
                query=part,
                retrieval_query=part,
                query_dense_vector=dense,
                confidence_query_dense=dense,
                query_sparse_vector=sparse,
                **serve_kwargs,
            )
        except asyncio.CancelledError:
            raise
        except (RuntimeError, ValueError, TypeError, KeyError, TimeoutError, OSError) as exc:
            logger.debug("[FirstPersonBridge] Part serve failed: %s", type(exc).__name__)
            return None
        ok = str(getattr(res, "status", "")) in ("success", "weak_match") and bool(
            getattr(res, "citations", None)
        )
        return res if ok else None

    results = list(await asyncio.gather(*(_one(p) for p in parts)))
    # A clip already chosen for an earlier part is not repeated for a later one.
    seen_text: set[str] = set()
    for i, r in enumerate(results):
        text = str(getattr(r, "answer_text", "") or "").strip() if r is not None else ""
        if r is not None and text in seen_text:
            results[i] = None
        seen_text.add(text)
    if not any(r is not None for r in results):
        return None
    merged = _merge_part_results(results)
    # Each part was gated alone; the combination is re-checked against the WHOLE
    # question (external-teacher, self-harm and relationship context live there).
    from services.first_person_evidence_policy import first_person_evidence_policy

    decision = first_person_evidence_policy.assess_contextual_safety(
        whole_question, merged.answer_text, retrieval_query=whole_question
    )
    if not decision.may_serve:
        logger.info("[FirstPersonBridge] Multipart answer failed the whole-question safety check.")
        return None
    return merged, _multipart_note(parts, [r is not None for r in results])


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
        *,
        reason: str | None = None,
        answerability: str | None = None,
        error: str | None = None,
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
        from guardrails.lightweight_handler import (
            needs_addiction_support_boundary,
            needs_relationship_safety_boundary,
        )
        from rag.meditation import is_meditation_imperative

        msg_str = str(getattr(ctx, "user_msg", "") or "")
        _has_promise_or_boundary = bool(
            _PROMISE_OR_OUTCOME_TRAP_RE.search(msg_str)
            or needs_relationship_safety_boundary(msg_str)
            or needs_addiction_support_boundary(msg_str)
        )
        if (
            is_meditation_imperative(msg_str)
            or bool(_STEP_INSTRUCTION_RE.search(msg_str))
            or bool(_DIFFERENCE_SYNTHESIS_RE.search(msg_str))
        ) and not _has_promise_or_boundary:
            logger.info(
                "[FirstPersonBridge] Meditation instruction / difference inquiry declined for single clip; falling through to GraphStage."
            )
            return None
        return await self._abstain(
            ctx,
            status,
            boundaries,
            compassion=compassion,
            related=await self._safe_related(ctx, related, compassion),
            reason=reason,
            answerability=answerability,
            error=error,
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
        from guardrails.lightweight_handler import (
            needs_addiction_support_boundary,
            needs_relationship_safety_boundary,
        )
        from rag.meditation import is_meditation_imperative

        _has_promise_or_boundary = bool(
            _PROMISE_OR_OUTCOME_TRAP_RE.search(query)
            or needs_relationship_safety_boundary(query)
            or needs_addiction_support_boundary(query)
        )
        if is_meditation_imperative(query):
            if not _has_promise_or_boundary:
                logger.info("[FirstPersonBridge] Guided-practice request; GraphStage runs.")
                return None
            logger.info(
                "[FirstPersonBridge] Guided practice carries promise trap or safety boundary; evaluating under bridge safety."
            )
        if _STEP_INSTRUCTION_RE.search(query) and not _has_promise_or_boundary:
            logger.info(
                "[FirstPersonBridge] Step-by-step meditation instruction inquiry; GraphStage runs."
            )
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
        multipart_enabled = getattr(settings, "first_person_multipart_enabled", False)
        resolved_parts = (
            await _resolve_question_parts(ctx.container, query)
            if multipart_enabled
            else []
        )
        has_multipart = len(resolved_parts) >= 2
        if (
            _DIFFERENCE_SYNTHESIS_RE.search(query)
            and not (needs_rel or needs_add or _has_promise_or_boundary)
            and not has_multipart
        ):
            if not fp_only:
                logger.info(
                    "[FirstPersonBridge] Difference/comparative synthesis inquiry; GraphStage runs."
                )
                return None
        if (_SYNTHESIS_SHAPE_RE.search(query) or needs_rel or needs_add) and not has_multipart:
            if not fp_only:
                logger.info(
                    "[FirstPersonBridge] Question needs synthesis, not one clip; GraphStage runs."
                )
                return None
            # First-person-only: carry the same safety boundary the graph path appends.
            from guardrails.lightweight_handler import (
                RELATIONSHIP_SAFETY_BOUNDARY,
                addiction_support_boundary,
            )

            if needs_rel and getattr(settings, "relationship_safety_boundary_enabled", False):
                boundaries.append(RELATIONSHIP_SAFETY_BOUNDARY)
            if needs_add:
                boundaries.append(addiction_support_boundary())
        from services.serene_mind_engine import LLM_STAGE2_UNAVAILABLE_SIGNAL

        _signals = getattr(getattr(ctx, "assessment", None), "detected_signals", None) or []
        _llm_check_unavailable = LLM_STAGE2_UNAVAILABLE_SIGNAL in [
            sig for sig in _signals if isinstance(sig, str)
        ]
        if _QUESTION_SELF_HARM_CUE_RE.search(query) or _llm_check_unavailable:
            # Notice only: the pattern distress engine rates these questions NONE
            # ("a bottle of sleeping pills ... I keep staring at it", a parent describing a
            # teen cutting), so no lane changes, but the human support line must still travel
            # with whatever is answered, an abstain included (2026-10-31 unanswerable set).
            from services.crisis_helplines import ensure_support_line

            _cue_line = ensure_support_line("")
            if _cue_line not in boundaries:
                boundaries.append(_cue_line)
        state = getattr(ctx, "state", None) or {}
        # RequestStateStage already produced the English query (its own
        # bounded translation); never pay for a second one here.
        retrieval_query = str(state.get("user_msg_en") or query)

        # Conversational Follow-Up Resolution (CQR / Anaphora):
        chat_history = getattr(ctx, "chat_body_messages", None) or []
        # Anonymous requests carry no trusted history; their one prior user turn
        # (same trust as the current message) feeds ONLY this resolver.
        _hint = getattr(ctx, "followup_hint_user_turn", None)
        if (
            not chat_history
            and _hint
            and not getattr(ctx, "incognito", False)
            and _hint_reads_calm(ctx, _hint)
        ):
            chat_history = [{"role": "user", "content": _hint}]
        # A history-resolved retrieval query depends on the conversation, but the
        # exact cache key hashes only the bare question; such a turn must bypass it.
        followup_resolved = False
        history_prepended = False
        meta_note: str | None = None
        max_context_spans: int | None = None
        _followup_input = retrieval_query
        shifted = _resolve_topic_shift(retrieval_query)
        meta = None if shifted is not None else _resolve_meta_followup(retrieval_query, chat_history)
        if shifted is not None:
            # Explicit topic shift: the marker is dropped and history is never used.
            retrieval_query = shifted.retrieval_query
            followup_resolved = True
        elif meta is not None:
            # Meta follow-up: the prior user turn is the question that is retrieved
            # AND scored; the seeker's request only shapes the labelled note.
            retrieval_query, meta_note, max_context_spans = (
                meta.retrieval_query,
                meta.note,
                meta.max_context_spans,
            )
            # The resolved query depends on this flag, not only on the bare question the
            # exact cache key hashes, so it may not read or write that cache.
            followup_resolved = True
        elif (
            chat_history
            and _is_heuristic_followup(retrieval_query, chat_history)
            and not names_new_topic(retrieval_query)
        ):
            last_user = _get_last_user_message(chat_history)
            if last_user:
                retrieval_query = f"{last_user} — {retrieval_query}"
                followup_resolved = True
                history_prepended = True
                logger.info(
                    "[FirstPersonBridge] Resolved follow-up query (len=%d sha=%s)",
                    len(retrieval_query),
                    hashlib.sha256(retrieval_query.encode()).hexdigest()[:12],
                )

        # Routing metadata for this turn: the kind and the rule that matched, logged as
        # primitives and a hash (SEC-003). It never reaches the answer body, a citation,
        # or a gate — a classifier label cannot make a clip eligible or a turn safe.
        followup_meta = (
            shifted
            or meta
            or followup_metadata(_followup_input, chat_history, continuation=history_prepended)
        )
        logger.info(
            "[FirstPersonBridge] Follow-up resolution %s hist_turns=%d",
            " ".join(f"{k}={v}" for k, v in followup_meta.log_fields(_followup_input).items()),
            min(len(chat_history), 10),
        )

        container = ctx.container

        # HyDE (Hypothetical Document Embeddings) for first-person retrieval.
        # When enabled, generate a short hypothetical spiritual teaching that answers
        # the query, then embed THAT text instead of the raw query. The hypothetical
        # text uses domain vocabulary ("Beautiful State", "Inner Transformation", etc.)
        # that is close to actual clip verbatim_text in vector space — dramatically
        # improving recall for abstract/conceptual questions.
        # Fail-open: any timeout or error falls back to the original retrieval_query.
        # Gated on the RETRIEVAL query's script, not the UI language (2026-11-20): an Indic
        # turn retrieves with its English translation (user_msg_en), which HyDE can expand;
        # a failed translation leaves native script there and HyDE stays off.
        _hyde_enabled = bool(getattr(settings, "first_person_hyde_enabled", False))
        _is_en = _retrieval_query_is_latin(retrieval_query)

        # Always embed the original query first — this vector is used for
        # calibrated cosine confidence scoring and must not be replaced by HyDE.
        try:
            original_encoded = await container.embedding.encode_single_full_async(retrieval_query)
        except Exception as exc:
            # Embedding is bridge infrastructure, not chat infrastructure:
            # GraphStage performs its own retrieval embedding, so a failure
            # here only means "no bridge" (kept at DEBUG — the embedding
            # service logs its own errors).
            logger.debug("[FirstPersonBridge] Query embed unavailable; no bridge: %s", exc)
            return await self._decline(ctx, "error", compassion=distress_compassion)
        dense = _dense_vector(original_encoded, settings.embedding_dimension)
        if dense is None:
            # Includes mocked/test containers: no vector contract, no bridge.
            logger.debug("[FirstPersonBridge] Dense vector contract not met; no bridge.")
            return await self._decline(ctx, "error", compassion=distress_compassion)
        sparse = _sparse_vector(
            original_encoded.get("sparse") if isinstance(original_encoded, dict) else None
        )
        # Flag first_person_answerability_prefetch_enabled: the question-only gate
        # starts now and overlaps HyDE + retrieval; serve_first_person cancels it if
        # the turn never reaches the gate.
        from services.first_person_pipeline import start_answerability_prefetch

        answerability_prefetch = start_answerability_prefetch(
            _fp_pipeline(container), retrieval_query
        )

        # HyDE (Hypothetical Document Embeddings) for first-person retrieval.
        # When enabled, generate a short hypothetical spiritual teaching that answers
        # the query, then embed THAT text instead of the raw query for Qdrant retrieval.
        # The HyDE embedding is passed only to pipeline.execute(); `dense` (original-query
        # embedding) is kept intact for all cosine confidence scoring so the calibration
        # contract is unchanged. Fail-open: timeout or error falls back to original.
        retrieval_dense = dense  # default: retrieval uses original-query vector
        if _hyde_enabled and _is_en:
            _q_norm = retrieval_query.strip().lower()
            _q_hash = hashlib.sha256(_q_norm.encode("utf-8")).hexdigest()
            _cached = _get_cached_hyde(_q_hash)
            if _cached is not None:
                _, cached_vec = _cached
                retrieval_dense = cached_vec
                logger.info(
                    "[FirstPersonBridge] HyDE cache hit for query hash %s; using deterministic cached vector.",
                    _q_hash[:8],
                )
            else:
                try:
                    import asyncio as _asyncio

                    _llm = _hyde_provider(container)
                    if _llm is None:
                        # Not silent: the old code checked one attribute and skipped HyDE
                        # without a trace when it was absent.
                        if not _HYDE_PROVIDER_WARNED["said"]:
                            _HYDE_PROVIDER_WARNED["said"] = True
                            logger.info(
                                "[FirstPersonBridge] No container provider implements "
                                "generate_hyde (checked llm, ollama, openrouter, nim); "
                                "HyDE is skipped for this deployment."
                            )
                    if _llm is not None:
                        _hyde_to = float(getattr(settings, "first_person_hyde_timeout_s", 15.0) or 15.0)
                        hyde_text = await _asyncio.wait_for(
                            _llm.generate_hyde(question=retrieval_query),
                            timeout=_hyde_to,
                        )
                        if hyde_text and len(hyde_text.strip()) > 10:
                            # Embed HyDE text + original query (keeps sparse signal).
                            _hyde_text_to_embed = f"{hyde_text.strip()} {retrieval_query}"
                            _hyde_encoded = await container.embedding.encode_single_full_async(
                                _hyde_text_to_embed
                            )
                            _hyde_dense = _dense_vector(_hyde_encoded, settings.embedding_dimension)
                            if _hyde_dense is not None:
                                retrieval_dense = _hyde_dense
                                _set_cached_hyde(_q_hash, hyde_text.strip(), _hyde_dense)
                                logger.info(
                                    "[FirstPersonBridge] HyDE hypothetical generated (%d chars); "
                                    "cached and using HyDE embedding for retrieval only.",
                                    len(hyde_text),
                                )
                except Exception as _hyde_exc:
                    # Fail-open: timeout, circuit-open, or any error → original query.
                    logger.debug(
                        "[FirstPersonBridge] HyDE generation skipped (fail-open): %s", _hyde_exc
                    )

        user_lang = str(getattr(ctx, "preferred_lang", "") or getattr(ctx, "language", "") or "en")

        # T6-02 (MEM-002): Extract memory signals (seen videos, stated interests) for clip diversity
        memory_signals = None
        if not getattr(ctx, "incognito", False):
            user_profile = (
                getattr(ctx, "state", {}).get("user_profile")
                if hasattr(ctx, "state") and isinstance(ctx.state, dict)
                else None
            )
            seen_videos = set()
            chat_history = (
                getattr(ctx, "state", {}).get("original_chat_history") or []
                if hasattr(ctx, "state") and isinstance(ctx.state, dict)
                else []
            )
            for msg in chat_history:
                if isinstance(msg, dict):
                    for cit in msg.get("citations") or []:
                        if isinstance(cit, dict):
                            vid = cit.get("videoId") or cit.get("video_id")
                            if vid:
                                seen_videos.add(str(vid))
            if getattr(settings, "first_person_server_seen_clips_enabled", False):
                try:
                    from services.first_person_seen_store import get_seen_clips

                    _uid = str(
                        getattr(ctx, "user_id", "")
                        or (
                            getattr(ctx, "state", {}).get("user_id")
                            if hasattr(ctx, "state") and isinstance(ctx.state, dict)
                            else ""
                        )
                        or ""
                    )
                    _tid = str(getattr(ctx, "tenant_id", "") or "default")
                    _rcli = getattr(container, "redis_client", None)
                    if _uid:
                        _, _server_videos = get_seen_clips(
                            user_id=_uid, tenant_id=_tid, redis_client=_rcli
                        )
                        seen_videos.update(_server_videos)
                except (
                    RuntimeError,
                    OSError,
                    ConnectionError,
                    TimeoutError,
                    ValueError,
                    KeyError,
                    AttributeError,
                ) as _seen_exc:
                    logger.debug(
                        "[FirstPersonBridge] Server seen clips lookup failed (fail-open): %s",
                        _seen_exc,
                    )
            if seen_videos or (user_profile and getattr(user_profile, "topics_of_interest", None)):
                memory_signals = {
                    "seen_video_ids": list(seen_videos),
                    "stated_interests": list(getattr(user_profile, "topics_of_interest", []) or [])
                    if user_profile
                    else [],
                }

        pipeline = _fp_pipeline(container)
        from services.first_person_pipeline import serve_first_person

        is_compound = _is_compound_question(query)
        _cache_bypass = (
            getattr(ctx, "cache_bypass", False) is True
            or getattr(ctx, "incognito", False) is True
            or followup_resolved
            or bool(memory_signals and memory_signals.get("seen_video_ids"))
        )
        # Flag first_person_multipart_enabled: each part through the full gate chain;
        # the whole question is served as before when no part serves.
        # Skip when history was prepended or meta follow-up active; allow on topic-shift turns.
        parts = (
            resolved_parts
            if (
                resolved_parts
                and not history_prepended
                and meta_note is None
            )
            else (
                await _resolve_question_parts(container, retrieval_query)
                if (
                    getattr(settings, "first_person_multipart_enabled", False)
                    and not history_prepended
                    and meta_note is None
                )
                else []
            )
        )
        multipart = (
            await _serve_question_parts(
                container,
                pipeline,
                parts,
                retrieval_query,
                teacher_id="both",
                max_clips=3,
                language=user_lang,
                cache_bypass=_cache_bypass,
                memory_signals=memory_signals,
                is_distress=distress_compassion,
            )
            if len(parts) >= 2
            else None
        )
        part_note: str | None = None
        if multipart is not None:
            result, part_note = multipart
            if answerability_prefetch is not None:
                answerability_prefetch[1].cancel()
        else:
            result = await serve_first_person(
                pipeline,
                query=query,
                # retrieval_dense is the HyDE embedding when HyDE is active; otherwise
                # identical to `dense`. `confidence_query_dense` carries the
                # original-query vector separately so the calibrated confidence
                # check still compares stored-clip vectors with the seeker's own
                # question, never with the HyDE expansion.
                query_dense_vector=retrieval_dense,
                confidence_query_dense=dense,
                query_sparse_vector=sparse,
                teacher_id="both",
                max_clips=4 if is_compound else 3,
                retrieval_query=retrieval_query,
                language=user_lang,
                # The chat cache stages honour both flags; the first-person exact
                # cache is a cache too, so it must honour them the same way.
                cache_bypass=_cache_bypass,
                memory_signals=memory_signals,
                # Venting/suffering queries: allow score-2 foundational clips and
                # honor HyDE expansion alignment in confidence (not raw colloquial cosine).
                # Lesson: L-VENTING-CONFIDENCE-HONORS-HYDE-1, L-VENTING-SCORE2-FOUNDATIONAL-ELIGIBLE-1.
                is_distress=distress_compassion,
                **({"max_context_spans": max_context_spans} if max_context_spans else {}),
                **({"answerability_prefetch": answerability_prefetch} if answerability_prefetch else {}),
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
        # Opt-in (first_person_serve_weak_match): a weak_match is servable under its
        # honest "Related, not a direct answer" label. The pipeline runs the
        # answerability gate only when first_person_answerability_check_enabled is
        # on; when it is off the harness records answerability="permissive" and no
        # gate ran. The getattr default
        # matches the declared default (True); real Settings always carries it.
        #
        # FP-primary posture (2026-10-27, plan Change 5): `first_person_primary_mode`
        # is the master switch for the whole posture. When it is on, a weak_match is
        # terminal for a topic the corpus covers — the generating graph never runs —
        # and the honest related label travels in metadata, never in answer text.
        # When it is off, weak matches are NOT served regardless of
        # `first_person_serve_weak_match`; see serve_weak below. Neither flag weakens
        # a gate.
        primary_mode = bool(getattr(settings, "first_person_primary_mode", True))
        # Serving posture is a typed decision (domain.first_person_decision):
        # content assessment + coverage. Question shape no longer decides — a
        # compound question is served as related when its required facets are
        # covered, and a "direct" verdict is downgraded when they are not.
        serve_decision = _serve_decision_for_result(
            query=query,
            answer_text=str(getattr(result, "answer_text", "") or ""),
            status=status,
            is_direct=is_direct,
            editorial_set=getattr(result, "editorial_set", None),
            primary_mode=primary_mode,
            serve_weak_match=bool(getattr(settings, "first_person_serve_weak_match", True)),
        )
        logger.debug(
            "[FirstPersonBridge] serve_posture=%s reason=%s coverage=%s content=%s",
            serve_decision.posture.value,
            serve_decision.reason,
            serve_decision.coverage.verdict.value if serve_decision.coverage else "none",
            serve_decision.assessment.severity.value
            if serve_decision.assessment and serve_decision.assessment.severity
            else "none",
        )
        if not serve_decision.serves:
            _query_str = query
            _is_promise_trap = bool(_PROMISE_OR_OUTCOME_TRAP_RE.search(_query_str))
            if _is_promise_trap:
                return await self._abstain(
                    ctx,
                    status,
                    boundaries,
                    compassion=distress_compassion,
                    related=await self._safe_related(ctx, related, distress_compassion),
                    reason=getattr(result, "abstain_reason", None),
                    answerability=getattr(result, "answerability", None),
                    error=getattr(result, "error", None),
                )
            if status == "crisis_redirect":
                return None

            if not getattr(settings, "first_person_llm_fallback_enabled", False):
                from rag.meditation import is_meditation_imperative

                _is_allowed_practice_or_diff = (
                    bool(_STEP_INSTRUCTION_RE.search(_query_str))
                    or bool(_DIFFERENCE_SYNTHESIS_RE.search(_query_str))
                ) and not (needs_rel or needs_add)
                if (
                    not is_meditation_imperative(_query_str)
                    and not _is_allowed_practice_or_diff
                ):
                    return await self._abstain(
                        ctx,
                        status,
                        boundaries,
                        compassion=distress_compassion,
                        related=await self._safe_related(ctx, related, distress_compassion),
                        # NEW-ANS-2: keep why the pipeline abstained.
                        reason=getattr(result, "abstain_reason", None),
                        answerability=getattr(result, "answerability", None),
                        error=getattr(result, "error", None),
                    )

            # When fallback is enabled, safely forward any verified eligible citations to state
            # only if Mode 2 Grounded Synthesis is enabled.
            if getattr(settings, "first_person_grounded_synthesis_enabled", False):
                raw_citations = getattr(result, "citations", None)
                eligible_cits = _eligible_citations(raw_citations)
                if eligible_cits and hasattr(ctx, "state") and isinstance(ctx.state, dict):
                    ctx.state["first_person_related_clips"] = eligible_cits
            logger.debug(
                "[FirstPersonBridge] No direct answer (status=%s, posture=%s); GraphStage runs.",
                status or "unknown",
                serve_decision.posture.value,
            )
            return None
        # A covered-but-partial set is served as related, never as direct.
        if not serve_decision.is_direct:
            is_direct = False

        raw_citations = getattr(result, "citations", None)
        citations = _eligible_citations(raw_citations)
        answer = str(getattr(result, "answer_text", "") or "").strip()
        if (
            not isinstance(raw_citations, list)
            or len(citations) != len(raw_citations)
            or not answer
            or not citations
        ):
            logger.debug("[FirstPersonBridge] No servable verbatim answer; declining.")
            return await self._decline(
                ctx,
                status,
                boundaries,
                compassion=distress_compassion,
                related=related,
                error=getattr(result, "error", None),
            )

        # Faculty dual-mode: when not a direct answer and LLM fallback is enabled,
        # pass related clips to state as faculty citations and route to LangGraph synthesis
        if not is_direct and getattr(settings, "first_person_llm_fallback_enabled", False):
            if (
                getattr(settings, "first_person_grounded_synthesis_enabled", False)
                and hasattr(ctx, "state")
                and isinstance(ctx.state, dict)
            ):
                ctx.state["first_person_related_clips"] = citations
            logger.debug(
                "[FirstPersonBridge] Weak match / not direct (status=%s) with LLM fallback enabled; passing %d related clips to state and allowing fallthrough to LangGraph.",
                status,
                len(citations),
            )
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
        if not verbatim_quotes or any(quote not in answer for quote in verbatim_quotes):
            logger.warning(
                "[FirstPersonBridge] Answer text does not contain its cited clip text; "
                "refusing to serve it as teacher voice."
            )
            return await self._decline(
                ctx,
                status,
                boundaries,
                compassion=distress_compassion,
                reason="quote_contract_violation",
            )

        # NEW-SEC-1 (OPS-002): re-check every served clip at assembly. A clip whose
        # text no longer matches its stored hash means a gate was bypassed; fail
        # closed and count it.
        from app.answer_contract import served_clip_integrity_failures

        integrity_failures = served_clip_integrity_failures(citations, answer)
        if integrity_failures:
            try:
                from app.metrics import SERVED_INTEGRITY_FAILURE_TOTAL

                for check in integrity_failures:
                    SERVED_INTEGRITY_FAILURE_TOTAL.labels(check=check).inc()
            except (ImportError, ValueError) as exc:  # telemetry never breaks a response
                logger.debug("served integrity failure not counted: %s", type(exc).__name__)
            logger.error(
                "[FirstPersonBridge] Served clip failed the assembly integrity re-check "
                "(%s); refusing to serve it.",
                ",".join(sorted(set(integrity_failures))),
            )
            return await self._decline(
                ctx,
                status,
                boundaries,
                compassion=distress_compassion,
                reason="served_integrity_failure",
            )

        # Pipeline renderers may include headings, missing-clip prose, or a source
        # footer. Those are UI structure, not guru speech. Rebuild from every
        # eligible citation in source order as discrete exact quote blocks; the
        # citation cards carry speaker/source attribution.
        answer = "\n\n".join(verbatim_quotes)

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
            return await self._decline(
                ctx,
                status,
                boundaries,
                compassion=distress_compassion,
                reason="output_rail_unavailable",
            )
        output_check = await guardrails.check_output(answer)
        if isinstance(output_check, dict) and output_check.get("blocked"):
            logger.info(
                "[FirstPersonBridge] Output rail blocked bridge answer (reason=%s); declining.",
                output_check.get("reason"),
            )
            return await self._decline(ctx, status, boundaries, compassion=distress_compassion)

        # Platform copy that accompanies the clip but is NOT the teacher's words.
        safety_notices: list[str] = []
        compassion_framing_text: str | None = None

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
            # boundaries above: it is the distress lane's own reviewed copy, not
            # generated text, so the English literal-phrase rail does not gate it.
            # Before glue translation, so an Indic seeker gets localized compassion
            # copy while the teacher's words stay verbatim.
            framing = _distress_compassion_framing(ctx)
            if framing.strip():
                compassion_framing_text = framing.strip()

        # Invariant 1 (answer text is evidence): the served body is the verbatim
        # quote plus its attribution — nothing else. Platform copy (compassion
        # framing, relationship/addiction safety boundaries, the human support
        # line) travels in `route_metadata["safety_notices"]` and is rendered by
        # the client as its own block, so a seeker can always tell the teacher's
        # words from the platform's words.
        if compassion_framing_text:
            safety_notices.append(compassion_framing_text)
        for boundary in boundaries or []:
            text = str(boundary or "").strip()
            if text:
                safety_notices.append(text)

        # Structure copy the evidence body no longer carries: the weak-match
        # "related, not a direct answer" label and the two-recording note. Rendered
        # by the client in the same block as the other platform notices.
        for _structure_copy in (
            getattr(result, "related_clips_heading", None),
            getattr(result, "second_quote_note", None),
        ):
            _text = str(_structure_copy or "").strip()
            if _text and _text not in safety_notices:
                safety_notices.append(_text)
        for _note in (meta_note, part_note):
            if _note and _note not in safety_notices:
                safety_notices.append(_note)

        # PipelineContext carries the seeker's text as `user_msg`; reading
        # `user_message` always returned "" and silently disabled the
        # question-side self-harm cue.
        user_msg = str(getattr(ctx, "user_msg", "") or "")
        level = getattr(getattr(ctx, "assessment", None), "level", None)
        level_val = int(getattr(level, "value", 0) or 0)
        has_self_harm_risk = bool(
            _QUESTION_SELF_HARM_CUE_RE.search(user_msg)
            or _CLIP_MENTIONS_SELF_HARM.search(answer)
            or level_val >= 3
        )

        if not distress_compassion and _CLIP_MENTIONS_SELF_HARM.search(answer):
            # The seeker did not signal distress, but the teacher's own words raise
            # self-harm (e.g. a talk quoting suicide statistics). The clip stays
            # verbatim; the human support line rides beside it as platform copy.
            from services.crisis_helplines import ensure_support_line

            _joined_notices = "\n\n".join(safety_notices)
            if ensure_support_line(_joined_notices) != _joined_notices:
                safety_notices.append(ensure_support_line(""))

        from guardrails.lightweight_handler import (
            addiction_support_boundary,
            needs_addiction_support_boundary,
        )

        if needs_addiction_support_boundary(answer):
            _add_bound = addiction_support_boundary()
            if _add_bound not in safety_notices:
                safety_notices.append(_add_bound)

        # Platform copy for whatever the content assessor flagged on the served
        # clip (Ayurvedic / spiritual-physiology framing today). The clip is NOT
        # excluded — it carries a notice so the seeker knows to consult a
        # physician. Clinical claims and causal-etiology claims never reach here:
        # the assessment excluded them before serving.
        from services.first_person_content_assessment import assess_content, notice_copy
        from services.first_person_evidence_policy import first_person_evidence_policy

        _ed_set = getattr(result, "editorial_set", None)
        _cs = str(_ed_set.get("content_safety") or "") if isinstance(_ed_set, dict) else None
        served_assessment = assess_content(answer, query=query, content_safety=_cs or None)
        if not served_assessment.may_serve:
            # Defense in depth: the assembled text changed after the gate.
            logger.warning(
                "[FirstPersonBridge] Assembled answer failed the content re-check (%s); declining.",
                ",".join(served_assessment.exclusion_codes) or "degraded",
            )
            return await self._decline(
                ctx,
                status,
                boundaries,
                compassion=distress_compassion,
                reason="content_assessment_failed",
            )
        for _notice in notice_copy(served_assessment):
            if _notice not in safety_notices:
                safety_notices.append(_notice)
        for _notice in first_person_evidence_policy.notices_for(
            answer, query=query, content_safety=_cs or None
        ):
            if _notice not in safety_notices:
                safety_notices.append(_notice)

        if distress_compassion and has_self_harm_risk:
            # Emergency helpline is appended when acute distress / self-harm risk is detected.
            # Benign pedagogical/spiritual inquiries receive compassion framing & practice without helpline numbers.
            from services.crisis_helplines import ensure_support_line

            # ensure_support_line returns its input unchanged when a helpline
            # block (Tele-MANAS / 14416 / the line itself) is already present, so
            # run it over the notices already collected, not over "".
            _joined = "\n\n".join(safety_notices)
            _with_support = ensure_support_line(_joined)
            if _with_support != _joined:
                safety_notices.append(ensure_support_line(""))
        if distress_compassion:
            # Distress-lane parity, defense-in-depth: the graph's distress handler
            # returns straight to END, so it re-runs this persona/constitutional
            # check itself (rag/nodes/intent.py::handle_distress). The bridge
            # short-circuits even earlier, so the same check runs here — on a hit the
            # clip is dropped and the reviewed compassion copy is served instead.
            # The check runs on the FULL user-visible text (quote + notices), which
            # is what the seeker reads.
            from rag.nodes.verification import check_persona_adherence

            violation = check_persona_adherence("\n\n".join([*safety_notices, answer]))
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
            if safety_notices:
                # Notices carry no quotes: each block is pure glue.
                # One round trip, not one serial 5 s fail-open call per notice.
                safety_notices = list(
                    await asyncio.gather(
                        *(
                            _translate_glue_only(
                                notice,
                                [],
                                container,
                                str(getattr(ctx, "preferred_lang", "") or ""),
                            )
                            for notice in safety_notices
                        )
                    )
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
        editorial_set = _public_editorial_set_metadata(getattr(result, "editorial_set", None))
        evidence_set_supported = (
            editorial_set.get("status") == "supported" if editorial_set is not None else is_direct
        )
        verification = {
            # Citation integrity and answer/set support are independent facts:
            # every quote can be authentic even when the evidence set is partial
            # or conflicting and therefore cannot be certified as a direct answer.
            "passed": bool(is_direct and evidence_set_supported),
            "method": "first_person_verbatim_clip_gate",
            "citations_verified": True,
            "citation_integrity_verified": True,
            "evidence_set_supported": evidence_set_supported,
            # False = weak_match served under the "Related, not a direct answer" label.
            "direct": is_direct,
        }
        if editorial_set is not None:
            verification["editorial_set"] = editorial_set
        # Dispatches consented canonical memory and outbox persistence asynchronously
        _dispatch_fp_memory(ctx, answer, citations)
        if getattr(settings, "first_person_server_seen_clips_enabled", False) and not getattr(
            ctx, "incognito", False
        ):
            try:
                from services.first_person_seen_store import record_seen_clip

                _uid = str(
                    getattr(ctx, "user_id", "")
                    or (
                        getattr(ctx, "state", {}).get("user_id")
                        if hasattr(ctx, "state") and isinstance(ctx.state, dict)
                        else ""
                    )
                    or ""
                )
                _tid = str(getattr(ctx, "tenant_id", "") or "default")
                _rcli = getattr(container, "redis_client", None)
                if _uid:
                    for cit in citations:
                        c_id = cit.get("id") or cit.get("chunk_id") or cit.get("clip_id")
                        v_id = cit.get("videoId") or cit.get("video_id")
                        record_seen_clip(
                            user_id=_uid,
                            tenant_id=_tid,
                            clip_id=str(c_id) if c_id else None,
                            video_id=str(v_id) if v_id else None,
                            redis_client=_rcli,
                        )
            except (
                RuntimeError,
                OSError,
                ConnectionError,
                TimeoutError,
                ValueError,
                KeyError,
                AttributeError,
            ) as _rec_exc:
                logger.debug(
                    "[FirstPersonBridge] Server seen clips recording failed: %s",
                    _rec_exc,
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
            verification=verification,
            release_manifest=get_release_manifest().to_dict(),
            route_metadata={
                "route_decision": "first_person_bridge",
                "requested_variant": "first_person",
                "selected_variant": "verbatim_clip_bridge",
                "decision_method": "calibrated_is_direct" if is_direct else "weak_match_opt_in",
                # FP-served marker (plan T5/Change 5). A response carrying this is a
                # recorded teaching clip that passed the verbatim/answerability/rights
                # gates; no LLM authored it. Weak matches are still first-person served,
                # so the marker is independent of `direct`.
                "fp_served": True,
                "first_person_primary_mode": primary_mode,
                "first_person_collection": str(getattr(settings, "first_person_collection", "")),
                # C8: corpus version for per-corpus abstain/serve analysis. Empty when
                # neither the result nor Settings carries one (never guessed).
                "corpus_version": str(
                    getattr(result, "corpus_version", "")
                    or getattr(settings, "first_person_corpus_version", "")
                    or ""
                ),
                "clips_served": len(citations),
                "is_compound_query": is_compound,
                "partial_compound": bool(is_compound and len(verbatim_quotes) == 1),
                "pipeline_latency_ms": round(float(getattr(result, "latency_ms", 0.0) or 0.0), 2),
                "pipeline_cached": bool(getattr(result, "cached", False)),
                "stage_timings": getattr(result, "stage_timings", {}) or {},
                "routing_chain": list(getattr(ctx, "routing_chain", [])),
                "audio_playback_clip": getattr(result, "audio_playback_clip", None),
                "audio_playback_clips": getattr(result, "audio_playback_clips", []) or [],
                "detected_concepts": getattr(result, "detected_concepts", []),
                "atma_vichara_inquiry": getattr(result, "atma_vichara_inquiry", None),
                "related_clips_heading": getattr(result, "related_clips_heading", None),
                # Structure note for a two-recording answer ("Recording 2 is a
                # different video; it does not continue the first"). Metadata,
                # never body text (invariant 1).
                "second_quote_note": getattr(result, "second_quote_note", None),
                "practice_recommendation": getattr(result, "practice_recommendation", None),
                # Invariant 1: platform copy that accompanies a served clip but is
                # not the teacher's words. Rendered as its own block by the client
                # (chat `safety_notices`), never concatenated into the evidence body.
                "safety_notices": safety_notices,
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
        *,
        reason: str | None = None,
        answerability: str | None = None,
        error: str | None = None,
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
        # NEW-ANS-2 (ANS-010, RET-17): why the turn abstained. A check that could
        # not run is never reported as a pass (verification.passed=False) and is
        # counted as an error, not as "no teaching found". D-PQ9 (2026-11-07): its
        # copy asks the seeker to try again.
        from app.answer_contract import abstain_cause, abstain_copy_key

        cause = abstain_cause(status, reason, answerability, error)
        if compassion and cause != "system_unavailable":
            cause = "safety"
        try:
            from app.metrics import ABSTAIN_CAUSE_TOTAL

            ABSTAIN_CAUSE_TOTAL.labels(cause=cause).inc()
        except (ImportError, ValueError) as exc:  # telemetry never breaks a response
            logger.debug("abstain cause not counted: %s", type(exc).__name__)
        if compassion:
            answer = _distress_compassion_framing(ctx)
            from services.crisis_helplines import ensure_support_line

            answer = ensure_support_line(answer)
            method = "first_person_distress_compassion"
        elif status == "error":
            answer = "I couldn't reach my teaching library just now. Please try again in a moment."
            method = "first_person_store_unavailable"
        elif cause == "system_unavailable":
            # D-PQ9 (owner decision 2026-11-07): a check that could not run (for
            # example a scorer timeout) is a failure, not an absence of teaching.
            answer = (
                "I couldn't finish checking the teachings for this question just now. "
                "Please try again in a moment."
            )
            method = "first_person_check_unavailable"
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
            from services.crisis_helplines import ensure_support_line

            _support = ensure_support_line("")
            _after = [b for b in boundaries if b != _support]
            if _support in boundaries and _support not in answer:
                # The human support line leads: someone staring at a bottle of pills should
                # not read "try rephrasing" first (2026-10-31 review of ua70 / ua71).
                answer = _support + "\n\n" + answer
            if _after:
                answer = answer + "\n\n" + "\n\n".join(_after)

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
        elif (
            getattr(ctx, "is_indic", False)
            and static
            and status != "error"
            and cause != "system_unavailable"  # D-PQ9: that copy says "no teaching"
            and not boundaries
        ):
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
            citations_verified=False,
            verification={
                "passed": cause != "system_unavailable",
                "method": method,
                "citations_verified": False,
                "abstain_cause": cause,
            },
            release_manifest=get_release_manifest().to_dict(),
            route_metadata={
                "route_decision": "first_person_abstain",
                "requested_variant": "first_person",
                "selected_variant": "no_match_abstain",
                "decision_method": method,
                "decline_status": status or "unknown",
                "abstain_cause": cause,
                "corpus_version": str(getattr(settings, "first_person_corpus_version", "") or ""),
                "abstain_reason": str(reason) if reason else None,
                "abstain_copy_key": abstain_copy_key(cause),
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


async def fail_closed_result(ctx: PipelineContext, method: str) -> PipelineResult:
    """T1-05: the static abstain for a teaching-lane turn FP could not serve.

    ``method`` is ``fp_disabled`` (kill switch) or ``fp_node_error`` (node
    fault). Reuses the bridge's static abstain, then marks it as a failed
    (not passed) verification so it is never counted as a grounded answer.
    """
    import dataclasses

    from services.fp_fail_closed import record_fail_closed

    record_fail_closed(method)
    base = await FirstPersonBridgeStage()._abstain(ctx, method, reason="serving_contract_violation")
    metadata = dict(base.route_metadata or {})
    metadata["decision_method"] = method
    return dataclasses.replace(
        base,
        verification={
            "passed": False,
            "method": method,
            "citations_verified": False,
            "abstain_cause": "system_unavailable",
        },
        route_metadata=metadata,
    )
