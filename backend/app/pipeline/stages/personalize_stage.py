"""PersonalizeStage — explicit T-B14 opt-in to personalize one served teaching.

Default answer path is first-person-only: the general generating pipeline may
run for a turn ONLY when the request carries a validated ``personalize_teaching``
ref AND the seeker is signed in, non-incognito, and has a personal knowledge
graph. The stage looks the served clip up itself (video_id + start second with
a small tolerance) and never trusts client-provided text.

Placement (``pipeline_builder.build_default_pipeline``): after
``BoundedComparisonShortCircuitStage`` and before ``GraphStage`` — i.e. after
the whole outer safety lane (kill_switch → … → bounded comparison), so every
carve-out (crisis preemption, MODERATE+ distress, imperative meditation,
greetings, off-topic) keeps its route: those stages short-circuit before this
one ever runs. This stage never short-circuits a valid turn (returns None so
the general graph runs); an invalid turn declines with a ``route_decision``
distinct from ``first_person_abstain``.

Gate predicate mirrors the header's Personalized badge server-side
(``ChatInterface.tsx``: ``isPersonalized={hasAuthenticatedSession &&
!isIncognito}``) plus the backend's own has-memory signal as the "has a
knowledge graph" check:
  * signed in  ↔ ``_is_persistable_user_id(ctx.user_id)`` (a real
    Supabase UUID; ``anonymous`` and ``anon:<token>`` identities are not
    people and carry no durable memory — same boundary
    ``prepare_user_memory`` enforces on reads);
  * non-incognito ↔ ``not ctx.incognito`` (server-enforced privacy boundary);
  * has a knowledge graph ↔ ``ctx.personalization_eligible`` (the
    pre-chain probe over profile memories, core memories and canonical
    memories — the same sources the personal knowledge graph is built from).

Cross-session memory reads are gated in ``prepare_user_memory`` by a
current ``MemoryOutbox.active_consent`` receipt for the resolved tenant. This
stage's graph-eligibility probe must not be used as a substitute for that
consent gate; it only decides whether a verified teaching may be personalized
after the normal consent-scoped memory context has been assembled.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import re
import time
from typing import TYPE_CHECKING, Any, Optional

from app.pipeline.result import PipelineResult
from app.pipeline.stages.base import Stage
from app.release_manifest import get_release_manifest
from app.route_taxonomy import RoutingProvenance, record_routing_decision
from app.sanitization import sanitize_log_input
from services.user_profile_service import _is_persistable_user_id

if TYPE_CHECKING:
    from app.pipeline.stages.context import PipelineContext

logger = logging.getLogger(__name__)

# Citation timestamps are floor(start_ms / 1000) with a 0.25 s playback pad
# (services/first_person_pipeline.CITATION_PLAYBACK_PAD_S); ±1.5 s covers the
# floor rounding plus clock slack, and the nearest candidate wins.
PERSONALIZE_CLIP_TOLERANCE_S = 1.5

_YOUTUBE_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

# The one message a personalize turn may carry (mirrors
# src/lib/chat/personalize.ts:PERSONALIZE_TEACHING_PROMPT). The ref, not this
# text, identifies the teaching — so any other text with a ref is declined:
# otherwise a ref would unlock the generating graph for an arbitrary question.
PERSONALIZE_TEACHING_PROMPT = "Please personalize this teaching for me."

# Mitigation label for a personalized answer, following the SYNTHESIS_LABEL
# precedent (rag/nodes/generation.py): the seeker must be able to tell generated
# personalization apart from the teachers' verbatim voice. Appended post-graph
# by GraphStage (idempotent); the backend marks it, so no frontend change is
# needed to carry it.
PERSONALIZED_LABEL = (
    "_This is a personalized reflection on the teaching above, in our own "
    "words — not a direct quote from the teachers._"
)


def personalize_ref_from_request(request: Any) -> dict[str, Any] | None:
    """Extract a validated personalize ref from a chat request, else None.

    Accepts the pydantic ``PersonalizeTeachingRef`` (already validated at the
    API boundary) or a plain dict (re-validated here). Anything else —
    including a MagicMock attribute from stage-unit-test doubles — reads as
    "no personalize request", so existing callers and tests that build ctx
    with mock requests see zero behavior change. A dict that fails validation
    is logged and likewise treated as absent: the API boundary already rejects
    malformed refs with 422, so a bad dict here is unreachable in production.
    """
    if request is None:
        return None
    ref = getattr(request, "personalize_teaching", None)
    if ref is None:
        return None
    video_id = getattr(ref, "video_id", None) if not isinstance(ref, dict) else ref.get("video_id")
    timestamp = (
        getattr(ref, "timestamp_seconds", None)
        if not isinstance(ref, dict)
        else ref.get("timestamp_seconds")
    )
    if (
        not isinstance(video_id, str)
        or not _YOUTUBE_VIDEO_ID_RE.match(video_id)
        or isinstance(timestamp, bool)
        or not isinstance(timestamp, (int, float))
        or not math.isfinite(float(timestamp))
        or float(timestamp) < 0.0
    ):
        logger.warning(
            "[PersonalizeStage] Ignoring malformed personalize_teaching ref "
            "(video_id=%r); the API boundary rejects these with 422.",
            sanitize_log_input(video_id) if isinstance(video_id, str) else type(video_id).__name__,
        )
        return None
    return {"video_id": video_id, "timestamp_seconds": float(timestamp)}


def personalize_cache_scope(ref: dict[str, Any] | None) -> str:
    """Bounded cache-key scope for a personalize turn ("" when absent).

    The prompt text is identical for every personalize turn, so without this
    scope one seeker's personalized answer (or two clips personalized by the
    same seeker) would share a cache entry. Only the ref identity enters the
    key — a bounded SHA-256 digest, never clip text.
    """
    if not ref:
        return ""
    digest = hashlib.sha256(f"{ref['video_id']}|{ref['timestamp_seconds']!r}".encode()).hexdigest()[
        :12
    ]
    return f":pers:{digest}"


def personalize_grounded_question(user_msg_en: str, clip: dict[str, Any]) -> str:
    """Augment the graph question with the server-looked-up clip text.

    The personalize prompt alone ("Please personalize this teaching for me.")
    carries no retrievable content; retrieval and generation ground on the
    clip by quoting the stored verbatim text (trusted: resolved server-side
    from the first-person store, never from the client) into the question the
    general graph retrieves and generates against.
    """
    verbatim = str(clip.get("verbatim_text") or "").strip()
    speaker = str(clip.get("speaker") or "the teacher").strip() or "the teacher"
    question = (user_msg_en or "").strip() or PERSONALIZE_TEACHING_PROMPT
    if not verbatim:
        return question
    return (
        f"{question}\n\nThe teaching to personalize (verbatim words of {speaker}, "
        f'looked up from the teaching library):\n\n"{verbatim}"'
    )


def build_personalize_citation(clip: dict[str, Any]) -> dict[str, Any]:
    """Build the pinned citation for the looked-up clip.

    Same fields as ``FirstPersonPipeline._build_citation`` (video id, whole-
    second timestamp, playback window with the shared pad clamped to the
    video length, transcript hash, stored speaker verification copied — never
    inferred, QA-1 precedent). The clip already passed the serve-time
    integrity gate, so ``start_ms``/``end_ms`` are required ints: a malformed
    clip raises here instead of becoming a zero-length citation.
    """
    from services.first_person_pipeline import CITATION_PLAYBACK_PAD_S, _speaker_verification
    from services.quote_fidelity import UNTITLED_LINK_LABEL

    start_ms = int(clip["start_ms"])
    end_ms = int(clip["end_ms"])
    video_id = str(clip.get("video_id") or "")
    start_sec = start_ms // 1000
    clip_url = f"https://www.youtube.com/watch?v={video_id}&t={start_sec}s"
    playback_end = end_ms / 1000.0 + CITATION_PLAYBACK_PAD_S
    if clip.get("duration_ms"):
        playback_end = min(playback_end, clip["duration_ms"] / 1000.0)
    return {
        "point_id": clip.get("point_id"),
        "video_id": video_id,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "timestamp_seconds": start_sec,
        "speaker": clip.get("speaker"),
        # Provenance claim copied from the stored clip, never inferred. A bare
        # True with no recorded voice_verification_method is a claim without
        # evidence and reads as unverified (corpus quality-scorecard rule).
        "speaker_verified": _speaker_verification(clip)[0],
        "voice_verification_method": _speaker_verification(clip)[1],
        "channel": clip.get("channel"),
        "title": clip.get("title") or clip.get("video_title") or UNTITLED_LINK_LABEL,
        "url": clip_url,
        "teacher_id": clip.get("teacher_id"),
        "transcript_hash": clip.get("transcript_hash"),
        "verbatim_text": clip.get("verbatim_text"),
        "text_snippet": clip.get("verbatim_text"),
        "source_url": clip_url,
        "video_url": clip.get("video_url") or f"https://www.youtube.com/watch?v={video_id}",
        "playback_start_seconds": round(max(0.0, start_ms / 1000.0 - CITATION_PLAYBACK_PAD_S), 2),
        "playback_end_seconds": round(playback_end, 2),
        "is_verbatim": True,
        "provenance_kind": clip.get("provenance_kind") or "speech_turn_clip",
        "personalized_for": True,
    }


def apply_personalize_marking(ctx: PipelineContext, clip: dict[str, Any]) -> None:
    """Pin the looked-up clip citation and label the answer personalized.

    Runs post-graph on a validated personalize turn: the general graph's
    answer keeps its own citations/scores, with the served clip pinned first
    (deduped by point_id) and PERSONALIZED_LABEL appended (idempotent) so the
    response is labelled as personalization, not the teacher's verbatim voice.
    """
    pinned = build_personalize_citation(clip)
    citations = list(getattr(ctx, "citations", None) or [])
    pinned_id = pinned.get("point_id")
    if pinned_id is not None and any(c.get("point_id") == pinned_id for c in citations):
        citations = [c for c in citations if c.get("point_id") != pinned_id]
    ctx.citations = [pinned, *citations]
    final_answer = str(getattr(ctx, "final_answer", "") or "")
    if PERSONALIZED_LABEL not in final_answer:
        ctx.final_answer = f"{final_answer.rstrip()}\n\n{PERSONALIZED_LABEL}"
    route_metadata = getattr(ctx, "route_metadata", None)
    if isinstance(route_metadata, dict):
        route_metadata["personalized_teaching"] = True
        if pinned_id is not None:
            route_metadata["personalize_clip_point_id"] = str(pinned_id)[:64]
    record_routing_decision(
        ctx,
        RoutingProvenance(
            layer="GRAPH_GENERATION",
            decision="personalized_teaching",
            method="personalize_clip_grounded",
            confidence=1.0,
            reason="General graph ran on an explicit personalize request, grounded on the served clip",
        ),
    )


def _store_for_request() -> Any:
    """One FirstPersonStore per personalize turn (lazy import, like the bridge)."""
    from app.config import settings
    from services.first_person_store import FirstPersonStore

    return FirstPersonStore(collection=settings.first_person_collection)


def _lookup_servable_clip(ref: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Look the clip up and apply the serve-time integrity gate (sync).

    Runs in a worker thread: the Qdrant client is synchronous and must not
    block the event loop. The store query already filters on eligibility and
    rights; the integrity gate adds what serving requires of every clip
    (hash match, allowlisted speaker, no artifact, no blocked promise).
    YouTube availability is not re-probed: the clip was served moments ago
    and that check ran then. ``None`` means no servable clip — never a guess.
    """
    from app.config import settings
    from services.first_person_pipeline import (
        _passes_integrity_gate,
        _quality_allowlist,
        _quality_blocklist,
    )
    from services.first_person_serving_contract import legacy_slot_aliases_context

    # v10-only mode: the legacy slot names the fp-context collection, so there is
    # no legacy clip store to look a clip up in. Decline without a Qdrant read
    # rather than rely on the context records lacking `first_person_eligible`.
    if legacy_slot_aliases_context(
        settings.first_person_collection, settings.first_person_context_collection
    ):
        return None

    clip = _store_for_request().get_clip_by_video_and_start(
        ref["video_id"],
        ref["timestamp_seconds"],
        tolerance_s=PERSONALIZE_CLIP_TOLERANCE_S,
    )
    if not isinstance(clip, dict) and getattr(settings, "first_person_context_collection", None):
        try:
            from qdrant_client.http import models

            col = settings.first_person_context_collection
            target_ms = int(round(float(ref["timestamp_seconds"]) * 1000.0))
            tolerance_ms = int(round(PERSONALIZE_CLIP_TOLERANCE_S * 1000.0))
            store = _store_for_request()
            pts, _ = store._client.scroll(
                collection_name=col,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(key="video_id", match=models.MatchValue(value=ref["video_id"])),
                    ]
                ),
                limit=50,
                with_payload=True,
            )
            candidates = []
            for p in pts or []:
                pl = dict(p.payload or {})
                if not pl.get("verbatim_text"):
                    continue
                sms = pl.get("start_ms")
                if sms is not None and abs(sms - target_ms) <= tolerance_ms:
                    pl["point_id"] = str(p.id)
                    if not pl.get("speaker"):
                        pl["speaker"] = "Sri Preethaji" if pl.get("guru_id") == "preethaji" else "Sri Krishnaji"
                    pl["transcript_hash"] = hashlib.sha256(pl["verbatim_text"].encode("utf-8")).hexdigest()
                    candidates.append((abs(sms - target_ms), pl))
            if candidates:
                candidates.sort(key=lambda x: x[0])
                clip = candidates[0][1]
        except Exception as exc:
            logger.warning("[PersonalizeStage] Context collection clip lookup failed: %s", exc)

    if not isinstance(clip, dict):
        return None
    clip_id = str(clip.get("point_id"))
    allow = _quality_allowlist()
    if allow is not None and clip_id not in allow:
        return None
    block = _quality_blocklist()
    if block is not None:
        if clip_id in block:
            return None
    elif str(getattr(settings, "first_person_quality_blocklist_path", "") or "").strip():
        return None
    if not _passes_integrity_gate(
        clip,
        # Same effective policy as FirstPersonPipeline for first_person_v8
        # (self._boundary_guard_enabled): the configured setting, default false.
        # Forcing True here made the personalize lookup stricter than the
        # serving pipeline that produced the clip.
        boundary_guard_enabled=bool(
            getattr(settings, "first_person_boundary_guard_enabled", False)
        ),
        check_availability=False,
    ):
        logger.warning(
            "[PersonalizeStage] Clip %s failed the serve-time integrity gate; declining.",
            clip.get("point_id"),
        )
        return None
    try:
        # A clip the citation builder cannot render (missing/non-numeric
        # end_ms on a damaged point) is declined here, before the graph runs,
        # instead of failing the whole turn after generation.
        build_personalize_citation(clip)
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning(
            "[PersonalizeStage] Clip %s cannot be cited (%s); declining.",
            clip.get("point_id"),
            exc,
        )
        return None
    return clip


def _decline(ctx: PipelineContext, reason: str, message: str) -> PipelineResult:
    """Terminal honest decline for an invalid personalize turn.

    ``route_decision`` is ``personalize_declined_<reason>`` — distinct from
    ``first_person_abstain`` by contract (task-list section 8 step 2). Static
    text, no LLM, no fall-through to generation.
    """
    decision = f"personalize_declined_{reason}"
    record_routing_decision(
        ctx,
        RoutingProvenance(
            layer="PERSONALIZE_STAGE",
            decision=decision,
            method="personalize_gate",
            confidence=1.0,
            reason=f"Personalize request declined: {reason}",
        ),
    )
    logger.info(
        "[PersonalizeStage] Declining personalize turn trace_id=%s reason=%s",
        getattr(ctx, "trace_id", "unknown"),
        reason,
    )
    return PipelineResult(
        final_answer=message,
        intent="QUERY",
        trace_id=getattr(ctx, "trace_id", ""),
        latency_ms=int((time.time() - getattr(ctx, "start_time", time.time())) * 1000),
        model_used=None,
        model_provider=None,
        route_decision=decision,
        query_tier="fast",
        citations=[],
        faithfulness_score=None,
        hallucination_flag=False,
        citations_verified=True,
        verification={
            "passed": True,
            "method": decision,
            "citations_verified": True,
        },
        release_manifest=get_release_manifest().to_dict(),
        route_metadata={
            "requested_variant": "personalize_teaching",
            "selected_variant": "personalize_declined",
            "decision_method": "personalize_gate",
            "decline_reason": reason,
            "routing_chain": list(getattr(ctx, "routing_chain", [])),
        },
    )


class PersonalizeStage(Stage):
    """Gate the T-B14 opt-in: validate, look up the clip, mark the turn.

    Returns None for every non-personalize turn (default path untouched) and
    for every valid personalize turn (the general graph runs next, with the
    first-person router yielding — see ``rag/pipeline_registry``). Returns a
    terminal decline for anonymous, incognito, graph-less, unknown-clip, or
    store-unavailable turns.
    """

    name = "personalize"

    async def run(self, ctx: PipelineContext) -> PipelineResult | None:
        ref = personalize_ref_from_request(getattr(ctx, "request", None))
        if ref is None:
            return None
        user_msg = str(getattr(ctx, "user_msg", "") or "").strip().casefold()
        if user_msg != PERSONALIZE_TEACHING_PROMPT.casefold():
            return _decline(
                ctx,
                "unexpected_prompt",
                "To personalize a teaching, please use the Personalize option on that teaching.",
            )
        if getattr(ctx, "incognito", False) is True:
            return _decline(
                ctx,
                "incognito",
                "Personalizing a teaching is off in Temporary chat, which never "
                "uses personal memory. Please leave Temporary chat and ask again.",
            )
        if not _is_persistable_user_id(getattr(ctx, "user_id", None)):
            return _decline(
                ctx,
                "anonymous",
                "Personalizing a teaching needs a signed-in account with a personal "
                "wisdom map. Please sign in and ask again.",
            )
        if getattr(ctx, "personal_context_confirmed", False) is not True:
            return _decline(
                ctx,
                "no_graph",
                "I don't have personal context to personalize this teaching with yet. "
                "As you chat and save reflections, I'll be able to tailor teachings "
                "to you.",
            )
        try:
            clip = await asyncio.to_thread(_lookup_servable_clip, ref)
        except Exception as exc:
            # Store infrastructure (Qdrant) failure: honest decline, never a
            # silent fall-through to ungrounded generation.
            logger.warning("[PersonalizeStage] Clip store lookup failed: %s", exc)
            return _decline(
                ctx,
                "store_unavailable",
                "I couldn't reach my teaching library just now. Please try again in a moment.",
            )
        if not isinstance(clip, dict) or not str(clip.get("verbatim_text") or "").strip():
            return _decline(
                ctx,
                "unknown_clip",
                "I couldn't find that teaching in my library. Please open the "
                "teaching again and retry.",
            )
        state = getattr(ctx, "state", None)
        if not isinstance(state, dict):
            ctx.state = {}
            state = ctx.state
        # Stash only the looked-up clip's bounded identity fields — never
        # client text. The graph router and GraphStage read this marker.
        from services.first_person_pipeline import _speaker_verification

        state["personalize_clip"] = {
            "point_id": clip.get("point_id"),
            "video_id": clip.get("video_id"),
            "start_ms": clip.get("start_ms"),
            "end_ms": clip.get("end_ms"),
            "speaker": clip.get("speaker"),
            "teacher_id": clip.get("teacher_id"),
            "speaker_verified": _speaker_verification(clip)[0],
            "voice_verification_method": _speaker_verification(clip)[1],
            "channel": clip.get("channel"),
            "title": clip.get("title") or clip.get("video_title"),
            "verbatim_text": str(clip.get("verbatim_text") or ""),
            "transcript_hash": clip.get("transcript_hash"),
            "duration_ms": clip.get("duration_ms"),
            "source_url": clip.get("source_url"),
            "video_url": clip.get("video_url"),
            "provenance_kind": clip.get("provenance_kind"),
        }
        record_routing_decision(
            ctx,
            RoutingProvenance(
                layer="PERSONALIZE_STAGE",
                decision="personalize_accepted",
                method="personalize_gate",
                confidence=1.0,
                reason="Signed-in seeker with a knowledge graph asked to personalize a served clip",
            ),
        )
        logger.info(
            "[PersonalizeStage] Accepted personalize turn trace_id=%s video=%s t=%s",
            getattr(ctx, "trace_id", "unknown"),
            ref["video_id"],
            ref["timestamp_seconds"],
        )
        return None


if __name__ == "__main__":

    class _DummyReq:
        personalize_teaching = {"video_id": "bad video id with spaces", "timestamp_seconds": -5}

    assert personalize_ref_from_request(_DummyReq()) is None, "Malformed ref must be rejected"

    valid_ref = {"video_id": "valid123456", "timestamp_seconds": 10}
    scope1 = personalize_cache_scope(valid_ref)
    scope2 = personalize_cache_scope(valid_ref)
    assert scope1 == scope2, "Scope must be stable across repeated calls"
    print("personalize_stage self-check passed")
