"""Healing course API routes.

Two operations over the shared `user_course_progress` table:

  - POST /api/healing-course/assign  — evaluate a seeker's turn history for a
    distress trigger and assign the matching course (idempotent: a user with an
    active course never receives a second one; see
    services.healing_course_service.assign_course_if_needed).
  - POST /api/healing-course/progress — persist lesson progress for a course
    (upsert on user_id + course_slug, mirroring the frontend hook's contract).

The supabase client is built per-request with the caller's JWT so Postgres RLS
sees auth.uid() (same pattern as app.api.metrics). All assignment-side DB work
is best-effort inside the service — a trigger may fire but assignment can be
skipped; the endpoint reports that outcome instead of failing the request.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import settings
from services.auth_service import get_current_user_from_supabase
from services.healing_course_service import assign_course_if_needed, evaluate_course_trigger

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/healing-course", tags=["healing-course"])


class AssignCourseRequest(BaseModel):
    """Recent turn history carrying distress metadata.

    Each turn: {"distress_level": int (0-3), "signal": str, "timestamp": float}.
    """

    history: list[dict[str, Any]] = Field(default_factory=list)


class ProgressUpdateRequest(BaseModel):
    course_slug: str
    completed_lessons: list[str] = Field(default_factory=list)
    current_lesson_index: int = 0
    status: Literal["active", "completed"] = "active"


def _supabase_client(request: Request) -> Any:
    """Build a supabase client carrying the caller's JWT so RLS sees auth.uid()."""
    if not settings.supabase_url or not settings.supabase_key:
        raise HTTPException(status_code=503, detail="Persistence backend unavailable.")
    from supabase import create_client

    client = create_client(settings.supabase_url, settings.supabase_key)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        client.auth.set_session(auth_header[7:], "")
    return client


@router.post("/assign")
async def assign_course(
    request: Request,
    body: AssignCourseRequest,
    user: dict = Depends(get_current_user_from_supabase),
) -> dict[str, Any]:
    """Evaluate turn history and assign a healing course when a trigger fires."""
    trigger = evaluate_course_trigger(body.history or [])
    if not trigger:
        return {"assigned": False}
    supabase = _supabase_client(request)
    result = await assign_course_if_needed(supabase, user["id"], trigger)
    if not result:
        return {"assigned": False, "course": None}
    return {"assigned": True, "course": result}


@router.post("/progress")
async def update_progress(
    request: Request,
    body: ProgressUpdateRequest,
    user: dict = Depends(get_current_user_from_supabase),
) -> dict[str, bool]:
    """Persist lesson progress for a course (upsert on user_id + course_slug)."""
    if user.get("is_anonymous"):
        raise HTTPException(status_code=403, detail="Sign in to track course progress.")
    supabase = _supabase_client(request)
    supabase.table("user_course_progress").upsert(
        {
            "user_id": user["id"],
            "course_slug": body.course_slug,
            "completed_lessons": body.completed_lessons,
            "current_lesson_index": body.current_lesson_index,
            "status": body.status,
        },
        on_conflict="user_id,course_slug",
    ).execute()
    return {"ok": True}


if __name__ == "__main__":
    sample = [
        {"distress_level": 2, "signal": "anxiety", "timestamp": 0},
        {"distress_level": 2, "signal": "anxiety", "timestamp": 1},
    ]
    trigger = evaluate_course_trigger(sample)
    print(f"Trigger: {trigger}")
    print(f"AssignCourseRequest fields: {sorted(AssignCourseRequest.model_fields)}")
    print(f"ProgressUpdateRequest fields: {sorted(ProgressUpdateRequest.model_fields)}")
