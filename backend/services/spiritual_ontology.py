"""
Service-layer re-export and facade for spiritual ontology domain models and utilities.
Reconciles spiritual ontology resolution and provides unified case-insensitive entity normalization.
"""

from domain.spiritual_ontology import (
    CANONICAL_ENTITY_ALIASES,
    ONTOLOGY_VERSION,
    RELATION_TYPE_ALIASES,
    SEED_CONCEPTS,
    SEED_RELATIONS,
    TEACHER_DOMAINS,
    ConceptType,
    Relation,
    RelationType,
    SpiritualConcept,
    TeacherDomain,
    canonical_entity_id,
    normalize_entity_name,
    relation_type_to_neo4j_label,
    resolve_relation_type,
    resolve_teacher_domain,
)

SpiritualRelation = Relation
canonical_edge_label = relation_type_to_neo4j_label

__all__ = [
    "ONTOLOGY_VERSION",
    "ConceptType",
    "RelationType",
    "RELATION_TYPE_ALIASES",
    "relation_type_to_neo4j_label",
    "canonical_edge_label",
    "resolve_relation_type",
    "CANONICAL_ENTITY_ALIASES",
    "TeacherDomain",
    "TEACHER_DOMAINS",
    "resolve_teacher_domain",
    "normalize_entity_name",
    "canonical_entity_id",
    "SpiritualConcept",
    "Relation",
    "SpiritualRelation",
    "SEED_CONCEPTS",
    "SEED_RELATIONS",
]
