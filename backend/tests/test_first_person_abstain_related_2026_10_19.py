"""A25 (2026-10-19) — abstain "related clips" backend half (flag-gated, OFF by default).

Measured defect this closes: a live sweep of 150 benign on-topic gold questions served a
teacher clip for only 24 (16%); 107 abstained, dominated by ``relevance_below_min`` (65) and
``answerability_withheld`` (43). When
``first_person_abstain_related_clips_enabled`` is ON, an abstain whose candidates were
integrity-verified but scored below the relevance minimum additionally carries a bounded
``related_clips`` offer — explicitly related, never an answer — each with the served path's
full-talk URL and attribution and a deterministic topic list. Out-of-scope / blocked / crisis
turns still abstain with nothing. When the flag is OFF the abstain payload is byte-identical
to before the feature.

Boundaries this file locks:
  * ``FirstPersonPipelineResult.to_dict()`` gains ``related_clips`` ONLY when non-empty.
  * ``_relate`` helpers reuse the served path's ``_build_citation_dict`` + the repo's
    ``resolve_attribution_label`` (``route_gated=True``), so an unverified clip can never be
    upgraded to a teacher name (L-NO-INVENTED-CREDIT-1 / L-FP-HYBRID-SCAFFOLD-1).
  * The bridge rides the list on ``route_metadata`` only; it never becomes a citation and
    never changes the abstain text.

Everything runs against mocked stores/pipelines: no Qdrant, no Neo4j, no LLM network calls.
"""

from __future__ import annotations

import hashlib
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import services.first_person_pipeline as fpp
from app.config import settings
from app.orchestrator_utils import _TRANSLATION_CACHE
from app.pipeline.stages import first_person_bridge as bridge_module
from app.pipeline.stages.context import PipelineContext
from app.pipeline.stages.first_person_bridge import FirstPersonBridgeStage
from services.first_person_pipeline import (
    _RELATED_CLIPS_CAP,
    FirstPersonPipeline,
    FirstPersonPipelineResult,
    _build_citation_dict,
    _build_related_clip,
    _clip_topics,
    _related_clips_for,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

# Long enough to pass the content-quality gate when that gate is left on, and it
# names a canonical concept ("Suffering") so the deterministic topic list is testable.
_CLIP_TEXT = (
    "Suffering is resistance to what is, and the body holds every resistance it has "
    "ever met until you meet it with awareness and let the breath soften the place "
    "that is holding on."
)
_CLIP_TEXT_HASH = hashlib.sha256(_CLIP_TEXT.encode("utf-8")).hexdigest()


def _clip(**overrides) -> dict:
    """A minimal stored clip payload with the keys ``_build_citation_dict`` reads."""
    base = {
        "point_id": "abc123@99s",
        "video_id": "abc123",
        "start_ms": 99_000,
        "end_ms": 129_000,
        "speaker": "Sri Preethaji",
        "teacher_id": "preethaji",
        "transcript_hash": _CLIP_TEXT_HASH,
        "verbatim_text": _CLIP_TEXT,
        "channel": "Preethaji Channel",
        "passage_dense": [1.0, 0.0],
        "caption_status": "auto_transcript",
    }
    base.update(overrides)
    return base


@pytest.fixture
def flag_on(monkeypatch):
    monkeypatch.setattr(settings, "first_person_abstain_related_clips_enabled", True)
    return True


@pytest.fixture
def flag_off(monkeypatch):
    monkeypatch.setattr(settings, "first_person_abstain_related_clips_enabled", False)
    return False


# --- bridge fixtures (mirror tests/test_first_person_bridge.py; that file is not edited) ---

_ANSWER = (
    "Sri Preethaji addresses this directly in her discourse on the nature of consciousness:\n\n"
    "**Sri Preethaji** · [The Nature of Consciousness]"
    "(https://www.youtube.com/watch?v=abc123&t=99s)\n\n"
    f"{_CLIP_TEXT}\n\n"
    "---\n\n"
    "*Where does resistance show up in the body right now?*"
)


def _clip_citation(**overrides) -> dict:
    citation = {
        "point_id": "abc123@99s",
        "video_id": "abc123",
        "start_ms": 99_000,
        "end_ms": 129_000,
        "timestamp_seconds": 99,
        "speaker": "Sri Preethaji",
        "teacher_id": "preethaji",
        "transcript_hash": _CLIP_TEXT_HASH,
        "verbatim_text": _CLIP_TEXT,
        "text_snippet": _CLIP_TEXT,
        "source_url": "https://www.youtube.com/watch?v=abc123&t=99s",
        "video_url": "https://www.youtube.com/watch?v=abc123",
        "confidence": 0.71,
        "is_verbatim": True,
        "provenance_kind": "speech_turn_clip",
        "caption_status": "auto_transcript",
    }
    citation.update(overrides)
    return citation


def _bridge_result(
    *,
    status: str = "success",
    is_direct: bool = True,
    related_clips: list | None = None,
    answer: str = _ANSWER,
    citations: list | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        answer_text=answer,
        citations=[_clip_citation()] if citations is None else citations,
        status=status,
        is_direct_answer=is_direct,
        latency_ms=42.0,
        cached=False,
        error=None,
        related_clips=related_clips,
        audio_playback_clip=None,
        audio_playback_clips=[],
        detected_concepts=[],
        atma_vichara_inquiry=None,
        practice_recommendation=None,
    )


def _container(*, block_output: bool = False) -> MagicMock:
    container = MagicMock()
    container.guardrails = AsyncMock()
    container.guardrails.check_output.return_value = {
        "blocked": block_output,
        "reason": "phrase" if block_output else None,
    }
    container.embedding = AsyncMock()
    container.embedding.encode_single_full_async.return_value = {
        "dense": [0.0] * int(settings.embedding_dimension),
        "sparse": {},
    }
    container.serene_mind = None
    container.translation = None
    return container


def _ctx(
    container,
    *,
    msg: str = "how do I find inner peace?",
    lang: str = "en",
    is_indic: bool = False,
) -> PipelineContext:
    return PipelineContext(
        container=container,
        coordinator=MagicMock(),
        request=MagicMock(),
        user_msg=msg,
        preferred_lang=lang,
        is_indic=is_indic,
        trace_id="trace-related-test",
        start_time=time.time(),
        state={"user_msg_en": msg},
    )


def _strip_volatile(route_metadata: dict) -> dict:
    """Route metadata minus the only per-run volatile field (routing timestamps)."""
    clone = dict(route_metadata)
    chain = clone.get("routing_chain")
    if isinstance(chain, list):
        clone["routing_chain"] = [{k: v for k, v in e.items() if k != "timestamp"} for e in chain]
    return clone


@pytest.fixture(autouse=True)
def _bridge_gates(monkeypatch):
    """The stage's own gates on, and a clean glue-translation cache."""
    monkeypatch.setattr(settings, "first_person_chat_bridge_enabled", True)
    monkeypatch.setattr(settings, "first_person_route_enabled", True)
    monkeypatch.setattr(settings, "first_person_mode", "retrieval_only")
    _TRANSLATION_CACHE.clear()


@pytest.fixture
def fp_pipeline(monkeypatch):
    """Patch the stage's pipeline lookup with a mocked FirstPersonPipeline."""
    pipeline = MagicMock()
    pipeline.execute = MagicMock(return_value=_bridge_result())
    monkeypatch.setattr(bridge_module, "_fp_pipeline", lambda container: pipeline)
    return pipeline


# ---------------------------------------------------------------------------
# Config — the flag exists and is OFF by default (production-safe flip)
# ---------------------------------------------------------------------------


def test_flag_defaults_off_and_is_declared():
    """Breaks if the flag name changes, is removed, or its default flips to ON:
    an accidental ON would add the related-clips block to every abstain payload."""
    from app.config import Settings

    assert "first_person_abstain_related_clips_enabled" in Settings.model_fields
    assert Settings.model_fields["first_person_abstain_related_clips_enabled"].default is False


# ---------------------------------------------------------------------------
# Pipeline helpers — bounded, not-an-answer, served-path URL + attribution
# ---------------------------------------------------------------------------


def test_flag_off_yields_no_related_clips(flag_off):
    """Breaks if the flag guard is removed or its default flips: with the feature off
    ``_related_clips_for`` must return nothing so the abstain payload is unchanged."""
    assert _related_clips_for([_clip()]) == []


def test_flag_on_builds_bounded_entries_marked_related_not_answer(flag_on):
    """Breaks if the cap changes, or if an entry ever claims to be the answer:
    the offer must stay bounded and every entry must be related / not-an-answer."""
    clips = [_clip(point_id=f"p{i}", video_id=f"vid{i}") for i in range(5)]
    out = _related_clips_for(clips)

    assert len(out) == _RELATED_CLIPS_CAP == 3
    for entry in out:
        assert entry["related"] is True
        assert entry["is_answer"] is False
        assert entry["label"] == "Related, not a direct answer"
        assert isinstance(entry["full_talk_url"], str)
        assert entry["full_talk_url"].startswith("https://")


def test_full_talk_url_is_the_served_path_derivation(flag_on):
    """Breaks if the full-talk URL is re-implemented or drifts from the served path:
    it must equal ``_build_citation_dict``'s ``video_url`` (no t= offset)."""
    clip = _clip()
    served = _build_citation_dict(clip, 0.7, "speech_turn_clip")
    entry = _build_related_clip(clip, 0.7)

    assert entry is not None
    assert entry["full_talk_url"] == served["video_url"] == "https://www.youtube.com/watch?v=abc123"
    # The clip-precise URL is still available, separately, with the offset.
    assert entry["url"] == served["url"] == "https://www.youtube.com/watch?v=abc123&t=99s"


def test_unverified_clip_is_never_upgraded_to_a_teacher_name(flag_on):
    """L-NO-INVENTED-CREDIT-1 / L-FP-HYBRID-SCAFFOLD-1: breaks if an unverified clip's
    bare ``speaker`` is surfaced or its attribution is not the shared-channel label."""
    entry = _build_related_clip(_clip(speaker_verified=False), 0.7)

    assert entry is not None
    assert entry["speaker"] is None
    assert entry["speaker_verified"] is False
    assert entry["attribution"] == "shared in Preethaji Channel"


def test_verified_clip_keeps_the_teacher_name(flag_on):
    """Breaks the opposite way: a voice-verified clip must keep its real speaker,
    matching the served path's ``route_gated=True`` attribution. Verified means
    the recorded method, not just the flag (P1-5)."""
    entry = _build_related_clip(
        _clip(speaker_verified=True, voice_verification_method="ecapa_anchor_v1"), 0.7
    )

    assert entry is not None
    assert entry["speaker"] == "Sri Preethaji"
    assert entry["speaker_verified"] is True
    assert entry["attribution"] == "Sri Preethaji"


def test_unknown_channel_unverified_clip_reads_unverified_clip(flag_on):
    """Breaks if the no-channel case invents a channel: an unverified clip with no known
    channel must read the repo's ``unverified clip`` label, and name nobody."""
    entry = _build_related_clip(_clip(speaker_verified=False, channel=None), 0.7)

    assert entry is not None
    assert entry["speaker"] is None
    assert entry["attribution"] == "unverified clip"


def test_damaged_clip_is_dropped_not_fabricated(flag_on):
    """Breaks if a clip missing required stored fields is shown anyway: it must be
    dropped (returns None) rather than rendered with invented text or a bad URL."""
    damaged = {k: v for k, v in _clip().items() if k != "start_ms"}
    assert _build_related_clip(damaged, 0.7) is None
    # And the list builder skips the damaged one, keeping the healthy siblings.
    out = _related_clips_for([damaged, _clip(point_id="ok")])
    assert [e["point_id"] for e in out] == ["ok"]


def test_scores_override_the_payload_score(flag_on):
    """Breaks if the caller's relevance scores are ignored: the entry confidence must
    come from the scores list the abstain path computed, not the stored payload."""
    clip = _clip(score=0.1)
    out = _related_clips_for([clip], [0.9])
    assert out[0]["confidence"] == pytest.approx(0.9)


def test_topics_are_deterministic_and_from_stored_data(flag_on):
    """Breaks if topics are invented or an LLM is introduced: topics must come only
    from the clip's own stored tags/labels/text, deduped and bounded."""
    clip = _clip(tags=["Suffering", "suffering", "Awareness"], okf_title="On Resistance")
    topics = _clip_topics(clip)

    assert topics[0] == "Suffering"  # first-seen order, case-insensitively deduped
    assert topics.count("suffering") == 0  # the lower-case duplicate is dropped
    assert "Awareness" in topics
    assert "On Resistance" in topics
    assert len(topics) <= 4
    # Same input, same output — no hidden state or model call.
    assert _clip_topics(clip) == topics


def test_canonical_concepts_matched_from_stored_text(flag_on):
    """Breaks if the canonical vocabulary is not matched against the clip text:
    the stored verbatim text names "Suffering", which must surface as a topic."""
    assert "Suffering" in _clip_topics(_clip())


# ---------------------------------------------------------------------------
# Result serialization — key only when non-empty (flag-off parity)
# ---------------------------------------------------------------------------


def test_to_dict_omits_related_clips_when_empty():
    """Breaks if ``to_dict`` always emits the key: an empty offer must leave the
    serialized result byte-identical to before the feature."""
    res = FirstPersonPipelineResult(
        answer_text="x",
        citations=[],
        status="abstained",
        is_direct_answer=False,
        latency_ms=1.0,
    )
    assert res.related_clips == []
    assert "related_clips" not in res.to_dict()


def test_to_dict_includes_related_clips_when_present():
    """Breaks if a non-empty offer is dropped from serialization: the list must be
    present under the ``related_clips`` key exactly as built."""
    entry = _build_related_clip(_clip(), 0.7)
    res = FirstPersonPipelineResult(
        answer_text="x",
        citations=[],
        status="abstained",
        is_direct_answer=False,
        latency_ms=1.0,
        related_clips=[entry],
    )
    assert res.to_dict()["related_clips"] == [entry]


# ---------------------------------------------------------------------------
# Bridge — flag OFF is byte-identical, even against adversarial candidates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_abstain_flag_off_ignores_candidates_and_is_byte_identical(fp_pipeline, monkeypatch):
    """Breaks if the bridge leaks candidates when the feature is off: with the flag
    off, the abstain payload must ignore any ``related_clips`` on the result and
    equal the payload produced with no candidates at all."""
    monkeypatch.setattr(settings, "first_person_llm_fallback_enabled", False)
    monkeypatch.setattr(settings, "first_person_serve_weak_match", False)
    monkeypatch.setattr(settings, "first_person_abstain_related_clips_enabled", False)

    # Baseline: result carries no related clips.
    fp_pipeline.execute.return_value = _bridge_result(status="abstained", is_direct=False)
    baseline = await FirstPersonBridgeStage().run(_ctx(_container()))

    # Adversarial: result DOES carry candidates, but the flag is off.
    entry = _build_related_clip(_clip(), 0.7)
    fp_pipeline.execute.return_value = _bridge_result(
        status="abstained", is_direct=False, related_clips=[entry]
    )
    with_candidates = await FirstPersonBridgeStage().run(_ctx(_container()))

    assert baseline is not None and with_candidates is not None
    assert _strip_volatile(baseline.route_metadata) == _strip_volatile(
        with_candidates.route_metadata
    )
    for key in (
        "related_clips",
        "related_topics",
        "related_clips_heading",
        "ask_faculty_available",
        "ask_faculty_prompt",
    ):
        assert key not in with_candidates.route_metadata


# ---------------------------------------------------------------------------
# Bridge — flag ON adds the offer to a below-min abstain only
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_abstain_flag_on_carries_related_clips_and_faculty_affordance(
    fp_pipeline, monkeypatch
):
    """Breaks if the flag-on abstain does not surface the offer: the route metadata
    must carry the clips, the shared heading vocabulary, the deduped topics, and the
    faculty affordance boolean + prompt — with no citations and unchanged text."""
    monkeypatch.setattr(settings, "first_person_llm_fallback_enabled", False)
    monkeypatch.setattr(settings, "first_person_serve_weak_match", False)
    monkeypatch.setattr(settings, "first_person_abstain_related_clips_enabled", True)

    related = [
        _build_related_clip(_clip(tags=["Suffering"]), 0.7),
        _build_related_clip(_clip(point_id="p2", tags=["Presence"]), 0.6),
    ]
    fp_pipeline.execute.return_value = _bridge_result(
        status="abstained", is_direct=False, related_clips=related
    )

    result = await FirstPersonBridgeStage().run(_ctx(_container()))

    assert result is not None
    assert result.route_decision == "first_person_abstain"
    assert result.citations == []
    meta = result.route_metadata
    assert meta["related_clips"] == related
    assert meta["related_clips_heading"] == "Related, not a direct answer"
    assert set(meta["related_topics"]) == {"Suffering", "Presence"}
    assert meta["ask_faculty_available"] is True
    assert isinstance(meta["ask_faculty_prompt"], str) and meta["ask_faculty_prompt"].strip()
    # The abstain text itself is untouched.
    assert "verified verbatim teaching" in result.final_answer


@pytest.mark.asyncio
async def test_abstain_status_without_candidates_carries_no_offer(fp_pipeline, monkeypatch):
    """Breaks if the bridge fabricates an offer: a below-min/blocked/withheld abstain
    whose result carries no candidates (the pipeline attaches none on those paths)
    must ride the payload with nothing related."""
    monkeypatch.setattr(settings, "first_person_llm_fallback_enabled", False)
    monkeypatch.setattr(settings, "first_person_serve_weak_match", False)
    monkeypatch.setattr(settings, "first_person_abstain_related_clips_enabled", True)

    fp_pipeline.execute.return_value = _bridge_result(
        status="abstained", is_direct=False, related_clips=[]
    )
    result = await FirstPersonBridgeStage().run(_ctx(_container()))

    assert result is not None
    assert result.route_metadata.get("related_clips") is None
    assert "ask_faculty_available" not in result.route_metadata


@pytest.mark.asyncio
async def test_serving_turn_never_carries_related_clips(fp_pipeline, monkeypatch):
    """Breaks if the offer bleeds into a served turn: even with adversarial candidates
    on the result, a direct serve must be a normal bridge answer with no related block."""
    monkeypatch.setattr(settings, "first_person_abstain_related_clips_enabled", True)
    entry = _build_related_clip(_clip(), 0.7)
    fp_pipeline.execute.return_value = _bridge_result(
        status="success", is_direct=True, related_clips=[entry]
    )

    result = await FirstPersonBridgeStage().run(_ctx(_container()))

    assert result is not None
    assert result.route_decision == "first_person_bridge"
    assert _CLIP_TEXT in result.final_answer
    assert "related_clips" not in result.route_metadata
    assert "ask_faculty_available" not in result.route_metadata


@pytest.mark.asyncio
async def test_crisis_redirect_with_candidates_still_falls_through(fp_pipeline, monkeypatch):
    """Safety carve-out: breaks if a crisis turn is converted into an abstain offer.
    ``crisis_redirect`` must keep flowing to distress handling with nothing served."""
    monkeypatch.setattr(settings, "first_person_llm_fallback_enabled", False)
    monkeypatch.setattr(settings, "first_person_abstain_related_clips_enabled", True)
    entry = _build_related_clip(_clip(), 0.7)
    fp_pipeline.execute.return_value = _bridge_result(
        status="crisis_redirect", is_direct=False, related_clips=[entry]
    )

    assert await FirstPersonBridgeStage().run(_ctx(_container())) is None


# ---------------------------------------------------------------------------
# Pipeline execute() — candidates are attached ONLY on the below-min relevance path
# ---------------------------------------------------------------------------


@pytest.fixture
def _toy_config(monkeypatch):
    """Content-quality off for short toy clips; answerability off (no LLM worker);
    non-speculative path. Mirrors tests/test_first_person_pipeline.py."""
    monkeypatch.setattr(settings, "first_person_content_quality_gate_enabled", False)
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", False)
    monkeypatch.setattr(settings, "first_person_speculative_parallelism_enabled", False)
    monkeypatch.setattr(settings, "first_person_serve_weak_match", False)


@pytest.fixture
def _mock_store():
    store = MagicMock()
    store.collection = "first_person_v1"
    return store


@pytest.fixture
def _mock_redis():
    redis = MagicMock()
    redis.get.return_value = None
    return redis


def _below_min_relevance(monkeypatch):
    """Force the relevance gate to reject the candidates (below-min abstain)."""
    monkeypatch.setattr(fpp, "_relevance_select", lambda *a, **k: None)


def test_execute_below_min_relevance_offers_verified_candidates(
    _toy_config, _mock_store, _mock_redis, monkeypatch, flag_on
):
    """Breaks if the candidates are discarded at the below-min return: with the flag
    on, the abstain must carry the verified candidates as explicit related clips."""
    _mock_store.search_hybrid.return_value = [_clip(), _clip(point_id="p2", video_id="vid2")]
    _below_min_relevance(monkeypatch)

    res = FirstPersonPipeline(store=_mock_store, redis_client=_mock_redis).execute(
        query="What is suffering?", query_dense_vector=[1.0, 0.0]
    )

    assert res.status == "abstained"
    assert res.abstain_reason == "relevance_below_min"
    assert res.citations == []
    assert len(res.related_clips) == 2
    assert all(e["related"] is True and e["is_answer"] is False for e in res.related_clips)
    assert all(str(e["full_talk_url"]).startswith("https://") for e in res.related_clips)
    assert res.to_dict()["related_clips"] == res.related_clips


def test_execute_below_min_relevance_flag_off_offers_nothing(
    _toy_config, _mock_store, _mock_redis, monkeypatch, flag_off
):
    """Breaks if the pipeline computes/stores candidates when the flag is off: the
    same below-min abstain must be empty and omit the serialized key entirely."""
    _mock_store.search_hybrid.return_value = [_clip()]
    _below_min_relevance(monkeypatch)

    res = FirstPersonPipeline(store=_mock_store, redis_client=_mock_redis).execute(
        query="What is suffering?", query_dense_vector=[1.0, 0.0]
    )

    assert res.abstain_reason == "relevance_below_min"
    assert res.related_clips == []
    assert "related_clips" not in res.to_dict()


def test_execute_blocked_topic_never_offers_related_clips(
    _toy_config, _mock_store, _mock_redis, flag_on
):
    """Out-of-scope carve-out: breaks if a blocked-topic abstain carries an offer.
    The topic rail returns before retrieval, so there are no candidates by design."""
    _mock_store.search_hybrid.return_value = [_clip()]

    res = FirstPersonPipeline(store=_mock_store, redis_client=_mock_redis).execute(
        query="should I invest in bitcoin?", query_dense_vector=[1.0, 0.0]
    )

    assert res.abstain_reason == "topic_blocked"
    assert res.related_clips == []
    _mock_store.search_hybrid.assert_not_called()


def test_execute_no_verified_clips_never_offers_related_clips(
    _toy_config, _mock_store, _mock_redis, flag_on
):
    """Integrity carve-out: breaks if a quarantined (tampered) clip is offered as
    related. Integrity-failed clips must never be shown, even marked related."""
    _mock_store.search_hybrid.return_value = [_clip(transcript_hash="0" * 64)]

    res = FirstPersonPipeline(store=_mock_store, redis_client=_mock_redis).execute(
        query="What is suffering?", query_dense_vector=[1.0, 0.0]
    )

    assert res.status == "abstained"
    assert res.abstain_reason == "no_verified_clips"
    assert res.related_clips == []
