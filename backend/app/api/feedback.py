import asyncio
import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import settings
from app.core.feedback_store import FeedbackStore
from app.core.limiter import limiter
from schemas.feedback import FeedbackCreate, FeedbackResponse
from services.auth_service import get_current_user_from_supabase
from services.feedback_service import FeedbackService

router = APIRouter(prefix="/feedback", tags=["Feedback"])
jsonl_store = FeedbackStore()


@router.post("/", response_model=FeedbackResponse)
@limiter.limit(settings.registration_rate_limit)
async def submit_feedback(
    request: Request,
    feedback_in: FeedbackCreate,
    background_tasks: BackgroundTasks,
    user: Optional[dict] = Depends(get_current_user_from_supabase),
):
    """
    Submit feedback (rating and optional text) for a generated answer.
    """
    service = FeedbackService()
    user_id = user.get("id") if user else None
    feedback_text = feedback_in.feedback_text or feedback_in.comment

    await jsonl_store.record_feedback(
        session_id=user_id or "anonymous",
        query=feedback_in.query,
        response=feedback_in.answer,
        feedback="positive" if feedback_in.rating > 0 else "negative",
    )

    if feedback_in.rating <= 0:
        from app.core.refiner import mine_failed_session

        # Try to pull retrieved chunks out of metadata_json if present
        retrieved_context = ""
        if feedback_in.metadata_json and "chunks" in feedback_in.metadata_json:
            retrieved_context = str(feedback_in.metadata_json["chunks"])

        background_tasks.add_task(
            mine_failed_session,
            query=feedback_in.query,
            retrieved_context=retrieved_context,
            answer=feedback_in.answer,
            comment=feedback_text,
        )

        # Thumbs-down also invalidates the cached semantic entry for this query
        # so the bad answer is not served again to other users.
        from app.dependencies import get_container

        _container = get_container()
        _sink = getattr(_container, "telemetry_sink", None)
        if _sink is not None:
            background_tasks.add_task(
                _sink._invalidate_semantic_cache_if_flagged,
                hallucination_flag=True,
                query_text=feedback_in.query,
            )

    return await service.create_feedback(feedback_in, user_id=user_id)


@router.get("/history", response_model=list[FeedbackResponse])
async def get_feedback_history(
    limit: int = 50,
    user: dict = Depends(get_current_user_from_supabase),
):
    """
    Retrieve recent feedback history (Admin only).
    """
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    service = FeedbackService()
    return await service.get_feedback_history(limit=limit)


@router.get("/feedback-lessons", response_model=list[dict])
async def get_feedback_lessons(
    user: dict = Depends(get_current_user_from_supabase),
):
    """
    Retrieve compiled RAG failure lessons (Admin only).
    """
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    from app.constants import FEEDBACK_LESSONS_FILE_PATH

    lessons = []
    if os.path.exists(FEEDBACK_LESSONS_FILE_PATH):
        try:
            with open(FEEDBACK_LESSONS_FILE_PATH, encoding="utf-8") as f:
                for line in f:
                    line_str = line.strip()
                    if line_str:
                        try:
                            lessons.append(json.loads(line_str))
                        except json.JSONDecodeError:
                            continue
        except Exception:
            raise HTTPException(
                status_code=500, detail="Failed to load feedback lessons. Please try again."
            )

    return lessons


# ── Simple thumbs up/down endpoint ──────────────────────────────────


class RateFeedbackRequest(BaseModel):
    """Schema for the lightweight thumbs up/down feedback."""

    message_id: str = Field(..., max_length=255)
    feedback_type: str = Field(..., pattern=r"^(positive|negative)$")
    query_text: Optional[str] = Field(None, max_length=10000)
    response_summary: Optional[str] = Field(None, max_length=5000)


@router.post("/rate", status_code=201)
@limiter.limit(settings.feedback_rate_limit)
async def rate_feedback(
    request: Request,
    body: RateFeedbackRequest,
    user: Optional[dict] = Depends(get_current_user_from_supabase),
):
    """Simple thumbs up/down — stores to feedback_events table."""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    user_id = user.get("id")
    client = _get_supabase_client()
    if not client:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    row = {
        "user_id": user_id,
        "message_id": body.message_id,
        "feedback_type": body.feedback_type,
        "query_text": body.query_text,
        "response_summary": body.response_summary,
    }
    try:
        result = await asyncio.to_thread(
            lambda: client.table("feedback_events").insert(row).execute()
        )
        return {"status": "ok", "id": result.data[0]["id"] if result.data else None}
    except Exception as e:
        logging.getLogger(__name__).error("Failed to store rate feedback: %s", e)
        raise HTTPException(status_code=500, detail="Failed to store feedback")


def _get_supabase_client():
    from app.telemetry_db import _get_client as _supa_client

    return _supa_client()
