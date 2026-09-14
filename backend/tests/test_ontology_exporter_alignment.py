"""domain/upper_ontology_mapping.py was written but never wired into the
exporter it names in its own docstring — services/ontology_exporter.py's
Turtle output had no schema.org/BFO/SKOS cross-references at all. These
tests pin the wiring: every ConceptType/RelationType must resolve to a real
external IRI in the exported Turtle, once per class/predicate (not repeated
per instance), and the SHACL passthrough must be reachable and never raise.
"""

from domain.spiritual_ontology import ConceptType, RelationType, SpiritualConcept
from services.ontology_exporter import OntologyExporter


def _concept(concept_type: ConceptType) -> SpiritualConcept:
    return SpiritualConcept(
        uri=f"https://askmukthiguru.org/ontology/{concept_type.name.lower()}/test",
        label="Test Concept",
        description="A test concept.",
        concept_type=concept_type,
        tradition="Ekam",
    )


def test_turtle_declares_schema_and_bfo_prefixes():
    turtle = OntologyExporter().to_rdf_turtle([_concept(ConceptType.EXPERIENCE)], [])
    assert "@prefix schema: <https://schema.org/> ." in turtle
    assert "@prefix bfo: <http://purl.obolibrary.org/obo/> ." in turtle


def test_every_concept_type_gets_one_alignment_block():
    """Schema-level axioms, not per-instance — count must match len(ConceptType)
    regardless of how many concept instances are exported."""
    turtle = OntologyExporter().to_rdf_turtle(
        [_concept(ConceptType.EXPERIENCE), _concept(ConceptType.EXPERIENCE)], []
    )
    for ct in ConceptType:
        assert turtle.count(f":{ct.name} a owl:Class ;") == 1, (
            f"ConceptType.{ct.name} alignment block missing or duplicated per-instance"
        )


def test_every_relation_type_gets_a_subproperty_alignment():
    turtle = OntologyExporter().to_rdf_turtle([], [])
    for rt in RelationType:
        assert f":{rt.value} rdfs:subPropertyOf <" in turtle, (
            f"RelationType.{rt.name} has no external predicate alignment"
        )


def test_validate_shacl_is_reachable_from_the_exporter_and_never_raises():
    turtle = OntologyExporter().to_rdf_turtle([_concept(ConceptType.PRACTICE)], [])
    result = OntologyExporter().validate_shacl(turtle)
    assert "available" in result
    assert result["conforms"] is None or isinstance(result["conforms"], bool)


def test_extended_turtle_still_passes_the_existing_rdflib_validator():
    """Guards against the alignment triples accidentally producing invalid Turtle."""
    turtle = OntologyExporter().to_rdf_turtle([_concept(ConceptType.EXPERIENCE)], [])
    assert OntologyExporter._validate_turtle(turtle) is True
