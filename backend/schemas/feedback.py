from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class FeedbackCreate(BaseModel):
    """Schema for creating a new feedback entry."""

    query: str = Field(..., max_length=10000, description="The original user query")
    answer: str = Field(..., max_length=50000, description="The generated answer being rated")
    rating: int = Field(..., ge=-1, le=1, description="1 for upvote, -1 for downvote")
    feedback_text: Optional[str] = Field(None, max_length=5000, description="Optional qualitative feedback")
    metadata_json: Optional[dict[str, Any]] = Field(
        None, description="Detailed metadata including retrieved doc IDs and scores"
    )


class FeedbackResponse(BaseModel):
    """Schema for returning feedback data."""

    id: str
    user_id: Optional[str] = None
    rating: int = 0
    query_text: str = ""
    answer_text: str = ""
    feedback_text: str = ""
    comment: Optional[str] = None
    metadata_json: Optional[dict[str, Any]] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
