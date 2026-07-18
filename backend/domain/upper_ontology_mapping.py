"""
Upper-ontology (schema.org / BFO / SKOS) alignment for the spiritual ontology.

Tony Seale's rule: reuse standard vocabularies, don't reinvent. Maps every
`ConceptType`/`RelationType` member in `domain/spiritual_ontology.py` to
well-known external IRIs so the doctrine graph is interoperable and
exportable to RDF/OWL. Additive only — does not modify `spiritual_ontology.py`.

Also carries the SHACL shape-validation helper (`validate_shacl`), which
degrades gracefully when `pyshacl` isn't installed, matching this repo's
existing convention (see `services/ontology_exporter.py::_validate_turtle`).

No hard external dependencies — stdlib only unless `validate_shacl()` is
actually called with `pyshacl` present.
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Namespace prefixes
# ---------------------------------------------------------------------------
PREFIXES = {
    "amg": "https://askmukthiguru.org/ontology/",
    "schema": "https://schema.org/",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "bfo": "http://purl.obolibrary.org/obo/",  # Basic Formal Ontology
    "dcterms": "http://purl.org/dc/terms/",
    "owl": "http://www.w3.org/2002/07/owl#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
}

# ---------------------------------------------------------------------------
# ConceptType -> external class IRIs. Keys are the REAL ConceptType member
# names from domain/spiritual_ontology.py (10 members) — not the pack's
# guessed STATE/CONCEPT/TEACHER, which don't exist in this repo's enum.
# ---------------------------------------------------------------------------
CONCEPT_TYPE_MAP: dict[str, dict[str, str]] = {
    "PRACTICE": {
        "schema": "https://schema.org/HowTo",
        "skos": "http://www.w3.org/2004/02/skos/core#Concept",
        "bfo": "http://purl.obolibrary.org/obo/BFO_0000015",  # process
    },
    "PRINCIPLE": {
        "schema": "https://schema.org/Intangible",
        "skos": "http://www.w3.org/2004/02/skos/core#Concept",
        "bfo": "http://purl.obolibrary.org/obo/BFO_0000031",  # generically dependent continuant
    },
    "EXPERIENCE": {
        "schema": "https://schema.org/Intangible",
        "skos": "http://www.w3.org/2004/02/skos/core#Concept",
        "bfo": "http://purl.obolibrary.org/obo/BFO_0000019",  # quality
    },
    "BEING": {
        "schema": "https://schema.org/Person",
        "skos": "http://www.w3.org/2004/02/skos/core#Concept",
        "bfo": "http://purl.obolibrary.org/obo/BFO_0000141",  # immaterial entity
    },
    "TEXT": {
        "schema": "https://schema.org/CreativeWork",
        "skos": "http://www.w3.org/2004/02/skos/core#Concept",
        "bfo": "http://purl.obolibrary.org/obo/BFO_0000031",
    },
    "TRADITION": {
        "schema": "https://schema.org/Intangible",
        "skos": "http://www.w3.org/2004/02/skos/core#ConceptScheme",
        "bfo": "http://purl.obolibrary.org/obo/BFO_0000031",
    },
    "QUALITY": {
        "schema": "https://schema.org/Intangible",
        "skos": "http://www.w3.org/2004/02/skos/core#Concept",
        "bfo": "http://purl.obolibrary.org/obo/BFO_0000019",  # quality
    },
    "OBSTACLE": {
        "schema": "https://schema.org/Intangible",
        "skos": "http://www.w3.org/2004/02/skos/core#Concept",
        "bfo": "http://purl.obolibrary.org/obo/BFO_0000031",
    },
    "TOOL": {
        "schema": "https://schema.org/Product",
        "skos": "http://www.w3.org/2004/02/skos/core#Concept",
        "bfo": "http://purl.obolibrary.org/obo/BFO_0000030",  # object
    },
    "PATH": {
        "schema": "https://schema.org/Intangible",
        "skos": "http://www.w3.org/2004/02/skos/core#ConceptScheme",
        "bfo": "http://purl.obolibrary.org/obo/BFO_0000031",
    },
}

_DEFAULT_CONCEPT_MAP = {
    "schema": "https://schema.org/Thing",
    "skos": "http://www.w3.org/2004/02/skos/core#Concept",
    "bfo": "http://purl.obolibrary.org/obo/BFO_0000001",  # entity
}

# ---------------------------------------------------------------------------
# RelationType -> external predicate IRIs. Keys are the REAL 21 RelationType
# members. Schema.org where a reasonable match exists; a stable first-party
# IRI otherwise (still resolvable, still versioned via the ontology).
# ---------------------------------------------------------------------------
RELATION_TYPE_MAP: dict[str, str] = {
    "IS_A": "http://www.w3.org/2004/02/skos/core#broader",
    "PART_OF": "https://schema.org/isPartOf",
    "INSTANCE_OF": "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
    "LEADS_TO": "https://schema.org/relatedTo",
    "CAUSES": "https://askmukthiguru.org/ontology/causes",
    "PREVENTS": "https://askmukthiguru.org/ontology/prevents",
    "PRECEDES": "https://askmukthiguru.org/ontology/precedes",
    "FOLLOWS": "https://askmukthiguru.org/ontology/follows",
    "IS_RELATED_TO": "https://schema.org/relatedTo",
    "IS_SIMILAR_TO": "http://www.w3.org/2004/02/skos/core#related",
    "IS_OPPOSITE_OF": "https://askmukthiguru.org/ontology/isOppositeOf",
    "IS_USED_FOR": "https://askmukthiguru.org/ontology/isUsedFor",
    "IS_PREREQUISITE_FOR": "https://askmukthiguru.org/ontology/isPrerequisiteFor",
    "IS_TECHNIQUE_FOR": "https://askmukthiguru.org/ontology/isTechniqueFor",
    "IS_MENTIONED_IN": "https://askmukthiguru.org/ontology/isMentionedIn",
    "IS_TAUGHT_BY": "https://schema.org/author",
    "LEADS_TO_STATE": "https://askmukthiguru.org/ontology/leadsToState",
    "REQUIRES_QUALITY": "https://askmukthiguru.org/ontology/requiresQuality",
    "TRANSFORMS": "https://askmukthiguru.org/ontology/transforms",
    "IS_MANIFESTATION_OF": "https://askmukthiguru.org/ontology/isManifestationOf",
    "IS_ASPECT_OF": "https://askmukthiguru.org/ontology/isAspectOf",
}

_DEFAULT_PREDICATE = "https://askmukthiguru.org/ontology/relatedTo"


def class_iris(concept_type_name: str) -> dict[str, str]:
    """External class IRIs for a ConceptType member name (falls back to Thing)."""
    return CONCEPT_TYPE_MAP.get(concept_type_name, _DEFAULT_CONCEPT_MAP)


def predicate_iri(relation_type_name: str) -> str:
    """External predicate IRI for a RelationType member name."""
    return RELATION_TYPE_MAP.get(relation_type_name, _DEFAULT_PREDICATE)


# ---------------------------------------------------------------------------
# SHACL validation — optional. `pyshacl` is not in requirements.txt; this
# degrades to a clear "not installed" result rather than crashing, same
# pattern as ontology_exporter.py's `_validate_turtle`.
# ---------------------------------------------------------------------------

SHACL_SHAPES_PATH = os.path.join(os.path.dirname(__file__), "ontology_shapes.ttl")


def validate_shacl(data_turtle: str, *, shapes_path: str = SHACL_SHAPES_PATH) -> dict:
    """Validate a Turtle graph against ontology_shapes.ttl.

    Returns {"available": bool, "conforms": bool | None, "report": str}.
    `available=False` means pyshacl isn't installed — not a validation
    failure, just an unmet optional dependency.
    """
    try:
        from pyshacl import validate as _pyshacl_validate
    except ImportError:
        return {"available": False, "conforms": None,
                "report": "pyshacl not installed — run `pip install pyshacl` to enable SHACL validation."}

    with open(shapes_path, "r", encoding="utf-8") as f:
        shapes_turtle = f.read()

    conforms, _report_graph, report_text = _pyshacl_validate(
        data_turtle, shacl_graph=shapes_turtle,
        data_graph_format="turtle", shacl_graph_format="turtle",
    )
    return {"available": True, "conforms": bool(conforms), "report": report_text}


if __name__ == "__main__":
    from domain.spiritual_ontology import ConceptType, RelationType

    # every real enum member must resolve to a mapping (no silent fallback holes)
    for ct in ConceptType:
        iris = class_iris(ct.name)
        assert iris is not _DEFAULT_CONCEPT_MAP, f"ConceptType.{ct.name} has no explicit mapping"
    for rt in RelationType:
        pred = predicate_iri(rt.name)
        assert pred != _DEFAULT_PREDICATE, f"RelationType.{rt.name} has no explicit mapping"

    result = validate_shacl("@prefix ex: <http://example.org/> . ex:x a ex:Y .")
    assert "available" in result

    print(f"upper_ontology_mapping self-check: OK — "
          f"{len(ConceptType)} ConceptTypes, {len(RelationType)} RelationTypes all mapped; "
          f"pyshacl available={result['available']}")
