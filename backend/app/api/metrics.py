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
    import asyncio

    user_id = user["id"]
    if user.get("is_anonymous"):
        return _empty_metrics()

    supabase = _supabase_client(request)

    def _fetch_metrics() -> UserMetrics:
        try:
            conv = (
                supabase.table("conversations")
                .select("id", count="exact")
                .eq("user_id", user_id)
                .execute()
            )
        except Exception:
            conv = None

        # chat_messages links to conversations.id, not direct user_id
        try:
            msgs = (
                supabase.table("chat_messages")
                .select("id, conversations!inner(user_id)", count="exact")
                .eq("conversations.user_id", user_id)
                .execute()
            )
        except Exception:
            # Fallback if inner join syntax unsupported by mock/version
            try:
                msgs = (
                    supabase.table("chat_messages")
                    .select("id", count="exact")
                    .eq("user_id", user_id)
                    .execute()
                )
            except Exception:
                msgs = None

        try:
            sessions = (
                supabase.table("meditation_sessions")
                .select("duration_seconds")
                .eq("user_id", user_id)
                .execute()
            )
        except Exception:
            sessions = None

        try:
            course = (
                supabase.table("user_course_progress")
                .select("*")
                .eq("user_id", user_id)
                .eq("status", "active")
                .maybe_single()
                .execute()
            )
        except Exception:
            course = None

        total_minutes = (
            sum(
                s.get("duration_seconds", 0) or 0 for s in (sessions.data if sessions else []) or []
            )
            / 60.0
        )
        return UserMetrics(
            total_conversations=(conv.count if conv else 0) or 0,
            total_messages=(msgs.count if msgs else 0) or 0,
            total_meditation_minutes=round(total_minutes, 2),
            average_distress_level=None,
            distress_trend="flat",
            active_healing_course=(course.data["course_slug"] if course and course.data else None),
            course_completion_percent=_course_completion_percent(course.data if course else None),
            last_active_at=None,
        )

    return await asyncio.to_thread(_fetch_metrics)


# Course curriculum is versioned in src/lib/healingCourses.ts. Keep the
# backend denominator in one explicit audited mapping rather than inventing a
# percentage from current_lesson_index (which is zero-based and can drift).
COURSE_LESSON_COUNTS = {
    "end-of-suffering": 4,
    "walking-through-grief": 3,
    "quieting-anxiety": 3,
    "dissolving-conflict": 3,
}


def _course_completion_percent(course_row: dict | None) -> float:
    """Return the percentage of completed lessons for the active course."""
    if not course_row:
        return 0.0

    slug = str(course_row.get("course_slug") or "").strip()
    total = COURSE_LESSON_COUNTS.get(slug)
    completed = course_row.get("completed_lessons") or []

    if total is None:
        # Unknown curriculum versions are intentionally not guessed.
        return 0.0

    if not isinstance(completed, (list, tuple)):
        return 0.0

    completed_count = min(total, len({str(item) for item in completed if item}))
    return round((completed_count / total) * 100.0, 2)


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
