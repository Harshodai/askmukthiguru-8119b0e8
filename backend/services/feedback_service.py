import logging
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from models.feedback import Feedback
from schemas.feedback import FeedbackCreate

logger = logging.getLogger(__name__)

class FeedbackService:
    """
    Service for managing user feedback and continuous learning loops.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_feedback(self, feedback_in: FeedbackCreate, user_id: Optional[str] = None) -> Feedback:
        """
        Store a new feedback entry in the database.
        """
        db_feedback = Feedback(
            query=feedback_in.query,
            answer=feedback_in.answer,
            rating=feedback_in.rating,
            feedback_text=feedback_in.feedback_text,
            metadata_json=feedback_in.metadata_json,
            user_id=user_id
        )
        self.db.add(db_feedback)
        await self.db.commit()
        await self.db.refresh(db_feedback)
        
        logger.info(f"Feedback stored: {db_feedback.id} (Rating: {db_feedback.rating})")
        
        # TODO: Trigger re-ranking weight updates if rating is negative
        # TODO: Add to 'golden dataset' if rating is highly positive
        
        return db_feedback

    async def get_feedback_history(self, limit: int = 100) -> List[Feedback]:
        """Retrieve recent feedback for analysis."""
        result = await self.db.execute(
            select(Feedback).order_by(Feedback.created_at.desc()).limit(limit)
        )
        return result.scalars().all()
