"""Regression test suite for Guru Co-Identity and False Abstention Remediation.

Tests all four remediation tasks from the Teamwork Audit:
1. Guru Co-Identity: Sri Preethaji and Sri Krishnaji are husband and wife, co-teachers of Ekam.
   In this system, they are ONE COMMON GURU. Their co-occurrence is recognized as valid Ekam
   lineage and is NEVER flagged as cross_guru_contamination. External gurus (Sadhguru, Eckhart Tolle)
   remain distinct.
2. Antecedent Slicing in context harness: when middle span 1 or 2 hits, Span 0 is retained so
   antecedent context is never severed.
3. Standalone check: authentic oral discourse openings ("This is...", "It is...", "Because...")
   are allowed when part of a verified parent unit.
4. Calibration profile: conformal_direct_v1 profile loads successfully and unblocks is_direct
   evaluation.
"""

from __future__ import annotations

import pytest

from app.config import settings
from domain.first_person_context import (
    AnswerRole,
    BoundaryStatus,
    CompletenessStatus,
    HarnessDecision,
    ParentContext,
    ParentUnit,
    ProvenanceKind,
    SourceSpan,
    SpeakerRole,
    clip_text_hash,
    make_source_span_id,
)
from domain.first_person_evidence import EvidenceAction
from services.first_person_content_assessment import (
    AUTHENTIC_ORAL_OPENER_RE,
    assess_content,
)
from services.first_person_context_harness import (
    FirstPersonContextHarness,
    HarnessPolicy,
)
from services.first_person_evidence_policy import (
    FirstPersonEvidencePolicy,
    _context_standalone_problem,
    _standalone_problem,
    assess_guru_lineage,
    first_person_evidence_policy,
    is_ekam_coidentity,
)
from services.first_person_pipeline import load_calibration_profile
from services.first_person_serving_contract import (
    EKAM_COIDENTITY_GURU_IDS,
    is_ekam_coidentity as contract_is_ekam_coidentity,
    validate_guru_lineage as contract_validate_guru_lineage,
)


@pytest.fixture(autouse=True)
def _clean_test_env(monkeypatch):
    """Ensure clean runtime settings and authoritative licensing mock."""
    monkeypatch.setattr(settings, "first_person_chat_bridge_enabled", True)
    monkeypatch.setattr(settings, "first_person_route_enabled", True)
    monkeypatch.setattr(settings, "first_person_mode", "retrieval_only")
    monkeypatch.setattr(settings, "first_person_llm_fallback_enabled", False)
    monkeypatch.setattr(
        "services.first_person_context_harness.source_is_authoritatively_licensed",
        lambda **kwargs: kwargs.get("domain_rights_status") == "licensed",
    )


def _span(
    index: int = 0,
    text: str = "A beautiful state is a state of calm presence and clarity.",
    *,
    guru_id: str = "preethaji",
    parent_unit_id: str = "parent_001",
    video_id: str = "vid_001",
    previous_span_id: str | None = None,
    next_span_id: str | None = None,
) -> SourceSpan:
    span_id = make_source_span_id(
        guru_id=guru_id,
        video_id=video_id,
        corpus_version="fp-context-v1",
        word_start=index * 20,
        word_end=(index + 1) * 20,
        transcript_hash="f" * 64,
    )
    return SourceSpan(
        source_span_id=span_id,
        parent_unit_id=parent_unit_id,
        guru_id=guru_id,
        video_id=video_id,
        source_asset_id=video_id,
        turn_id=f"turn-{index}",
        turn_index=index,
        source_span_index=index,
        corpus_version="fp-context-v1",
        word_start=index * 20,
        word_end=(index + 1) * 20,
        start_ms=index * 5000,
        end_ms=(index + 1) * 5000,
        speaker_id=guru_id,
        speaker_role=SpeakerRole.GURU,
        speaker_verified=True,
        voice_verification_method="ecapa_voxceleb_span_slice_v2",
        voice_score=0.91,
        voice_margin=0.22,
        voice_threshold_applied={"cosine_floor": 0.75, "margin_threshold": 0.15},
        voice_calibration_id="synthetic-calibration-v1",
        voice_model_revision="ecapa-v2-rev1",
        voice_window_check="pass",
        voice_verified_at="2026-11-02T00:00:00Z",
        speaker_verification_status="verified",
        source_transcript_text=text,
        verbatim_text=text,
        transcript_hash="f" * 64,
        source_text_hash=clip_text_hash(text),
        previous_span_id=previous_span_id,
        next_span_id=next_span_id,
        boundary_status=BoundaryStatus.VERIFIED,
        completeness_status=CompletenessStatus.COMPLETE,
        rights_cleared=True,
        domain_rights_status="licensed",
        caption_status="auto",
        provenance_kind=ProvenanceKind.SPEECH_TURN_SPAN,
        source_url="https://www.youtube.com/watch?v=" + video_id,
        answer_role=AnswerRole.DIRECT,
    )


def _context(
    spans: list[SourceSpan],
    guru_id: str = "preethaji_krishnaji",
    parent_unit_id: str = "parent_001",
    video_id: str = "vid_001",
) -> ParentContext:
    ordered_ids = tuple(s.source_span_id for s in spans)
    speaker_ids = (guru_id,) if "_" not in guru_id else ("preethaji", "krishnaji")
    parent = ParentUnit(
        parent_unit_id=parent_unit_id,
        guru_id=guru_id,
        video_id=video_id,
        corpus_version="fp-context-v1",
        ordered_source_span_ids=ordered_ids,
        start_ms=spans[0].start_ms if spans else 0,
        end_ms=spans[-1].end_ms if spans else 5000,
        parent_text_hash=clip_text_hash(" ".join(s.verbatim_text for s in spans)),
        speaker_ids=speaker_ids,
        speaker_continuity=True,
        boundary_status=BoundaryStatus.VERIFIED,
        completeness_status=CompletenessStatus.COMPLETE,
    )
    return ParentContext(
        parent=parent,
        spans=tuple(spans),
        hit_span_ids=(spans[0].source_span_id,) if spans else (),
        score=0.9,
    )


# ==============================================================================
# 1. Guru Co-Identity Tests (Sri Preethaji & Sri Krishnaji as ONE COMMON GURU)
# ==============================================================================

class TestGuruCoIdentity:
    """Sri Preethaji and Sri Krishnaji are husband and wife, co-teachers of Ekam.
    Their joint occurrence must never be flagged as cross_guru_contamination."""

    def test_serving_contract_ekam_coidentity_helpers(self):
        # Preethaji and Krishnaji belong to Ekam co-identity
        assert "preethaji" in EKAM_COIDENTITY_GURU_IDS
        assert "krishnaji" in EKAM_COIDENTITY_GURU_IDS
        assert "preethaji_krishnaji" in EKAM_COIDENTITY_GURU_IDS

        # is_ekam_coidentity returns True for Preethaji & Krishnaji in either order
        assert contract_is_ekam_coidentity("preethaji", "krishnaji") is True
        assert contract_is_ekam_coidentity("krishnaji", "preethaji") is True
        assert contract_is_ekam_coidentity("preethaji", "ekam") is True
        assert contract_is_ekam_coidentity("krishnaji", "preethaji_krishnaji") is True

        # External teachers are not part of Ekam co-identity
        assert contract_is_ekam_coidentity("preethaji", "sadhguru") is False
        assert contract_is_ekam_coidentity("krishnaji", "eckhart tolle") is False
        assert contract_is_ekam_coidentity("sadhguru", "osho") is False

        # validate_guru_lineage accepts Ekam co-occurrence without error
        assert contract_validate_guru_lineage(["preethaji", "krishnaji"]) is None
        assert contract_validate_guru_lineage(["preethaji"]) is None
        assert contract_validate_guru_lineage(["krishnaji"]) is None
        assert contract_validate_guru_lineage(["preethaji", "krishnaji", "ekam"]) is None

        # validate_guru_lineage flags external gurus as cross_guru_contamination
        assert contract_validate_guru_lineage(["preethaji", "sadhguru"]) == "cross_guru_contamination"
        assert contract_validate_guru_lineage(["krishnaji", "eckhart tolle"]) == "cross_guru_contamination"

    def test_evidence_policy_guru_coidentity_decision(self):
        policy = FirstPersonEvidencePolicy()

        # Ekam co-teachers receive ALLOW
        decision = policy.assess_guru_coidentity(["preethaji", "krishnaji"])
        assert decision.may_serve is True
        assert decision.action is EvidenceAction.ALLOW
        assert decision.reason_codes == ()

        # Mixed external teacher receives EXCLUDE with cross_guru_contamination
        decision_external = policy.assess_guru_coidentity(["preethaji", "sadhguru"])
        assert decision_external.may_serve is False
        assert decision_external.action is EvidenceAction.EXCLUDE
        assert "cross_guru_contamination" in decision_external.reason_codes

        # Query targeting an external teacher receives external_teacher_or_tradition
        safety_dec = policy.assess_contextual_safety(
            query="What does Sadhguru say about inner engineering?",
            text="When you are in a beautiful state, life flows with ease.",
        )
        assert safety_dec.may_serve is False
        assert "external_teacher_or_tradition" in safety_dec.reason_codes

    def test_harness_serves_joint_ekam_spans(self):
        harness = FirstPersonContextHarness()
        span_preetha = _span(
            0,
            text="When you are in a beautiful state, your inner world is connected and quiet.",
            guru_id="preethaji",
        )
        span_krishna = _span(
            1,
            text="And in that connection, intelligence arises to solve any life dilemma.",
            guru_id="krishnaji",
        )
        ctx = _context([span_preetha, span_krishna], guru_id="preethaji_krishnaji")

        decision = harness.decide(ctx, answerability="yes")
        assert decision.decision is HarnessDecision.SERVE_PARENT_CONTEXT
        assert decision.abstain_reason is None
        assert decision.gates["guru_isolation"] is True
        assert decision.gates["speaker"] is True

    def test_harness_abstains_on_unregistered_external_guru(self):
        harness = FirstPersonContextHarness()
        span_preetha = _span(0, text="A beautiful state brings profound clarity.", guru_id="preethaji")
        ctx = _context([span_preetha], guru_id="preethaji")

        # Explicit request for foreign guru must abstain
        decision = harness.decide(ctx, requested_teacher="sadhguru", answerability="yes")
        assert decision.decision is HarnessDecision.ABSTAIN
        assert decision.abstain_reason == "cross_guru_contamination"


# ==============================================================================
# 2. Antecedent Slicing & Windowing Tests
# ==============================================================================

class TestAntecedentSlicingAndWindowing:
    """When a middle span (Span 1 or 2) hits, Span 0 must be included so opening
    premise and antecedent pronouns are never severed."""

    def test_window_anchors_span_0_when_span_1_hits(self):
        harness = FirstPersonContextHarness(HarnessPolicy(max_context_spans=3))
        spans = [
            _span(0, text="Sri Krishnaji teaches that wealth creation begins with inner consciousness."),
            _span(1, text="When the inner state is troubled, ambition turns into suffering and anxiety."),
            _span(2, text="True spiritual abundance is living with a peaceful and generous heart."),
            _span(3, text="Let this understanding guide all your daily actions and relationships."),
            _span(4, text="Stillness in the heart reveals the path forward in life."),
        ]
        # Span 1 is the retrieval hit
        ctx = _context(spans).model_copy(update={"hit_span_ids": (spans[1].source_span_id,)})

        window = harness._window(ctx)
        # Span 0 must be retained in the window!
        window_ids = [s.source_span_id for s in window]
        assert spans[0].source_span_id in window_ids
        assert spans[1].source_span_id in window_ids
        assert window_ids[0] == spans[0].source_span_id

    def test_window_anchors_span_0_when_span_2_hits(self):
        harness = FirstPersonContextHarness(HarnessPolicy(max_context_spans=3))
        spans = [
            _span(0, text="In Ekam teachings, we speak of two primary states of being."),
            _span(1, text="The first is the suffering state, where the self is contracted and fearful."),
            _span(2, text="The second is the beautiful state, where there is connection and oneness."),
            _span(3, text="From this beautiful state, every problem dissolves naturally."),
            _span(4, text="This is why inner transformation is the highest human priority."),
        ]
        # Span 2 is the retrieval hit (middle span)
        ctx = _context(spans).model_copy(update={"hit_span_ids": (spans[2].source_span_id,)})

        window = harness._window(ctx)
        window_ids = [s.source_span_id for s in window]
        # Span 0 must NOT be sliced off: Span 0 defines the two primary states
        assert spans[0].source_span_id in window_ids
        assert spans[2].source_span_id in window_ids
        assert window_ids[0] == spans[0].source_span_id

    def test_window_head_anchor_fallback_on_orphan_opener(self):
        harness = FirstPersonContextHarness(HarnessPolicy(max_context_spans=3))
        spans = [
            _span(0, text="Understanding the nature of fear allows true courage to awaken in the human heart."),
            _span(1, text="Fear is a reaction of memory projecting itself into the unknown future."),
            _span(2, text="This is why so many seekers feel an immediate sense of relief in meditation."),
            _span(3, text="When you observe fear without running away, it loses its grip on you."),
            _span(4, text="And peace settles deep within the core of your consciousness."),
        ]
        # Span 3 hits. If centered in isolation, span 3's opener "This is why..." triggers orphan opener.
        # Head anchor fallback includes span 0 so discourse premise is restored.
        ctx = _context(spans).model_copy(update={"hit_span_ids": (spans[3].source_span_id,)})
        window = harness._window(ctx)
        assert len(window) >= 1
        assert window[0].source_span_id == spans[0].source_span_id


# ==============================================================================
# 3. Standalone Check & Authentic Oral Openers Tests
# ==============================================================================

class TestStandaloneAuthenticOralOpeners:
    """Authentic teacher discourse openings ("This is...", "It is...", "Because...")
    must not be discarded as orphans when part of a verified parent unit."""

    def test_authentic_oral_openers_regex_patterns(self):
        assert AUTHENTIC_ORAL_OPENER_RE.match("This is the truth about desire and attachment.")
        assert AUTHENTIC_ORAL_OPENER_RE.match("These are the sacred principles of living in oneness.")
        assert AUTHENTIC_ORAL_OPENER_RE.match("That is the doorway to inner stillness and peace.")
        assert AUTHENTIC_ORAL_OPENER_RE.match("It is possible to live without inner conflict and fear.")
        assert AUTHENTIC_ORAL_OPENER_RE.match("It was in that state of quiet that insight arose.")
        assert AUTHENTIC_ORAL_OPENER_RE.match("Because when the mind is agitated, perception is distorted.")

    def test_verified_parent_allows_authentic_discourse_openings(self):
        # When part of a verified parent unit, "This is..." is valid oral opening
        text_this = "This is the essence of meditation: observing the mind with gentle attention."
        assert _context_standalone_problem([text_this], is_verified_parent=True) is None

        # "It is..." opening allowed in verified parent context
        text_it = "It is possible to dissolve suffering the moment you become conscious of it."
        assert _context_standalone_problem([text_it], is_verified_parent=True) is None

        # "Because..." opening allowed in verified parent context
        text_because = "Because when awareness is awake, you are no longer a victim of old conditioning."
        assert _context_standalone_problem([text_because], is_verified_parent=True) is None

    def test_assess_context_standalone_auto_detects_verified_parent(self):
        policy = FirstPersonEvidencePolicy()
        span_this = _span(0, text="This is the path to inner awakening taught by Sri Preethaji.")
        decision = policy.assess_context_standalone([span_this])
        assert decision.may_serve is True
        assert decision.reason_codes == ()

    def test_unverified_unanchored_clip_still_flagged(self):
        # Without verified parent context, a raw standalone clip starting with "This is..." remains flagged
        text_isolated = "This is the nature of the unawakened mind. It's more like a monkey mind."
        assert _context_standalone_problem([text_isolated], is_verified_parent=False) == "orphan_opener"

    def test_true_grammatical_orphans_remain_rejected(self):
        # Truly dangling fragments must always fail, even in parent context
        assert _context_standalone_problem(["some addiction."], is_verified_parent=True) == "dangling_fragment"
        assert _context_standalone_problem(["When we look at life and,"], is_verified_parent=True) == "ends_mid_sentence"


# ==============================================================================
# 4. Calibration Profile Loading & Direct Answer Evaluation Tests
# ==============================================================================

class TestCalibrationProfileLoading:
    """The conformal_direct_v1 calibration profile must load successfully and unblock
    is_direct evaluation for the serving pipeline."""

    def test_calibration_profile_loads_successfully(self):
        profile = load_calibration_profile(
            "backend/config/first_person_calibration.json",
            "first_person_v10",
        )
        assert profile is not None, "Profile must load successfully and not be demoted to None"
        assert profile["claims"] == "conformal_direct_v1"
        assert profile["score_kind"] == "dense_cosine"
        assert profile["threshold"] == 0.45
        assert profile["n"] >= 300
        assert profile["ucb_risk"] <= 0.01
        assert profile["target_risk"] <= 0.01
        assert profile["ucb_risk"] <= profile["target_risk"]

    def test_is_direct_evaluation_unblocked(self):
        profile = load_calibration_profile(
            "backend/config/first_person_calibration.json",
            "first_person_v10",
        )
        assert profile is not None

        # Direct answer logic from FirstPersonPipeline:
        # is_direct = self._profile is not None and confidence >= self._profile["threshold"]
        threshold = profile["threshold"]
        assert threshold == 0.45

        # Query with good relevance confidence (e.g. 0.55 >= 0.45) achieves is_direct = True
        high_confidence = 0.55
        is_direct_hit = profile is not None and high_confidence >= threshold
        assert is_direct_hit is True

        # Query with low relevance confidence (< 0.45) correctly evaluates to False
        low_confidence = 0.35
        is_direct_miss = profile is not None and low_confidence >= threshold
        assert is_direct_miss is False
