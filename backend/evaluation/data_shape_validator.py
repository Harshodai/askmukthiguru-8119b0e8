"""Data-Shape Assertions for Chunk Ingestion and Persistence (Phase 5: DE-5.2).

Validates chunk corpora to ensure no broken chunking (e.g., halved length),
contamination with LLM reasoning artifacts, or excessive duplication.
"""

from __future__ import annotations

import math
from typing import Any

try:
    from services.text_quality_filter import find_artifact
except ImportError:
    from backend.services.text_quality_filter import find_artifact


class DataShapeViolationError(Exception):
    """Raised when chunk data shape violates length, artifact, or duplicate thresholds."""

    pass


def _extract_chunk_text(chunk: dict[str, Any] | str) -> str:
    """Extract plain text string from a chunk dict or string."""
    if isinstance(chunk, str):
        return chunk
    if isinstance(chunk, dict):
        for key in ("text", "content", "chunk_text", "payload_text", "body"):
            val = chunk.get(key)
            if isinstance(val, str):
                return val
        return ""
    return str(chunk)


def _compute_percentile(sorted_vals: list[int | float], p: float) -> float:
    """Calculate percentile using linear interpolation."""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    k = (len(sorted_vals) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(sorted_vals[int(k)])
    d0 = sorted_vals[int(f)] * (c - k)
    d1 = sorted_vals[int(c)] * (k - f)
    return float(d0 + d1)


def validate_chunk_data_shape(
    chunks: list[dict[str, Any] | str],
    min_mean_length: int = 200,
    max_artifact_rate: float = 0.0,
    max_duplicate_rate: float = 0.05,
) -> dict[str, Any]:
    """Validate data shape of chunks against length, artifact, and duplicate thresholds.

    Calculates: count, mean_length, p95_length, p05_length, duplicate_rate, artifact_rate.
    Raises DataShapeViolationError if mean_length < min_mean_length,
    artifact_rate > max_artifact_rate, or duplicate_rate > max_duplicate_rate.
    """
    texts = [_extract_chunk_text(c) for c in chunks]
    count = len(texts)

    if count == 0:
        if min_mean_length > 0:
            raise DataShapeViolationError(
                f"Empty chunk list provided; mean length 0 is below required minimum {min_mean_length}"
            )
        return {
            "count": 0,
            "mean_length": 0.0,
            "p95_length": 0.0,
            "p05_length": 0.0,
            "duplicate_rate": 0.0,
            "artifact_rate": 0.0,
        }

    lengths = [len(t) for t in texts]
    mean_length = sum(lengths) / count
    sorted_lengths = sorted(lengths)

    p95_length = _compute_percentile(sorted_lengths, 0.95)
    p05_length = _compute_percentile(sorted_lengths, 0.05)

    # Duplication calculation
    unique_texts = set(texts)
    duplicate_count = count - len(unique_texts)
    duplicate_rate = duplicate_count / count

    # Artifact rate using find_artifact
    artifact_count = sum(1 for t in texts if find_artifact(t) is not None)
    artifact_rate = artifact_count / count

    # Threshold checks
    if mean_length < min_mean_length:
        raise DataShapeViolationError(
            f"Mean chunk length {mean_length:.1f} is below minimum {min_mean_length}"
        )

    if artifact_rate > max_artifact_rate:
        raise DataShapeViolationError(
            f"Artifact rate {artifact_rate:.4f} exceeds maximum allowed {max_artifact_rate}"
        )

    if max_duplicate_rate is not None and duplicate_rate > max_duplicate_rate:
        raise DataShapeViolationError(
            f"Duplicate rate {duplicate_rate:.4f} exceeds maximum allowed {max_duplicate_rate}"
        )

    return {
        "count": count,
        "mean_length": round(mean_length, 2),
        "p95_length": round(p95_length, 2),
        "p05_length": round(p05_length, 2),
        "duplicate_rate": round(duplicate_rate, 4),
        "artifact_rate": round(artifact_rate, 4),
    }
