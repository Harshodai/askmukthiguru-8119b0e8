"""Calibrated, non-numeric user-facing evidence support labels."""
from __future__ import annotations

from math import isfinite
from typing import Any

LIMITED_SUPPORT = "Limited support"
PARTIALLY_SUPPORTED = "Partially supported"
TEACHING_SUPPORTED = "Teaching-supported"


def evidence_support_label(score: Any, *, source_count: int) -> str:
    """Map verified evidence confidence to a conservative display label.

    Empty retrieval is always limited support. This function intentionally does
    not convert an arbitrary generation score into evidence support.
    """
    if source_count <= 0:
        return LIMITED_SUPPORT
    if not isinstance(score, (int, float)):
        return LIMITED_SUPPORT
    if not isfinite(float(score)) or score < 5.0:
        return LIMITED_SUPPORT
    if score < 8.0:
        return PARTIALLY_SUPPORTED
    return TEACHING_SUPPORTED
