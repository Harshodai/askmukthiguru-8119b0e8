"""Serving-time source policy for rights and corpus quarantine boundaries.

This module is intentionally independent of ingestion. A source can remain in a
legacy vector collection during a staged reingestion or deletion drill, but it
must not reach user-facing retrieval, provenance, or generation until an
explicit rights review re-authorizes it.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from typing import Any

logger = logging.getLogger(__name__)

# The source was removed from the repository history and is quarantined from
# serving. Keep matching narrow: do not block unrelated YouTube teachings that
# merely mention the book title in prose.
_BLOCKED_SOURCE_IDENTITIES = frozenset(
    {
        "the_four_sacred_secrets.pdf",
        "the four sacred secrets.pdf",
    }
)

_SOURCE_SEPARATORS = re.compile(r"[\\/]+")


def _source_candidates(doc: Any) -> Iterable[str]:
    if not isinstance(doc, dict):
        return ()
    values: list[str] = []
    for key in ("source_url", "source", "title", "source_id", "document_id"):
        value = doc.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    return values


def _normalise_identity(value: str) -> str:
    value = value.strip().casefold().split("#", 1)[0].split("?", 1)[0]
    value = _SOURCE_SEPARATORS.sub("/", value)
    return value.rsplit("/", 1)[-1]


def is_blocked_source(doc: Any) -> bool:
    """Return True when a retrieved document belongs to a quarantined source."""
    for candidate in _source_candidates(doc):
        identity = _normalise_identity(candidate)
        if identity in _BLOCKED_SOURCE_IDENTITIES:
            return True
    return False


def filter_blocked_sources(documents: Iterable[dict]) -> tuple[list[dict], int]:
    """Drop quarantined sources and return (allowed_documents, dropped_count)."""
    allowed: list[dict] = []
    dropped = 0
    for document in documents:
        if is_blocked_source(document):
            dropped += 1
            logger.error(
                "Serving policy dropped quarantined source=%s",
                next(iter(_source_candidates(document)), "unknown"),
            )
            continue
        allowed.append(document)
    return allowed, dropped


__all__ = ["filter_blocked_sources", "is_blocked_source"]
