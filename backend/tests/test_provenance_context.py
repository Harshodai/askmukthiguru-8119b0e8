from services.provenance_context import (
    BAND_COMMUNITY,
    BAND_CORROBORATED,
    BAND_DIRECT,
    BAND_GRAPH,
    build_provenance_context,
)


def test_provenance_context_builds_four_ranked_bands_and_manifest():
    docs = [
        {"text": "Direct teaching", "score": 0.9, "source_url": "https://source/1", "chunk_id": "seg-1", "entity_ids": ["Soul Sync"], "domain_rights_status": "licensed"},
        {"text": "Graph fact", "score": 0.8, "channel": "graph", "provenance": {"source": "neo4j://ontology/Soul Sync", "entity_id": "Soul Sync", "relation": "PRACTICE_FOR", "hop": 1}},
        {"text": "Corroborated fact", "score": 0.7, "channel": "vector", "provenance": {"source": "https://source/2", "graph": True, "relation": "EXPOUNDS", "hop": 1, "entity_ids": ["Soul Sync"], "ontology_version": "v1"}},
        {"text": "Community summary", "score": 0.6, "content_type": "community_summary", "source_url": "neo4j://community/1"},
    ]
    context = build_provenance_context(docs, entities_touched=["Soul Sync"], max_tokens=1000)
    assert len(context.bands[BAND_DIRECT]) == 1
    assert len(context.bands[BAND_GRAPH]) == 1
    assert len(context.bands[BAND_CORROBORATED]) == 1
    assert len(context.bands[BAND_COMMUNITY]) == 1
    assert context.entities_touched == ["Soul Sync"]
    manifest = context.to_manifest()
    assert manifest["bands"][BAND_CORROBORATED][0]["ontology_version"] == "v1"
    assert manifest["bands"][BAND_DIRECT][0]["rights_status"] == "licensed"


def test_provenance_context_obeys_token_budget():
    docs = [{"text": "x" * 1000, "score": 1.0, "source_url": "https://source/1"}]
    context = build_provenance_context(docs, max_tokens=10)
    assert context.evidence_count == 0
    assert context.total_tokens == 0
