from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class MessagePayload(BaseModel):
    """Single message in the conversation history."""

    role: str = Field(..., description="'user' or 'assistant'")
    content: str = Field(..., description="Message text")


class ChatRequest(BaseModel):
    """Chat API request body — matches frontend's sendMessage format."""

    messages: list[MessagePayload] = Field(..., description="Conversation history")
    user_message: str = Field(..., description="Current user message")
    session_id: Optional[str] = Field(None, description="Optional session ID")
    meditation_step: int = Field(default=0, description="Current meditation step (0 = none)")
    language: Optional[str] = Field(default="en", description="Preferred language")
    last_serene_mind_at: Optional[float] = Field(
        default=None,
        description="Unix timestamp of the user's last completed Serene Mind session (client-reported)",
    )


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
