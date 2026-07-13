from __future__ import annotations

import logging
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from services.user_profile_service import LanguagePreference, SpiritualLevel

logger = logging.getLogger(__name__)

_ALLOWED_ROLES = frozenset({"user", "assistant"})


class MessagePayload(BaseModel):
    """Single message in the conversation history."""

    role: str = Field(..., description="'user' or 'assistant'")
    content: str = Field(..., description="Message text")

    @field_validator("role")
    @classmethod
    def _normalize_role(cls, v: str) -> str:
        normalized = v.strip().lower()
        if normalized not in _ALLOWED_ROLES:
            raise ValueError(
                f"role must be one of {sorted(_ALLOWED_ROLES)}, got {v!r}"
            )
        return normalized


class AssistantContext(BaseModel):
    """Optional assistant override for a chat turn."""

    slug: str = Field(..., description="Assistant identifier")
    system_prompt: Optional[str] = Field(default=None, description="Assistant-specific system persona")
    knowledge_tags: list[str] = Field(default_factory=list, description="Tags to scope retrieval to")


class ChatRequest(BaseModel):
    """Chat API request body — matches frontend's sendMessage format."""

    messages: list[MessagePayload] = Field(..., description="Conversation history")
    user_message: str = Field(..., min_length=1, max_length=10000, description="Current user message")
    session_id: Optional[str] = Field(None, description="Optional session ID")
    meditation_step: int = Field(default=0, description="Current meditation step (0 = none)")
    language: Optional[str] = Field(default="en", description="Preferred language")
    last_serene_mind_at: Optional[float] = Field(
        default=None,
        description="Unix timestamp of the user's last completed Serene Mind session (client-reported)",
    )
    assistant: Optional[AssistantContext] = Field(
        default=None,
        description="Optional assistant context to scope persona and retrieval",
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


class ProfileUpdate(BaseModel):
    """Schema for updating user profile."""

    preferred_language: Optional[str] = Field(None, description="Preferred language code")
    spiritual_level: Optional[str] = Field(None, description="Spiritual level")
    topics_of_interest: Optional[list[str]] = Field(None, description="Topics the user is interested in")
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


class ChatResponse(BaseModel):
    """Chat API response body."""

    response: str = Field(..., description="Guru's response")
    intent: Optional[str] = Field(None, description="Detected intent")
    meditation_step: int = Field(default=0, description="Next meditation step")
    citations: list[str] = Field(default_factory=list, description="Source URLs")
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
    model_used: Optional[str] = Field(None, description="Underlying LLM model used")
    model_provider: Optional[str] = Field(None, description="Underlying LLM provider")
    route_decision: Optional[str] = Field(None, description="Model/routing decision")
    query_tier: Optional[str] = Field(
        None, description="Graph variant used (fast, standard, deep)"
    )
    follow_up_suggestions: list[str] = Field(
        default_factory=list,
        description="Claude-style suggested follow-up questions for the user",
    )
