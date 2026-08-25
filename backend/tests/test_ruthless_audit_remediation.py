from __future__ import annotations

from pathlib import Path

from services.lettuce_detect_service import LettuceDetectService
from services.memory_service import _derive_fact_key


ROOT = Path(__file__).resolve().parents[1]


def test_reworded_location_facts_share_deterministic_key():
    assert _derive_fact_key("I live in Delhi", {}) == "user:lives_in"
    assert _derive_fact_key("I moved to Chennai", {}) == "user:lives_in"


def test_unrelated_memory_facts_do_not_share_key():
    assert _derive_fact_key("I live in Delhi", {}) != _derive_fact_key(
        "I prefer morning meditation", {}
    )


def test_heuristic_faithfulness_exposes_atomic_claims():
    scorer = LettuceDetectService()
    result = scorer.score_faithfulness(
        "What is the Beautiful State?",
        "The Beautiful State is a state of connection and peace.",
        "The Beautiful State is a state of connection and peace. The moon controls every decision.",
        semantic=False,
    )

    assert len(result["claims"]) == 2
    assert result["claims"][0]["supported"] is True
    assert result["claims"][1]["supported"] is False
    assert result["is_faithful"] is False


def test_ontology_edges_are_pending_and_cross_teacher_query_requires_review():
    writer = (ROOT / "ingest" / "ontology_writer.py").read_text()
    reasoning = (ROOT / "rag" / "nodes" / "cross_teacher_reasoning.py").read_text()

    assert "r.reviewed = false" in writer
    assert "r.review_status = 'pending'" in writer
    assert "r.evidence = $evidence" in writer
    assert "coalesce(r1.reviewed, false) = true" in reasoning
    assert "coalesce(r2.reviewed, false) = true" in reasoning
    assert "confidence_floor" in reasoning


def test_fast_strategy_contains_verification_nodes():
    source = (ROOT / "rag" / "graph_strategies.py").read_text()
    fast_source = source[source.index("class FastGraphStrategy"):source.index("async def deep_contradiction_gate")]

    assert 'graph.add_node("reflect_on_answer", reflect_on_answer)' in fast_source
    assert 'graph.add_node("verify_answer", verify_answer)' in fast_source
    assert 'graph.add_edge("generate_answer", "reflect_on_answer")' in fast_source
    assert 'graph.add_edge("verify_answer", "extract_citations")' in fast_source


def test_okf_extraction_rejects_auto_approval():
    source = (ROOT / "scripts" / "extract_okf_from_stores.py").read_text()
    assert "cannot auto-approve generated doctrine" in source
    assert '"--auto-approve"' not in source
