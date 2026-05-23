from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FeedbackCreate(BaseModel):
    """Schema for creating a new feedback entry."""

    query: str = Field(..., description="The original user query")
    answer: str = Field(..., description="The generated answer being rated")
    rating: int = Field(..., description="1 for upvote, -1 for downvote")
    feedback_text: str | None = Field(None, description="Optional qualitative feedback")
    metadata_json: dict[str, Any] | None = Field(
        None, description="Detailed metadata including retrieved doc IDs and scores"
    )


class FeedbackResponse(FeedbackCreate):
    """Schema for returning feedback data."""

    id: str
    user_id: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
