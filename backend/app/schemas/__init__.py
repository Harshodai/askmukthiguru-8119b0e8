from __future__ import annotations

import datetime as _dt
import logging
from typing import Any, Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.compliance_provenance import (
    AIProvenanceManifest,
    ArtifactModality,  # noqa: F401
    ComplianceStandard,  # noqa: F401
    ContentCategory,  # noqa: F401
    EUComplianceRiskTier,  # noqa: F401
    GroundingSourceReference,  # noqa: F401
    OriginType,  # noqa: F401
    SoftwareAgentDescriptor,  # noqa: F401
    WatermarkType,  # noqa: F401
)
from services.user_profile_service import LanguagePreference, SpiritualLevel

logger = logging.getLogger(__name__)

_ALLOWED_ROLES = frozenset({"user", "assistant"})


class ReleaseManifestPublic(BaseModel):
    """Public projection of the release manifest.

    Only fields approved for client exposure. The full manifest (git_sha,
    model identifiers, build timestamp) stays on internal/telemetry paths.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    release_id: str = Field(..., description="Release identifier")
    policy_version: Optional[str] = Field(default=None, description="Model policy version")
    schema_version: Optional[str] = Field(default=None, description="Response schema version")


_MESSAGE_CONTENT_MAX = 10_000
_HISTORY_TURNS_MAX = 50


class MessagePayload(BaseModel):
    """Single message in the conversation history."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    role: str = Field(..., description="'user' or 'assistant'")
    # C4: bound to match ChatRequest.user_message so one history turn can never
    # carry more than one fresh user message worth of text.
    content: str = Field(..., max_length=_MESSAGE_CONTENT_MAX, description="Message text")

    @field_validator("role")
    @classmethod
    def _normalize_role(cls, v: str) -> str:
        normalized = v.strip().lower()
        if normalized not in _ALLOWED_ROLES:
            raise ValueError(f"role must be one of {sorted(_ALLOWED_ROLES)}, got {v!r}")
        return normalized


class AssistantContext(BaseModel):
    """Optional assistant override for a chat turn."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    slug: str = Field(..., description="Assistant identifier")
    system_prompt: Optional[str] = Field(
        default=None, description="Assistant-specific system persona"
    )
    knowledge_tags: list[str] = Field(
        default_factory=list, description="Tags to scope retrieval to"
    )


class ResponsePreferences(BaseModel):
    """Explicit response-form controls; never inferred from seeker traits."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    mode: Literal["balanced_guidance", "concise", "reflective_guidance", "teaching_explanation"] = (
        Field(default="balanced_guidance", description="Requested response presentation mode")
    )
    include_practice: bool = Field(
        default=True, description="Allow one bounded optional practice when safety permits"
    )
    include_reflection: bool = Field(
        default=True, description="Allow one bounded reflective follow-up when safety permits"
    )
    action_depth: Literal["none", "one_step"] = Field(
        default="one_step", description="Maximum optional action depth"
    )


_YOUTUBE_VIDEO_ID_RE = r"^[A-Za-z0-9_-]{11}$"


class PersonalizeTeachingRef(BaseModel):
    """Explicit opt-in to personalize one served teaching (T-B14).

    Identifies the served first-person clip by its YouTube video id and start
    second. The backend looks the clip up itself (video_id + start with a
    small tolerance) and never trusts client-provided text: the accompanying
    user message is the fixed prompt
    (``src/lib/chat/personalize.ts:PERSONALIZE_TEACHING_PROMPT``), which the
    pipeline keys off only to detect the intent, never for content.

    Shape validation lives here (malformed refs fail with 422 at the API
    boundary); existence and consent gating live in
    ``app/pipeline/stages/personalize_stage.py``.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    video_id: str = Field(
        ...,
        min_length=11,
        max_length=11,
        pattern=_YOUTUBE_VIDEO_ID_RE,
        description="YouTube video id of the served clip (exactly 11 chars)",
    )
    timestamp_seconds: float = Field(
        ...,
        ge=0.0,
        allow_inf_nan=False,
        description=(
            "Start second of the served clip. Citations carry "
            "floor(start_ms / 1000), so the lookup applies a small tolerance."
        ),
    )


class ChatRequest(BaseModel):
    """Chat API request body — matches frontend's sendMessage format."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    # C4 body-size budget: at most _HISTORY_TURNS_MAX turns of at most
    # _MESSAGE_CONTENT_MAX chars each (~500k chars worst case, matching the
    # user_message 10k + attachment_context 8k single-turn caps below), so one
    # request cannot blow the pipeline context, cost or latency budgets no
    # matter how long the client-side history grows.
    messages: list[MessagePayload] = Field(
        ..., max_length=_HISTORY_TURNS_MAX, description="Conversation history"
    )
    user_message: str = Field(
        ..., min_length=1, max_length=10000, description="Current user message"
    )
    session_id: Optional[str] = Field(None, description="Optional session ID")
    conversation_summary: Optional[str] = Field(
        default=None,
        max_length=4000,
        description=(
            "Optional compact summary intentionally carried into a fresh continuation chat; "
            "never treated as the original transcript and ignored for Temporary Chat."
        ),
    )
    meditation_step: int = Field(default=0, description="Current meditation step (0 = none)")
    language: Optional[str] = Field(default="en", description="Preferred language")
    incognito: bool = Field(
        default=False,
        description="Ephemeral privacy mode; disables persistence, memory, and shared reuse.",
    )
    cache_bypass: bool = Field(
        default=False,
        description=(
            "Evaluation control: take the cold path for this request without "
            "disabling any other layer. Distinct from incognito, which is a "
            "privacy boundary and also suppresses memory — using incognito as "
            "a cache switch measures the system with memory absent. See "
            "docs/EVAL_PRECONDITIONS.md."
        ),
    )
    response_preferences: ResponsePreferences = Field(
        default_factory=ResponsePreferences,
        description="Explicit response-form preferences; disabled from persistence in incognito.",
    )
    last_serene_mind_at: Optional[float] = Field(
        default=None,
        description="Unix timestamp of the user's last completed Serene Mind session (client-reported)",
    )
    assistant: Optional[AssistantContext] = Field(
        default=None,
        description="Optional assistant context to scope persona and retrieval",
    )
    attachment_context: Optional[str] = Field(
        default=None,
        max_length=8000,
        description=(
            "Ephemeral, pre-extracted evidence from user attachments. The upload route "
            "returns this value; it is never persisted or indexed automatically."
        ),
    )
    guru_tone: Optional[Literal["gentle", "direct", "poetic"]] = Field(
        default=None,
        description=(
            "User-selected answer voice from the profile (gentle is the default and "
            "adds no style block). Applied as a generation-time persona hint, never "
            "as a post-hoc rewrite, so citations stay source-qualified."
        ),
    )
    personalize_teaching: Optional[PersonalizeTeachingRef] = Field(
        default=None,
        description=(
            "T-B14 explicit opt-in: personalize the served teaching identified by "
            "this ref. The backend looks the clip up itself and runs the general "
            "graph only for signed-in, non-incognito seekers with a personal "
            "knowledge graph; every other turn stays first-person-only."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _drop_client_system_messages(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        messages = data.get("messages")
        if not isinstance(messages, list):
            return data
        kept: list[Any] = []
        for msg in messages:
            if isinstance(msg, dict):
                role = str(msg.get("role", "")).strip().lower()
                if role not in _ALLOWED_ROLES:
                    logger.warning(
                        "Dropping client message with disallowed role=%r; only user/assistant "
                        "roles are forwarded to generation. content prefix=%r",
                        msg.get("role"),
                        str(msg.get("content", ""))[:60],
                    )
                    continue
            kept.append(msg)
        data["messages"] = kept
        return data

    @field_validator("user_message")
    @classmethod
    def _validate_user_message(cls, v: str) -> str:
        if "\x00" in v:
            raise ValueError("Null bytes are not allowed in user_message")
        return v


class ProfileUpdate(BaseModel):
    """Schema for updating user profile."""

    preferred_language: Optional[str] = Field(None, description="Preferred language code")
    spiritual_level: Optional[str] = Field(None, description="Spiritual level")
    topics_of_interest: Optional[list[str]] = Field(
        None, description="Topics the user is interested in"
    )
    codemix_preference: Optional[bool] = Field(None, description="Prefer code-mixed responses")

    @field_validator("preferred_language")
    @classmethod
    def validate_language(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            valid = {m.value for m in LanguagePreference}
            if v not in valid:
                raise ValueError(f"Must be one of {valid}")
        return v

    @field_validator("spiritual_level")
    @classmethod
    def validate_spiritual_level(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            valid = {m.value for m in SpiritualLevel}
            if v not in valid:
                raise ValueError(f"Must be one of {valid}")
        return v

    @field_validator("topics_of_interest")
    @classmethod
    def validate_topics(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is not None:
            for t in v:
                if len(t) > 200:
                    raise ValueError(f"Topic too long (max 200 chars): {t[:50]}...")
        return v


class Citation(BaseModel):
    """A single cited source: its URL and, when known, its real title.

    `title` is resolved server-side from the Qdrant document payload (or the
    live-search/official result) behind the citation — never guessed or
    synthesized. The frontend falls back to a domain-derived label when it
    is None.
    """

    url: str = Field(..., description="Absolute HTTP(S) source URL")
    title: Optional[str] = Field(None, description="Real source title, when known")
    chunk_provenance: Optional[str] = Field(
        None,
        description=(
            "services.provenance.ChunkProvenance value for the chunk this citation "
            "came from (verbatim_speech/polished_speech/third_party_prose/"
            "machine_summary) — lets a reviewer confirm this was the teachers' own "
            "words without re-querying Qdrant. GURU_DEMO_READINESS F4."
        ),
    )
    speaker: Optional[str] = Field(None, description="Speaker attribution for the source chunk")
    speaker_verified: Optional[bool] = Field(
        None,
        description=(
            "True only when the source payload marks the speaker as verified. "
            "No ingestion stage sets this yet (voice verification is not wired into "
            "ingest/pipeline.py), so it is currently always None or False."
        ),
    )
    timestamp_seconds: Optional[float] = Field(
        None,
        description=(
            "Second offset into the source video this citation points to, when the "
            "retrieved chunk's payload carries one (timestamp_seconds/start_ms/"
            "start/start_time/timestamp/start_sec). Most chat-corpus chunks carry "
            "none of these today, so this is usually None -- never fabricated "
            "to give the player a fake start point. A real 0.0 is a valid start."
        ),
    )
    text_snippet: Optional[str] = Field(
        None, description="Exact source text (retrieved chunk) this citation points to"
    )
    transcript_status: Optional[str] = Field(
        None,
        description=(
            "First-person clips only: 'auto_transcript' unless a human reviewed the "
            "transcript and it carries no ASR word restarts, then 'reviewed'. A label, "
            "never a text edit (services/first_person_pipeline.transcript_label). None "
            "for non-first-person citations."
        ),
    )
    asr_artifacts: Optional[list[str]] = Field(
        None,
        description="First-person clips only: words the ASR decoder restarted on.",
    )


class ChatResponse(BaseModel):
    """Chat API response body."""

    response: str = Field(..., description="Guru's response")
    intent: Optional[str] = Field(None, description="Detected intent")
    meditation_step: int = Field(default=0, description="Next meditation step")
    citations: list[Citation] = Field(default_factory=list, description="Cited sources")
    blocked: bool = Field(default=False, description="Was the message blocked?")
    block_reason: Optional[str] = Field(None, description="Why it was blocked")
    proactive_serene_mind: Optional[dict] = Field(
        None, description="Proactive Serene Mind trigger details"
    )
    faithfulness_score: Optional[float] = Field(None, description="Self-RAG faithfulness score")
    relevancy_score: Optional[float] = Field(None, description="Answer relevancy score")
    confidence_score: Optional[float] = Field(None, description="Verifier confidence score")
    verification: Optional[dict] = Field(None, description="CoVe/Self-RAG verification result")
    hallucination_flag: Optional[bool] = Field(
        None, description="Whether verification flagged hallucination risk"
    )
    cache_hit: bool = Field(default=False, description="Whether the response came from cache")
    trace_id: Optional[str] = Field(None, description="Trace/query ID for observability")
    latency_ms: Optional[int] = Field(
        None, description="End-to-end response latency in milliseconds"
    )
    node_timings: Optional[dict] = Field(
        None, description="Per-node LangGraph timings in milliseconds"
    )
    evaluation_trace: Optional[dict] = Field(
        None, description="Trajectory metadata for benchmark and production AI evaluation"
    )
    retrieval_metadata: Optional[dict] = Field(
        default=None,
        description=(
            "Which retrieval lanes contributed to this answer — Qdrant dense/"
            "sparse, OKF, Neo4j subgraph, LightRAG. Already computed on "
            "PipelineResult; withheld from the response until 2026-09-14, "
            "which made component attribution log-only."
        ),
    )
    citations_verified: Optional[bool] = Field(
        None, description="Whether inline citations were verified against retrieved sources"
    )
    orphan_citations_stripped: Optional[bool] = Field(
        None, description="Whether any orphan citation markers were stripped from the answer"
    )
    model_used: Optional[str] = Field(None, description="Underlying LLM model used")
    model_provider: Optional[str] = Field(None, description="Underlying LLM provider")
    route_decision: Optional[str] = Field(None, description="Model/routing decision")
    query_tier: Optional[str] = Field(None, description="Graph variant used (fast, standard, deep)")
    follow_up_suggestions: list[str] = Field(
        default_factory=list,
        description="Claude-style suggested follow-up questions for the user",
    )
    audio_url: Optional[str] = Field(
        default=None,
        description="Matched guided meditation or wisdom practice audio track",
    )
    kg_concept_nodes: list[str] = Field(
        default_factory=list,
        description="Interactive Knowledge Graph concept tags associated with the answer",
    )
    daily_practice_card: Optional[dict[str, Any]] = Field(
        default=None,
        description="Actionable daily inner growth practice card recommendation",
    )

    guidance_plan: Optional[dict[str, Any]] = Field(
        default=None,
        description="Structured, source-aware presentation guidance for a response",
    )
    answer_evidence: Optional[dict[str, Any]] = Field(
        None,
        description="Typed evidence provenance for a response",
    )
    personalization_provenance: Optional[dict[str, Any]] = Field(
        default=None,
        description="Public-safe explanation of personal context classes provided to this answer; never includes raw private memory text.",
    )
    # Must list every state the pipeline actually emits. The previous 4-value
    # Literal omitted bounded_hypothetical, capability_answer,
    # provenance_boundary and response_format_capability — all of which
    # rag/nodes/generation.py produces — so constructing a ChatResponse on
    # those paths raised ValidationError (verified: three of the four fail
    # against the old Literal). Widening the contract to match the code; the
    # alternative reading, that the contract was right and the code wrong,
    # would mean deleting four working response modes.
    grounding_state: Literal[
        "grounded",
        "abstained",
        "safety_redirect",
        "system_error",
        "bounded_hypothetical",
        "capability_answer",
        "provenance_boundary",
        "response_format_capability",
        # General-assistant answers are explicitly not corpus-grounded. The
        # general-knowledge lane (rag/nodes/verification.py:427,622 and
        # rag/nodes/generation.py:3998) emits this value, so omitting it made a
        # normal answer raise ValidationError and return 500.
        "unverified",
    ] = Field(
        default="abstained",
        description="Truthful final state of retrieval and response grounding",
    )
    release_manifest: Optional[ReleaseManifestPublic] = Field(
        default=None,
        description="Public release provenance and policy projection",
    )
    provenance_manifest: Optional[AIProvenanceManifest] = Field(
        default=None,
        description="EU AI Act Article 50 & W3C PROV-O compliance manifest",
    )
    ai_provenance: Optional[dict[str, Any]] = Field(
        default=None,
        description="EU AI Act Article 50 provenance manifest",
    )


class LiveLogisticsEvent(BaseModel):
    """Verified metadata for an official event, booking, or schedule result."""

    event_name: str = Field(..., min_length=1, max_length=300)
    official_source_url: str = Field(..., min_length=8, max_length=2000)
    booking_url: Optional[str] = Field(default=None, max_length=2000)
    verified_at: _dt.datetime
    expires_at: _dt.datetime

    @field_validator("official_source_url", "booking_url")
    @classmethod
    def validate_official_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("live logistics URLs must be absolute HTTPS URLs")
        return value


def parse_chat_request_json(raw_json: str) -> ChatRequest:
    """Parse a raw JSON body into ChatRequest via Pydantic v2 native path.

    Uses model_validate_json() (single-pass, no intermediate dict) instead of
    json.loads + model_validate.
    """
    return ChatRequest.model_validate_json(raw_json)


def parse_message_payload_json(raw_json: str) -> MessagePayload:
    """Parse a raw JSON body into MessagePayload via model_validate_json()."""
    return MessagePayload.model_validate_json(raw_json)
