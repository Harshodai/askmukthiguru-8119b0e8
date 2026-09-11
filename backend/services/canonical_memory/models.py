"""Pydantic models for canonical memory extraction pipeline — Phase 3.

These models define the extraction boundary: MemoryCandidate is the output of
the isolated extractor, and ExtractionResult wraps candidates with provenance.
The extractor MUST NOT write these to any store directly.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class MemoryType(str, Enum):
    """Memory classification — must match canonical_memories.memory_type CHECK constraint."""

    PROFILE = "PROFILE"
    PREFERENCE = "PREFERENCE"
    COMMUNICATION_STYLE = "COMMUNICATION_STYLE"
    GOAL = "GOAL"
    PROJECT = "PROJECT"
    INTEREST = "INTEREST"
    RELATIONSHIP = "RELATIONSHIP"
    USER_EXPLICIT = "USER_EXPLICIT"
    TEMPORARY_CONTEXT = "TEMPORARY_CONTEXT"
    REFLECTION = "REFLECTION"


# Single-valued fact keys that trigger supersession (not accumulation).
SINGLE_VALUED_FACT_KEYS: frozenset[str] = frozenset(
    {
        "user:lives_in",
        "user:occupation",
        "user:prefers_tone",
        "user:prefers_depth",
        "user:prefers_language",
        "user:meditation_experience",
        "user:current_project",
    }
)


class MemoryCandidate(BaseModel):
    """A single extracted memory candidate from a conversation turn.

    This is the isolated output of the extractor — it does NOT write to any store.
    The Judge (Phase 4) will decide whether to persist this candidate.
    """

    statement: str = Field(
        description="Natural-language fact about the user, self-contained and clear."
    )
    normalized_statement: Optional[str] = Field(
        default=None,
        description="Canonicalized form: lowercased, filler removed, deduplicated.",
    )
    memory_type: MemoryType = Field(
        description="Classification of the memory (PROFILE, PREFERENCE, GOAL, etc.)."
    )
    confidence: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="Extraction confidence 0.0-1.0. Direct self-report = higher, inferred = lower.",
    )
    importance: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="How critical is this memory? 0.0-1.0.",
    )
    sensitivity: str = Field(
        default="normal",
        description="Privacy sensitivity: 'normal', 'sensitive', or 'highly_sensitive'.",
    )
    fact_key: Optional[str] = Field(
        default=None,
        description="Dedup namespace (e.g. 'user:lives_in', 'user:prefers_tone'). None = multi-valued.",
    )
    evidence: str = Field(
        default="",
        description="Verbatim user utterance(s) that produced this candidate.",
    )
    source_turn_index: int = Field(
        default=0,
        description="Which turn in the input window produced this candidate.",
    )
    explicit_request: bool = Field(
        default=False,
        description="True if user said 'remember that...' or similar explicit instruction.",
    )
    extraction_id: str = Field(
        default="",
        description="Unique extraction ID for idempotency (UUID derived from conversation+window hash).",
    )
    expires_at: Optional[str] = Field(
        default=None,
        description="ISO-8601 expiry timestamp for TEMPORARY_CONTEXT memories.",
    )

    def normalized(self) -> str:
        """Return canonicalized statement for dedup comparison."""
        if self.normalized_statement:
            return self.normalized_statement.strip().lower()
        return self.statement.strip().lower()


def compute_extraction_id(
    conversation_id: str, turn_window: list[dict[str, Any]]
) -> str:
    """Derive a deterministic extraction_id from conversation_id + turn window hash.

    Same input → same extraction_id → idempotent processing.
    """
    window_bytes = json.dumps(turn_window, sort_keys=True, default=str).encode()
    window_hash = hashlib.sha256(window_bytes).hexdigest()[:16]
    return f"{conversation_id}:{window_hash}"


class ExtractionResult(BaseModel):
    """Output of the isolated extractor — list of candidates with provenance.

    The extractor MUST NOT write these to any store. The Judge and Resolver
    handle persistence decisions downstream.
    """

    candidates: list[MemoryCandidate] = Field(default_factory=list)
    extraction_id: str = Field(description="Unique ID for this extraction (idempotency key).")
    source_conversation_id: Optional[str] = Field(
        default=None, description="The conversation session that produced these candidates."
    )

    def filter_above_confidence(self, threshold: float = 0.3) -> list[MemoryCandidate]:
        """Return candidates above the confidence threshold."""
        return [c for c in self.candidates if c.confidence >= threshold]

    def by_type(self, memory_type: MemoryType) -> list[MemoryCandidate]:
        """Return candidates of a specific memory type."""
        return [c for c in self.candidates if c.memory_type == memory_type]

    def explicit_only(self) -> list[MemoryCandidate]:
        """Return only candidates from explicit user requests."""
        return [c for c in self.candidates if c.explicit_request]


if __name__ == "__main__":
    c = MemoryCandidate(
        statement="User lives in Mumbai, India.",
        memory_type=MemoryType.PROFILE,
        confidence=0.9,
        importance=0.7,
        fact_key="user:lives_in",
        evidence="I live in Mumbai.",
    )
    print(c.model_dump_json(indent=2))
    r = ExtractionResult(candidates=[c], extraction_id="test:abc123")
    print(r.model_dump_json(indent=2))
