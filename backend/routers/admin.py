"""Backward-compatible facade for the admin router.

Unit 13 — the implementation has moved to `app.api.admin`.
"""

from app.api.admin import admin_router

__all__ = ["admin_router"]
