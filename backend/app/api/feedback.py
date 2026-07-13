import os
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks

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
            comment=feedback_in.feedback_text
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
            with open(FEEDBACK_LESSONS_FILE_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line_str = line.strip()
                    if line_str:
                        try:
                            lessons.append(json.loads(line_str))
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            raise HTTPException(status_code=500, detail="Failed to load feedback lessons. Please try again.")
            
    return lessons
