"""
OKF Quality Filter Service
--------------------------
Validates generated OKF markdown entries to ensure highest format and data quality.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Text that proves an entry is a machine artifact rather than a teaching. All of these
# were found live in memory/okf/: RAPTOR debug headers, unresolved provenance, and —
# worst — the extraction LLM's own commentary about its prompt ("The user wants me to
# analyze a spiritual teaching and list the top 3-5 distinct topics"). Every OKF entry
# is embedded and injected verbatim into answers, so this text gets cited to a seeker
# as the gurus' words. generation.py's own prompt (rule 6) forbids exposing exactly it.
_LEAKAGE_PATTERNS = (
    r"RAPTOR Level\s*:",
    r"_\(Source:\s*unknown\)_",
    r"\bThe user (?:wants me to|has provided)\b",
    r"\bInterpret the Input\b",
    r"\bLet me analyze\b",
    r"\bWe are given\b",
    r"\bcomma-separated list\b",
    r"^\s*>\s*\[Source:",  # raw chunk-provenance blockquote
    r"^\s*>\s*\[RAPTOR",
)
_LEAKAGE_RE = re.compile("|".join(_LEAKAGE_PATTERNS), re.IGNORECASE | re.MULTILINE)


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
        source = str(parsed.get("source", "") or "").strip()

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

        # Provenance is mandatory: format_final_answer cites every OKF-derived claim.
        # An entry with no source cannot be attributed, so it cannot be doctrine.
        if not source:
            return False, "Missing 'source' — an uncitable entry cannot be doctrine"

        # Machine artifacts must never be served as teachings.
        leak = _LEAKAGE_RE.search(body)
        if leak:
            return False, f"Extraction artifact / prompt leakage in body: {leak.group(0)!r}"

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
