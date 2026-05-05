from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

class FeedbackCreate(BaseModel):
    """Schema for creating a new feedback entry."""
    query: str = Field(..., description="The original user query")
    answer: str = Field(..., description="The generated answer being rated")
    rating: int = Field(..., description="1 for upvote, -1 for downvote")
    feedback_text: Optional[str] = Field(None, description="Optional qualitative feedback")
    metadata_json: Optional[Dict[str, Any]] = Field(
        None, description="Detailed metadata including retrieved doc IDs and scores"
    )

class FeedbackResponse(FeedbackCreate):
    """Schema for returning feedback data."""
    id: str
    user_id: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
