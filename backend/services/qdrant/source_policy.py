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
from typing import Any, Optional

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


class ReleasePolicyUnavailable(RuntimeError):
    """The active source-release version could not be resolved.

    Raised only in ``enforce`` mode. There is no safe default: guessing the
    configured fallback version either drops most of the corpus or serves
    revoked content, and neither is an abstain. Callers must fail closed
    (serve no document from this retrieval) rather than decide for the registry.
    """


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


def _coerce_release_version(value: Any) -> Optional[int]:
    """The payload's release version as an int, or None when absent/non-numeric.

    A malformed payload must not raise inside the retrieval hot loop (one bad
    point would 500 the whole answer): it is treated exactly like a missing
    version, which ``enforce`` drops and ``shadow`` only reports.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def filter_by_release(
    documents: Iterable[Any],
    filter_mode: Optional[str] = None,
    registry: Optional[Any] = None,
    corpus_id: Optional[str] = None,
) -> tuple[list[Any], int]:
    """DE-0.3: Filter documents based on active source-release version.

    Modes:
      - 'off': pass all documents through untouched.
      - 'shadow': evaluate which points would be excluded, log would_filter_inactive_release,
        increment RETRIEVAL_RELEASE_SHADOW_EXCLUSIONS_TOTAL, but retain the hits.
      - 'enforce': exclude hits whose ``source_release_version`` is missing,
        non-numeric, or does not match the active version.

    ``enforce`` fails CLOSED on missing evidence (ADR 0001 /
    SPEC-corpus-governance): an unstamped legacy point is not proof that it is
    current, so revocation really does cut it instantly. A registry read failure
    raises :class:`ReleasePolicyUnavailable` in ``enforce`` — a guessed fallback
    version would either drop most of the corpus or serve revoked content.
    ``shadow`` never changes what is served, so there a read failure keeps the
    hit and is only logged.
    """
    from app.config import settings

    mode = (
        str(
            filter_mode
            if filter_mode is not None
            else getattr(settings, "release_filter_mode", "off")
        )
        .strip()
        .lower()
    )
    if mode not in ("shadow", "enforce"):
        return list(documents), 0

    if registry is None:
        from app.corpus_release_registry import CorpusReleaseRegistry

        registry = CorpusReleaseRegistry.from_settings(settings)

    cid = corpus_id or getattr(settings, "default_corpus_id", "askmukthiguru")
    fallback_version = getattr(settings, "corpus_release_fallback_version", 1)

    allowed: list[Any] = []
    dropped = 0
    active_version_cache: dict[str, Optional[int]] = {}
    unresolvable: dict[str, str] = {}

    for doc in documents:
        if hasattr(doc, "payload") and isinstance(doc.payload, dict):
            payload = doc.payload
            doc_id = getattr(doc, "id", None)
        elif isinstance(doc, dict):
            payload = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else doc
            doc_id = doc.get("id") or doc.get("point_id")
        else:
            payload = {}
            doc_id = None

        point_version = _coerce_release_version(payload.get("source_release_version"))
        source_identity = (
            payload.get("source_identity")
            or payload.get("source_url")
            or payload.get("video_id")
            or (doc.get("source_url") if isinstance(doc, dict) else None)
            or "unknown"
        )

        if source_identity not in active_version_cache and source_identity not in unresolvable:
            try:
                resolved = registry.get_active_version(
                    corpus_id=cid,
                    source_identity=source_identity,
                    fallback_version=fallback_version,
                    # enforce must fail closed: an unreadable registry raises instead of
                    # silently becoming the fallback version.
                    **({"strict": True} if mode == "enforce" else {}),
                )
                active_version_cache[source_identity] = _coerce_release_version(resolved)
            except Exception as e:  # noqa: BLE001 - classified below
                logger.error("Active release version lookup failed for %s: %s", source_identity, e)
                unresolvable[source_identity] = str(e)

        if source_identity in unresolvable:
            if mode == "enforce":
                # Deferred: one raise for the whole call, with the real cause.
                raise ReleasePolicyUnavailable(
                    f"release registry unavailable for source {source_identity!r}: "
                    f"{unresolvable[source_identity]}"
                )
            # shadow: report only, never change what is served.
            active_version_cache[source_identity] = None

        active_ver = active_version_cache.get(source_identity)

        is_mismatch = point_version is None or active_ver is None or point_version != active_ver

        if is_mismatch:
            if mode == "shadow":
                logger.info(
                    "would_filter_inactive_release: point=%s source=%s version=%s active_version=%s",
                    doc_id,
                    source_identity,
                    payload.get("source_release_version"),
                    active_ver,
                )
                try:
                    from app.metrics import RETRIEVAL_RELEASE_SHADOW_EXCLUSIONS_TOTAL

                    RETRIEVAL_RELEASE_SHADOW_EXCLUSIONS_TOTAL.inc()
                except Exception as m_err:
                    logger.debug("Failed to increment shadow exclusion metric: %s", m_err)
                allowed.append(doc)
            elif mode == "enforce":
                dropped += 1
                continue
        else:
            allowed.append(doc)

    return allowed, dropped


__all__ = [
    "ReleasePolicyUnavailable",
    "filter_blocked_sources",
    "filter_unregistered_sources",
    "filter_by_release",
    "is_blocked_source",
    "is_registered_source",
]
