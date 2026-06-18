import logging
from typing import Optional

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

    async def create_feedback(
        self, feedback_in: FeedbackCreate, user_id: Optional[str] = None
    ) -> Feedback:
        """
        Store a new feedback entry in the database.
        """
        db_feedback = Feedback(
            query=feedback_in.query,
            answer=feedback_in.answer,
            rating=feedback_in.rating,
            feedback_text=feedback_in.feedback_text,
            metadata_json=feedback_in.metadata_json,
            user_id=user_id,
        )
        self.db.add(db_feedback)
        await self.db.commit()
        await self.db.refresh(db_feedback)

        logger.info(f"Feedback stored: {db_feedback.id} (Rating: {db_feedback.rating})")

        # Trigger downstream quality improvement pipelines
        if db_feedback.rating is not None:
            if db_feedback.rating < 0:
                logger.warning(
                    f"Negative feedback {db_feedback.id}: query='{db_feedback.query[:60]}...' "
                    "Flagging for re-ranking weight recalibration."
                )
                # Future: emit to a background task (Celery / RQ) that adjusts
                # reranking weights based on the negative example.
            elif db_feedback.rating > 0:
                # Treat any positive rating as candidate for golden dataset
                logger.info(
                    f"Positive feedback {db_feedback.id}: query='{db_feedback.query[:60]}...' "
                    "Adding to golden dataset for re-evaluation benchmarks."
                )
                # Future: write to golden_dataset table used by eval_runner.py

        return db_feedback

    async def get_feedback_history(self, limit: int = 100) -> list[Feedback]:
        """Retrieve recent feedback for analysis."""
        result = await self.db.execute(
            select(Feedback).order_by(Feedback.created_at.desc()).limit(limit)
        )
        return result.scalars().all()
