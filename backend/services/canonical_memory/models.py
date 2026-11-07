"""Pydantic models for canonical memory extraction pipeline — Phase 3.

These models define the extraction boundary: MemoryCandidate is the output of
the isolated extractor, and ExtractionResult wraps candidates with provenance.
The extractor MUST NOT write these to any store directly.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
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


def compute_extraction_id(conversation_id: str, turn_window: list[dict[str, Any]]) -> str:
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


class SeekerCoreDashboard(BaseModel):
    """Compact seeker profile dashboard for Layer 4 minimal context injection.

    Anthropic research ("The Components of Agent Memory"): The preemptively loaded
    Layer 4 context must be kept small (strictly <= 120 tokens / ~480 chars) to prevent
    context poisoning.
    """

    user_id: str
    tenant_id: str = "oneness"
    preferred_language: str = "en"
    spiritual_stage: str = "seeker"
    spiritual_urgency: str = "moderate"
    seeker_journey_phase: str = "discovery"
    name: Optional[str] = None
    pronouns: Optional[str] = None
    primary_tradition: Optional[str] = None
    core_values: list[str] = Field(default_factory=list)
    key_life_context: list[str] = Field(default_factory=list)
    growth_goals: list[str] = Field(default_factory=list)
    active_challenges: list[str] = Field(default_factory=list)
    last_session_topic: Optional[str] = None
    last_discussed_at: Optional[datetime] = None
    session_count: int = 0
    active_inquiry: Optional[str] = None
    active_practices: list[str] = Field(default_factory=list)
    dominant_themes: list[str] = Field(default_factory=list)
    key_goals: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    top_memories: list[str] = Field(default_factory=list)
    summary: str = ""
    last_consolidated_at: Optional[datetime] = None
    fingerprint: str = ""

    def estimate_tokens(self) -> int:
        """Estimate token count for the rendered XML prompt block."""
        return max(1, len(self.to_system_prompt_block()) // 4)

    @property
    def core_practices(self) -> list[str]:
        return self.active_practices

    def model_post_init(self, __context: Any) -> None:
        if not self.fingerprint:
            self.fingerprint = self.compute_fingerprint()

    def compute_fingerprint(self) -> str:
        """Compute SHA-256 hash of the dashboard state for exact-cache binding."""
        state_dict = {
            "user_id": self.user_id,
            "preferred_language": self.preferred_language,
            "spiritual_stage": self.spiritual_stage,
            "active_inquiry": self.active_inquiry or "",
            "active_practices": sorted(self.active_practices),
            "dominant_themes": sorted(self.dominant_themes),
            "key_goals": sorted(self.key_goals),
        }
        raw = json.dumps(state_dict, sort_keys=True)
        fp = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.fingerprint = fp
        return fp

    def to_system_prompt_block(self) -> str:
        """Format a strict fenced XML block strictly under 120 tokens (~480 chars)."""
        lines = ["<seeker_context>"]
        lines.append(f"language: {self.preferred_language}")
        lines.append(f"stage: {self.spiritual_stage}")
        if self.active_inquiry:
            inquiry = " ".join(self.active_inquiry.split())
            if len(inquiry) > 120:
                inquiry = inquiry[:117] + "..."
            lines.append(f"inquiry: {inquiry}")
        if self.active_practices:
            clean_practices = [p.strip() for p in self.active_practices if p.strip()][:4]
            if clean_practices:
                practices_str = ", ".join(clean_practices)
                if len(practices_str) > 120:
                    practices_str = practices_str[:117] + "..."
                lines.append(f"practices: {practices_str}")
        lines.append("</seeker_context>")
        block = "\n".join(lines)
        if len(block) > 480:
            block = block[:460].rstrip() + "\n</seeker_context>"
        return block

    def to_core_content(self) -> str:
        """Format the dashboard into markdown text within guru_core_memory length limits (<= 2048 chars)."""
        lines = ["# Seeker Core Dashboard"]
        if self.summary:
            lines.append(f"Summary: {self.summary}")
        if self.active_inquiry:
            lines.append(f"Inquiry: {self.active_inquiry}")
        if self.key_goals:
            lines.append("## Goals\n" + "\n".join(f"- {g}" for g in self.key_goals[:5]))
        if self.active_practices:
            lines.append("## Core Practices\n" + "\n".join(f"- {p}" for p in self.active_practices[:5]))
        if self.preferences:
            lines.append("## Preferences\n" + "\n".join(f"- {p}" for p in self.preferences[:5]))
        if self.dominant_themes:
            lines.append(f"Themes: {', '.join(self.dominant_themes[:5])}")
        if self.top_memories:
            lines.append("## Key Insights\n" + "\n".join(f"- {m}" for m in self.top_memories[:7]))
        if self.last_consolidated_at:
            lines.append(f"\n_Last consolidated: {self.last_consolidated_at}_")
        content = "\n\n".join(lines)
        if len(content) > 2045:
            content = content[:2042] + "..."
        return content

    @classmethod
    def from_core_facts(
        cls,
        user_id: str,
        facts: list[Any],
        preferred_language: str = "en",
    ) -> SeekerCoreDashboard:
        """Construct a dashboard from raw core memory rows/claims."""
        stage = "seeker"
        lang = preferred_language or "en"
        inquiry: Optional[str] = None
        practices: list[str] = []

        for item in facts or []:
            text = ""
            if isinstance(item, dict):
                text = str(
                    item.get("content")
                    or item.get("claim")
                    or item.get("statement")
                    or ""
                ).strip()
                fact_key = str(item.get("fact_key") or "").strip().lower()
                if fact_key == "user:prefers_language" and text:
                    lang = text
                    continue
                if fact_key in ("user:stage", "user:spiritual_stage") and text:
                    stage = text
                    continue
            elif isinstance(item, str):
                text = item.strip()

            if not text:
                continue

            lower = text.lower()
            if lower.startswith("stage:") or lower.startswith("spiritual_stage:"):
                stage = text.split(":", 1)[1].strip()
            elif lower.startswith("language:") or lower.startswith("preferred_language:"):
                lang = text.split(":", 1)[1].strip()
            elif lower.startswith("inquiry:") or lower.startswith("active_inquiry:"):
                inquiry = text.split(":", 1)[1].strip()
            elif lower.startswith("practice:") or lower.startswith("practices:"):
                raw_practices = text.split(":", 1)[1].strip()
                for p in raw_practices.split(","):
                    p_clean = p.strip()
                    if p_clean and p_clean not in practices:
                        practices.append(p_clean)
            elif any(k in lower for k in ("meditat", "breathwork", "pranayama", "yoga", "vipassana", "sadhana")):
                if len(text) < 40 and text not in practices:
                    practices.append(text)
            elif inquiry is None and any(k in lower for k in ("inquiry", "seeking", "question", "struggl")):
                inquiry = text

        return cls(
            user_id=user_id,
            preferred_language=lang,
            spiritual_stage=stage,
            active_inquiry=inquiry,
            active_practices=practices,
        )


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
