"""Server-authoritative assistant persona and corpus-scope registry."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AssistantScope:
    """Server-resolved retrieval authority for an approved assistant persona."""

    corpus_id: str
    teacher_id: str | None = None
    graph_namespace: str | None = None
    source_release_id: str | None = None
    rights_status: str = "approved"
    rollout_enabled: bool = True


@lru_cache(maxsize=1)
def _allowed_slugs() -> frozenset[str]:
    raw = getattr(settings, "allowed_assistant_slugs", "") or ""
    return frozenset(s.strip() for s in raw.split(",") if s.strip())


@lru_cache(maxsize=1)
def _scope_registry() -> dict[str, AssistantScope]:
    """Parse configured assistant scopes; malformed entries are ignored."""
    raw = getattr(settings, "assistant_corpus_registry", "") or ""
    if not raw.strip():
        return {}
    try:
        parsed: Any = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("assistant_corpus_registry is invalid JSON; ignoring it")
        return {}
    if not isinstance(parsed, dict):
        logger.error("assistant_corpus_registry must be a JSON object")
        return {}

    scopes: dict[str, AssistantScope] = {}
    for slug, value in parsed.items():
        if not isinstance(slug, str) or not isinstance(value, dict):
            logger.warning("Ignoring malformed assistant scope entry %r", slug)
            continue
        corpus_id = value.get("corpus_id") or settings.default_corpus_id
        teacher_id = value.get("teacher_id")
        graph_namespace = value.get("graph_namespace")
        source_release_id = value.get("source_release_id")
        rights_status = str(value.get("rights_status", "approved")).strip().lower()
        rollout_enabled = value.get("rollout_enabled", True)
        if not isinstance(corpus_id, str) or not corpus_id.strip():
            logger.warning("Ignoring assistant scope %r with invalid corpus", slug)
            continue
        if teacher_id is not None and (not isinstance(teacher_id, str) or not teacher_id.strip()):
            logger.warning("Ignoring assistant scope %r with invalid teacher", slug)
            continue
        if rights_status not in {"approved", "pending", "revoked"}:
            logger.warning("Ignoring assistant scope %r with invalid rights status", slug)
            continue
        if not isinstance(rollout_enabled, bool):
            logger.warning("Ignoring assistant scope %r with invalid rollout flag", slug)
            continue
        scopes[slug] = AssistantScope(
            corpus_id=corpus_id.strip(),
            teacher_id=teacher_id.strip() if isinstance(teacher_id, str) else None,
            graph_namespace=graph_namespace.strip()
            if isinstance(graph_namespace, str) and graph_namespace.strip()
            else None,
            source_release_id=source_release_id.strip()
            if isinstance(source_release_id, str) and source_release_id.strip()
            else None,
            rights_status=rights_status,
            rollout_enabled=rollout_enabled,
        )
    return scopes


def validate_assistant_slug(slug: Optional[str]) -> Optional[str]:
    """Return a server-allowlisted slug or ``None`` for untrusted input."""
    if not slug or not isinstance(slug, str):
        return None
    if slug in _allowed_slugs():
        return slug
    logger.info("Rejecting non-allowlisted assistant slug %r.", slug)
    return None


def resolve_assistant_scope(slug: Optional[str]) -> AssistantScope | None:
    """Resolve an allowlisted persona to server-configured retrieval scope."""
    if not slug:
        return AssistantScope(corpus_id=settings.default_corpus_id)
    validated = validate_assistant_slug(slug)
    if validated is None:
        return None
    scope = _scope_registry().get(validated)
    if scope is None:
        logger.error("Allowlisted assistant slug %r has no configured scope", validated)
        return None
    if scope.rights_status != "approved" or not scope.rollout_enabled:
        logger.warning("Assistant scope %r is not currently approved for rollout", validated)
        return None
    return scope
