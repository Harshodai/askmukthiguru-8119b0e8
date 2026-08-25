"""

KG Phase 6 — Ontology Writer: auto-extraction from ingestion.

Thin adapter that materializes hyper_extract entities + relationships
(deterministic) into Neo4j using the spiritual ontology schema
(`domain/spiritual_ontology.py`). Optional: also accepts LLM-extracted
triples (`ingest/triple_extractor.py`) for callers that want to merge
of seed scripts. Raises an explicit exception when a write cannot commit.

Ponytail: one async function, one Cypher, no new LLM calls, no imports
of seed scripts. Non-fatal on any failure (logs + returns 0).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, Optional

from domain.spiritual_ontology import (
    ConceptType,
    RelationType,
    canonical_entity_id,
    resolve_relation_type,
    resolve_teacher_domain,
)

logger = logging.getLogger(__name__)


class OntologyWriteError(RuntimeError):
    """Raised when required ontology materialization cannot be committed."""


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
        "Sparsha Deeksha",
        "Smarana Deeksha",
        "Prana Deeksha",
        "Netra Deeksha",
        "Saptapadi",
        "Hamsa Soham Ekam",
        "Vastu Purusha Mandala",
        "Matra Shastra",
        "Neelakantha",
        "Nagabharana",
        "Ajna Chakra",
        "Sat-Chit-Ananda",
        "Shivaratri",
        "Antaryamin",
        "Sthitha Pragna",
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
# Central map lives in domain.spiritual_ontology.RELATION_TYPE_ALIASES.
# =============================================================================


def _map_concept_type(entity: str) -> ConceptType:
    """Heuristic: teacher name -> BEING; practice keyword -> PRACTICE; else PRINCIPLE."""
    name = " ".join(entity.strip().split())
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


def _resolve_relation(verb: str) -> RelationType:
    """Map verb -> RelationType via central domain map."""
    return resolve_relation_type(verb, strict=False)[0]


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
    n.extracted_at = $extracted_at,
    n.licensed_domain = $licensed_domain,
    n.domain_rights_status = $domain_rights_status
"""

# Cypher: MERGE typed relationships inside a corpus scope. Relationship scope is
# part of the merge key so a future teacher/corpus cannot overwrite a relation
# authored by the current corpus.
_REL_MERGE_CYPHER_TEMPLATE = """
MATCH (s:base {{entity_id: $subject_id}})
MATCH (o:base {{entity_id: $object_id}})
MERGE (s)-[r:{rel_type} {{tenant_id: $tenant_id, corpus_id: $corpus_id}}]->(o)
ON CREATE SET
    r.source = $source,
    r.source_doc_id = $source_doc_id,
    r.source_chunk_id = $source_chunk_id,
    r.teacher_id = $teacher_id,
    r.confidence = $confidence,
    r.extracted_at = $extracted_at,
    r.licensed_domain = $licensed_domain,
    r.domain_rights_status = $domain_rights_status,
    r.evidence = $evidence,
    r.reviewed = false,
    r.review_status = 'pending',
    r.reviewed_at = null,
    r.reviewed_by = null,
    r.reviewer_notes = null
ON MATCH SET
    r.extracted_at = $extracted_at,
    r.confidence = CASE WHEN $confidence > coalesce(r.confidence, 0.0) THEN $confidence ELSE r.confidence END,
    r.teacher_id = coalesce(r.teacher_id, $teacher_id),
    r.licensed_domain = coalesce(r.licensed_domain, $licensed_domain),
    r.domain_rights_status = coalesce(r.domain_rights_status, $domain_rights_status),
    r.evidence = coalesce(r.evidence, $evidence),
    r.reviewed = coalesce(r.reviewed, false),
    r.review_status = coalesce(r.review_status, 'pending')
"""


def _resolve_edge_rights_stamp(
    s_id: str, s_name: str, o_id: str, o_name: str
) -> tuple[Optional[bool], Optional[str]]:
    """Rights stamp for a relationship: if either endpoint resolves to a
    BEING/Teacher domain, propagate that domain's rights_status onto the
    edge (nodes for non-BEING types stay domain-agnostic, but the edge
    still traces back to the teacher/domain it was extracted alongside).
    """
    domain = (
        resolve_teacher_domain(s_id)
        or resolve_teacher_domain(s_name)
        or resolve_teacher_domain(o_id)
        or resolve_teacher_domain(o_name)
    )
    if domain is None:
        return None, None
    return domain.rollout_enabled, domain.rights_status


async def write_extraction_to_neo4j(
    driver: Any,
    entities: list[str],
    relationships: list[tuple[str, str, str]],
    source_doc_id: str,
    source_chunk_id: str,
    confidence: float = 0.7,
    *,
    triples: Optional[Iterable[dict[str, str]]] = None,
    source_evidence: Optional[str] = None,
    corpus_id: str = "askmukthiguru",
    teacher_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
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
        source_evidence: optional source text excerpt retained for human review.

    Raises:
        OntologyWriteError: if a Neo4j transaction cannot be committed. Callers
            must decide whether to roll back or explicitly mark graph output unavailable.
    """
    if driver is None:
        return 0
    written = 0
    from services.tenant_context import TenantContext

    tenant_id = tenant_id or TenantContext.get() or "default"
    now = datetime.now(UTC).isoformat()
    evidence = " ".join((source_evidence or source_doc_id or source_chunk_id or "").split())[:12000]

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
                    canon_id = canonical_entity_id(name)
                    concept_type = _map_concept_type(canon_id)
                    label = _CONCEPT_TYPE_TO_LABEL.get(concept_type, "Concept")
                    # Rights gate: only BEING (Teacher) nodes carry a domain — everything
                    # else has no licensing concept, so both stay None (not applicable).
                    licensed_domain: Optional[bool] = None
                    domain_rights_status: Optional[str] = None
                    if concept_type is ConceptType.BEING:
                        domain = resolve_teacher_domain(canon_id) or resolve_teacher_domain(name)
                        if domain is not None:
                            licensed_domain = domain.rollout_enabled
                            domain_rights_status = domain.rights_status
                        else:
                            # Recognized as BEING but not in the registry yet — quarantine
                            # as unverified rather than silently treating it as licensed.
                            licensed_domain = False
                            domain_rights_status = "unverified"
                    cypher = _NODE_MERGE_CYPHER_TEMPLATE.format(label=label)
                    tx.run(
                        cypher,
                        entity_id=canon_id,
                        name=name,
                        entity_type=concept_type.name.lower(),
                        licensed_domain=licensed_domain,
                        domain_rights_status=domain_rights_status,
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
                    s_id = canonical_entity_id(s_name)
                    o_id = canonical_entity_id(o_name)
                    rel_enum = _resolve_relation(relation_str)
                    rel_type = rel_enum.value.upper()
                    licensed_domain, domain_rights_status = _resolve_edge_rights_stamp(
                        s_id, s_name, o_id, o_name
                    )
                    cypher = _REL_MERGE_CYPHER_TEMPLATE.format(rel_type=rel_type)
                    tx.run(
                        cypher,
                        subject_id=s_id,
                        object_id=o_id,
                        source="hyper_extract",
                        source_doc_id=source_doc_id,
                        source_chunk_id=source_chunk_id,
                        corpus_id=corpus_id,
                        teacher_id=teacher_id,
                        tenant_id=tenant_id,
                        confidence=confidence,
                        extracted_at=now,
                        licensed_domain=licensed_domain,
                        domain_rights_status=domain_rights_status,
                        evidence=evidence,
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
                        s_id = canonical_entity_id(s_name)
                        o_id = canonical_entity_id(o_name)
                        rel_enum = _resolve_relation(relation_str)
                        rel_type = rel_enum.value.upper()
                        licensed_domain, domain_rights_status = _resolve_edge_rights_stamp(
                            s_id, s_name, o_id, o_name
                        )
                        cypher = _REL_MERGE_CYPHER_TEMPLATE.format(rel_type=rel_type)
                        tx.run(
                            cypher,
                            subject_id=s_id,
                            object_id=o_id,
                            source="triple_extractor",
                            source_doc_id=source_doc_id,
                            source_chunk_id=source_chunk_id,
                            corpus_id=corpus_id,
                            teacher_id=teacher_id,
                            tenant_id=tenant_id,
                            confidence=confidence,
                            extracted_at=now,
                            licensed_domain=licensed_domain,
                            domain_rights_status=domain_rights_status,
                        )
                        written += 1

                tx.commit()
    except Exception as e:
        logger.exception("write_extraction_to_neo4j failed: %s", e)
        raise OntologyWriteError("Neo4j ontology materialization failed") from e
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

    def __enter__(self) -> _MockTransaction:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


class _MockSession:
    """Records Cypher + params for assertion. Context-manager compatible."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.tx: Optional[_MockTransaction] = None

    def __enter__(self) -> _MockSession:
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
