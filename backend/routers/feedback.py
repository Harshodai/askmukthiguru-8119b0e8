from typing import List, Optional, Dict
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from services.feedback_service import FeedbackService
from schemas.feedback import FeedbackCreate, FeedbackResponse
from services.auth_service import get_current_user_from_supabase

router = APIRouter(prefix="/feedback", tags=["Feedback"])

@router.post("/", response_model=FeedbackResponse)
async def submit_feedback(
    feedback_in: FeedbackCreate,
    db: AsyncSession = Depends(get_db),
    user: Optional[Dict] = Depends(get_current_user_from_supabase)
):
    """
    Submit feedback (rating and optional text) for a generated answer.
    """
    service = FeedbackService(db)
    user_id = user.get("id") if user else None
    return await service.create_feedback(feedback_in, user_id=user_id)

@router.get("/history", response_model=List[FeedbackResponse])
async def get_feedback_history(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: Dict = Depends(get_current_user_from_supabase)
):
    """
    Retrieve recent feedback history (Admin only).
    """
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    service = FeedbackService(db)
    return await service.get_feedback_history(limit=limit)
