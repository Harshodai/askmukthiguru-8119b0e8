"""
KG Phase 6 — Ontology Writer: auto-extraction from ingestion.

Thin adapter that materializes hyper_extract entities + relationships
(deterministic) into Neo4j using the spiritual ontology schema
(`domain/spiritual_ontology.py`). Optional: also accepts LLM-extracted
triples (`ingest/triple_extractor.py`) for callers that want to merge
both sources.

Ponytail: one async function, one Cypher, no new LLM calls, no imports
of seed scripts. Non-fatal on any failure (logs + returns 0).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from domain.spiritual_ontology import ConceptType, RelationType

logger = logging.getLogger(__name__)

# =============================================================================
# Domain name lists — sourced from app/db/seed_ontology.py
# Kept in sync manually; do NOT import the seed function (it is a script).
# =============================================================================

# Teachers (person + organization) from seed_ontology.py teachers list.
_KNOWN_TEACHERS: frozenset[str] = frozenset(
    {
        "Sadhguru",
        "Sri Amma Bhagavan",
        "ISKCON",
        "Sri Preethaji",
        "Sri Krishnaji",
        "Ekam",
        "O&O Academy",
        "Mukthi Guru",
    }
)

# Practices from seed_ontology.py practices list + common practice keywords.
_KNOWN_PRACTICES: frozenset[str] = frozenset(
    {
        "Meditation",
        "Yoga",
        "Serene Mind",
        "Soul Sync",
        "Three Question Meditation",
        "Three Questions",
        "Inner Stillness Practice",
        "Collective Meditation Practice",
        "Collective Meditation",
        "Kriya Practice",
        "Heart Awakening Practice",
        "Four Sacred Secrets Practice",
        "Breath Awareness",
        "Witnessing",
        "Kriya",
        "Pranayama",
        "Mantra",
        "Japa",
    }
)

# Practice keyword fragments for fuzzy matching (lowercase substrings).
_PRACTICE_KEYWORDS: tuple[str, ...] = (
    "meditation",
    "breath",
    "yoga",
    "soul sync",
    "serene mind",
    "kriya",
    "pranayama",
    "mantra",
    "japa",
    "witnessing",
    "practice",
)

# =============================================================================
# Relation-verb -> RelationType mapping
# Covers verbs emitted by hyper_extract_adapter._infer_relation
# (see _RELATION_VERBS) + triple_extractor uppercase relation strings.
# Unknown -> IS_RELATED_TO.
# =============================================================================

_RELATION_VERB_TO_ENUM: dict[str, RelationType] = {
    # Generic / co-occurrence
    "related_to": RelationType.IS_RELATED_TO,
    "is_related_to": RelationType.IS_RELATED_TO,
    "related": RelationType.IS_RELATED_TO,
    # Teaching lineage
    "teaches": RelationType.IS_TAUGHT_BY,
    "teach": RelationType.IS_TAUGHT_BY,
    "guides": RelationType.IS_TAUGHT_BY,
    "guide": RelationType.IS_TAUGHT_BY,
    "expounds": RelationType.IS_TAUGHT_BY,
    "expound": RelationType.IS_TAUGHT_BY,
    # Causal / leads_to
    "leads_to": RelationType.LEADS_TO,
    "leads": RelationType.LEADS_TO,
    "brings": RelationType.LEADS_TO,
    "bring": RelationType.LEADS_TO,
    "creates": RelationType.CAUSES,
    "create": RelationType.CAUSES,
    "causes": RelationType.CAUSES,
    "cause": RelationType.CAUSES,
    "prevents": RelationType.PREVENTS,
    # Transformative
    "transforms": RelationType.TRANSFORMS,
    "transform": RelationType.TRANSFORMS,
    "awakens": RelationType.LEADS_TO_STATE,
    "awaken": RelationType.LEADS_TO_STATE,
    "manifests": RelationType.IS_MANIFESTATION_OF,
    "manifest": RelationType.IS_MANIFESTATION_OF,
    # Revealing / showing
    "reveals": RelationType.IS_MENTIONED_IN,
    "reveal": RelationType.IS_MENTIONED_IN,
    "shows": RelationType.IS_MENTIONED_IN,
    "show": RelationType.IS_MENTIONED_IN,
    # Helper verbs -> pragmatic
    "helps": RelationType.IS_USED_FOR,
    "help": RelationType.IS_USED_FOR,
    "connects": RelationType.IS_RELATED_TO,
    "connect": RelationType.IS_RELATED_TO,
    "opens": RelationType.IS_RELATED_TO,
    "open": RelationType.IS_RELATED_TO,
    "clears": RelationType.IS_RELATED_TO,
    "clear": RelationType.IS_RELATED_TO,
    "dissolves": RelationType.TRANSFORMS,
    "dissolve": RelationType.TRANSFORMS,
    "frees": RelationType.LEADS_TO,
    "free": RelationType.LEADS_TO,
    "expands": RelationType.IS_RELATED_TO,
    "expand": RelationType.IS_RELATED_TO,
    "deepens": RelationType.IS_RELATED_TO,
    "deepen": RelationType.IS_RELATED_TO,
    "restores": RelationType.IS_RELATED_TO,
    "restore": RelationType.IS_RELATED_TO,
    # Copula
    "is": RelationType.IS_A,
    "are": RelationType.IS_A,
    "was": RelationType.IS_A,
    "were": RelationType.IS_A,
    # Uppercase variants from triple_extractor LLM output
    "EXPOUNDS": RelationType.IS_TAUGHT_BY,
    "TEACHES": RelationType.IS_TAUGHT_BY,
    "PRACTICE_FOR": RelationType.IS_TECHNIQUE_FOR,
    "CONTRASTS_WITH": RelationType.IS_OPPOSITE_OF,
    "LEADS_TO": RelationType.LEADS_TO,
    "CAUSES": RelationType.CAUSES,
    "PREVENTS": RelationType.PREVENTS,
    "TRANSFORMS": RelationType.TRANSFORMS,
    "RELATED_TO": RelationType.IS_RELATED_TO,
    "REVEALS": RelationType.IS_MENTIONED_IN,
    "MANIFESTS_AS": RelationType.IS_MANIFESTATION_OF,
    "EXPRESSION_OF": RelationType.IS_ASPECT_OF,
    "PREREQUISITE_FOR": RelationType.IS_PREREQUISITE_FOR,
    "COMPONENT_OF": RelationType.PART_OF,
    "IS_A": RelationType.IS_A,
    "PART_OF": RelationType.PART_OF,
    # Inverse predicate forms — the relation-verb map uses active voice
    # (teaches/guides/expounds → IS_TAUGHT_BY), but triple extractors may
    # emit the passive inverse ("is a technique for" → IS_TECHNIQUE_FOR).
    # These inverse verbs ensure both directions are recognised.
    "IS_TAUGHT_BY": RelationType.IS_TAUGHT_BY,
    "IS_TECHNIQUE_FOR": RelationType.IS_TECHNIQUE_FOR,
    "IS_OPPOSITE_OF": RelationType.IS_OPPOSITE_OF,
    "IS_MENTIONED_IN": RelationType.IS_MENTIONED_IN,
    "IS_MANIFESTATION_OF": RelationType.IS_MANIFESTATION_OF,
    "IS_ASPECT_OF": RelationType.IS_ASPECT_OF,
    "IS_PREREQUISITE_FOR": RelationType.IS_PREREQUISITE_FOR,
    "IS_USED_FOR": RelationType.IS_USED_FOR,
}


def _normalize_entity(name: str) -> str:
    """Normalize entity name: strip whitespace, collapse inner spaces."""
    return " ".join(name.strip().split())


def _map_concept_type(entity: str) -> ConceptType:
    """Heuristic: teacher name -> BEING; practice keyword -> PRACTICE; else PRINCIPLE."""
    name = _normalize_entity(entity)
    lower_set = {t.lower() for t in _KNOWN_TEACHERS}
    if name in _KNOWN_TEACHERS or name.lower() in lower_set:
        return ConceptType.BEING
    lower_practices = {p.lower() for p in _KNOWN_PRACTICES}
    if name in _KNOWN_PRACTICES or name.lower() in lower_practices:
        return ConceptType.PRACTICE
    lower_name = name.lower()
    if any(keyword in lower_name for keyword in _PRACTICE_KEYWORDS):
        return ConceptType.PRACTICE
    return ConceptType.PRINCIPLE


def _map_relation(verb: str) -> RelationType:
    """Map a relation string (verb lemma or UPPERCASE label) -> RelationType."""
    key = verb.strip()
    if key in _RELATION_VERB_TO_ENUM:
        return _RELATION_VERB_TO_ENUM[key]
    lower_key = key.lower()
    if lower_key in _RELATION_VERB_TO_ENUM:
        return _RELATION_VERB_TO_ENUM[lower_key]
    upper_key = key.upper()
    if upper_key in _RELATION_VERB_TO_ENUM:
        return _RELATION_VERB_TO_ENUM[upper_key]
    return RelationType.IS_RELATED_TO


# Map ConceptType -> Neo4j label. BEING -> Teacher; PRACTICE -> Practice; else Concept.
_CONCEPT_TYPE_TO_LABEL: dict[ConceptType, str] = {
    ConceptType.BEING: "Teacher",
    ConceptType.PRACTICE: "Practice",
    ConceptType.PRINCIPLE: "Concept",
    ConceptType.EXPERIENCE: "Concept",
    ConceptType.TEXT: "Concept",
    ConceptType.TRADITION: "Concept",
    ConceptType.QUALITY: "Concept",
    ConceptType.OBSTACLE: "Concept",
    ConceptType.TOOL: "Concept",
    ConceptType.PATH: "Concept",
}


# Cypher: MERGE base node keyed by entity_id, then SET the typed label + props.
# Label is interpolated as a literal (safe: comes from a fixed map, not user input).
_NODE_MERGE_CYPHER_TEMPLATE = """
MERGE (n:base {{entity_id: $entity_id}})
SET n:{label},
    n.name = $name,
    n.entity_type = $entity_type,
    n.source_doc_id = $source_doc_id,
    n.source_chunk_id = $source_chunk_id,
    n.confidence = $confidence,
    n.extracted_at = $extracted_at
"""

# Cypher: MERGE typed relationship with provenance + confidence.
# Uses ON CREATE SET so first write stamps all original metadata; subsequent
# writes (re-ingestion of the same source) update timestamp+confidence but
# do NOT clear older provenance fields that a prior run may have set.
_REL_MERGE_CYPHER_TEMPLATE = """
MATCH (s:base {{entity_id: $subject_id}})
MATCH (o:base {{entity_id: $object_id}})
MERGE (s)-[r:{rel_type}]->(o)
ON CREATE SET
    r.source = $source,
    r.source_doc_id = $source_doc_id,
    r.source_chunk_id = $source_chunk_id,
    r.confidence = $confidence,
    r.extracted_at = $extracted_at
ON MATCH SET
    r.extracted_at = $extracted_at,
    r.confidence = CASE WHEN $confidence > r.confidence THEN $confidence ELSE r.confidence END
"""


async def write_extraction_to_neo4j(
    driver: Any,
    entities: list[str],
    relationships: list[tuple[str, str, str]],
    source_doc_id: str,
    source_chunk_id: str,
    confidence: float = 0.7,
    *,
    triples: Optional[Iterable[dict[str, str]]] = None,
) -> int:
    """Materialize entities + relationships (+ optional LLM triples) into Neo4j.

    Args:
        driver: neo4j.Driver (or any object with a `session()` context manager
            whose session exposes `run(query, **params)`).
        entities: list of entity name strings (from hyper_extract).
        relationships: list of (subject, relation_str, object) tuples.
        source_doc_id: provenance — doc URL / id this extraction came from.
        source_chunk_id: provenance — chunk id (may be "" if unknown).
        confidence: extraction confidence to stamp on nodes + edges.
        triples: optional iterable of {"subject","relation","object"} dicts
            (from triple_extractor.extract_triples) merged in the same pass.

    Returns:
        Count of writes performed (nodes MERGEd + relationships MERGEd).
        Non-fatal: on any exception logs a warning and returns 0.
    """
    if driver is None:
        return 0
    written = 0
    now = datetime.now(timezone.utc).isoformat()

    # Collect all entity names from both sources so we MERGE nodes first.
    all_entities: list[str] = list(entities or [])
    if triples:
        for t in triples:
            s = (t.get("subject") or "").strip()
            o = (t.get("object") or "").strip()
            if s and s not in all_entities:
                all_entities.append(s)
            if o and o not in all_entities:
                all_entities.append(o)

    try:
        with driver.session() as session:
            with session.begin_transaction() as tx:
                # 1. MERGE nodes with typed labels.
                for entity in all_entities:
                    name = (entity or "").strip()
                    if not name:
                        continue
                    concept_type = _map_concept_type(name)
                    label = _CONCEPT_TYPE_TO_LABEL.get(concept_type, "Concept")
                    cypher = _NODE_MERGE_CYPHER_TEMPLATE.format(label=label)
                    tx.run(
                        cypher,
                        entity_id=name,
                        name=name,
                        entity_type=concept_type.name.lower(),
                        source_doc_id=source_doc_id,
                        source_chunk_id=source_chunk_id,
                        confidence=confidence,
                        extracted_at=now,
                    )
                    written += 1

                # 2. MERGE relationships from hyper_extract.
                for subject, relation_str, obj in relationships or []:
                    s_name = (subject or "").strip()
                    o_name = (obj or "").strip()
                    if not s_name or not o_name:
                        continue
                    rel_enum = _map_relation(relation_str)
                    rel_type = rel_enum.value.upper()
                    cypher = _REL_MERGE_CYPHER_TEMPLATE.format(rel_type=rel_type)
                    tx.run(
                        cypher,
                        subject_id=s_name,
                        object_id=o_name,
                        source="hyper_extract",
                        source_doc_id=source_doc_id,
                        source_chunk_id=source_chunk_id,
                        confidence=confidence,
                        extracted_at=now,
                    )
                    written += 1

                # 3. MERGE relationships from LLM triples (if provided).
                if triples:
                    for t in triples:
                        s_name = (t.get("subject") or "").strip()
                        o_name = (t.get("object") or "").strip()
                        relation_str = (t.get("relation") or "").strip()
                        if not s_name or not o_name or not relation_str:
                            continue
                        rel_enum = _map_relation(relation_str)
                        rel_type = rel_enum.value.upper()
                        cypher = _REL_MERGE_CYPHER_TEMPLATE.format(rel_type=rel_type)
                        tx.run(
                            cypher,
                            subject_id=s_name,
                            object_id=o_name,
                            source="triple_extractor",
                            source_doc_id=source_doc_id,
                            source_chunk_id=source_chunk_id,
                            confidence=confidence,
                            extracted_at=now,
                        )
                        written += 1

                tx.commit()
    except Exception as e:
        logger.warning(f"write_extraction_to_neo4j failed (non-fatal): {e}")
        return 0
    return written


# =============================================================================
# Self-check
# =============================================================================

class _MockTransaction:
    """Records Cypher + params, supports commit/rollback."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def run(self, cypher: str, **params: Any) -> None:
        self.calls.append((cypher, params))

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass

    def __enter__(self) -> "_MockTransaction":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


class _MockSession:
    """Records Cypher + params for assertion. Context-manager compatible."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.tx: Optional[_MockTransaction] = None

    def __enter__(self) -> "_MockSession":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def run(self, cypher: str, **params: Any) -> None:
        self.calls.append((cypher, params))

    def begin_transaction(self) -> _MockTransaction:
        self.tx = _MockTransaction()
        return self.tx


class _MockDriver:
    """Minimal driver: session() returns a fresh recording session each call."""

    def __init__(self) -> None:
        self.sessions: list[_MockSession] = []

    def session(self) -> _MockSession:
        s = _MockSession()
        self.sessions.append(s)
        return s


if __name__ == "__main__":
    import asyncio

    async def _run() -> None:
        driver = _MockDriver()
        entities = ["Meditation", "Sri Preethaji", "Breath Awareness"]
        relationships = [
            ("Sri Preethaji", "teaches", "Meditation"),
            ("Meditation", "leads_to", "Breath Awareness"),
        ]
        count = await write_extraction_to_neo4j(
            driver,
            entities,
            relationships,
            source_doc_id="self-check-doc",
            source_chunk_id="self-check-chunk",
        )

        all_calls: list[tuple[str, dict]] = []
        for s in driver.sessions:
            if s.tx is not None:
                all_calls.extend(s.tx.calls)
            else:
                all_calls.extend(s.calls)

        node_cyphers = [c for c, _ in all_calls if "MERGE (n:base" in c]
        rel_cyphers = [c for c, _ in all_calls if "MERGE (s)-[r:" in c]

        print(f"writes: {count}")
        print(f"nodes MERGEd: {len(node_cyphers)} (expected 3)")
        print(f"relationships MERGEd: {len(rel_cyphers)} (expected 2)")
        print("\nCaptured Cypher statements:")
        for i, (cypher, params) in enumerate(all_calls, 1):
            compact = " ".join(line.strip() for line in cypher.strip().splitlines())
            print(f"  [{i}] {compact}")
            print(f"      params: {params}")

        assert len(node_cyphers) == 3, f"expected 3 node MERGEs, got {len(node_cyphers)}"
        assert len(rel_cyphers) == 2, f"expected 2 rel MERGEs, got {len(rel_cyphers)}"
        # Sri Preethaji -> Teacher, Meditation/Breath Awareness -> Practice.
        assert any(":Teacher" in c for c in node_cyphers), "expected a Teacher node"
        assert any(":Practice" in c for c in node_cyphers), "expected a Practice node"
        # teaches -> IS_TAUGHT_BY, leads_to -> LEADS_TO
        assert any("IS_TAUGHT_BY" in c for c in rel_cyphers), "expected IS_TAUGHT_BY edge"
        assert any("LEADS_TO" in c for c in rel_cyphers), "expected LEADS_TO edge"

        print("\nP6 OK")

    asyncio.run(_run())