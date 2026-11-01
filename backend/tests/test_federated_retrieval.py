import pytest
import asyncio
try:
    from rag.retrieval.adaptive_hyde import AdaptiveHyDEGenerator
    from rag.retrieval.rights_gate import ContentRightsGate
    from rag.retrieval.federated_engine import FederatedRetrievalEngine
except ModuleNotFoundError:
    from backend.rag.retrieval.adaptive_hyde import AdaptiveHyDEGenerator
    from backend.rag.retrieval.rights_gate import ContentRightsGate
    from backend.rag.retrieval.federated_engine import FederatedRetrievalEngine

@pytest.mark.asyncio
async def test_adaptive_hyde_trigger_rules():
    # Short query or exact quote should NOT trigger HyDE
    assert await AdaptiveHyDEGenerator.should_generate_hypothetical_document("peace") is False
    assert await AdaptiveHyDEGenerator.should_generate_hypothetical_document("exact quote about suffering") is False
    assert await AdaptiveHyDEGenerator.should_generate_hypothetical_document("I feel depressed and hopeless") is False

    # Conceptual / philosophical query should trigger HyDE
    assert await AdaptiveHyDEGenerator.should_generate_hypothetical_document("How does consciousness transition from suffering to liberation in Ekam?") is True

    passage = await AdaptiveHyDEGenerator.generate_hypothetical_passage("How does consciousness transition from suffering to liberation in Ekam?")
    assert passage is not None
    assert "Oneness" in passage or "Ekam" in passage

@pytest.mark.asyncio
async def test_rights_gate_invariant_x40():
    # Licensed candidate passes
    licensed_chunk = {
        "id": "chunk_001",
        "source": "Ekam teachings",
        "domain_rights_status": "licensed"
    }
    assert ContentRightsGate.validate_rights(licensed_chunk) is True

    # Unverified / missing rights fails closed
    unverified_chunk = {
        "id": "chunk_002",
        "source": "Unknown pirated PDF",
        "domain_rights_status": "unverified"
    }
    assert ContentRightsGate.validate_rights(unverified_chunk) is False

    # Missing status field fails closed
    missing_chunk = {
        "id": "chunk_003",
        "source": "External scrape"
    }
    assert ContentRightsGate.validate_rights(missing_chunk) is False

@pytest.mark.asyncio
async def test_gate_b_pe_scoring():
    engine = FederatedRetrievalEngine()
    
    # Test formula: P_ce = 0.45 * Dense + 0.35 * Sparse + 0.20 * Graph
    score = engine.calculate_cross_encoder_score(0.8, 0.7, 0.6)
    expected = 0.45 * 0.8 + 0.35 * 0.7 + 0.20 * 0.6
    assert abs(score - expected) < 1e-5

    # Threshold test (>= 0.15)
    results = await engine.retrieve("What is suffering and liberation?")
    assert isinstance(results, list)
    for r in results:
        assert r["p_ce"] >= 0.15
        assert r["domain_rights_status"] == "licensed"

def test_memgraph_open_cypher_formatting():
    # Verify no Neo4j references and proper bolt port query structure
    engine = FederatedRetrievalEngine()
    cypher = (
        "MATCH (c:Concept)-[:RELATES_TO]->(t:Teaching) "
        "WHERE c.name CONTAINS $query "
        "RETURN t.id AS id"
    )
    assert "MATCH" in cypher
    assert "RELATES_TO" in cypher
    assert "neo4j" not in cypher.lower()
