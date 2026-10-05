"""Pydantic schemas for clip auto-approval and human review.

Adheres strictly to the Ponytail Principle (lessons.md L-OBS-2: thin wrapper
over existing logic, zero new deps, Pydantic-only schemas).
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ClipEvaluationVerdict(BaseModel):
    """Auto-evaluation verdict for a single verbatim clip."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    clip_id: str
    video_id: str
    start_s: float = Field(..., ge=0.0)
    end_s: float = Field(..., ge=0.0)
    duration_s: float = Field(..., ge=0.0)
    boundary_clean: bool
    boundary_defects: list[str] = Field(default_factory=list)
    doctrinal_score: float = Field(..., ge=0.0, le=1.0)
    doctrinal_rationale: str
    tone_score: float = Field(..., ge=0.0, le=1.0)
    tone_rationale: str
    composite_score: float = Field(..., ge=0.0, le=1.0)
    approved: bool = Field(
        ...,
        description="True if boundary_clean and composite_score >= 0.85",
    )
    needs_human_review: bool = Field(
        ...,
        description="True if not approved and (composite_score >= 0.60 or boundary_defects)",
    )
    rejection_reason: Optional[str] = None

    # Contextual metadata for review server and export
    text: Optional[str] = None
    question_id: Optional[str] = None
    question_text: Optional[str] = None


class HumanReviewDecision(BaseModel):
    """Human adjudicator review record for an evaluated clip."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    clip_id: str
    video_id: str
    human_verdict: Literal["approved", "rejected", "adjusted"]
    rejection_reason: Optional[str] = None
    notes: Optional[str] = None
    reviewed_at_iso: str
