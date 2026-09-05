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

import re
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
ONTOLOGY_VERSION = "1.1.0"


class ConceptType(Enum):
    """Types of spiritual concepts."""

    PRACTICE = auto()  # Meditation technique, breathing exercise
    PRINCIPLE = auto()  # Core teaching, philosophical concept
    EXPERIENCE = auto()  # State of consciousness, feeling
    BEING = auto()  # Deity, guru, spiritual figure
    TEXT = auto()  # Scripture, teaching, book
    TRADITION = auto()  # Lineage, school of thought
    QUALITY = auto()  # Virtue, attribute
    OBSTACLE = auto()  # Challenge, limitation
    TOOL = auto()  # Mala, singing bowl, etc.
    PATH = auto()  # Spiritual path or stage


class RelationType(Enum):
    """Types of relationships between concepts."""

    # Hierarchical
    IS_A = "is_a"  # Taxonomic
    PART_OF = "part_of"  # Meronomic
    INSTANCE_OF = "instance_of"  # Instantiation

    # Causal
    LEADS_TO = "leads_to"  # Causation
    CAUSES = "causes"  # Strong causation
    PREVENTS = "prevents"  # Negative causation

    # Temporal
    PRECEDES = "precedes"  # Temporal order
    FOLLOWS = "follows"  # Temporal successor

    # Semantic
    IS_RELATED_TO = "is_related_to"  # Generic
    IS_SIMILAR_TO = "is_similar_to"  # Similarity
    IS_OPPOSITE_OF = "is_opposite_of"  # Antonym

    # Pragmatic
    IS_USED_FOR = "is_used_for"  # Purpose
    IS_PREREQUISITE_FOR = "is_prerequisite_for"
    IS_TECHNIQUE_FOR = "is_technique_for"  # Method-goal

    # Spiritual-specific
    IS_MENTIONED_IN = "is_mentioned_in"  # Reference
    IS_TAUGHT_BY = "is_taught_by"  # Teaching lineage
    LEADS_TO_STATE = "leads_to_state"  # Practice -> state
    REQUIRES_QUALITY = "requires_quality"  # Practice needs virtue
    TRANSFORMS = "transforms"  # State A -> State B
    IS_MANIFESTATION_OF = "is_manifestation_of"
    IS_ASPECT_OF = "is_aspect_of"  # Partial identity


# Aliases for relation extraction. Maps natural-language verbs and uppercase
# labels (from LLM extractors) to the canonical RelationType.
# This single map prevents divergent relation typing across the codebase.
RELATION_TYPE_ALIASES: dict[str, RelationType] = {
    # Generic / co-occurrence
    "related_to": RelationType.IS_RELATED_TO,
    "is_related_to": RelationType.IS_RELATED_TO,
    "related": RelationType.IS_RELATED_TO,
    "RELATED_TO": RelationType.IS_RELATED_TO,
    # Teaching lineage
    "teaches": RelationType.IS_TAUGHT_BY,
    "teach": RelationType.IS_TAUGHT_BY,
    "guides": RelationType.IS_TAUGHT_BY,
    "guide": RelationType.IS_TAUGHT_BY,
    "expounds": RelationType.IS_TAUGHT_BY,
    "expound": RelationType.IS_TAUGHT_BY,
    "EXPOUNDS": RelationType.IS_TAUGHT_BY,
    "TEACHES": RelationType.IS_TAUGHT_BY,
    "IS_TAUGHT_BY": RelationType.IS_TAUGHT_BY,
    # Causal / leads_to
    "leads_to": RelationType.LEADS_TO,
    "leads": RelationType.LEADS_TO,
    "brings": RelationType.LEADS_TO,
    "bring": RelationType.LEADS_TO,
    "frees": RelationType.LEADS_TO,
    "free": RelationType.LEADS_TO,
    "LEADS_TO": RelationType.LEADS_TO,
    "causes": RelationType.CAUSES,
    "cause": RelationType.CAUSES,
    "creates": RelationType.CAUSES,
    "create": RelationType.CAUSES,
    "CAUSES": RelationType.CAUSES,
    "prevents": RelationType.PREVENTS,
    "prevent": RelationType.PREVENTS,
    "PREVENTS": RelationType.PREVENTS,
    # Transformative
    "transforms": RelationType.TRANSFORMS,
    "transform": RelationType.TRANSFORMS,
    "dissolves": RelationType.TRANSFORMS,
    "dissolve": RelationType.TRANSFORMS,
    "TRANSFORMS": RelationType.TRANSFORMS,
    "awakens": RelationType.LEADS_TO_STATE,
    "awaken": RelationType.LEADS_TO_STATE,
    "LEADS_TO_STATE": RelationType.LEADS_TO_STATE,
    "manifests": RelationType.IS_MANIFESTATION_OF,
    "manifest": RelationType.IS_MANIFESTATION_OF,
    "MANIFESTS_AS": RelationType.IS_MANIFESTATION_OF,
    "EXPRESSION_OF": RelationType.IS_ASPECT_OF,
    # Revealing / showing
    "reveals": RelationType.IS_MENTIONED_IN,
    "reveal": RelationType.IS_MENTIONED_IN,
    "shows": RelationType.IS_MENTIONED_IN,
    "show": RelationType.IS_MENTIONED_IN,
    "REVEALS": RelationType.IS_MENTIONED_IN,
    # Pragmatic
    "helps": RelationType.IS_USED_FOR,
    "help": RelationType.IS_USED_FOR,
    "IS_USED_FOR": RelationType.IS_USED_FOR,
    "IS_TECHNIQUE_FOR": RelationType.IS_TECHNIQUE_FOR,
    "PRACTICE_FOR": RelationType.IS_TECHNIQUE_FOR,
    "IS_PREREQUISITE_FOR": RelationType.IS_PREREQUISITE_FOR,
    "PREREQUISITE_FOR": RelationType.IS_PREREQUISITE_FOR,
    "CONTRASTS_WITH": RelationType.IS_OPPOSITE_OF,
    "IS_OPPOSITE_OF": RelationType.IS_OPPOSITE_OF,
    "COMPONENT_OF": RelationType.PART_OF,
    "IS_A": RelationType.IS_A,
    "PART_OF": RelationType.PART_OF,
    # Passive / inverse forms
    "is_technique_for": RelationType.IS_TECHNIQUE_FOR,
    "is_prerequisite_for": RelationType.IS_PREREQUISITE_FOR,
    "is_opposite_of": RelationType.IS_OPPOSITE_OF,
    "is_manifestation_of": RelationType.IS_MANIFESTATION_OF,
    "is_aspect_of": RelationType.IS_ASPECT_OF,
    "is_mentioned_in": RelationType.IS_MENTIONED_IN,
    # Copula
    "is": RelationType.IS_A,
    "are": RelationType.IS_A,
    "was": RelationType.IS_A,
    "were": RelationType.IS_A,
}


def resolve_relation_type(verb: str, *, strict: bool = False) -> tuple[RelationType, bool]:
    """
    Resolve a relation string to a canonical RelationType.

    Returns (relation_type, is_known). When `strict` is False, unknown verbs
    fall back to RelationType.IS_RELATED_TO so no edge is lost. When strict is
    True, unknown verbs return (None, False) — callers should drop them.
    """
    if not verb:
        return (RelationType.IS_RELATED_TO, False) if not strict else (None, False)  # type: ignore[return-value]
    key = verb.strip()
    if key in RELATION_TYPE_ALIASES:
        return RELATION_TYPE_ALIASES[key], True
    lower = key.lower()
    if lower in RELATION_TYPE_ALIASES:
        return RELATION_TYPE_ALIASES[lower], True
    upper = key.upper()
    if upper in RELATION_TYPE_ALIASES:
        return RELATION_TYPE_ALIASES[upper], True
    return (RelationType.IS_RELATED_TO, False) if not strict else (None, False)  # type: ignore[return-value]


def relation_type_to_neo4j_label(rel: RelationType) -> str:
    """Canonical Neo4j edge label: snake_case -> UPPER_SNAKE_CASE."""
    return rel.value.upper()


# Canonical entity aliases: maps common surface forms to a single entity_id.
# Used at ingestion time to deduplicate nodes across extraction sources.
CANONICAL_ENTITY_ALIASES: dict[str, str] = {
    # Teachers
    "preethaji": "Sri Preethaji",
    "krishnaji": "Sri Krishnaji",
    "amma bhagavan": "Sri Amma Bhagavan",
    "sri preethaji": "Sri Preethaji",
    "sri krishnaji": "Sri Krishnaji",
    # Organizations / Sacred Centers
    "o&o": "O&O Academy",
    "o and o academy": "O&O Academy",
    "o and o": "O&O Academy",
    "oo academy": "O&O Academy",
    "ekam": "Ekam",
    "ekam world": "Ekam",
    "ekam world centre": "Ekam",
    "ekam world center": "Ekam",
    "world centre for enlightenment": "Ekam",
    "world center for enlightenment": "Ekam",
    # Core States & Philosophical Concepts
    "beautiful state": "Beautiful State",
    "the beautiful state": "Beautiful State",
    "blissful state": "Beautiful State",
    "state of bliss": "Beautiful State",
    "state of calm": "Beautiful State",
    "state of joy": "Beautiful State",
    "no-stress state": "Beautiful State",
    "beautiful_state": "Beautiful State",
    "suffering state": "Suffering State",
    "the suffering state": "Suffering State",
    "state of suffering": "Suffering State",
    "painful state": "Suffering State",
    "state of pain": "Suffering State",
    "stressful state": "Suffering State",
    "suffering_state": "Suffering State",
    "aham": "Aham",
    "ahamkara": "Aham",
    "ahamkar": "Aham",
    "sense of i": "Aham",
    "ego-self": "Aham",
    "i-ness": "Aham",
    # Core Teachings & Sacred Treatises
    "four sacred secrets": "Four Sacred Secrets",
    "4 sacred secrets": "Four Sacred Secrets",
    "the four sacred secrets": "Four Sacred Secrets",
    "the four secrets": "Four Sacred Secrets",
    "sacred secrets": "Four Sacred Secrets",
    # Practices, Meditations & Transmissions
    "breath awareness": "Breath Awareness",
    "soul sync": "Soul Sync",
    "soul synchronization": "Soul Sync",
    "soul sync meditation": "Soul Sync",
    "breath meditation": "Soul Sync",
    "serene mind": "Serene Mind",
    "serene mind practice": "Serene Mind",
    "serene mind meditation": "Serene Mind",
    "conscious breathing": "Serene Mind",
    "deeksha": "Deeksha",
    "diksha": "Deeksha",
    "oneness blessing": "Deeksha",
    "divine blessing": "Deeksha",
    "energy transmission": "Deeksha",
    "sacred transfer": "Deeksha",
    "japa": "Japa",
    # Texts / traditions
    "bhagavad gita": "Bhagavad Gita",
    "gita": "Bhagavad Gita",
    "yoga sutras": "Yoga Sutras",
    "patanjali": "Yoga Sutras",
}


@dataclass
class TeacherDomain:
    """
    A rights-scoped teacher domain — the isolation boundary for one teacher's
    corpus, graph namespace, voice policy, and safety overlay. Nothing about
    one domain's content, voice, or safety policy crosses into another's
    without going through explicit cross-domain comparison logic.

    A domain with rollout_enabled=False may still be *recognized* as an
    entity (e.g. mentioned by name in a comparative teaching) but must never
    be treated as a retrievable corpus, and answers must never be voiced in
    that teacher's first person.
    """

    domain_id: str
    display_name: str
    # Canonical entity names belonging to this domain (matches values in
    # CANONICAL_ENTITY_ALIASES / _KNOWN_TEACHERS in ingest/ontology_writer.py).
    aliases: list[str] = field(default_factory=list)
    rights_status: str = "unverified"  # "licensed" | "unlicensed_reference_only" | "unverified"
    corpus_release: Optional[str] = (
        None  # e.g. settings.qdrant_collection value, if this domain has one
    )
    graph_namespace: Optional[str] = (
        None  # Neo4j scoping label/property for this domain's own nodes
    )
    voice_policy: str = "third_person_attribution_only"  # never first-person impersonation
    rollout_enabled: bool = (
        False  # gate: may this domain's content ever reach an answer as doctrine?
    )
    ontology_version: str = ONTOLOGY_VERSION


# Per root CLAUDE.md: "Data source: only Sri Preethaji & Sri Krishnaji's YouTube
# videos + approved images." Ekam is the only domain with a licensed corpus.
# The other three names in ingest/ontology_writer.py's _KNOWN_TEACHERS are
# recognized so cross-teacher mentions can be graphed and cited correctly,
# but none of them has an approved corpus, voice policy, or retrieval scope —
# they stay unlicensed reference entities until a real rights/corpus decision
# is made for each, per the plan's teacher-domain-registry requirement.
TEACHER_DOMAINS: dict[str, TeacherDomain] = {
    "ekam": TeacherDomain(
        domain_id="ekam",
        display_name="Sri Preethaji & Sri Krishnaji (Ekam / O&O Academy)",
        # Spelling/honorific variants confirmed live in the Neo4j graph
        # (2026-09-04 audit) that were resolving to no domain at all —
        # "Krishnaji" alone, "Shri"/"Sri Sri" honorific variants — meaning
        # genuine mentions of our own teachers were falling through the
        # domain-rights gate unrecognized (not blocked, just untracked).
        aliases=[
            "Sri Preethaji", "Shri Preethaji", "Sri Sri Preethaji",
            "Sri Krishnaji", "Shri Krishnaji", "Sri Sri Krishnaji", "Krishnaji",
            "Ekam", "O&O Academy",
        ],
        rights_status="licensed",
        graph_namespace="ekam",
        rollout_enabled=True,
    ),
    "sadhguru_external": TeacherDomain(
        domain_id="sadhguru_external",
        display_name="Sadhguru (external reference only)",
        aliases=["Sadhguru"],
        rights_status="unlicensed_reference_only",
        rollout_enabled=False,
    ),
    "amma_bhagavan_external": TeacherDomain(
        domain_id="amma_bhagavan_external",
        display_name="Sri Amma Bhagavan (external reference only)",
        aliases=["Sri Amma Bhagavan"],
        rights_status="unlicensed_reference_only",
        rollout_enabled=False,
    ),
    "iskcon_external": TeacherDomain(
        domain_id="iskcon_external",
        display_name="ISKCON (external reference only)",
        aliases=["ISKCON"],
        rights_status="unlicensed_reference_only",
        rollout_enabled=False,
    ),
}

# Reverse index: normalized alias -> domain_id, built once at import time.
_ALIAS_TO_DOMAIN: dict[str, str] = {
    alias.lower(): domain.domain_id
    for domain in TEACHER_DOMAINS.values()
    for alias in domain.aliases
}


def resolve_teacher_domain(entity_name: str) -> Optional[TeacherDomain]:
    """Resolve an entity name (teacher/org name) to its TeacherDomain, if any.

    Returns None for entities that aren't a recognized teacher/org name at
    all (most concepts, practices, etc. have no domain). Callers that need to
    gate on rights must additionally check `.rollout_enabled` — an entity can
    resolve to a domain and still be reference-only, not a licensed corpus.
    """
    domain_id = _ALIAS_TO_DOMAIN.get(normalize_entity_name(entity_name).lower())
    return TEACHER_DOMAINS.get(domain_id) if domain_id else None


def normalize_entity_name(name: str) -> str:
    """Normalize entity name: strip whitespace, collapse inner spaces."""
    if not name:
        return ""
    return " ".join(name.strip().split())


# Honorific prefixes/suffixes stripped before alias lookup — mirrors
# ingest/pipeline.py's `_consolidate_graph_entities.clean_name()` regex so
# LLM-extracted variants like "Guru Preethaji" resolve the same canonical
# id as "Sri Preethaji".
_HONORIFIC_PREFIX_RE = re.compile(
    r"^(sri|shri|sree|guruji|guru|swami|swamiji|acharya)\s+", re.IGNORECASE
)
_HONORIFIC_SUFFIX_RE = re.compile(r"\s+(ji|deva|dev|maharaj|swami|swamiji)$", re.IGNORECASE)


def canonical_entity_id(name: str) -> str:
    """Resolve entity name to canonical entity_id (case-insensitive).

    Strips honorific prefixes/suffixes before the alias lookup so a name
    variant that only differs by honorific still resolves to the same
    canonical id. Falls back to the (unstripped) normalized name when no
    alias matches, so unmapped entities keep their original entity_id.
    """
    if not name:
        return ""
    normalized = normalize_entity_name(name)
    stripped = _HONORIFIC_SUFFIX_RE.sub("", _HONORIFIC_PREFIX_RE.sub("", normalized)).strip()
    return (
        CANONICAL_ENTITY_ALIASES.get(stripped.lower())
        or CANONICAL_ENTITY_ALIASES.get(normalized.lower())
        or normalized
    )


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
    verified: bool = False  # Human-verified?

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
    assert all(c.ontology_version == ONTOLOGY_VERSION for c in SEED_CONCEPTS), (
        "Seed concept missing current ontology_version"
    )
    assert all(r.ontology_version == ONTOLOGY_VERSION for r in SEED_RELATIONS), (
        "Seed relation missing current ontology_version"
    )
    print(
        f"All {len(SEED_CONCEPTS)} seed concepts and {len(SEED_RELATIONS)} "
        f"seed relations stamped with ontology_version={ONTOLOGY_VERSION}"
    )

    # (f) TeacherDomain registry: exactly one licensed domain, aliases resolve
    # back to their own domain, unknown names resolve to None.
    licensed = [d for d in TEACHER_DOMAINS.values() if d.rollout_enabled]
    assert len(licensed) == 1 and licensed[0].domain_id == "ekam", (
        f"Expected exactly one enabled domain (ekam), got: {[d.domain_id for d in licensed]}"
    )
    assert resolve_teacher_domain("Sri Preethaji").domain_id == "ekam"
    assert resolve_teacher_domain("sadhguru").domain_id == "sadhguru_external"
    assert resolve_teacher_domain("sadhguru").rollout_enabled is False
    assert resolve_teacher_domain("Not A Real Teacher") is None
    print(
        f"TeacherDomain registry: {len(TEACHER_DOMAINS)} domains "
        f"({len(licensed)} licensed/enabled), alias resolution OK"
    )

    # (g) Final sentinel.
    print("A1 OK")
