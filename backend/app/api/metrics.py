"""User engagement metrics routes.

Consumes the shared `UserMetrics` schema (backend mirror of
`src/lib/metricsSchema.ts`); the frontend hook reads `GET /api/metrics`.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.config import settings
from app.schemas.metrics import UserMetrics
from services.auth_service import get_current_user_from_supabase

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


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


@router.get("", response_model=UserMetrics)
async def get_metrics(
    request: Request,
    user: dict = Depends(get_current_user_from_supabase),
) -> UserMetrics:
    """Aggregate engagement metrics for the authenticated user."""
    user_id = user["id"]
    if user.get("is_anonymous"):
        return _empty_metrics()

    supabase = _supabase_client(request)
    conv = supabase.table("conversations").select("id", count="exact").eq("user_id", user_id).execute()
    msgs = supabase.table("chat_messages").select("id", count="exact").eq("user_id", user_id).execute()
    sessions = supabase.table("meditation_sessions").select("duration_seconds").eq("user_id", user_id).execute()
    course = (
        supabase.table("user_course_progress")
        .select("*")
        .eq("user_id", user_id)
        .eq("status", "active")
        .maybe_single()
        .execute()
    )

    total_minutes = sum(s.get("duration_seconds", 0) or 0 for s in sessions.data or []) / 60.0
    return UserMetrics(
        total_conversations=conv.count or 0,
        total_messages=msgs.count or 0,
        total_meditation_minutes=round(total_minutes, 2),
        average_distress_level=None,
        distress_trend="flat",
        active_healing_course=course.data["course_slug"] if course.data else None,
        course_completion_percent=_course_completion_percent(course.data),
        last_active_at=None,
    )


def _course_completion_percent(course_row: dict | None) -> float:
    """Completion share of an active healing course.

    Lesson totals live in course content, not the DB; until a
    content-driven denominator is available the percentage reports 0.0
    and the frontend falls back to per-lesson progress.
    """
    if not course_row:
        return 0.0
    return 0.0


def _empty_metrics() -> UserMetrics:
    return UserMetrics(
        total_conversations=0,
        total_messages=0,
        total_meditation_minutes=0.0,
        average_distress_level=None,
        distress_trend="flat",
        active_healing_course=None,
        course_completion_percent=0.0,
        last_active_at=None,
    )


if __name__ == "__main__":
    print("UserMetrics fields:", sorted(UserMetrics.model_json_schema()["properties"].keys()))
