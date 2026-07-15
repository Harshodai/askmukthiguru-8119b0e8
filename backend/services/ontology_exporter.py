"""
Export the spiritual ontology to standard W3C formats.

Materializes concepts and relations from the LIVE Neo4j graph (labels
``Teacher``/``Concept``/``Practice``/``base`` + ``EXPOUNDS`` relations) into
the in-memory :class:`domain.spiritual_ontology.SpiritualConcept` /
:class:`Relation` dataclasses, then serializes them to Turtle or JSON-LD.

This module never imports ``app/db/seed_ontology.py`` — the seed script is a
test fixture, not a data source. The exporter queries the real graph through
the shared ``container.neo4j_driver`` accessor.

No third-party deps required for serialization (stdlib only). ``rdflib`` is
imported opportunistically inside :func:`_validate_turtle` purely as an
optional validation aid — it is never required.

Self-check (no Neo4j needed):
    python services/ontology_exporter.py
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from domain.spiritual_ontology import (
    ConceptType,
    Relation,
    RelationType,
    SpiritualConcept,
    ONTOLOGY_VERSION,
)

logger = logging.getLogger(__name__)

ONTOLOGY_NAMESPACE = "https://askmukthiguru.org/ontology/"

# Map a Neo4j node label to a ConceptType. The live graph uses
# ``Teacher`` (with ``person``/``organization`` sub-labels), ``Concept``,
# ``Practice``, and the LightRAG ``base`` schema label. We only map the
# three semantic labels; ``base``/``person``/``organization`` are ignored as
# sub-labels and surface only as metadata.
_LABEL_TO_CONCEPT_TYPE: dict[str, ConceptType] = {
    "Practice": ConceptType.PRACTICE,
    "Teacher": ConceptType.BEING,
    "Concept": ConceptType.PRINCIPLE,
    # LightRAG ``base`` nodes that carry an ``entity_type`` hint
    "base": ConceptType.PRINCIPLE,
}

# Relation types observed (or expected) in the live graph, mapped to the
# ontology's RelationType enum. The analysis enumerates 21 types but the live
# graph today only emits ``EXPOUNDS`` (Teacher -> Concept). Unknown relation
# types fall back to ``IS_RELATED_TO`` so no edge is dropped on export.
_RELATION_TYPE_ALIASES: dict[str, RelationType] = {
    "EXPOUNDS": RelationType.IS_TAUGHT_BY,  # Teacher expounds Concept
    "IS_A": RelationType.IS_A,
    "PART_OF": RelationType.PART_OF,
    "INSTANCE_OF": RelationType.INSTANCE_OF,
    "LEADS_TO": RelationType.LEADS_TO,
    "CAUSES": RelationType.CAUSES,
    "PREVENTS": RelationType.PREVENTS,
    "PRECEDES": RelationType.PRECEDES,
    "FOLLOWS": RelationType.FOLLOWS,
    "IS_RELATED_TO": RelationType.IS_RELATED_TO,
    "IS_SIMILAR_TO": RelationType.IS_SIMILAR_TO,
    "IS_OPPOSITE_OF": RelationType.IS_OPPOSITE_OF,
    "IS_USED_FOR": RelationType.IS_USED_FOR,
    "IS_PREREQUISITE_FOR": RelationType.IS_PREREQUISITE_FOR,
    "IS_TECHNIQUE_FOR": RelationType.IS_TECHNIQUE_FOR,
    "IS_MENTIONED_IN": RelationType.IS_MENTIONED_IN,
    "IS_TAUGHT_BY": RelationType.IS_TAUGHT_BY,
    "LEADS_TO_STATE": RelationType.LEADS_TO_STATE,
    "REQUIRES_QUALITY": RelationType.REQUIRES_QUALITY,
    "TRANSFORMS": RelationType.TRANSFORMS,
    "IS_MANIFESTATION_OF": RelationType.IS_MANIFESTATION_OF,
    "IS_ASPECT_OF": RelationType.IS_ASPECT_OF,
}


def _slugify(value: str) -> str:
    """Stable slug for URIs: lowercase, alnum + hyphen, collapse repeats."""
    if not value:
        return "unknown"
    s = value.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "unknown"


def _concept_type_for(labels: list[str], entity_type: Optional[str]) -> ConceptType:
    """Pick the most specific ConceptType from a node's labels + entity_type.

    Checks labels in a fixed priority order so the result is deterministic:
    Teacher > Practice > Concept > base. Falls back to entity_type hints
    when no semantic label is present.
    """
    # Priority-ordered label check (semantic labels first).
    _LABEL_PRIORITY = ["Teacher", "Practice", "Concept", "base"]
    for label in _LABEL_PRIORITY:
        if label in labels:
            return _LABEL_TO_CONCEPT_TYPE.get(label, ConceptType.PRINCIPLE)
    # Fall back to entity_type hints.
    if entity_type:
        et = entity_type.strip().lower()
        for ct in ConceptType:
            if ct.name.lower() == et:
                return ct
        if et in {"teacher", "guru", "deity", "person", "organization", "sage", "master"}:
            return ConceptType.BEING
        if et in {"practice", "technique", "method", "exercise"}:
            return ConceptType.PRACTICE
        if et in {"experience", "state", "feeling"}:
            return ConceptType.EXPERIENCE
    return ConceptType.PRINCIPLE


def _relation_type_for(raw_type: str) -> RelationType:
    """Map a Neo4j relationship type to a RelationType (fallback IS_RELATED_TO)."""
    if not raw_type:
        return RelationType.IS_RELATED_TO
    key = raw_type.upper()
    if key in _RELATION_TYPE_ALIASES:
        return _RELATION_TYPE_ALIASES[key]
    # Try matching by the RelationType value (lowercase) as a last resort.
    for rt in RelationType:
        if rt.value.upper() == key:
            return rt
    logger.debug("ontology_exporter: unmapped relation type %r -> IS_RELATED_TO", raw_type)
    return RelationType.IS_RELATED_TO


def _build_uri(concept_type: ConceptType, entity_id: str) -> str:
    """Stable URI: https://askmukthiguru.org/ontology/<type>/<slug>."""
    slug = _slugify(entity_id)
    return f"{ONTOLOGY_NAMESPACE.rstrip('/')}/{concept_type.name.lower()}/{slug}"


def _escape_turtle_literal(value: str) -> str:
    """Escape a string for inclusion in a Turtle double-quoted literal."""
    if value is None:
        return ""
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


class OntologyExporter:
    """Export the spiritual ontology to W3C standard formats."""

    ONTOLOGY_NAMESPACE = ONTOLOGY_NAMESPACE

    def __init__(self, neo4j_driver: Any = None) -> None:
        """
        Parameters
        ----------
        neo4j_driver:
            Optional Neo4j driver (the shared ``container.neo4j_driver``).
            When provided, :meth:`materialize_from_graph` queries the live
            graph. The pure serialization methods (:meth:`to_rdf_turtle`,
            :meth:`to_jsonld`) work without a driver — they only consume
            in-memory concept/relation lists.
        """
        self._driver = neo4j_driver

    # ── Graph materialization ──────────────────────────────────────────────

    def materialize_from_graph(self) -> tuple[list[SpiritualConcept], list[Relation]]:
        """
        Query the live Neo4j graph and return (concepts, relations).

        Queries:
          1. All nodes labelled ``:Concept``, ``:Practice``, or ``:Teacher``
             (sub-labels ``person``/``organization`` ride along as metadata).
          2. All relationships between those nodes (``EXPOUNDS`` and any
             others that exist — we export what is present, not what the
             analysis speculates).
        """
        concepts: list[SpiritualConcept] = []
        relations: list[Relation] = []

        if self._driver is None:
            logger.warning("ontology_exporter: no neo4j_driver; returning empty graph.")
            return concepts, relations

        # No catch block: let exceptions propagate to the caller's existing
        # exception handling (e.g., the ontology/export route catches timeouts
        # and returns HTTP 504/500). Only the no-driver case returns empty.
        with self._driver.session() as session:
            concepts = self._fetch_concepts(session)
            relations = self._fetch_relations(session, concepts)

        return concepts, relations

    def _fetch_concepts(self, session: Any) -> list[SpiritualConcept]:
        """Pull all Concept/Practice/Teacher nodes and build SpiritualConcepts."""
        cypher = """
        MATCH (n)
        WHERE any(l IN labels(n) WHERE l IN ['Concept', 'Practice', 'Teacher'])
        RETURN
            coalesce(n.entity_id, n.name, elementId(n)) AS entity_id,
            coalesce(n.name, n.entity_id, n.description) AS name,
            coalesce(n.description, n.bio, '') AS description,
            labels(n) AS labels,
            n.entity_type AS entity_type,
            n.teacher_id AS teacher_id
        """
        seen_uris: set[str] = set()
        out: list[SpiritualConcept] = []
        for rec in session.run(cypher):
            entity_id = rec.get("entity_id")
            if not entity_id:
                continue
            labels = rec.get("labels") or []
            entity_type = rec.get("entity_type")
            concept_type = _concept_type_for(labels, entity_type)
            uri = _build_uri(concept_type, str(entity_id))
            if uri in seen_uris:
                continue
            seen_uris.add(uri)
            name = rec.get("name") or entity_id
            description = rec.get("description") or ""
            # Preserve teacher linkage as tradition hint when present.
            tradition = rec.get("teacher_id")
            out.append(
                SpiritualConcept(
                    uri=uri,
                    label=str(name),
                    description=str(description),
                    concept_type=concept_type,
                    tradition=str(tradition) if tradition else None,
                )
            )
        return out

    def _fetch_relations(
        self, session: Any, concepts: list[SpiritualConcept]
    ) -> list[Relation]:
        """Pull all relationships between exported concepts."""
        if not concepts:
            return []
        # Index by full entity_id first, with a fallback by short_id (slug via
        # recursion/descendants that don't carry the base entity_id property).
        uri_index: dict[str, str] = {}
        for c in concepts:
            if c.entity_id:
                uri_index[c.entity_id] = c.uri
            uri_index.setdefault(c.short_id, c.uri)
        cypher = """
        MATCH (a)-[r]->(b)
        WHERE any(la IN labels(a) WHERE la IN ['Concept', 'Practice', 'Teacher'])
          AND any(lb IN labels(b) WHERE lb IN ['Concept', 'Practice', 'Teacher'])
        RETURN
            coalesce(a.entity_id, a.name, elementId(a)) AS src_id,
            coalesce(b.entity_id, b.name, elementId(b)) AS dst_id,
            type(r) AS rel_type,
            r.confidence AS confidence,
            r.source AS source
        """
        out: list[Relation] = []
        seen: set[tuple[str, str, str]] = set()
        for rec in session.run(cypher):
            src_id = rec.get("src_id")
            dst_id = rec.get("dst_id")
            rel_type = rec.get("rel_type")
            if not src_id or not dst_id or not rel_type:
                continue
            src_uri = uri_index.get(_slugify(str(src_id)))
            dst_uri = uri_index.get(_slugify(str(dst_id)))
            # Fall back to a rebuilt URI if the slug isn't in the index
            # (can happen if the node labels differ from what we mapped).
            if src_uri is None:
                src_uri = _build_uri(ConceptType.PRINCIPLE, str(src_id))
            if dst_uri is None:
                dst_uri = _build_uri(ConceptType.PRINCIPLE, str(dst_id))
            predicate = _relation_type_for(str(rel_type))
            key = (src_uri, predicate.value, dst_uri)
            if key in seen:
                continue
            seen.add(key)
            conf = rec.get("confidence")
            try:
                confidence = float(conf) if conf is not None else 1.0
            except (TypeError, ValueError):
                confidence = 1.0
            out.append(
                Relation(
                    subject_uri=src_uri,
                    predicate=predicate,
                    object_uri=dst_uri,
                    source=str(rec.get("source") or "graph"),
                    confidence=confidence,
                )
            )
        return out

    # ── Serializers ────────────────────────────────────────────────────────

    def to_rdf_turtle(
        self, concepts: list[SpiritualConcept], relations: list[Relation]
    ) -> str:
        """Export to RDF Turtle format (stdlib-only serializer)."""
        lines: list[str] = [
            "@prefix : <https://askmukthiguru.org/ontology/> .",
            "@prefix owl: <http://www.w3.org/2002/07/owl#> .",
            "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .",
            "@prefix xml: <http://www.w3.org/XML/1998/namespace> .",
            "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
            "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
            "@prefix skos: <http://www.w3.org/2004/02/skos/core#> .",
            "",
            ": a owl:Ontology ;",
            '    rdfs:label "Ask Mukthi Guru Spiritual Ontology"@en ;',
            '    rdfs:comment "Formal ontology for spiritual concepts and practices"@en ;',
            '    owl:versionInfo "%s" .' % ONTOLOGY_VERSION,
            "",
        ]

        for concept in concepts:
            lines.extend(self._concept_to_turtle(concept))
            lines.append("")

        for relation in relations:
            lines.extend(self._relation_to_turtle(relation))
            lines.append("")

        return "\n".join(lines)

    def _concept_to_turtle(self, concept: SpiritualConcept) -> list[str]:
        """Convert a single concept to Turtle triples."""
        uri = f":{concept.short_id}"
        label = _escape_turtle_literal(concept.label)
        desc = _escape_turtle_literal(concept.description)

        lines: list[str] = [
            f"{uri} a :{concept.concept_type.name} ;",
            f'    rdfs:label "{label}"@en ;',
            f'    rdfs:comment "{desc}"@en ;',
        ]

        if concept.tradition:
            lines.append(f'    :tradition "{_escape_turtle_literal(concept.tradition)}" ;')

        for text in concept.source_texts:
            lines.append(f'    :sourceText "{_escape_turtle_literal(text)}" ;')

        lines.append(f'    :ontologyVersion "{concept.ontology_version}" ;')
        lines.append(f'    :confidence "{concept.confidence}"^^xsd:float ;')
        # Replace trailing separator on the last triple with a terminator.
        lines[-1] = lines[-1].rstrip(" ;") + " ."
        return lines

    def _relation_to_turtle(self, relation: Relation) -> list[str]:
        """Convert a single relation to Turtle triples."""
        subj = f":{relation.subject_uri.split('/')[-1]}"
        pred = f":{relation.predicate.value}"
        obj = f":{relation.object_uri.split('/')[-1]}"
        src = _escape_turtle_literal(relation.source)
        return [
            f"{subj} {pred} {obj} ;",
            f'    :ontologyVersion "{relation.ontology_version}" ;',
            f'    :confidence "{relation.confidence}"^^xsd:float ;',
            f'    :source "{src}" .',
        ]

    def to_owl_xml(
        self, concepts: list[SpiritualConcept], relations: list[Relation]
    ) -> str:
        """Export to OWL/XML format for Protege and other tools."""
        raise NotImplementedError("OWL/XML export coming in v1.1")

    def to_jsonld(
        self, concepts: list[SpiritualConcept], relations: list[Relation]
    ) -> dict:
        """Export to JSON-LD for web APIs."""
        return {
            "@context": {
                "@vocab": self.ONTOLOGY_NAMESPACE,
                "owl": "http://www.w3.org/2002/07/owl#",
                "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
            },
            "@type": "owl:Ontology",
            "rdfs:label": "Ask Mukthi Guru Spiritual Ontology",
            "owl:versionInfo": ONTOLOGY_VERSION,
            "concepts": [
                {
                    "@id": c.uri,
                    "@type": c.concept_type.name,
                    "rdfs:label": c.label,
                    "rdfs:comment": c.description,
                    "ontology_version": c.ontology_version,
                    **({"tradition": c.tradition} if c.tradition else {}),
                }
                for c in concepts
            ],
            "relations": [
                {
                    "@type": "Relation",
                    "subject": r.subject_uri,
                    "predicate": r.predicate.value,
                    "object": r.object_uri,
                    "confidence": r.confidence,
                    "source": r.source,
                    "ontology_version": r.ontology_version,
                }
                for r in relations
            ],
        }

    # ── Optional validation ───────────────────────────────────────────────

    @staticmethod
    def _validate_turtle(turtle: str) -> bool:
        """Best-effort Turtle validation. Requires ``rdflib`` if available."""
        try:
            import rdflib  # type: ignore
        except Exception:  # noqa: BLE001 — optional dep
            logger.debug("ontology_exporter: rdflib not installed; skipping validation.")
            return True
        try:
            g = rdflib.Graph()
            g.parse(data=turtle, format="turtle")
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("ontology_exporter: turtle validation failed: %s", exc)
            return False


# ── Self-check ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Build an exporter with no Neo4j driver — serialization-only path.
    exporter = OntologyExporter(neo4j_driver=None)

    sample_concepts = [
        SpiritualConcept(
            uri="https://askmukthiguru.org/ontology/practice/breath-awareness",
            label="Breath Awareness",
            description="The practice of observing the natural flow of breath without controlling it.",
            concept_type=ConceptType.PRACTICE,
            tradition="Universal",
            source_texts=["Anapanasati Sutta"],
            confidence=0.95,
        ),
        SpiritualConcept(
            uri="https://askmukthiguru.org/ontology/experience/presence",
            label="Presence",
            description="The state of being fully aware and engaged in the current moment.",
            concept_type=ConceptType.EXPERIENCE,
            tradition="Universal",
            confidence=1.0,
        ),
    ]
    sample_relation = Relation(
        subject_uri=sample_concepts[0].uri,
        predicate=RelationType.LEADS_TO_STATE,
        object_uri=sample_concepts[1].uri,
        source="doctrinal",
        confidence=0.9,
    )

    turtle_out = exporter.to_rdf_turtle(sample_concepts, [sample_relation])
    jsonld_out = exporter.to_jsonld(sample_concepts, [sample_relation])

    print("--- TURTLE (first 200 chars) ---")
    print(turtle_out[:200])
    print("--- JSON-LD (first 200 chars) ---")
    print(str(jsonld_out)[:200])
    print("A2 OK")