"""Backward-compatible facade for the feedback router.

Unit 13 — the implementation has moved to `app.api.feedback`.
"""

from app.api.feedback import router

__all__ = ["router"]
