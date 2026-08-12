"""Regression coverage for corpus-scoped ontology relationship writes."""

from __future__ import annotations

import pytest

from ingest.ontology_writer import _MockDriver, write_extraction_to_neo4j


@pytest.mark.asyncio
async def test_ontology_relationships_are_merged_with_corpus_provenance():
    driver = _MockDriver()

    writes = await write_extraction_to_neo4j(
        driver,
        entities=["Teacher", "Meditation"],
        relationships=[("Teacher", "teaches", "Meditation")],
        source_doc_id="source-1",
        source_chunk_id="chunk-1",
        corpus_id="teacher-a-corpus",
        teacher_id="teacher-a",
    )

    assert writes == 3
    calls = driver.sessions[0].tx.calls
    relationship_calls = [(cypher, params) for cypher, params in calls if "MERGE (s)-[r:" in cypher]
    assert len(relationship_calls) == 1
    cypher, params = relationship_calls[0]
    assert "{corpus_id: $corpus_id}" in cypher
    assert params["corpus_id"] == "teacher-a-corpus"
    assert params["teacher_id"] == "teacher-a"

@pytest.mark.asyncio
async def test_ontology_write_failure_is_explicit():
    from unittest.mock import MagicMock
    from ingest.ontology_writer import OntologyWriteError

    driver = MagicMock()
    session = driver.session.return_value.__enter__.return_value
    tx = session.begin_transaction.return_value
    tx.__enter__.return_value = tx
    tx.run.side_effect = RuntimeError("Neo4j unavailable")

    with pytest.raises(OntologyWriteError, match="materialization failed"):
        await write_extraction_to_neo4j(
            driver,
            entities=["Meditation"],
            relationships=[],
            source_doc_id="source-1",
            source_chunk_id="chunk-1",
        )
