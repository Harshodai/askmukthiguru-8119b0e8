"""Backward-compatible facade for the compliance router.

Unit 13 — the implementation has moved to `app.api.compliance`.
"""

from app.api.compliance import router

__all__ = ["router"]
