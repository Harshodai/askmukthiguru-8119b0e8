"""
Ontology schema validator for extracted triples.

Centralizes relation-typing so that deterministic extraction (hyper_extract),
LLM extraction (triple_extractor), and Neo4j materialization
(ontology_writer) all speak the same relation vocabulary.

Ponytail: thin wrapper around domain.spiritual_ontology.resolve_relation_type.
"""

from __future__ import annotations

import logging
from typing import Optional

from domain.spiritual_ontology import (
    RelationType,
    resolve_relation_type,
    relation_type_to_neo4j_label,
)

logger = logging.getLogger(__name__)


class OntologySchemaValidator:
    """
    Validate (subject, relation, object) triples against the spiritual ontology.

    In strict mode unknown relation verbs are rejected.
    In non-strict mode they fall back to IS_RELATED_TO with a logged warning.
    """

    def __init__(self, *, strict: bool = False) -> None:
        self.strict = strict

    def validate_triple(
        self,
        subject: str,
        verb: str,
        obj: str,
    ) -> Optional[dict[str, str]]:
        """
        Validate a single triple.

        Returns None if the triple is invalid (empty fields) or, in strict mode,
        if the verb cannot be mapped. Otherwise returns a dict with:
            subject, object, relation_label (Neo4j UPPER_CASE),
            relation_type (RelationType enum value), is_known.
        """
        s = (subject or "").strip()
        v = (verb or "").strip()
        o = (obj or "").strip()
        if not s or not v or not o:
            return None

        rel_enum, is_known = resolve_relation_type(v, strict=self.strict)
        if rel_enum is None:
            logger.debug(
                "ontology_schema_validator: dropping unknown verb %r "
                "for triple (%r, %r, %r) in strict mode",
                v, s, v, o,
            )
            return None

        if not is_known:
            logger.warning(
                "ontology_schema_validator: unknown verb %r -> IS_RELATED_TO "
                "for triple (%r, %r, %r)",
                v, s, v, o,
            )

        return {
            "subject": s,
            "object": o,
            "relation_label": relation_type_to_neo4j_label(rel_enum),
            "relation_type": rel_enum.value,
            "is_known": is_known,
        }


if __name__ == "__main__":
    validator = OntologySchemaValidator(strict=False)
    result = validator.validate_triple("Sri Preethaji", "teaches", "Beautiful State")
    assert result is not None
    assert result["relation_label"] == "IS_TAUGHT_BY"
    assert result["relation_type"] == "is_taught_by"

    strict = OntologySchemaValidator(strict=True)
    assert strict.validate_triple("X", "mysterious_verb", "Y") is None

    unknown = validator.validate_triple("X", "mysterious_verb", "Y")
    assert unknown is not None
    assert unknown["relation_label"] == "IS_RELATED_TO"
    assert unknown["is_known"] is False

    print("ontology_schema_validator OK")
