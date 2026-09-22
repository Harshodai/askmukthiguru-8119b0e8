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

# 2026-09-22 rights-register audit (docs/rights/source-register.md): the same
# book re-entered the live collection under a different source_url (an Amazon
# listing, not the scrubbed PDF filename), so the identity-only match above
# never caught it -- 1,199 chunks of its full text are live in
# spiritual_wisdom_contextual as of this writing. Block by ASIN (source_url
# substring) and title prefix (any chunk's chapter-qualified title starts with
# the book's title) until CONTENT-RIGHTS.md records a confirmed rights basis.
_BLOCKED_SOURCE_URL_SUBSTRINGS = frozenset({"1846046319"})  # Four Sacred Secrets ASIN/ISBN-10
_BLOCKED_TITLE_PREFIXES = ("the four sacred secrets",)

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
