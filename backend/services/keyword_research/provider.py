"""Keyword research provider interface.

The workbook generator must never manufacture SEO metrics. This module defines
the provider protocol and error hierarchy. When an external provider is not
configured or data is unavailable, the pipeline fails closed or uses the
uncertified public data baseline explicitly marked as such.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol


class KeywordResearchDataUnavailable(RuntimeError):
    """Raised when sourced keyword data is not configured or cannot be fetched."""


class KeywordResearchProvider(Protocol):
    def fetch(
        self,
        *,
        seed_keyword: str,
        target_country: str,
        keywords: Sequence[str],
    ) -> Mapping[str, Any]:
        """Return the normalized external research response."""
