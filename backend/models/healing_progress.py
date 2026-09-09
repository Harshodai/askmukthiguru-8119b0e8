"""Pydantic model for the user_healing_progress table."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UserHealingProgress(BaseModel):
    id: Optional[str] = None
    user_id: str
    course_slug: str
    current_step: int = Field(default=0, ge=0)
    completed_steps: list[str] = Field(default_factory=list)
    last_accessed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


if __name__ == "__main__":
    p = UserHealingProgress(user_id="u1", course_slug="test", current_step=2, completed_steps=["s1", "s2"])
    print(p.model_dump_json(indent=2))
