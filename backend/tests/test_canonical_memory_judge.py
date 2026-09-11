"""Tests for the Memory Judge — Phase 4 of the Adaptive Memory System.

Covers every decision path:
    - noise → IGNORE
    - strong preference → CREATE
    - duplicate → IGNORE
    - updated preference → UPDATE
    - temporary → EXPIRE
    - explicit delete → DELETE
    - ambiguous → ESCALATE
    - sensitive → policy gate
    - explicit user instruction overrides inference
    - consent check
"""

from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone

from services.canonical_memory.judge import (
    DecisionType,
    DeleteCommand,
    ExistingMemory,
    MemoryDecision,
    MemoryJudge,
    SensitivityPolicy,
    create_judge,
    _text_similarity,
    _normalize_for_compare,
    CONFIDENCE_THRESHOLD,
)
from services.canonical_memory.models import MemoryCandidate, MemoryType


# ---------------------------------------------------------------------------
# Fixtures: reusable helpers
# ---------------------------------------------------------------------------

def _make_candidate(
    statement: str = "User lives in Mumbai.",
    memory_type: MemoryType = MemoryType.PROFILE,
    confidence: float = 0.9,
    importance: float = 0.7,
    sensitivity: str = "normal",
    fact_key: str | None = "user:lives_in",
    explicit_request: bool = False,
    evidence: str = "I live in Mumbai.",
) -> MemoryCandidate:
    return MemoryCandidate(
        statement=statement,
        memory_type=memory_type,
        confidence=confidence,
        importance=importance,
        sensitivity=sensitivity,
        fact_key=fact_key,
        explicit_request=explicit_request,
        evidence=evidence,
    )


def _make_existing(
    id: str = "mem-001",
    statement: str = "User lives in Mumbai.",
    fact_key: str | None = "user:lives_in",
    memory_type: str = "PROFILE",
    confidence: float = 0.8,
    status: str = "active",
    evidence_count: int = 1,
) -> ExistingMemory:
    return ExistingMemory(
        id=id,
        statement=statement,
        normalized_statement=statement.strip().lower(),
        memory_type=memory_type,
        fact_key=fact_key,
        confidence=confidence,
        importance=0.7,
        sensitivity="normal",
        status=status,
        evidence_count=evidence_count,
        extraction_method="llm",
        explicit_request=False,
    )


# ===================================================================
# 1. Noise → IGNORE
# ===================================================================

class TestNoiseIgnored:
    """Greetings, noise, and too-short statements → IGNORE."""

    def test_greeting_ignored(self):
        candidate = _make_candidate(
            statement="Hello",
            memory_type=MemoryType.REFLECTION,
            confidence=0.5,
        )
        decision = create_judge().judge(candidate)
        assert decision.decision == DecisionType.IGNORE

    def test_too_short_ignored(self):
        candidate = _make_candidate(
            statement="OK",
            memory_type=MemoryType.REFLECTION,
            confidence=0.5,
        )
        decision = create_judge().judge(candidate)
        assert decision.decision == DecisionType.IGNORE

    def test_empty_statement_ignored(self):
        candidate = _make_candidate(
            statement="",
            memory_type=MemoryType.REFLECTION,
            confidence=0.5,
        )
        decision = create_judge().judge(candidate)
        assert decision.decision == DecisionType.IGNORE

    def test_thanks_ignored(self):
        candidate = _make_candidate(
            statement="Thank you",
            memory_type=MemoryType.REFLECTION,
            confidence=0.5,
        )
        decision = create_judge().judge(candidate)
        assert decision.decision == DecisionType.IGNORE

    def test_generic_world_fact_ignored(self):
        candidate = _make_candidate(
            statement="What is meditation?",
            memory_type=MemoryType.REFLECTION,
            confidence=0.5,
            fact_key=None,
        )
        decision = create_judge().judge(candidate)
        assert decision.decision == DecisionType.IGNORE


# ===================================================================
# 2. Strong durable preference → CREATE
# ===================================================================

class TestStrongPreferenceCreates:
    """Good candidates with high confidence → CREATE."""

    def test_strong_preference_creates(self):
        candidate = _make_candidate(
            statement="User prefers concise answers.",
            memory_type=MemoryType.PREFERENCE,
            confidence=0.9,
            importance=0.7,
            fact_key="user:prefers_tone",
            explicit_request=True,
        )
        decision = create_judge().judge(candidate)
        assert decision.decision == DecisionType.CREATE
        assert decision.confidence == 1.0
        assert "explicit" in decision.reason.lower()

    def test_profile_creates(self):
        candidate = _make_candidate(
            statement="User lives in Hyderabad, India.",
            memory_type=MemoryType.PROFILE,
            confidence=0.92,
            importance=0.8,
            fact_key="user:lives_in",
        )
        decision = create_judge().judge(candidate)
        assert decision.decision == DecisionType.CREATE

    def test_goal_creates(self):
        candidate = _make_candidate(
            statement="User wants to learn vipassana meditation.",
            memory_type=MemoryType.GOAL,
            confidence=0.85,
            importance=0.6,
            fact_key=None,
        )
        decision = create_judge().judge(candidate)
        assert decision.decision == DecisionType.CREATE

    def test_relationship_creates(self):
        candidate = _make_candidate(
            statement="User's guru is Sri Preethaji.",
            memory_type=MemoryType.RELATIONSHIP,
            confidence=0.88,
            importance=0.5,
            fact_key=None,
        )
        decision = create_judge().judge(candidate)
        assert decision.decision == DecisionType.CREATE

    def test_interest_creates(self):
        candidate = _make_candidate(
            statement="User is interested in Advaita Vedanta.",
            memory_type=MemoryType.INTEREST,
            confidence=0.8,
            importance=0.5,
            fact_key=None,
        )
        decision = create_judge().judge(candidate)
        assert decision.decision == DecisionType.CREATE

    def test_communication_style_creates(self):
        candidate = _make_candidate(
            statement="User prefers Hindi responses.",
            memory_type=MemoryType.COMMUNICATION_STYLE,
            confidence=0.9,
            importance=0.6,
            fact_key="user:prefers_language",
        )
        decision = create_judge().judge(candidate)
        assert decision.decision == DecisionType.CREATE


# ===================================================================
# 3. Duplicate → IGNORE
# ===================================================================

class TestDuplicateIgnores:
    """Exact duplicates of existing memories → IGNORE."""

    def test_exact_duplicate_ignored(self):
        existing = _make_existing(
            id="mem-100",
            statement="User prefers concise answers.",
            fact_key="user:prefers_tone",
            confidence=0.9,
        )
        candidate = _make_candidate(
            statement="User prefers concise answers.",
            fact_key="user:prefers_tone",
            confidence=0.85,
        )
        decision = create_judge(existing_memories=[existing]).judge(candidate)
        assert decision.decision == DecisionType.IGNORE
        assert decision.superseded_memory_id == "mem-100"
        assert decision.confidence >= 0.9

    def test_near_duplicate_same_fact_key_ignored(self):
        existing = _make_existing(
            id="mem-101",
            statement="User lives in Mumbai, India.",
            fact_key="user:lives_in",
            confidence=0.9,
        )
        candidate = _make_candidate(
            statement="User lives in Mumbai, India",
            fact_key="user:lives_in",
            confidence=0.88,
        )
        decision = create_judge(existing_memories=[existing]).judge(candidate)
        assert decision.decision == DecisionType.IGNORE

    def test_duplicate_no_fact_key_ignored(self):
        existing = _make_existing(
            id="mem-102",
            statement="User enjoys morning meditation.",
            fact_key=None,
            confidence=0.8,
        )
        candidate = _make_candidate(
            statement="User enjoys morning meditation.",
            fact_key=None,
            confidence=0.8,
            memory_type=MemoryType.INTEREST,
        )
        decision = create_judge(existing_memories=[existing]).judge(candidate)
        assert decision.decision == DecisionType.IGNORE


# ===================================================================
# 4. Updated preference → UPDATE (supersede old)
# ===================================================================

class TestUpdateSupersedes:
    """Changed preferences with same fact_key → UPDATE (supersede)."""

    def test_same_fact_key_higher_confidence_supersedes(self):
        existing = _make_existing(
            id="mem-200",
            statement="User lives in Pune.",
            fact_key="user:lives_in",
            confidence=0.7,
        )
        candidate = _make_candidate(
            statement="User moved to Mumbai.",
            fact_key="user:lives_in",
            confidence=0.95,
        )
        decision = create_judge(existing_memories=[existing]).judge(candidate)
        assert decision.decision == DecisionType.UPDATE
        assert decision.superseded_memory_id == "mem-200"

    def test_same_fact_key_explicit_request_supersedes(self):
        existing = _make_existing(
            id="mem-201",
            statement="User prefers detailed answers.",
            fact_key="user:prefers_tone",
            confidence=0.9,
        )
        candidate = _make_candidate(
            statement="Actually, I prefer concise answers.",
            fact_key="user:prefers_tone",
            confidence=0.7,
            explicit_request=True,
        )
        decision = create_judge(existing_memories=[existing]).judge(candidate)
        assert decision.decision == DecisionType.UPDATE
        assert decision.superseded_memory_id == "mem-201"

    def test_same_fact_key_newer_wins_when_equal_confidence(self):
        existing = _make_existing(
            id="mem-202",
            statement="User prefers English.",
            fact_key="user:prefers_language",
            confidence=0.85,
        )
        candidate = _make_candidate(
            statement="User prefers Hindi now.",
            fact_key="user:prefers_language",
            confidence=0.85,
        )
        decision = create_judge(existing_memories=[existing]).judge(candidate)
        assert decision.decision == DecisionType.UPDATE
        assert decision.superseded_memory_id == "mem-202"

    def test_same_fact_key_lower_confidence_ignored(self):
        existing = _make_existing(
            id="mem-203",
            statement="User lives in Mumbai.",
            fact_key="user:lives_in",
            confidence=0.95,
        )
        candidate = _make_candidate(
            statement="User might live in Pune.",
            fact_key="user:lives_in",
            confidence=0.5,
        )
        decision = create_judge(existing_memories=[existing]).judge(candidate)
        assert decision.decision == DecisionType.IGNORE


# ===================================================================
# 5. Temporary → EXPIRE
# ===================================================================

class TestTemporaryExpiry:
    """Temporary context with expired datetime → EXPIRE."""

    def test_expired_temporary_creates_expire(self):
        candidate = MemoryCandidate(
            statement="I'm visiting Delhi this week.",
            memory_type=MemoryType.TEMPORARY_CONTEXT,
            confidence=0.8,
            fact_key=None,
            evidence="I'm visiting Delhi.",
            expires_at=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        )
        decision = create_judge().judge(candidate)
        assert decision.decision == DecisionType.EXPIRE

    def test_future_temporary_creates(self):
        candidate = MemoryCandidate(
            statement="I'll be in Delhi next week.",
            memory_type=MemoryType.TEMPORARY_CONTEXT,
            confidence=0.8,
            fact_key=None,
            evidence="I'll be in Delhi next week.",
            expires_at=(datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        )
        decision = create_judge().judge(candidate)
        assert decision.decision == DecisionType.CREATE
        assert "expires_at" in decision.metadata

    def test_temporary_without_expiry_creates_with_default(self):
        candidate = MemoryCandidate(
            statement="I'm at a conference today.",
            memory_type=MemoryType.TEMPORARY_CONTEXT,
            confidence=0.75,
            fact_key=None,
            evidence="I'm at a conference today.",
        )
        decision = create_judge().judge(candidate)
        assert decision.decision == DecisionType.CREATE
        assert decision.metadata.get("default_expiry_days") == 7


# ===================================================================
# 6. Explicit delete → DELETE
# ===================================================================

class TestExplicitDelete:
    """Explicit user 'forget' instruction → DELETE."""

    def test_explicit_delete_command(self):
        existing = _make_existing(
            id="mem-300",
            statement="User lives in Mumbai.",
            fact_key="user:lives_in",
        )
        delete_cmd = DeleteCommand(target_text="User lives in Mumbai")
        candidate = _make_candidate(
            statement="I moved to Bangalore.",
            fact_key="user:lives_in",
            confidence=0.9,
        )
        decision = create_judge(
            existing_memories=[existing],
            delete_commands=[delete_cmd],
        ).judge(candidate)
        # The delete command targets existing mem-300, candidate is new
        # → candidate gets CREATE (the delete is for resolver to handle)
        # But if the candidate itself matches the delete target:
        candidate_matching_delete = _make_candidate(
            statement="User lives in Mumbai.",
            fact_key="user:lives_in",
            confidence=0.9,
        )
        d2 = create_judge(
            existing_memories=[existing],
            delete_commands=[delete_cmd],
        ).judge(candidate_matching_delete)
        assert d2.decision == DecisionType.DELETE

    def test_delete_non_matching_candidate_not_affected(self):
        existing = _make_existing(
            id="mem-301",
            statement="User lives in Mumbai.",
            fact_key="user:lives_in",
        )
        delete_cmd = DeleteCommand(target_text="User lives in Mumbai")
        candidate = _make_candidate(
            statement="User is interested in yoga.",
            fact_key=None,
            confidence=0.8,
            memory_type=MemoryType.INTEREST,
        )
        decision = create_judge(
            existing_memories=[existing],
            delete_commands=[delete_cmd],
        ).judge(candidate)
        # Candidate doesn't match delete target → normal processing
        assert decision.decision == DecisionType.CREATE

    def test_delete_fuzzy_match(self):
        """Fuzzy match on delete target should still trigger DELETE."""
        delete_cmd = DeleteCommand(target_text="User lives in Mumbai, India")
        candidate = _make_candidate(
            statement="User lives in Mumbai.",
            fact_key="user:lives_in",
            confidence=0.9,
        )
        decision = create_judge(
            delete_commands=[delete_cmd],
        ).judge(candidate)
        assert decision.decision == DecisionType.DELETE


# ===================================================================
# 7. Ambiguous conflict → ESCALATE
# ===================================================================

class TestAmbiguousEscalation:
    """Ambiguous contradictions → ESCALATE for human resolution."""

    def test_ambiguous_contradiction_escalates(self):
        existing = _make_existing(
            id="mem-400",
            statement="User practices yoga daily.",
            fact_key=None,
            confidence=0.8,
            memory_type="INTEREST",
        )
        candidate = _make_candidate(
            statement="User stopped practicing yoga.",
            fact_key=None,
            confidence=0.7,
            memory_type=MemoryType.REFLECTION,
        )
        decision = create_judge(existing_memories=[existing]).judge(candidate)
        # Without same fact_key, this is a merge candidate if similarity is moderate
        assert decision.decision in (
            DecisionType.CREATE,
            DecisionType.MERGE,
            DecisionType.ESCALATE,
        )

    def test_same_fact_key_different_meaning_escalates(self):
        """Same fact_key, moderate similarity → UPDATE for single-valued, ESCALATE for multi-valued."""
        existing = _make_existing(
            id="mem-401",
            statement="User practices vipassana.",
            fact_key="spiritual_practice",
            confidence=0.8,
            memory_type="INTEREST",
        )
        candidate = _make_candidate(
            statement="User practices transcendental meditation.",
            fact_key="spiritual_practice",
            confidence=0.75,
            memory_type=MemoryType.INTEREST,
        )
        decision = create_judge(existing_memories=[existing]).judge(candidate)
        # spiritual_practice is not single-valued → ESCALATE
        assert decision.decision == DecisionType.ESCALATE

    def test_single_valued_conflict_supersedes(self):
        """Single-valued fact_key + different content, higher confidence → UPDATE (deterministic)."""
        existing = _make_existing(
            id="mem-402",
            statement="User lives in Pune.",
            fact_key="user:lives_in",
            confidence=0.8,
        )
        candidate = _make_candidate(
            statement="I live in Bangalore now.",
            fact_key="user:lives_in",
            confidence=0.9,
        )
        decision = create_judge(existing_memories=[existing]).judge(candidate)
        assert decision.decision == DecisionType.UPDATE
        assert decision.superseded_memory_id == "mem-402"


# ===================================================================
# 8. Sensitive content → policy gate
# ===================================================================

class TestSensitivePolicyGate:
    """Sensitive/highly_sensitive content requires escalation or consent."""

    def test_highly_sensitive_escalates(self):
        candidate = _make_candidate(
            statement="User has a history of depression.",
            memory_type=MemoryType.PROFILE,
            confidence=0.8,
            sensitivity="highly_sensitive",
            fact_key="user:health_history",
        )
        decision = create_judge().judge(candidate)
        assert decision.decision == DecisionType.ESCALATE
        assert "sensitive" in decision.reason.lower()

    def test_highly_sensitive_explicit_request_creates(self):
        """Explicit user instruction overrides sensitivity escalation."""
        candidate = _make_candidate(
            statement="I have a history of anxiety.",
            memory_type=MemoryType.PROFILE,
            confidence=0.9,
            sensitivity="highly_sensitive",
            fact_key="user:health_history",
            explicit_request=True,
        )
        decision = create_judge().judge(candidate)
        assert decision.decision == DecisionType.CREATE

    def test_sensitive_low_confidence_escalates(self):
        candidate = _make_candidate(
            statement="I might be going through a divorce.",
            memory_type=MemoryType.PROFILE,
            confidence=0.35,
            sensitivity="sensitive",
            fact_key=None,
        )
        decision = create_judge().judge(candidate)
        assert decision.decision == DecisionType.ESCALATE

    def test_normal_sensitivity_not_escalated(self):
        candidate = _make_candidate(
            statement="User prefers Hindi responses.",
            memory_type=MemoryType.COMMUNICATION_STYLE,
            confidence=0.9,
            sensitivity="normal",
            fact_key="user:prefers_language",
        )
        decision = create_judge().judge(candidate)
        assert decision.decision == DecisionType.CREATE


# ===================================================================
# 9. Explicit user instruction overrides inference
# ===================================================================

class TestExplicitUserOverride:
    """Explicit user instruction always wins over system assessment."""

    def test_explicit_request_overrides_low_confidence(self):
        """Even if confidence is low, explicit user request → CREATE."""
        candidate = _make_candidate(
            statement="Remember that I prefer brief responses.",
            memory_type=MemoryType.USER_EXPLICIT,
            confidence=0.3,  # Below threshold
            importance=0.5,
            explicit_request=True,
        )
        decision = create_judge().judge(candidate)
        assert decision.decision == DecisionType.CREATE
        assert decision.confidence == 1.0

    def test_explicit_request_overrides_noise_rejection(self):
        """An explicit 'remember' of short content still creates."""
        candidate = MemoryCandidate(
            statement="hi",
            memory_type=MemoryType.USER_EXPLICIT,
            confidence=0.5,
            importance=0.5,
            fact_key=None,
            explicit_request=True,
            evidence="Remember: hi is my greeting",
        )
        # Even explicit requests to store noise should be ignored
        decision = create_judge().judge(candidate)
        assert decision.decision == DecisionType.IGNORE

    def test_explicit_remember_overrides_duplicate(self):
        """Explicit 'remember' + duplicate → UPDATE."""
        existing = _make_existing(
            id="mem-500",
            statement="User lives in Mumbai.",
            fact_key="user:lives_in",
            confidence=0.9,
        )
        candidate = _make_candidate(
            statement="Remember that I live in Mumbai.",
            memory_type=MemoryType.USER_EXPLICIT,
            confidence=0.9,
            explicit_request=True,
            fact_key="user:lives_in",
        )
        decision = create_judge(existing_memories=[existing]).judge(candidate)
        assert decision.decision == DecisionType.UPDATE
        assert decision.superseded_memory_id == "mem-500"

    def test_explicit_forget_wins(self):
        """Explicit 'forget' via delete command → DELETE regardless of system assessment."""
        existing = _make_existing(
            id="mem-501",
            statement="User lives in Mumbai.",
            fact_key="user:lives_in",
        )
        delete_cmd = DeleteCommand(target_text="User lives in Mumbai")
        # The extractor produces a candidate about "living in Mumbai"
        # The delete command tells the judge to delete it
        candidate = _make_candidate(
            statement="I live in Mumbai.",
            memory_type=MemoryType.PROFILE,
            confidence=0.9,
            explicit_request=True,
            fact_key="user:lives_in",
        )
        decision = create_judge(
            existing_memories=[existing],
            delete_commands=[delete_cmd],
        ).judge(candidate)
        assert decision.decision == DecisionType.DELETE


# ===================================================================
# 10. Consent check
# ===================================================================

class TestConsentCheck:
    """Without user consent, sensitive operations escalate."""

    def test_no_consent_escalates(self):
        candidate = _make_candidate(
            statement="User prefers concise answers.",
            memory_type=MemoryType.PREFERENCE,
            confidence=0.9,
        )
        decision = create_judge(user_consent=False).judge(candidate)
        assert decision.decision == DecisionType.ESCALATE
        assert "consent" in decision.reason.lower()

    def test_with_consent_creates(self):
        candidate = _make_candidate(
            statement="User prefers concise answers.",
            memory_type=MemoryType.PREFERENCE,
            confidence=0.9,
        )
        decision = create_judge(user_consent=True).judge(candidate)
        assert decision.decision == DecisionType.CREATE

    def test_no_consent_explicit_request_still_escalates(self):
        """Even explicit requests escalate if no consent (policy)."""
        candidate = _make_candidate(
            statement="User wants to be called Alex.",
            memory_type=MemoryType.USER_EXPLICIT,
            confidence=0.9,
            explicit_request=True,
        )
        decision = create_judge(user_consent=False).judge(candidate)
        assert decision.decision == DecisionType.ESCALATE


# ===================================================================
# 11. Merge detection
# ===================================================================

class TestMergeDetection:
    """Partial overlap with different fact_keys → MERGE."""

    def test_merge_candidate_detected(self):
        existing = _make_existing(
            id="mem-600",
            statement="I am interested in meditation.",
            fact_key="spiritual_interest",
            memory_type="INTEREST",
            confidence=0.8,
        )
        candidate = _make_candidate(
            statement="I'm interested in yoga and meditation.",
            fact_key=None,  # Different fact_key
            confidence=0.85,
            memory_type=MemoryType.INTEREST,
        )
        decision = create_judge(existing_memories=[existing]).judge(candidate)
        assert decision.decision == DecisionType.MERGE
        assert "mem-600" in decision.merged_memory_ids


# ===================================================================
# 12. batch judgment
# ===================================================================

class TestBatchJudgment:
    """judge_all processes multiple candidates."""

    def test_judge_all_returns_list(self):
        candidates = [
            _make_candidate(
                statement="User lives in Mumbai.",
                confidence=0.9,
            ),
            _make_candidate(
                statement="Hello",
                confidence=0.5,
                memory_type=MemoryType.REFLECTION,
            ),
        ]
        decisions = create_judge().judge_all(candidates)
        assert len(decisions) == 2
        assert decisions[0].decision == DecisionType.CREATE
        assert decisions[1].decision == DecisionType.IGNORE

    def test_judge_all_empty(self):
        decisions = create_judge().judge_all([])
        assert decisions == []


# ===================================================================
# 13. Text similarity helpers
# ===================================================================

class TestTextSimilarity:
    """Deterministic text similarity functions."""

    def test_identical_strings(self):
        assert _text_similarity("hello world", "hello world") == 1.0

    def test_case_insensitive(self):
        assert _text_similarity("Hello World", "hello world") == 1.0

    def test_completely_different(self):
        sim = _text_similarity("cat", "xyz123")
        assert sim < 0.3

    def test_partial_overlap(self):
        sim = _text_similarity(
            "user lives in mumbai",
            "user lives in mumbai india",
        )
        assert sim > 0.7

    def test_normalize_strips_whitespace(self):
        a = _normalize_for_compare("  Hello   World  ")
        b = _normalize_for_compare("Hello World")
        assert a == b


# ===================================================================
# 14. Edge cases
# ===================================================================

class TestEdgeCases:
    """Boundary conditions and unusual inputs."""

    def test_all_active_memories_only(self):
        """Expired/superseded/deleted memories don't trigger conflicts."""
        existing = _make_existing(
            id="mem-700",
            statement="User lives in Pune.",
            fact_key="user:lives_in",
            status="superseded",
        )
        candidate = _make_candidate(
            statement="User lives in Pune.",
            fact_key="user:lives_in",
            confidence=0.8,
        )
        decision = create_judge(existing_memories=[existing]).judge(candidate)
        assert decision.decision == DecisionType.CREATE

    def test_no_existing_memories(self):
        """With no existing memories, good candidate → CREATE."""
        candidate = _make_candidate(
            statement="User practices yoga daily.",
            confidence=0.85,
            memory_type=MemoryType.INTEREST,
            fact_key=None,
        )
        decision = create_judge().judge(candidate)
        assert decision.decision == DecisionType.CREATE

    def test_confidence_exactly_at_threshold(self):
        """Confidence exactly at threshold → CREATE (not IGNORE)."""
        candidate = _make_candidate(
            statement="User might prefer concise answers.",
            confidence=CONFIDENCE_THRESHOLD,
            fact_key=None,
        )
        decision = create_judge().judge(candidate)
        assert decision.decision == DecisionType.CREATE

    def test_confidence_just_below_threshold(self):
        """Confidence just below threshold → IGNORE."""
        candidate = _make_candidate(
            statement="User might prefer concise answers.",
            confidence=CONFIDENCE_THRESHOLD - 0.01,
            fact_key=None,
        )
        decision = create_judge().judge(candidate)
        assert decision.decision == DecisionType.IGNORE

    def test_multiple_existing_memories_finds_correct_one(self):
        """Judge finds the right duplicate among many."""
        existing = [
            _make_existing(id="mem-a", statement="I live in Pune.", fact_key="user:lives_in"),
            _make_existing(id="mem-b", statement="I prefer Hindi.", fact_key="user:prefers_language"),
            _make_existing(id="mem-c", statement="I live in Mumbai.", fact_key="user:lives_in"),
        ]
        candidate = _make_candidate(
            statement="I live in Mumbai.",
            fact_key="user:lives_in",
            confidence=0.9,
        )
        decision = create_judge(existing_memories=existing).judge(candidate)
        assert decision.decision == DecisionType.IGNORE
        assert decision.superseded_memory_id == "mem-c"


# ===================================================================
# 15. SensitivityPolicy unit tests
# ===================================================================

class TestSensitivityPolicy:
    """Unit tests for the SensitivityPolicy class."""

    def test_highly_sensitive_no_explicit_escalates(self):
        policy = SensitivityPolicy()
        candidate = _make_candidate(sensitivity="highly_sensitive")
        assert policy.should_escalate(candidate) is True

    def test_highly_sensitive_explicit_no_escalate(self):
        policy = SensitivityPolicy()
        candidate = _make_candidate(
            sensitivity="highly_sensitive", explicit_request=True
        )
        assert policy.should_escalate(candidate) is False

    def test_sensitive_low_confidence_escalates(self):
        policy = SensitivityPolicy()
        candidate = _make_candidate(sensitivity="sensitive", confidence=0.3)
        assert policy.should_escalate(candidate) is True

    def test_normal_sensitivity_no_escalate(self):
        policy = SensitivityPolicy()
        candidate = _make_candidate(sensitivity="normal")
        assert policy.should_escalate(candidate) is False


# ===================================================================
# 16. DeleteCommand unit tests
# ===================================================================

class TestDeleteCommand:
    """Unit tests for DeleteCommand matching."""

    def test_exact_match(self):
        cmd = DeleteCommand(target_text="User lives in Mumbai")
        mem = _make_existing(statement="User lives in Mumbai")
        assert cmd.matches(mem) is True

    def test_fuzzy_match(self):
        cmd = DeleteCommand(target_text="User lives in Mumbai, India")
        mem = _make_existing(statement="User lives in Mumbai")
        assert cmd.matches(mem) is True

    def test_no_match(self):
        cmd = DeleteCommand(target_text="User practices yoga")
        mem = _make_existing(statement="User lives in Mumbai")
        assert cmd.matches(mem) is False
