"""
Formal Spiritual Ontology for Ask Mukthi Guru.

This module is the *formal definition* of the spiritual knowledge domain —
independent of any seed script, storage backend, or runtime service. It
defines the concepts, relationships, and constraints that govern spiritual
knowledge representation in the Knowledge Graph, following W3C OWL
principles adapted for the spiritual domain.

Tony Seale principle: "Semantics without identification is philosophy
without physics." Every concept carries a stable URI identifier so that
the ontology can be referenced cross-system, exported to RDF/OWL, and
used as the symbolic backbone for ontology-aware RAG and validation.

The real Neo4j graph (described by, but NOT queried from, this module)
uses labels `Teacher`, `Concept`, `Practice`, and `base` (LightRAG base
schema), with properties `entity_id`, `name`, `description`, `bio`,
`entity_type`, and the `EXPOUNDS` relation. This module stays naming-
consistent with that graph without hardcoding any Cypher.

No external dependencies beyond the Python standard library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


# === ONTOLOGY VERSIONING ===
# Semantic versioning (MAJOR.MINOR.PATCH):
#   MAJOR — breaking schema change (new ConceptType/RelationType removed/renamed,
#           URI scheme altered, dataclass shape changed in a back-incompatible way)
#   MINOR — new concepts/relations/ConceptTypes added (backward compatible)
#   PATCH — description fixes, seed-instance corrections, doc tweaks
# Single source of truth: the exporter and the /ontology/version endpoint both
# read from this constant so the version surfaced externally always matches
# the version stamped on every concept and relation.
ONTOLOGY_VERSION = "1.0.0"


class ConceptType(Enum):
    """Types of spiritual concepts."""

    PRACTICE = auto()       # Meditation technique, breathing exercise
    PRINCIPLE = auto()       # Core teaching, philosophical concept
    EXPERIENCE = auto()      # State of consciousness, feeling
    BEING = auto()           # Deity, guru, spiritual figure
    TEXT = auto()            # Scripture, teaching, book
    TRADITION = auto()       # Lineage, school of thought
    QUALITY = auto()         # Virtue, attribute
    OBSTACLE = auto()        # Challenge, limitation
    TOOL = auto()            # Mala, singing bowl, etc.
    PATH = auto()            # Spiritual path or stage


class RelationType(Enum):
    """Types of relationships between concepts."""

    # Hierarchical
    IS_A = "is_a"                            # Taxonomic
    PART_OF = "part_of"                      # Meronomic
    INSTANCE_OF = "instance_of"              # Instantiation

    # Causal
    LEADS_TO = "leads_to"                    # Causation
    CAUSES = "causes"                        # Strong causation
    PREVENTS = "prevents"                    # Negative causation

    # Temporal
    PRECEDES = "precedes"                    # Temporal order
    FOLLOWS = "follows"                      # Temporal successor

    # Semantic
    IS_RELATED_TO = "is_related_to"          # Generic
    IS_SIMILAR_TO = "is_similar_to"          # Similarity
    IS_OPPOSITE_OF = "is_opposite_of"        # Antonym

    # Pragmatic
    IS_USED_FOR = "is_used_for"              # Purpose
    IS_PREREQUISITE_FOR = "is_prerequisite_for"
    IS_TECHNIQUE_FOR = "is_technique_for"    # Method-goal

    # Spiritual-specific
    IS_MENTIONED_IN = "is_mentioned_in"      # Reference
    IS_TAUGHT_BY = "is_taught_by"            # Teaching lineage
    LEADS_TO_STATE = "leads_to_state"        # Practice -> state
    REQUIRES_QUALITY = "requires_quality"    # Practice needs virtue
    TRANSFORMS = "transforms"                # State A -> State B
    IS_MANIFESTATION_OF = "is_manifestation_of"
    IS_ASPECT_OF = "is_aspect_of"            # Partial identity


@dataclass
class SpiritualConcept:
    """
    A concept in the spiritual ontology.

    Every concept has a stable URI identifier, enabling cross-system
    reference and semantic interoperability.
    """

    # Stable identifier (URI format)
    uri: str  # e.g., "https://askmukthiguru.org/ontology/practice/breath-awareness"

    # Human-readable
    label: str  # e.g., "Breath Awareness"
    description: str

    # Classification
    concept_type: ConceptType

    # Source attribution
    tradition: Optional[str] = None  # e.g., "Buddhist", "Vedantic", "Ekam"
    source_texts: list[str] = field(default_factory=list)

    # Temporal
    historical_period: Optional[str] = None  # e.g., "Ancient India", "Contemporary"

    # Validation
    confidence: float = 1.0  # KG extraction confidence
    verified: bool = False   # Human-verified?

    # Metadata
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    # Ontology version this concept was defined under (single source of truth:
    # domain.spiritual_ontology.ONTOLOGY_VERSION). Defaults to the current
    # version so seed instances and any caller constructing a SpiritualConcept
    # without specifying it remain valid.
    ontology_version: str = ONTOLOGY_VERSION

    @property
    def short_id(self) -> str:
        """Extract short ID from URI."""
        return self.uri.split("/")[-1]

    @property
    def namespace(self) -> str:
        """Extract namespace from URI."""
        parts = self.uri.split("/")
        return "/".join(parts[:-1])


@dataclass
class Relation:
    """
    A typed relationship between two concepts.
    """

    subject_uri: str
    predicate: RelationType
    object_uri: str

    # Provenance
    source: str  # How was this relation established?
    confidence: float = 1.0

    # Temporal
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None

    # Context
    context: Optional[str] = None  # Teaching context where relation appears

    # Ontology version this relation was defined under (single source of truth:
    # domain.spiritual_ontology.ONTOLOGY_VERSION). Defaults to the current
    # version so seed instances and any caller constructing a Relation without
    # specifying it remain valid.
    ontology_version: str = ONTOLOGY_VERSION


# === ONTOLOGY INSTANCES ===

# Core practices
BREATH_AWARENESS = SpiritualConcept(
    uri="https://askmukthiguru.org/ontology/practice/breath-awareness",
    label="Breath Awareness",
    description="The practice of observing the natural flow of breath without controlling it.",
    concept_type=ConceptType.PRACTICE,
    tradition="Universal",
    source_texts=["Anapanasati Sutta", "Vijnana Bhairava Tantra"],
)

WITNESSING = SpiritualConcept(
    uri="https://askmukthiguru.org/ontology/practice/witnessing",
    label="Witnessing",
    description="The practice of observing thoughts, emotions, and sensations without identification.",
    concept_type=ConceptType.PRACTICE,
    tradition="Non-dual",
    source_texts=["Ashtavakra Gita", "Teachings of Nisargadatta Maharaj"],
)

# Core states
PRESENCE = SpiritualConcept(
    uri="https://askmukthiguru.org/ontology/experience/presence",
    label="Presence",
    description="The state of being fully aware and engaged in the current moment.",
    concept_type=ConceptType.EXPERIENCE,
    tradition="Universal",
)

# Core principles
NON_DUALITY = SpiritualConcept(
    uri="https://askmukthiguru.org/ontology/principle/non-duality",
    label="Non-Duality",
    description="The understanding that subject and object, self and universe, are not separate.",
    concept_type=ConceptType.PRINCIPLE,
    tradition="Advaita Vedanta",
    source_texts=["Mandukya Upanishad", "Avadhuta Gita"],
)

# Key relations
BREATH_AWARENESS_LEADS_TO_PRESENCE = Relation(
    subject_uri=BREATH_AWARENESS.uri,
    predicate=RelationType.LEADS_TO_STATE,
    object_uri=PRESENCE.uri,
    source="doctrinal",
    confidence=0.95,
)

WITNESSING_IS_TECHNIQUE_FOR_NON_DUALITY = Relation(
    subject_uri=WITNESSING.uri,
    predicate=RelationType.IS_TECHNIQUE_FOR,
    object_uri=NON_DUALITY.uri,
    source="doctrinal",
    confidence=0.90,
)

# Convenience registries for downstream services / validation
SEED_CONCEPTS: list[SpiritualConcept] = [
    BREATH_AWARENESS,
    WITNESSING,
    PRESENCE,
    NON_DUALITY,
]

SEED_RELATIONS: list[Relation] = [
    BREATH_AWARENESS_LEADS_TO_PRESENCE,
    WITNESSING_IS_TECHNIQUE_FOR_NON_DUALITY,
]


if __name__ == "__main__":
    # Validate: every seed instance has unique URI, every relation references
    # existing URIs, enum sizes correct.

    # (a) Count ConceptType and RelationType members.
    concept_type_count = len(ConceptType)
    relation_type_count = len(RelationType)
    print(f"ConceptType members: {concept_type_count}")
    print(f"RelationType members: {relation_type_count}")

    # (b) Assert all seed concept URIs are unique.
    seed_uris = [c.uri for c in SEED_CONCEPTS]
    assert len(seed_uris) == len(set(seed_uris)), "Duplicate seed concept URIs detected"
    print(f"Seed concepts: {len(SEED_CONCEPTS)} (all URIs unique)")

    # (c) Assert every Relation's subject_uri and object_uri match a seed concept URI.
    uri_set = set(seed_uris)
    for rel in SEED_RELATIONS:
        assert rel.subject_uri in uri_set, f"Relation subject_uri not in seeds: {rel.subject_uri}"
        assert rel.object_uri in uri_set, f"Relation object_uri not in seeds: {rel.object_uri}"
    print(f"Seed relations: {len(SEED_RELATIONS)} (all endpoints resolve to seed URIs)")

    # (d) Print short_id and namespace of BREATH_AWARENESS.
    print(f"BREATH_AWARENESS short_id: {BREATH_AWARENESS.short_id}")
    print(f"BREATH_AWARENESS namespace: {BREATH_AWARENESS.namespace}")

    # (e) Ontology version stamp — single source of truth.
    print(f"ONTOLOGY_VERSION: {ONTOLOGY_VERSION}")
    assert all(
        c.ontology_version == ONTOLOGY_VERSION for c in SEED_CONCEPTS
    ), "Seed concept missing current ontology_version"
    assert all(
        r.ontology_version == ONTOLOGY_VERSION for r in SEED_RELATIONS
    ), "Seed relation missing current ontology_version"
    print(
        f"All {len(SEED_CONCEPTS)} seed concepts and {len(SEED_RELATIONS)} "
        f"seed relations stamped with ontology_version={ONTOLOGY_VERSION}"
    )

    # (f) Final sentinel.
    print("A1 OK")