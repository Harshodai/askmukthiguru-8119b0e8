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

# 2026-09-23: The Four Sacred Secrets block (identity/title/ASIN match) was
# removed here -- CONTENT-RIGHTS.md now records rights confirmed by the
# project owner (2026-09-23). Not independently verified by any agent (N9);
# recorded as the human decision-maker's statement per this repo's rights
# policy. See CONTENT-RIGHTS.md and docs/rights/source-register.md for the
# full record. This module stays in place, empty for now, for any future
# source that needs a serve-time quarantine pending rights review -- keep
# matching narrow (exact identity/title/URL-substring, not broad prose
# mentions) if a new entry is ever added.
_BLOCKED_SOURCE_IDENTITIES: frozenset[str] = frozenset()
_BLOCKED_SOURCE_URL_SUBSTRINGS: frozenset[str] = frozenset()
_BLOCKED_TITLE_PREFIXES: tuple[str, ...] = ()

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
        casefolded = candidate.strip().casefold()
        if casefolded.startswith(_BLOCKED_TITLE_PREFIXES):
            return True
        if any(needle in casefolded for needle in _BLOCKED_SOURCE_URL_SUBSTRINGS):
            return True
    return False


def is_registered_source(doc: Any) -> bool:
    """Return True only when a document's rights basis is human-confirmed.

    Distinct from `domain_rights_status == "licensed"`, which ingestion stamps
    on every chunk by default (services/qdrant/indexer.py) and is not a
    per-source rights determination. "cleared" is set only by a human-run
    backfill after a source is entered in docs/rights/source-register.md /
    CONTENT-RIGHTS.md with a confirmed basis. See settings.serve_only_registered_sources.
    """
    if not isinstance(doc, dict):
        return False
    status = doc.get("domain_rights_status")
    if not status:
        provenance = doc.get("provenance")
        if isinstance(provenance, dict):
            status = provenance.get("domain_rights_status")
    return status == "cleared"


def filter_unregistered_sources(documents: Iterable[dict]) -> tuple[list[dict], int]:
    """Keep only documents with a human-confirmed rights basis; drop the rest.

    Only call this when settings.serve_only_registered_sources is True -- see
    that flag's docstring in app/config.py for why it defaults off.
    """
    allowed: list[dict] = []
    dropped = 0
    for document in documents:
        if is_registered_source(document):
            allowed.append(document)
        else:
            dropped += 1
    return allowed, dropped


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


__all__ = [
    "filter_blocked_sources",
    "filter_unregistered_sources",
    "is_blocked_source",
    "is_registered_source",
]
