"""Canonical first-person context contract (fp-context-v1).

This module is the single source of truth for the parent/child context schema
described in ``FIRST_PERSON_CONTEXT_HARNESS_AND_TAGGING_PLAN_2026-10-20.md``.
It is deliberately free of Qdrant, LLM, Redis, and FastAPI imports: enums,
frozen models, deterministic identifiers, and pure conversion helpers only.
The Qdrant adapter and the harness depend on this module, never the reverse.

Two deviations from the plan document are intentional and documented here
because the existing corpus cannot satisfy the document as written:

1. ``SourceSpan.transcript_hash`` is video-level in the current indexer (it
   hashes the verbatim transcript layer for the whole video), so it cannot be
   compared with ``sha256(verbatim_text)``. The clip-level equality check lives
   on ``source_text_hash``, which is computed at build time.
2. ``provider_span_id`` style free-form tags are rejected. ``extra="forbid"``
   means a payload carrying an unknown field fails closed instead of silently
   importing untyped metadata into serving.
"""

from __future__ import annotations

from enum import StrEnum
from hashlib import sha256
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "fp-context-v1"
# Versioned independently of the record schema so a boundary/annotation revision
# can invalidate caches without renaming the collection.
PARENT_VERSION = "parent-v1"
EDGE_ANNOTATION_VERSION = "annotation-v1"


class SpeakerRole(StrEnum):
    GURU = "guru"
    HOST = "host"
    GUEST = "guest"
    UNKNOWN = "unknown"


class BoundaryStatus(StrEnum):
    VERIFIED = "verified"
    REPAIRED = "repaired"
    UNCERTAIN = "uncertain"


class CompletenessStatus(StrEnum):
    COMPLETE = "complete"
    FRAGMENT = "fragment"
    UNCERTAIN = "uncertain"


class ProvenanceKind(StrEnum):
    SPEECH_TURN_SPAN = "speech_turn_span"
    PARENT_CONTEXT = "parent_context"
    HOST_QUESTION = "host_question"
    SYSTEM_LABEL = "system_label"


class AnswerRole(StrEnum):
    DIRECT = "direct"
    SUPPORTING = "supporting"
    ANTECEDENT = "antecedent"
    CONSEQUENCE = "consequence"
    CONTRAST = "contrast"


class TextOrigin(StrEnum):
    ASR_VOTED = "asr_voted"
    DISPLAY_PUNCT = "display_punct"
    MD_DISPLAY = "md_display"
    HUMAN_EDIT = "human_edit"


class EdgeType(StrEnum):
    PREVIOUS = "previous"
    NEXT = "next"
    INTRODUCED_BY = "introduced_by"
    EXPLAINS = "explains"
    SAME_TOPIC = "same_topic"
    HOST_QUESTION = "host_question"


class EdgeStatus(StrEnum):
    DETERMINISTIC = "deterministic"
    REVIEWED = "reviewed"
    CANDIDATE = "candidate"


class AnnotationStatus(StrEnum):
    CANDIDATE = "candidate"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    REJECTED = "rejected"


class LinkType(StrEnum):
    NAME = "name"
    ALIAS = "alias"
    PRONOUN = "pronoun"
    DESCRIPTOR = "descriptor"


class HarnessState(StrEnum):
    RETRIEVED = "RETRIEVED"
    GROUPED_BY_PARENT = "GROUPED_BY_PARENT"
    CONTEXT_EXPANDED = "CONTEXT_EXPANDED"
    SPEAKER_GATE = "SPEAKER_GATE"
    RIGHTS_GATE = "RIGHTS_GATE"
    HASH_GATE = "HASH_GATE"
    COMPLETENESS_GATE = "COMPLETENESS_GATE"
    COREFERENCE_GATE = "COREFERENCE_GATE"
    ANSWERABILITY_GATE = "ANSWERABILITY_GATE"
    RECONSTRUCTED_FROM_SPANS = "RECONSTRUCTED_FROM_SPANS"
    CITATION_AND_AUDIO_GATE = "CITATION_AND_AUDIO_GATE"
    SERVE = "SERVE"


class HarnessDecision(StrEnum):
    SERVE_SINGLE_SPAN = "serve_single_span"
    SERVE_PARENT_CONTEXT = "serve_parent_context"
    SERVE_RELATED_NOT_DIRECT = "serve_related_not_direct"
    ASK_CLARIFYING_QUESTION = "ask_clarifying_question"
    ABSTAIN = "abstain"


def clip_text_hash(verbatim_text: str) -> str:
    """Clip-level hash. Must mirror ``services.transcript_verbatim`` hashing."""
    return sha256(verbatim_text.encode("utf-8")).hexdigest()


def make_source_span_id(
    *,
    guru_id: str,
    video_id: str,
    corpus_version: str,
    word_start: int,
    word_end: int,
    transcript_hash: str,
) -> str:
    payload = f"{guru_id}|{video_id}|{corpus_version}|{word_start}|{word_end}|{transcript_hash}"
    return sha256(payload.encode("utf-8")).hexdigest()


def make_parent_unit_id(
    *,
    guru_id: str,
    video_id: str,
    corpus_version: str,
    first_word_index: int,
    last_word_index: int,
) -> str:
    payload = f"{guru_id}|{video_id}|{corpus_version}|{first_word_index}|{last_word_index}"
    return sha256(payload.encode("utf-8")).hexdigest()


def make_edge_id(*, corpus_version: str, from_span_id: str, to_span_id: str, edge_type: str) -> str:
    payload = f"{corpus_version}|{from_span_id}|{to_span_id}|{edge_type}"
    return sha256(payload.encode("utf-8")).hexdigest()


class SourceSpan(BaseModel):
    """One immutable, citable unit of teacher speech."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["fp-context-v1"] = SCHEMA_VERSION
    corpus_version: str = Field(min_length=1)
    guru_id: str = Field(min_length=1)
    video_id: str = Field(min_length=1)
    source_asset_id: str = Field(min_length=1)
    source_span_id: str = Field(min_length=1)
    parent_unit_id: str = Field(min_length=1)
    turn_id: str = Field(min_length=1)
    turn_index: int = Field(ge=0)
    source_span_index: int = Field(ge=0)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    word_start: int = Field(ge=0)
    word_end: int = Field(gt=0)
    speaker_id: str = Field(min_length=1)
    speaker_role: SpeakerRole
    speaker_verified: bool
    source_transcript_text: str = Field(min_length=1)
    verbatim_text: str = Field(min_length=1)
    transcript_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_text_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    is_verbatim: Literal[True] = True
    boundary_status: BoundaryStatus
    completeness_status: CompletenessStatus
    rights_cleared: bool
    caption_status: str = Field(min_length=1)
    provenance_kind: ProvenanceKind = ProvenanceKind.SPEECH_TURN_SPAN
    previous_span_id: str | None = None
    next_span_id: str | None = None
    question_span_id: str | None = None
    entity_ids: tuple[str, ...] = ()
    alias_ids: tuple[str, ...] = ()
    coreference_chain_ids: tuple[str, ...] = ()
    topic_ids: tuple[str, ...] = ()
    facet_ids: tuple[str, ...] = ()
    speech_act: str | None = None
    answer_role: AnswerRole = AnswerRole.DIRECT
    voice_verification_method: str | None = None
    # Speaker-verification provenance (P1). Flat keys so Qdrant can filter on each. All
    # optional: payloads written before these existed must still load, and the rule that a
    # verified span carries them is enforced at WRITE time (domain.speaker_provenance), not
    # here, so the live spans that predate it stay readable until the backfill.
    voice_model_revision: str | None = None
    voice_score: float | None = None
    voice_margin: float | None = None
    # {"cosine_floor": float, "margin_threshold": float} in force when the verdict was made.
    voice_threshold_applied: dict[str, float] | None = None
    voice_calibration_id: str | None = None
    voice_window_check: Literal["pass", "fail", "no_diarization"] | None = None
    voice_verified_at: str | None = None
    speaker_verification_status: (
        Literal["verified", "ecapa_failed", "pending_voice_check", "pending_listen"] | None
    ) = None
    # Human listen (method ``human_listen_v1``) only.
    reviewer_id: str | None = None
    reviewed_at: str | None = None
    review_guidelines_version: str | None = None
    reviewed_audio_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    review_choice: (
        Literal["sri_krishnaji", "sri_preethaji", "host_or_interviewer", "other", "unclear"] | None
    ) = None
    asr_engine: str | None = None
    asr_model_version: str | None = None
    # ISO 639-1 code of the language SPOKEN in this span, from a language-ID step (audit
    # D10). None on every span built so far: undeclared means the English corpus, and the
    # serve-time text gate then expects Latin script. A span in another language must
    # declare it to be served; the gate then expects that language's script.
    language: str | None = None
    retrieval_text_version: str = "fp-retrieval-v1"
    contextual_header_version: str | None = None
    source_url: str = Field(min_length=1)
    quality_status: str = "verified_verbatim"
    quarantine_reason: str | None = None
    embedding_model: str | None = None
    embedding_revision: str | None = None
    embedded_text_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    window_count: int | None = Field(default=None, ge=0)
    min_window_cosine: float | None = None
    foreign_window_count: int | None = Field(default=None, ge=0)
    # Origin of the stored text. ``None`` means "not recorded by the producer",
    # which is the honest state for spans carried over from a payload that never
    # said where its text came from. Builders that know set it explicitly; a
    # default of ``asr_voted`` would assert provenance nobody verified.
    text_origin: TextOrigin | None = None
    # sha256 of the on-disk artifact the span's coordinates came from. Distinct
    # from ``transcript_hash``, which hashes the transcript body because it is
    # part of the span id. ``None`` when the producer did not read an artifact it
    # could hash (a payload carry-over).
    source_artifact_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @field_validator("end_ms")
    @classmethod
    def _end_after_start(cls, value: int, info: Any) -> int:
        start = info.data.get("start_ms")
        if start is not None and value <= start:
            raise ValueError("end_ms must be greater than start_ms")
        return value

    @field_validator("word_end")
    @classmethod
    def _word_end_after_start(cls, value: int, info: Any) -> int:
        start = info.data.get("word_start")
        if start is not None and value <= start:
            raise ValueError("word_end must be greater than word_start")
        return value

    @field_validator("source_text_hash")
    @classmethod
    def _hash_matches_verbatim(cls, value: str, info: Any) -> str:
        text = info.data.get("verbatim_text")
        if text is not None and clip_text_hash(text) != value:
            raise ValueError("source_text_hash must match verbatim_text exactly")
        return value

    @model_validator(mode="after")
    def _identity_is_deterministic(self) -> SourceSpan:
        expected = make_source_span_id(
            guru_id=self.guru_id,
            video_id=self.video_id,
            corpus_version=self.corpus_version,
            word_start=self.word_start,
            word_end=self.word_end,
            transcript_hash=self.transcript_hash,
        )
        if self.source_span_id != expected:
            raise ValueError("source_span_id is not the deterministic id for this span")
        return self

    def to_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload["record_type"] = "retrieval_child"
        return payload

    def retrieval_text(self, contextual_header: str = "") -> str:
        """Text used for embedding only — never rendered as teacher speech."""
        header = contextual_header.strip()
        return f"{header}\n{self.verbatim_text}" if header else self.verbatim_text

    def validate_release_grade(self) -> list[str]:
        """Validate whether this span meets public release grade standards.

        Returns a list of defect reasons. An empty list indicates the span
        is public-release grade.
        """
        defects: list[str] = []
        if self.speaker_verified and not self.voice_verification_method:
            defects.append("speaker_verified_without_method")

        from ingest.verbatim.boundaries import boundary_defects

        b_defects = boundary_defects(self.verbatim_text.split())
        if self.boundary_status == BoundaryStatus.VERIFIED and b_defects:
            defects.append(f"boundary_status_verified_with_defects:{','.join(b_defects)}")

        if self.contextual_header_version is not None:
            defects.append("unverified_contextual_header_claimed")

        duration_s = (self.end_ms - self.start_ms) / 1000.0
        if duration_s < 8.0 or duration_s > 60.0:
            defects.append(f"duration_out_of_band:{duration_s:.1f}s")

        return defects


class ParentUnit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["fp-context-v1"] = SCHEMA_VERSION
    corpus_version: str = Field(min_length=1)
    guru_id: str = Field(min_length=1)
    video_id: str = Field(min_length=1)
    parent_unit_id: str = Field(min_length=1)
    ordered_source_span_ids: tuple[str, ...] = Field(min_length=1)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    parent_text_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    speaker_ids: tuple[str, ...] = Field(min_length=1)
    speaker_continuity: bool
    boundary_status: BoundaryStatus
    completeness_status: CompletenessStatus
    host_question_span_id: str | None = None
    parent_version: str = PARENT_VERSION

    @model_validator(mode="after")
    def _ordered_spans_unique(self) -> ParentUnit:
        if len(set(self.ordered_source_span_ids)) != len(self.ordered_source_span_ids):
            raise ValueError("ordered_source_span_ids must not repeat a span")
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        return self

    def to_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload["record_type"] = "parent_unit"
        return payload


class ContextEdge(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["fp-context-v1"] = SCHEMA_VERSION
    edge_id: str = Field(min_length=1)
    guru_id: str = Field(min_length=1)
    video_id: str = Field(min_length=1)
    from_span_id: str = Field(min_length=1)
    to_span_id: str = Field(min_length=1)
    edge_type: EdgeType
    status: EdgeStatus
    confidence: float = Field(ge=0.0, le=1.0)
    created_by: str = Field(min_length=1)
    annotation_version: str = Field(default=EDGE_ANNOTATION_VERSION, min_length=1)
    model_version: str | None = None
    corpus_version: str | None = None

    @model_validator(mode="after")
    def _no_self_edge(self) -> ContextEdge:
        if self.from_span_id == self.to_span_id:
            raise ValueError("a context edge must connect two distinct spans")
        return self

    @property
    def is_servable(self) -> bool:
        """Only deterministic or reviewed edges may expand a served context."""
        return self.status in (EdgeStatus.DETERMINISTIC, EdgeStatus.REVIEWED)


class EntityAnnotation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["fp-context-v1"] = SCHEMA_VERSION
    annotation_id: str = Field(min_length=1)
    guru_id: str = Field(min_length=1)
    video_id: str = Field(min_length=1)
    span_id: str = Field(min_length=1)
    surface_form: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    link_type: LinkType
    status: AnnotationStatus
    confidence: float = Field(ge=0.0, le=1.0)
    created_by: str = Field(min_length=1)
    model_version: str | None = None
    annotation_version: str = Field(min_length=1)

    @property
    def is_servable(self) -> bool:
        return self.status is AnnotationStatus.APPROVED


class ParentContext(BaseModel):
    """Retriever output: a parent plus the child spans that produced the hit."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    parent: ParentUnit
    spans: tuple[SourceSpan, ...] = Field(min_length=1)
    hit_span_ids: tuple[str, ...] = Field(min_length=1)
    score: float = 0.0

    @model_validator(mode="after")
    def _hit_ids_are_in_spans(self) -> ParentContext:
        span_ids = {s.source_span_id for s in self.spans}
        if not set(self.hit_span_ids) <= span_ids:
            raise ValueError("hit_span_ids must all be present in spans")
        if any(s.parent_unit_id != self.parent.parent_unit_id for s in self.spans):
            raise ValueError("every span must belong to the parent unit")
        if any(s.guru_id != self.parent.guru_id for s in self.spans):
            raise ValueError("every span must belong to the parent guru")
        if any(s.video_id != self.parent.video_id for s in self.spans):
            raise ValueError("every span must belong to the parent video")
        if any(s.corpus_version != self.parent.corpus_version for s in self.spans):
            raise ValueError("every span must belong to the parent corpus_version")
        parent_ordered_set = set(self.parent.ordered_source_span_ids)
        if any(s.source_span_id not in parent_ordered_set for s in self.spans):
            raise ValueError(
                "every span source_span_id must appear in parent.ordered_source_span_ids"
            )
        return self


class CitationSpan(BaseModel):
    """Exactly what the UI may render, and where the audio starts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_span_id: str
    video_id: str
    guru_id: str
    text: str = Field(min_length=1)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    source_url: str = Field(min_length=1)
    label: str | None = None


class RetrievalDecision(BaseModel):
    """Harness output. ``answer_text`` is reconstructed, never model-authored."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: HarnessDecision
    state: HarnessState
    guru_id: str
    parent_unit_id: str | None = None
    source_span_ids: tuple[str, ...] = ()
    context_edges_used: tuple[str, ...] = ()
    speaker_boundary_passed: bool = False
    context_sufficiency: Literal["sufficient", "insufficient", "unknown"] = "unknown"
    llm_used: bool = False
    llm_role: Literal["selector_only", "none"] = "none"
    answer_text_reconstructed: bool = False
    citations_verified: bool = False
    answer_text: str | None = None
    citations: tuple[CitationSpan, ...] = ()
    gates: dict[str, bool] = Field(default_factory=dict)
    abstain_reason: str | None = None
    # Observability (Phase F5): every state the harness entered, in order, plus
    # the gate that produced an abstain/related outcome. A dashboard can chart
    # state_path and abstain_stage without parsing free-text logs.
    state_path: tuple[HarnessState, ...] = ()
    abstain_stage: HarnessState | None = None
