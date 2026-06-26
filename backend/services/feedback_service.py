import logging
from typing import Optional

from schemas.feedback import FeedbackCreate

logger = logging.getLogger(__name__)


def _get_client():
    from app.telemetry_db import _get_client as _supa_client
    return _supa_client()


class FeedbackService:
    """
    Service for managing user feedback via Supabase (single operational DB).
    """

    async def create_feedback(
        self, feedback_in: FeedbackCreate, user_id: Optional[str] = None
    ) -> dict:
        fallback_data = {
            "id": "",
            "user_id": user_id,
            "rating": feedback_in.rating,
            "query_text": feedback_in.query,
            "answer_text": feedback_in.answer,
            "feedback_text": feedback_in.feedback_text or "",
            "comment": feedback_in.feedback_text,
            "metadata_json": feedback_in.metadata_json or {},
            "created_at": None,
        }
        client = _get_client()
        if not client:
            logger.warning("Supabase client unavailable — skipping feedback record")
            return fallback_data

        row = {
            "query_text": feedback_in.query,
            "answer_text": feedback_in.answer,
            "rating": feedback_in.rating,
            "feedback_text": feedback_in.feedback_text or "",
            "metadata_json": feedback_in.metadata_json or {},
            "user_id": user_id,
        }
        try:
            result = client.table("feedback_events").insert(row).execute()
            if result.data:
                data = dict(result.data[0])
                if "id" not in data:
                    data["id"] = ""
                return data
            fallback_data["id"] = "stored"
            return fallback_data
        except Exception as e:
            logger.error(f"Failed to store feedback: {e}")
            return fallback_data

    async def get_feedback_history(self, limit: int = 100) -> list[dict]:
        client = _get_client()
        if not client:
            return []
        try:
            rows = (
                client.table("feedback_events")
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
                .data or []
            )
            return rows
        except Exception as e:
            logger.error(f"Failed to fetch feedback history: {e}")
            return []
