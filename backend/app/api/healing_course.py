"""Healing course API routes.

Three operations over the shared `user_course_progress` table and the new
`user_healing_progress` table:

  - POST /api/healing-course/assign  — evaluate a seeker's turn history for a
    distress trigger and assign the matching course (idempotent: a user with an
    active course never receives a second one; see
    services.healing_course_service.assign_course_if_needed).
  - POST /api/healing-course/progress — persist lesson progress for a course
    (upsert on user_id + course_slug, mirroring the frontend hook's contract).
  - POST /api/healing-course/{course_slug}/progress — mark a step as completed,
    advance current_step, update last_accessed_at.
  - GET  /api/healing-course/{course_slug}/progress — return current step-level
    progress for the authenticated user.

The supabase client is built per-request with the caller's JWT so Postgres RLS
sees auth.uid() (same pattern as app.api.metrics). All assignment-side DB work
is best-effort inside the service — a trigger may fire but assignment can be
skipped; the endpoint reports that outcome instead of failing the request.
"""

from __future__ import annotations

import asyncio
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


class StepProgressRequest(BaseModel):
    step_id: str
    total_steps: int = Field(default=1, ge=1)


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


@router.post("/{course_slug}/progress")
async def mark_step_completed(
    request: Request,
    course_slug: str,
    body: StepProgressRequest,
    user: dict = Depends(get_current_user_from_supabase),
) -> dict[str, Any]:
    """Mark a step as completed and advance current_step."""
    if user.get("is_anonymous"):
        raise HTTPException(status_code=403, detail="Sign in to track course progress.")
    supabase = _supabase_client(request)
    user_id = user["id"]

    def _upsert_step():
        existing = (
            supabase.table("user_healing_progress")
            .select("completed_steps, current_step")
            .eq("user_id", user_id)
            .eq("course_slug", course_slug)
            .maybe_single()
            .execute()
        )
        completed: list[str] = []
        if existing and getattr(existing, "data", None):
            completed = list(existing.data.get("completed_steps") or [])

        if body.step_id not in completed:
            completed.append(body.step_id)
        new_step = min(len(completed), body.total_steps - 1)

        supabase.table("user_healing_progress").upsert(
            {
                "user_id": user_id,
                "course_slug": course_slug,
                "current_step": new_step,
                "completed_steps": completed,
                "last_accessed_at": "now()",
            },
            on_conflict="user_id,course_slug",
        ).execute()
        return {"current_step": new_step, "completed_steps": completed, "total_steps": body.total_steps}

    try:
        result = await asyncio.to_thread(_upsert_step)
    except Exception as e:
        logger.warning(f"Healing step progress upsert failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to save progress.")
    return {"ok": True, **result}


@router.get("/{course_slug}/progress")
async def get_step_progress(
    request: Request,
    course_slug: str,
    user: dict = Depends(get_current_user_from_supabase),
) -> dict[str, Any]:
    """Return current step-level progress for the authenticated user."""
    if user.get("is_anonymous"):
        return {"current_step": 0, "completed_steps": [], "total_steps": 0}
    supabase = _supabase_client(request)

    def _select():
        return (
            supabase.table("user_healing_progress")
            .select("current_step, completed_steps, last_accessed_at")
            .eq("user_id", user["id"])
            .eq("course_slug", course_slug)
            .maybe_single()
            .execute()
        )

    try:
        result = await asyncio.to_thread(_select)
    except Exception as e:
        logger.warning(f"Healing step progress fetch failed: {e}")
        return {"current_step": 0, "completed_steps": [], "total_steps": 0}

    if not result or not getattr(result, "data", None):
        return {"current_step": 0, "completed_steps": [], "total_steps": 0}
    row = result.data
    return {
        "current_step": row.get("current_step", 0),
        "completed_steps": row.get("completed_steps") or [],
        "last_accessed_at": row.get("last_accessed_at"),
    }


if __name__ == "__main__":
    sample = [
        {"distress_level": 2, "signal": "anxiety", "timestamp": 0},
        {"distress_level": 2, "signal": "anxiety", "timestamp": 1},
    ]
    trigger = evaluate_course_trigger(sample)
    print(f"Trigger: {trigger}")
    print(f"AssignCourseRequest fields: {sorted(AssignCourseRequest.model_fields)}")
    print(f"ProgressUpdateRequest fields: {sorted(ProgressUpdateRequest.model_fields)}")
