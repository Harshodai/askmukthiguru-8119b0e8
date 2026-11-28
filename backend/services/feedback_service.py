import asyncio
import logging
from typing import Optional

from schemas.feedback import FeedbackCreate

logger = logging.getLogger(__name__)


def _get_client():
    from app.telemetry_db import _get_client as _supa_client

    return _supa_client()


class FeedbackStoreError(RuntimeError):
    """Feedback could not be persisted. `reason` is a bounded code, never user text."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class FeedbackService:
    """
    Service for managing user feedback via Supabase (single operational DB).
    """

    async def _insert_event(self, row: dict) -> dict:
        """Insert one feedback_events row. Raises FeedbackStoreError; never fakes success."""
        client = _get_client()
        if not client:
            logger.error("feedback_store_failed reason=supabase_unavailable")
            raise FeedbackStoreError("supabase_unavailable")
        try:
            result = await asyncio.to_thread(
                lambda: client.table("feedback_events").insert(row).execute()
            )
        except Exception as exc:
            # Log the exception class only: PostgREST messages can echo row values.
            logger.error("feedback_store_failed reason=insert_failed kind=%s", type(exc).__name__)
            raise FeedbackStoreError("insert_failed") from exc
        data = dict(result.data[0]) if result.data else {}
        data.setdefault("id", "stored")
        return data

    async def create_feedback(
        self, feedback_in: FeedbackCreate, user_id: Optional[str] = None
    ) -> dict:
        feedback_text = feedback_in.feedback_text or feedback_in.comment
        data = await self._insert_event(
            {
                "query_text": feedback_in.query,
                "answer_text": feedback_in.answer,
                "rating": feedback_in.rating,
                "feedback_text": feedback_text or "",
                "metadata_json": feedback_in.metadata_json or {},
                "user_id": user_id,
            }
        )
        return {
            "user_id": user_id,
            "rating": feedback_in.rating,
            "query_text": feedback_in.query,
            "answer_text": feedback_in.answer,
            "feedback_text": feedback_text or "",
            "comment": feedback_text,
            "metadata_json": feedback_in.metadata_json or {},
            "created_at": None,
            **data,
        }

    async def record_clip_report(
        self,
        *,
        user_id: Optional[str],
        served_point_id: str,
        reason: str,
        reason_category: Optional[str],
        video_id: Optional[str],
    ) -> dict:
        """Persist a faculty clip report as a negative feedback_events row (ids + note only)."""
        return await self._insert_event(
            {
                "user_id": user_id,
                "rating": -1,
                "feedback_text": reason,
                "metadata_json": {
                    "kind": "clip_report",
                    "served_point_id": served_point_id,
                    "reason_category": reason_category or "other",
                    "video_id": video_id or "",
                },
            }
        )

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
                .data
                or []
            )
            return rows
        except Exception as e:
            logger.error(f"Failed to fetch feedback history: {e}")
            return []
