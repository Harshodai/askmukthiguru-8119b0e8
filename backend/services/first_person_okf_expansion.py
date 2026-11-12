"""OKF-driven concept expansion for first-person span retrieval.

Reads curated teachings from memory/okf/compiled.json via cached numpy dot product (<0.1ms).
Extracts doctrine tags and title concepts matching the query dense vector (1024-dim BGE-M3).
Additive and fail-open: returns [] on any failure without delaying serving.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Optional

import numpy as np

from services.memory.okf_store import OKF_DIR, _load_compiled_matrix

logger = logging.getLogger(__name__)

_DEFAULT_MAX_CONCEPTS = 8
_DEFAULT_MIN_SIMILARITY = 0.40


def expand_concepts_via_okf(
    query_dense_vector: Sequence[float],
    *,
    teacher_id: Optional[str] = None,
    max_concepts: int = _DEFAULT_MAX_CONCEPTS,
    min_similarity: float = _DEFAULT_MIN_SIMILARITY,
    compiled_path: Optional[Path] = None,
) -> list[str]:
    """Extract top ontology concept terms from memory/okf/compiled.json.

    Args:
        query_dense_vector: 1024-dim BGE-M3 query vector.
        teacher_id: Optional filter (a `guru_registry` teacher id, or None).
        max_concepts: Ceiling on unique returned concept terms.
        min_similarity: Cosine similarity threshold for doctrine entry matching.
        compiled_path: Path override for tests.

    Returns:
        List of distinct concept/tag strings for FirstPersonContextStore.retrieve().
    """
    if not query_dense_vector or len(query_dense_vector) != 1024 or max_concepts <= 0:
        return []

    c_path = compiled_path or (OKF_DIR / "compiled.json")
    try:
        entries, matrix = _load_compiled_matrix(c_path)
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        logger.debug("[OKFConceptExpansion] Failed to load compiled matrix: %s", exc)
        return []

    if matrix is None or not entries:
        return []

    try:
        q = np.asarray(query_dense_vector, dtype=np.float32)
        q_norm = float(np.linalg.norm(q))
        if q_norm == 0.0:
            return []
        q_unit = q / q_norm

        similarities = np.dot(matrix, q_unit)
    except (ValueError, TypeError, KeyError, RuntimeError) as exc:
        logger.debug("[OKFConceptExpansion] Vector similarity failed: %s", exc)
        return []

    target_teacher = (teacher_id or "").strip().lower()
    teacher_filter_active = target_teacher not in ("", "both", "all")

    matched_indices = np.where(similarities >= min_similarity)[0]
    if len(matched_indices) == 0:
        return []

    # Sort descending by cosine similarity
    sorted_order = matched_indices[np.argsort(-similarities[matched_indices])]

    collected: list[str] = []
    seen: set[str] = set()

    for idx in sorted_order:
        entry = entries[int(idx)]
        if teacher_filter_active:
            entry_teacher = str(entry.get("teacher", "both")).strip().lower()
            if entry_teacher != "both":
                if "preetha" in target_teacher and "preetha" not in entry_teacher:
                    continue
                if "krishna" in target_teacher and "krishna" not in entry_teacher:
                    continue

        # 1. Collect canonical tags from frontmatter
        for tag in entry.get("tags", []):
            if isinstance(tag, str):
                cleaned = tag.strip()
                key = cleaned.lower()
                if cleaned and key not in seen:
                    seen.add(key)
                    collected.append(cleaned)
                    if len(collected) >= max_concepts:
                        return collected

        # 2. Extract title concepts if tags budget remains
        title = str(entry.get("title", "")).strip()
        if title:
            key = title.lower()
            if key not in seen and len(title) <= 40:
                seen.add(key)
                collected.append(title)
                if len(collected) >= max_concepts:
                    return collected

    return collected
