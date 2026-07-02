"""
OKF Quality Filter Service
--------------------------
Validates generated OKF markdown entries to ensure highest format and data quality.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class OKFQualityFilter:
    """Filters and validates synthesized OKF entries."""

    MIN_BODY_LENGTH = 100
    REQUIRED_FIELDS = {"type", "title"}

    @classmethod
    def validate_entry(cls, parsed: dict[str, Any]) -> tuple[bool, str]:
        """
        Validate parsed OKF dictionary representation.
        Returns (is_valid, error_reason).
        """
        title = parsed.get("title", "").strip()
        body = parsed.get("body", "").strip()
        type_ = parsed.get("type", "").strip()

        # Check required fields
        if not title:
            return False, "Empty title"
        if not body:
            return False, "Empty body content"
        if not type_:
            return False, "Empty type field"

        # Check body length
        if len(body) < cls.MIN_BODY_LENGTH:
            return False, f"Body too short ({len(body)} chars, min={cls.MIN_BODY_LENGTH})"

        # Verify doctrine-specific validation
        body_lower = body.lower()
        if "sri preethaji" not in body_lower and "sri krishnaji" not in body_lower and "ekam" not in body_lower:
            # We don't fail, but log warning for low spiritual context
            logger.debug(f"OKF Warning: '{title}' has low doctrine term density.")

        return True, ""

    @classmethod
    def filter_duplicate_entries(
        cls, entries: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Remove duplicates by title (case-insensitive), keeping the longest body."""
        seen: dict[str, dict[str, Any]] = {}
        for entry in entries:
            title_key = entry.get("title", "").strip().lower()
            if not title_key:
                continue

            existing = seen.get(title_key)
            if not existing or len(entry.get("body", "")) > len(existing.get("body", "")):
                seen[title_key] = entry

        return list(seen.values())
