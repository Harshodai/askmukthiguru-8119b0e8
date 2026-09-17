from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class FeedbackCreate(BaseModel):
    """Schema for creating a new feedback entry."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", from_attributes=True)

    query: str = Field(..., max_length=10000, description="The original user query")
    answer: str = Field(..., max_length=50000, description="The generated answer being rated")
    rating: int = Field(..., ge=-1, le=1, description="1 for upvote, -1 for downvote")
    feedback_text: Optional[str] = Field(
        None, max_length=5000, description="Optional qualitative feedback"
    )
    # Backward-compatible alias for older clients that sent `comment`.
    comment: Optional[str] = Field(
        None, max_length=5000, description="Backward-compatible feedback text alias"
    )
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

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", from_attributes=True)


FeedbackResponseListAdapter: TypeAdapter[list[FeedbackResponse]] = TypeAdapter(
    list[FeedbackResponse]
)


def parse_feedback_create_json(raw_json: str) -> FeedbackCreate:
    """Parse a raw JSON body into FeedbackCreate via model_validate_json()."""
    return FeedbackCreate.model_validate_json(raw_json)


def parse_feedback_batch_json(raw_json: str) -> list[FeedbackResponse]:
    """Validate a batch payload into list[FeedbackResponse] via TypeAdapter."""
    return FeedbackResponseListAdapter.validate_json(raw_json)


if __name__ == "__main__":
    fc = parse_feedback_create_json('{"query": " q ", "answer": "a", "rating": 1}')
    assert fc.query == "q", fc.query
    batch = parse_feedback_batch_json('[{"id": "1"}]')
    assert isinstance(batch, list) and isinstance(batch[0], FeedbackResponse)
    print("feedback schemas OK")
