from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class UserMetrics(BaseModel):
    """Aggregate engagement metrics for a single user.

    Field names are snake_case on the wire (FastAPI contract). The
    frontend mirrors these as camelCase in `src/lib/metricsSchema.ts`;
    parity is enforced by `src/test/metricsSchema.test.ts`.
    """

    total_conversations: int
    total_messages: int
    total_meditation_minutes: float
    average_distress_level: Optional[float]
    distress_trend: Literal["up", "down", "flat"]
    active_healing_course: Optional[str]
    course_completion_percent: float
    last_active_at: Optional[datetime]


if __name__ == "__main__":
    schema = UserMetrics.model_json_schema()
    print("UserMetrics fields:", sorted(schema["properties"].keys()))
    print("required:", sorted(schema.get("required", [])))
    print("distress_trend enum:", schema["properties"]["distress_trend"]["enum"])
