"""Mandatory corpus-and-tenant containment contract for retrieval paths."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.config import settings


@dataclass(frozen=True)
class CorpusScope:
    """The smallest scope allowed to cross retrieval and graph boundaries."""

    tenant_id: str = settings.default_tenant_id
    corpus_id: str = settings.default_corpus_id
    teacher_id: str | None = None
    allowed_tags: tuple[str, ...] = field(default_factory=tuple)
    required_rights_status: str | None = None

    def to_qdrant_filter(self) -> dict[str, Any]:
        """Return strict payload conditions for shared Qdrant collections."""
        must: list[dict[str, Any]] = [
            {"key": "tenant_id", "match": {"value": self.tenant_id}},
            {"key": "corpus_id", "match": {"value": self.corpus_id}},
        ]
        if self.teacher_id:
            must.append({"key": "teacher_id", "match": {"value": self.teacher_id}})
        if self.required_rights_status:
            must.append(
                {"key": "domain_rights_status", "match": {"value": self.required_rights_status}}
            )
        return {"must": must}

    def to_neo4j_params(self) -> dict[str, Any]:
        """Return bound Cypher parameters; never interpolate scope values."""
        return {
            "tenant_id": self.tenant_id,
            "corpus_id": self.corpus_id,
            "teacher_id": self.teacher_id,
            "required_rights_status": self.required_rights_status,
        }
