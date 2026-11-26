"""Canonical Evidence Contract & Four-Category Epistemic Model.

Defines the normalized evidence interface shared across Qdrant, Memgraph, OKF,
the Canonical Evidence Registry, Seeker Intelligence, and Editorial Intelligence.
Database-specific record formats must be normalized at adapter boundaries and
must not leak into orchestration or application layers.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SourceType(str, Enum):
    VIDEO = "video"
    INTERVIEW = "interview"
    PODCAST = "podcast"
    BOOK = "book"
    AUDIO = "audio"
    WEBSITE = "website"
    COURSE_EVENT = "course_event"
    DOCUMENT = "document"


class EpistemicCategory(str, Enum):
    """Strict epistemic separation required across Seeker & Editorial outputs."""

    VERBATIM_EVIDENCE = "verbatim_evidence"
    VERIFIED_CORRECTION = "verified_correction"
    PARAPHRASE = "paraphrase"
    INTERPRETATION = "interpretation"
    SYNTHESIS = "synthesis"
    APPLICATION = "application"
    EDITORIAL_NARRATION = "editorial_narration"


class VerificationStatus(str, Enum):
    UNVERIFIED = "unverified"
    AUTOMATED_CANDIDATE = "automated_candidate"
    HUMAN_VERIFIED = "human_verified"
    QUARANTINED = "quarantined"
    REVOKED = "revoked"


class RetrievalSource(str, Enum):
    QDRANT = "qdrant"
    MEMGRAPH = "memgraph"
    OKF = "okf"
    CANONICAL_REGISTRY = "canonical_registry"


def content_sha256(text: str) -> str:
    """Deterministic SHA-256 hash of whitespace-normalized UTF-8 text."""
    normalized = " ".join((text or "").split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def make_source_id(canonical_uri: str) -> str:
    """Deterministic UUIDv5 source identifier from canonical URI or document ref."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"source:{canonical_uri.strip()}"))


def make_evidence_id(
    *,
    source_id: str,
    source_version: str,
    segment_version: str,
    locator: str,
    text_hash: str,
) -> str:
    """Deterministic canonical evidence ID across Qdrant, Memgraph, OKF, and Postgres."""
    key = f"evidence:{source_id}:{source_version}:{segment_version}:{locator}:{text_hash}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


class CanonicalEvidenceRecord(BaseModel):
    """Immutable original source record with optional versioned correction metadata."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    source_id: str
    teacher_id: str | None = None
    source_type: SourceType
    source_title: str = ""
    canonical_uri: str = ""
    original_text: str
    corrected_text: str | None = None
    start_time_ms: int | None = None
    end_time_ms: int | None = None
    page_number: int | None = None
    chapter: str | None = None
    language: str = "en"
    concepts: list[str] = Field(default_factory=list)
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    transcription_confidence: float | None = None
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    rights_status: str = "unverified"
    speaker_verified: bool = False
    source_version: str = "1"
    transcript_version: str = "1"
    segment_version: str = "1"
    chunker_version: str = "unknown_legacy"
    content_hash: str = ""
    ingestion_model_version: str = ""
    provenance: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EvidenceCandidate(BaseModel):
    """Normalized retrieval candidate returned by Qdrant, Memgraph, and OKF adapters."""

    model_config = ConfigDict(extra="ignore")

    evidence_id: str
    source_id: str
    source_type: str = "video"
    source_title: str = ""
    source_url: str = ""
    teacher_id: str | None = None
    speaker_label: str | None = None
    speaker_verified: bool = False
    text: str
    start_time: float | None = None
    end_time: float | None = None
    page_number: int | None = None
    chapter: str | None = None
    language: str = "en"
    retrieval_source: str
    retrieval_score: float | None = None
    rrf_score: float | None = None
    rerank_score: float | None = None
    corroborating_sources: list[str] = Field(default_factory=list)
    source_version: str = "1"
    verification_status: str = "unverified"
    rights_status: str = "unverified"
    content_hash: str | None = None
    surrounding_context: str | None = None
    concepts: list[str] = Field(default_factory=list)
    graph_paths: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)

    @property
    def dedup_key(self) -> str:
        """Canonical identity used to prevent counting one passage N times across stores."""
        if self.evidence_id:
            return self.evidence_id
        loc = f"{self.start_time}:{self.page_number}"
        return f"{self.source_id}:{loc}:{content_sha256(self.text)}"


class ClaimEvidenceMapping(BaseModel):
    """Maps a single generated or editorial claim to its supporting evidence IDs."""

    model_config = ConfigDict(extra="forbid")

    claim_id: str
    claim_text: str
    epistemic_category: EpistemicCategory
    teacher_attributed: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    verification_status: Literal[
        "verified",
        "unsupported",
        "misattributed",
        "quote_mismatch",
        "outdated_version",
        "ai_labeled",
    ] = "unsupported"
    notes: str = ""


class ClaimVerificationReport(BaseModel):
    """Aggregate verification outcome across an answer or editorial script."""

    model_config = ConfigDict(extra="forbid")

    passed: bool
    mappings: list[ClaimEvidenceMapping] = Field(default_factory=list)
    unsupported_count: int = 0
    misattributed_count: int = 0
    quote_mismatch_count: int = 0
    outdated_version_count: int = 0
    summary: str = ""
