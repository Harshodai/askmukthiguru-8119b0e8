"""Memory Judge — Phase 4 of the Adaptive Memory System.

Deterministic governance layer between extraction and persistence.
Evaluates each MemoryCandidate and produces a MemoryDecision.

Design principles:
    - LLM proposes; deterministic policy controls persistence.
    - Explicit user instruction takes precedence over inferred memory.
    - Sensitive-memory handling is policy-driven.
    - The judge is deterministic where possible; LLM used only for ambiguity.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from enum import Enum
from typing import Optional

from services.canonical_memory.models import (
    MemoryCandidate,
    MemoryType,
    SINGLE_VALUED_FACT_KEYS,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration thresholds
# ---------------------------------------------------------------------------

CONFIDENCE_THRESHOLD = 0.4
IMPORTANCE_THRESHOLD = 0.0
SIMILARITY_EXACT_THRESHOLD = 0.88
SIMILARITY_MERGE_THRESHOLD = 0.75


# ---------------------------------------------------------------------------
# Decision types
# ---------------------------------------------------------------------------

class DecisionType(str, Enum):
    """Possible judge actions on a MemoryCandidate."""
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    MERGE = "MERGE"
    IGNORE = "IGNORE"
    EXPIRE = "EXPIRE"
    DELETE = "DELETE"
    ESCALATE = "ESCALATE"


# ---------------------------------------------------------------------------
# Decision output
# ---------------------------------------------------------------------------

@dataclass
class MemoryDecision:
    """Result of judging a single MemoryCandidate.

    Attributes:
        candidate: The original candidate being judged.
        decision: The action to take.
        confidence: Judge's confidence in its own decision (0.0-1.0).
        reason: Human-readable explanation of why this decision was made.
        superseded_memory_id: ID of existing memory being superseded (UPDATE).
        merged_memory_ids: IDs of existing memories being merged (MERGE).
        metadata: Arbitrary metadata for audit trail / observability.
    """
    candidate: MemoryCandidate
    decision: DecisionType
    confidence: float = 1.0
    reason: str = ""
    superseded_memory_id: Optional[str] = None
    merged_memory_ids: Optional[list[str]] = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.merged_memory_ids is None:
            self.merged_memory_ids = []


# ---------------------------------------------------------------------------
# Text similarity helpers (deterministic, no LLM)
# ---------------------------------------------------------------------------

def _normalize_for_compare(text: str) -> str:
    """Normalize text for deterministic comparison.

    Lowercases, strips whitespace, collapses multiple spaces.
    """
    return re.sub(r"\s+", " ", text.strip().lower())


def _text_similarity(a: str, b: str) -> float:
    """Compute similarity between two normalized strings.

    Uses SequenceMatcher for deterministic, fast comparison.
    Returns 0.0-1.0.
    """
    na = _normalize_for_compare(a)
    nb = _normalize_for_compare(b)
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


# ---------------------------------------------------------------------------
# Existing-memory lookup (injected, not coupled to store)
# ---------------------------------------------------------------------------

@dataclass
class ExistingMemory:
    """Minimal representation of a persisted memory for judge comparison."""
    id: str
    statement: str
    normalized_statement: str
    memory_type: str
    fact_key: Optional[str]
    confidence: float
    importance: float
    sensitivity: str
    status: str
    evidence_count: int
    extraction_method: str
    explicit_request: bool
    expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


@dataclass
class DeleteCommand:
    """Represents an explicit user 'forget' instruction."""
    target_text: str
    """Text describing what to forget (from user utterance)."""

    def matches(self, memory: ExistingMemory) -> bool:
        """Check if this delete command targets the given memory."""
        sim = _text_similarity(self.target_text, memory.statement)
        if sim >= SIMILARITY_MERGE_THRESHOLD:
            return True
        # Also check normalized statements
        sim_n = _text_similarity(
            _normalize_for_compare(self.target_text),
            memory.normalized_statement,
        )
        return sim_n >= SIMILARITY_MERGE_THRESHOLD


# ---------------------------------------------------------------------------
# Sensitivity policy
# ---------------------------------------------------------------------------

class SensitivityPolicy:
    """Deterministic policy for sensitive memory handling."""

    @staticmethod
    def should_escalate(candidate: MemoryCandidate) -> bool:
        """Return True if candidate needs user confirmation before persisting.

        Highly sensitive content always escalates unless the user explicitly
        requested it.
        """
        if candidate.sensitivity == "highly_sensitive" and not candidate.explicit_request:
            return True
        if candidate.sensitivity == "sensitive" and not candidate.explicit_request:
            # Sensitive + low confidence → escalate; otherwise allow with caution
            if candidate.confidence < CONFIDENCE_THRESHOLD + 0.1:
                return True
        return False


# ---------------------------------------------------------------------------
# Core judge logic
# ---------------------------------------------------------------------------

class MemoryJudge:
    """Deterministic governance layer between extraction and persistence.

    Evaluates each MemoryCandidate against:
        1. memory_worthy — is this worth storing?
        2. user_specific — is this about the user?
        3. confidence — how confident is the extraction?
        4. importance — how important is this?
        5. sensitivity — is this sensitive content?
        6. duplicate — does this already exist?
        7. contradiction — does this contradict existing memories?
        8. supersession — should this replace an existing memory?
        9. temporary — should this expire?
        10. explicit_request — did the user ask to remember/forget?
        11. consent — does the user have memory consent?
    """

    def __init__(
        self,
        *,
        existing_memories: list[ExistingMemory] | None = None,
        user_consent: bool = True,
        delete_commands: list[DeleteCommand] | None = None,
        sensitivity_policy: SensitivityPolicy | None = None,
    ):
        self.existing_memories = existing_memories or []
        self.user_consent = user_consent
        self.delete_commands = delete_commands or []
        self.sensitivity_policy = sensitivity_policy or SensitivityPolicy()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def judge(self, candidate: MemoryCandidate) -> MemoryDecision:
        """Evaluate a single MemoryCandidate and return a MemoryDecision.

        This is the core deterministic policy engine. It applies rules in
        precedence order:

            1. Explicit delete commands (highest — user wants to forget)
            2. Consent gate (blocks all writes if no consent)
            3. Explicit user instruction (user wants to remember)
            4. Deterministic policy rules
            5. Default: CREATE if no conflicts
        """
        # --- Explicit delete commands (highest precedence) ---
        if self.delete_commands:
            for cmd in self.delete_commands:
                if self._candidate_matches_delete_target(candidate, cmd):
                    return MemoryDecision(
                        candidate=candidate,
                        decision=DecisionType.DELETE,
                        confidence=1.0,
                        reason=(
                            "Explicit user instruction to forget: "
                            f"{candidate.statement}"
                        ),
                        metadata={"delete_target": cmd.target_text},
                    )

        # --- Consent gate (blocks all writes, including explicit requests) ---
        if not self.user_consent:
            return MemoryDecision(
                candidate=candidate,
                decision=DecisionType.ESCALATE,
                confidence=1.0,
                reason="User has not granted memory consent",
                metadata={"consent_required": True},
            )

        # --- Explicit user "remember" instruction ---
        if candidate.explicit_request:
            decision = self._judge_explicit_request(candidate)
            if decision is not None:
                return decision

        # --- Memory worthiness ---
        if not self._is_memory_worthy(candidate):
            return MemoryDecision(
                candidate=candidate,
                decision=DecisionType.IGNORE,
                confidence=1.0,
                reason=self._worthiness_reason(candidate),
            )

        # --- User specificity ---
        if not self._is_user_specific(candidate):
            return MemoryDecision(
                candidate=candidate,
                decision=DecisionType.IGNORE,
                confidence=0.9,
                reason="Not user-specific information",
            )

        # --- Sensitivity policy (checked before confidence — sensitive content
        # with low confidence should escalate, not silently ignore) ---
        if self.sensitivity_policy.should_escalate(candidate):
            return MemoryDecision(
                candidate=candidate,
                decision=DecisionType.ESCALATE,
                confidence=0.85,
                reason=(
                    f"Sensitive content (sensitivity={candidate.sensitivity}) "
                    "requires user confirmation"
                ),
            )

        # --- Confidence threshold ---
        if candidate.confidence < CONFIDENCE_THRESHOLD:
            return MemoryDecision(
                candidate=candidate,
                decision=DecisionType.IGNORE,
                confidence=0.8,
                reason=(
                    f"Confidence {candidate.confidence:.2f} below threshold "
                    f"{CONFIDENCE_THRESHOLD}"
                ),
            )

        # --- Temporary / expiry ---
        if candidate.memory_type == MemoryType.TEMPORARY_CONTEXT:
            decision = self._judge_temporary(candidate)
            if decision is not None:
                return decision

        # --- Duplicate / contradiction / supersession ---
        conflict_decision = self._judge_conflicts(candidate)
        if conflict_decision is not None:
            return conflict_decision

        # --- Default: CREATE ---
        return MemoryDecision(
            candidate=candidate,
            decision=DecisionType.CREATE,
            confidence=min(candidate.confidence, 1.0),
            reason="New durable fact, no conflicts detected",
        )

    def judge_all(
        self, candidates: list[MemoryCandidate]
    ) -> list[MemoryDecision]:
        """Judge a batch of candidates."""
        return [self.judge(c) for c in candidates]

    # ------------------------------------------------------------------
    # Internal evaluation helpers
    # ------------------------------------------------------------------

    def _is_memory_worthy(self, candidate: MemoryCandidate) -> bool:
        """Determine if a candidate is worth storing as a memory.

        Rejects: greetings, noise, generic world facts, assistant assumptions.
        """
        statement = candidate.statement.strip()
        if not statement:
            return False

        # Too short to be meaningful
        words = statement.split()
        if len(words) < 3:
            return False

        # Noise patterns (greetings, thanks, ok, etc.)
        noise_patterns = [
            r"^\s*(hi|hello|hey|ok|okay|thanks|thank you|bye|goodbye)\s*[!.]*\s*$",
            r"^\s*(namaste|namaskaram|vanakkam|नमस्ते)\s*[!.]*\s*$",
        ]
        for pat in noise_patterns:
            if re.match(pat, statement, re.IGNORECASE):
                return False

        # Memory type matters
        if candidate.memory_type in (
            MemoryType.USER_EXPLICIT,
            MemoryType.TEMPORARY_CONTEXT,
        ):
            return True

        # Generic questions about the world (not about the user)
        world_facts = [
            "what is", "who is", "when did", "where is",
            "how do", "why do", "can you explain",
        ]
        if any(statement.lower().startswith(wf) for wf in world_facts):
            return False

        return True

    def _worthiness_reason(self, candidate: MemoryCandidate) -> str:
        """Explain why a candidate was rejected as not memory-worthy."""
        statement = candidate.statement.strip()
        if not statement:
            return "Empty statement"
        words = statement.split()
        if len(words) < 3:
            return f"Too short ({len(words)} words)"
        noise_patterns = [
            r"^\s*(hi|hello|hey|ok|okay|thanks|thank you|bye|goodbye)\s*[!.]*\s*$",
            r"^\s*(namaste|namaskaram|vanakkam|नमस्ते)\s*[!.]*\s*$",
        ]
        for pat in noise_patterns:
            if re.match(pat, statement, re.IGNORECASE):
                return "Noise/greeting pattern"
        return "Not memory-worthy"

    def _is_user_specific(self, candidate: MemoryCandidate) -> bool:
        """Determine if the candidate is about the user specifically.

        Rejects: facts about the world, other people, the corpus, etc.
        """
        statement = candidate.statement.lower()

        # USER_EXPLICIT always counts as user-specific
        if candidate.memory_type == MemoryType.USER_EXPLICIT:
            return True

        # Patterns indicating non-user-specific content
        non_user_patterns = [
            "the world is",
            "mumbai is",
            "india is",
            "the sun",
            "the moon",
            "python is a",
            "meditation is",
        ]
        for pat in non_user_patterns:
            if pat in statement:
                # But "user lives in Mumbai" IS user-specific
                user_pats = ["i live", "i work", "i am", "i prefer", "i want"]
                if any(up in statement for up in user_pats):
                    continue
                return False

        # Must contain first-person indicator or be a self-report
        first_person = [
            "i live", "i work", "i am", "i prefer", "i want", "i need",
            "i like", "i practice", "my", "i've been", "i was", "i feel",
            "i study", "i teach", "i run", "i manage", "i lead",
            "i'm", "i will", "i can", "i do", "i have", "i had",
            "i used to", "i stopped", "i started", "i visit",
            "i'm visiting", "i'll be", "i might", "i could",
        ]
        if any(fp in statement for fp in first_person):
            return True

        # Explicit types are always user-specific
        if candidate.memory_type in (
            MemoryType.PROFILE,
            MemoryType.PREFERENCE,
            MemoryType.COMMUNICATION_STYLE,
            MemoryType.GOAL,
            MemoryType.PROJECT,
            MemoryType.INTEREST,
            MemoryType.RELATIONSHIP,
            MemoryType.REFLECTION,
        ):
            return True

        return False

    def _judge_explicit_request(
        self, candidate: MemoryCandidate
    ) -> MemoryDecision | None:
        """Handle explicit user 'remember that...' requests.

        Explicit user instruction overrides confidence thresholds and
        most other gates. The user asked for it — we create it.
        """
        # Even explicit requests must be user-specific and non-empty
        if not self._is_memory_worthy(candidate):
            return MemoryDecision(
                candidate=candidate,
                decision=DecisionType.IGNORE,
                confidence=0.5,
                reason=(
                    "Explicit request but not memory-worthy "
                    "(noise or empty)"
                ),
            )

        # Check for duplicate — explicit request + duplicate → UPDATE
        dup = self._find_duplicate(candidate)
        if dup is not None:
            if dup.id:
                return MemoryDecision(
                    candidate=candidate,
                    decision=DecisionType.UPDATE,
                    confidence=1.0,
                    reason=(
                        "Explicit user instruction overrides confidence; "
                        f"updates existing memory {dup.id}"
                    ),
                    superseded_memory_id=dup.id,
                )

        # Check for same-fact-key conflict — explicit request supersedes
        if candidate.fact_key:
            conflict = self._find_fact_key_conflict(candidate)
            if conflict is not None:
                return MemoryDecision(
                    candidate=candidate,
                    decision=DecisionType.UPDATE,
                    confidence=1.0,
                    reason=(
                        "Explicit user instruction supersedes existing "
                        f"memory {conflict.id}"
                    ),
                    superseded_memory_id=conflict.id,
                )

        return MemoryDecision(
            candidate=candidate,
            decision=DecisionType.CREATE,
            confidence=1.0,
            reason="Explicit user instruction to remember",
        )

    def _judge_temporary(
        self, candidate: MemoryCandidate
    ) -> MemoryDecision | None:
        """Handle temporary context memories.

        Temporary memories have a natural expiry. If already expired,
        we don't create them. If they have an expiry, we CREATE with
        an expires_at set in the metadata.
        """
        now = datetime.now(timezone.utc)

        expires_str = getattr(candidate, "expires_at", None)
        if expires_str is not None:
            try:
                expires_at = datetime.fromisoformat(str(expires_str))
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                if expires_at < now:
                    return MemoryDecision(
                        candidate=candidate,
                        decision=DecisionType.EXPIRE,
                        confidence=1.0,
                        reason="Temporary context already expired",
                    )
                return MemoryDecision(
                    candidate=candidate,
                    decision=DecisionType.CREATE,
                    confidence=0.8,
                    reason="Temporary context with defined expiry",
                    metadata={"expires_at": str(expires_at)},
                )
            except (ValueError, TypeError):
                pass

        # No expiry set — create as temporary with default TTL (7 days)
        return MemoryDecision(
            candidate=candidate,
            decision=DecisionType.CREATE,
            confidence=0.7,
            reason="Temporary context (default 7-day expiry)",
            metadata={"default_expiry_days": 7},
        )

    def _judge_conflicts(
        self, candidate: MemoryCandidate
    ) -> MemoryDecision | None:
        """Check for duplicates, contradictions, and supersession.

        This is the most complex part of the judge. It compares the
        candidate against existing memories for the same user.

        Strategy (order matters):
            1. Exact/near duplicate (high similarity + same fact_key)
            2. Same fact_key + different text → supersession (UPDATE)
            3. Same fact_key + different meaning, multi-valued → ESCALATE
            4. Partial overlap + different fact_keys → MERGE
        """
        # Step 1: Find exact/near duplicate
        dup = self._find_duplicate(candidate)
        if dup is not None:
            return self._decide_on_duplicate(candidate, dup)

        # Step 2: Same fact_key, different text → supersession or escalation
        if candidate.fact_key:
            conflict = self._find_fact_key_conflict(candidate)
            if conflict is not None:
                return self._decide_on_conflict(candidate, conflict)

        # Step 3: Find merge candidate (partial overlap, different fact_keys)
        merge = self._find_merge_candidate(candidate)
        if merge is not None:
            return self._decide_on_merge(candidate, merge)

        return None

    def _find_duplicate(
        self, candidate: MemoryCandidate
    ) -> ExistingMemory | None:
        """Find an existing memory that is a near-duplicate of the candidate.

        Uses text similarity + fact_key match for deterministic dedup.
        """
        candidate_norm = candidate.normalized()

        for mem in self.existing_memories:
            if mem.status != "active":
                continue
            # Must match on user_id (enforced externally) and fact_key
            if candidate.fact_key and mem.fact_key == candidate.fact_key:
                sim = _text_similarity(candidate_norm, mem.normalized_statement)
                if sim >= SIMILARITY_EXACT_THRESHOLD:
                    return mem

        # Also check by statement similarity (no fact_key needed)
        for mem in self.existing_memories:
            if mem.status != "active":
                continue
            sim = _text_similarity(candidate_norm, mem.normalized_statement)
            if sim >= SIMILARITY_EXACT_THRESHOLD:
                return mem

        return None

    def _find_fact_key_conflict(
        self, candidate: MemoryCandidate
    ) -> ExistingMemory | None:
        """Find an existing memory with the same fact_key but different text.

        This catches the case where user says "I live in Mumbai" when existing
        is "I live in Pune" — same fact_key, different value → supersession.
        Prefers the most similar existing memory (closest match).
        """
        if not candidate.fact_key:
            return None

        candidate_norm = candidate.normalized()
        best_match: ExistingMemory | None = None
        best_sim = -1.0

        for mem in self.existing_memories:
            if mem.status != "active":
                continue
            if mem.fact_key != candidate.fact_key:
                continue

            sim = _text_similarity(candidate_norm, mem.normalized_statement)

            # Exact duplicate → handled by _find_duplicate, skip here
            if sim >= SIMILARITY_EXACT_THRESHOLD:
                continue

            # Same fact_key + different text → candidate for conflict
            if sim > best_sim:
                best_sim = sim
                best_match = mem

        return best_match

    def _find_conflict(
        self, candidate: MemoryCandidate
    ) -> ExistingMemory | None:
        """Find an existing memory that contradicts the candidate.

        A contradiction requires: same fact_key, different meaning,
        moderate-to-high similarity (they're about the same topic
        but say different things).
        """
        if not candidate.fact_key:
            return None

        for mem in self.existing_memories:
            if mem.status != "active":
                continue
            if mem.fact_key != candidate.fact_key:
                continue

            sim = _text_similarity(
                candidate.normalized(), mem.normalized_statement
            )

            # High similarity = duplicate (handled elsewhere)
            if sim >= SIMILARITY_EXACT_THRESHOLD:
                continue

            # Same fact_key + moderate similarity = same topic, different state
            # → supersession candidate
            if sim >= SIMILARITY_MERGE_THRESHOLD:
                return mem

        return None

    def _find_merge_candidate(
        self, candidate: MemoryCandidate
    ) -> ExistingMemory | None:
        """Find an existing memory that partially overlaps with the candidate.

        Different fact_keys but related content → merge candidate.
        """
        for mem in self.existing_memories:
            if mem.status != "active":
                continue
            # Different fact_keys but same memory type
            if candidate.fact_key and mem.fact_key == candidate.fact_key:
                continue
            if candidate.memory_type.value != mem.memory_type:
                continue

            sim = _text_similarity(
                candidate.normalized(), mem.normalized_statement
            )
            if SIMILARITY_MERGE_THRESHOLD <= sim < SIMILARITY_EXACT_THRESHOLD:
                return mem

        return None

    def _decide_on_duplicate(
        self, candidate: MemoryCandidate, dup: ExistingMemory
    ) -> MemoryDecision:
        """Decide what to do with a duplicate candidate.

        - Same statement → IGNORE (already known)
        - Same fact_key + explicit request → UPDATE
        - Same fact_key + higher confidence → UPDATE
        """
        sim = _text_similarity(
            candidate.normalized(), dup.normalized_statement
        )

        # Exact duplicate → IGNORE
        if sim >= SIMILARITY_EXACT_THRESHOLD:
            # But explicit user instruction overrides
            if candidate.explicit_request:
                return MemoryDecision(
                    candidate=candidate,
                    decision=DecisionType.UPDATE,
                    confidence=1.0,
                    reason=(
                        "Explicit user instruction to re-remember; "
                        "updating existing memory"
                    ),
                    superseded_memory_id=dup.id,
                    metadata={
                        "similarity": sim,
                        "existing_evidence_count": dup.evidence_count,
                    },
                )
            return MemoryDecision(
                candidate=candidate,
                decision=DecisionType.IGNORE,
                confidence=0.95,
                reason=(
                    f"Duplicate of existing memory {dup.id} "
                    f"(similarity={sim:.2f})"
                ),
                superseded_memory_id=dup.id,
                metadata={"similarity": sim},
            )

        # Near-duplicate with higher confidence or explicit → UPDATE
        if (
            candidate.confidence > dup.confidence
            or candidate.explicit_request
        ):
            return MemoryDecision(
                candidate=candidate,
                decision=DecisionType.UPDATE,
                confidence=0.9,
                reason=(
                    f"Near-duplicate with "
                    f"{'explicit instruction' if candidate.explicit_request else 'higher confidence'}; "
                    f"updating existing memory {dup.id}"
                ),
                superseded_memory_id=dup.id,
                metadata={"similarity": sim},
            )

        # Same fact_key, similar content → IGNORE
        if candidate.fact_key and dup.fact_key == candidate.fact_key:
            return MemoryDecision(
                candidate=candidate,
                decision=DecisionType.IGNORE,
                confidence=0.85,
                reason=(
                    f"Same fact_key ({candidate.fact_key}), similar content; "
                    f"existing memory {dup.id} has higher or equal confidence"
                ),
                superseded_memory_id=dup.id,
                metadata={"similarity": sim},
            )

        # Default: ignore near-duplicate
        return MemoryDecision(
            candidate=candidate,
            decision=DecisionType.IGNORE,
            confidence=0.8,
            reason=f"Near-duplicate of existing memory {dup.id}",
            superseded_memory_id=dup.id,
            metadata={"similarity": sim},
        )

    def _decide_on_conflict(
        self, candidate: MemoryCandidate, conflict: ExistingMemory
    ) -> MemoryDecision:
        """Decide what to do when candidate contradicts an existing memory.

        - Same fact_key + explicit request → UPDATE (user said so)
        - Same fact_key + higher confidence → UPDATE (newer info wins)
        - Same fact_key + lower confidence → IGNORE (existing is more reliable)
        - Same fact_key + equal confidence → UPDATE (newer extraction wins)
        - Ambiguous contradiction → ESCALATE
        """
        # Single-valued fact key → deterministic supersession
        if (
            candidate.fact_key
            and candidate.fact_key in SINGLE_VALUED_FACT_KEYS
        ):
            # User explicitly said something → always supersede
            if candidate.explicit_request:
                return MemoryDecision(
                    candidate=candidate,
                    decision=DecisionType.UPDATE,
                    confidence=1.0,
                    reason=(
                        "Explicit user instruction supersedes existing "
                        f"memory {conflict.id} (single-valued key "
                        f"{candidate.fact_key})"
                    ),
                    superseded_memory_id=conflict.id,
                )

            # Higher confidence → supersede
            if candidate.confidence > conflict.confidence:
                return MemoryDecision(
                    candidate=candidate,
                    decision=DecisionType.UPDATE,
                    confidence=0.85,
                    reason=(
                        f"Updated information supersedes existing memory "
                        f"{conflict.id} (single-valued key "
                        f"{candidate.fact_key}, higher confidence)"
                    ),
                    superseded_memory_id=conflict.id,
                )

            # Lower confidence → ignore (existing is more reliable)
            if candidate.confidence < conflict.confidence:
                return MemoryDecision(
                    candidate=candidate,
                    decision=DecisionType.IGNORE,
                    confidence=0.8,
                    reason=(
                        f"Lower confidence ({candidate.confidence:.2f}) than "
                        f"existing memory {conflict.id} "
                        f"({conflict.confidence:.2f}); keeping existing"
                    ),
                    superseded_memory_id=conflict.id,
                    metadata={
                        "existing_confidence": conflict.confidence,
                        "candidate_confidence": candidate.confidence,
                    },
                )

            # Equal confidence → newer extraction wins
            return MemoryDecision(
                candidate=candidate,
                decision=DecisionType.UPDATE,
                confidence=0.7,
                reason=(
                    f"Conflicting information; newer extraction supersedes "
                    f"existing memory {conflict.id} (single-valued key "
                    f"{candidate.fact_key})"
                ),
                superseded_memory_id=conflict.id,
            )

        # Multi-valued fact key + explicit user → still supersede
        if candidate.explicit_request:
            return MemoryDecision(
                candidate=candidate,
                decision=DecisionType.UPDATE,
                confidence=0.9,
                reason=(
                    "Explicit user instruction; updating existing memory "
                    f"{conflict.id}"
                ),
                superseded_memory_id=conflict.id,
            )

        # Ambiguous contradiction → ESCALATE
        return MemoryDecision(
            candidate=candidate,
            decision=DecisionType.ESCALATE,
            confidence=0.5,
            reason=(
                f"Ambiguous contradiction with existing memory {conflict.id}; "
                "requires resolution"
            ),
            superseded_memory_id=conflict.id,
            metadata={
                "existing_statement": conflict.statement,
                "candidate_statement": candidate.statement,
            },
        )

    def _decide_on_merge(
        self, candidate: MemoryCandidate, merge_target: ExistingMemory
    ) -> MemoryDecision:
        """Decide what to do with a merge candidate.

        Partial overlap → MERGE (combine evidence, keep both related).
        """
        return MemoryDecision(
            candidate=candidate,
            decision=DecisionType.MERGE,
            confidence=0.75,
            reason=(
                f"Partial overlap with existing memory {merge_target.id}; "
                "merge recommended"
            ),
            merged_memory_ids=[merge_target.id],
            metadata={
                "existing_statement": merge_target.statement,
                "candidate_statement": candidate.statement,
            },
        )

    def _candidate_matches_delete_target(
        self, candidate: MemoryCandidate, cmd: DeleteCommand
    ) -> bool:
        """Check if a candidate is what the user asked to forget.

        This covers the case where the extractor produces a candidate
        that matches a delete command — the judge should DELETE it
        rather than creating it.
        """
        sim = _text_similarity(candidate.statement, cmd.target_text)
        if sim >= SIMILARITY_MERGE_THRESHOLD:
            return True
        sim_n = _text_similarity(candidate.normalized(), _normalize_for_compare(cmd.target_text))
        return sim_n >= SIMILARITY_MERGE_THRESHOLD


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------

def create_judge(
    existing_memories: list[ExistingMemory] | None = None,
    user_consent: bool = True,
    delete_commands: list[DeleteCommand] | None = None,
) -> MemoryJudge:
    """Factory to create a MemoryJudge with sensible defaults."""
    return MemoryJudge(
        existing_memories=existing_memories or [],
        user_consent=user_consent,
        delete_commands=delete_commands or [],
    )


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from services.canonical_memory.models import MemoryCandidate, MemoryType

    # Quick self-check: a strong preference should be CREATE'd
    candidate = MemoryCandidate(
        statement="User prefers concise answers.",
        memory_type=MemoryType.PREFERENCE,
        confidence=0.9,
        importance=0.7,
        fact_key="user:prefers_tone",
        evidence="I prefer concise answers.",
    )
    judge = create_judge()
    decision = judge.judge(candidate)
    print(f"Decision: {decision.decision.value}")
    print(f"Reason: {decision.reason}")
    print(f"Confidence: {decision.confidence}")

    # Duplicate check
    existing = ExistingMemory(
        id="mem-001",
        statement="User prefers concise answers.",
        normalized_statement="user prefers concise answers.",
        memory_type="PREFERENCE",
        fact_key="user:prefers_tone",
        confidence=0.85,
        importance=0.7,
        sensitivity="normal",
        status="active",
        evidence_count=1,
        extraction_method="llm",
        explicit_request=False,
    )
    dup_judge = create_judge(existing_memories=[existing])
    dup_decision = dup_judge.judge(candidate)
    print(f"\nDuplicate test:")
    print(f"Decision: {dup_decision.decision.value}")
    print(f"Reason: {dup_decision.reason}")
    print(f"Target: {dup_decision.superseded_memory_id}")

    # Supersession test
    new_candidate = MemoryCandidate(
        statement="User prefers detailed answers.",
        memory_type=MemoryType.PREFERENCE,
        confidence=0.95,
        importance=0.7,
        fact_key="user:prefers_tone",
        evidence="Actually, I prefer detailed answers.",
    )
    sup_decision = dup_judge.judge(new_candidate)
    print(f"\nSupersession test:")
    print(f"Decision: {sup_decision.decision.value}")
    print(f"Reason: {sup_decision.reason}")
    print(f"Target: {sup_decision.superseded_memory_id}")
