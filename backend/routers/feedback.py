from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

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
    user: Optional[dict] = Depends(get_current_user_from_supabase),
):
    """
    Submit feedback (rating and optional text) for a generated answer.
    """
    service = FeedbackService()
    user_id = user.get("id") if user else None

    jsonl_store.record_feedback(
        session_id=user_id or "anonymous",
        query=feedback_in.query,
        response=feedback_in.answer,
        rating="up" if feedback_in.rating > 0 else "down",
        intent="QUERY",
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
