from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from services.feedback_service import FeedbackService
from schemas.feedback import FeedbackCreate, FeedbackResponse
from services.auth_service import current_active_user
from models.user import User

router = APIRouter(prefix="/feedback", tags=["Feedback"])

@router.post("/", response_model=FeedbackResponse)
async def submit_feedback(
    feedback_in: FeedbackCreate,
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(current_active_user)
):
    """
    Submit feedback (rating and optional text) for a generated answer.
    """
    service = FeedbackService(db)
    user_id = str(user.id) if user else None
    return await service.create_feedback(feedback_in, user_id=user_id)

@router.get("/history", response_model=List[FeedbackResponse])
async def get_feedback_history(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_active_user)
):
    """
    Retrieve recent feedback history (Admin only in future).
    """
    # In a real app, we'd check if user.is_superuser here
    service = FeedbackService(db)
    return await service.get_feedback_history(limit=limit)
