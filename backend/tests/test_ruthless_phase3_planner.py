"""Unit tests for Phase 3 Ruthless Remediation:
1. Lane budget configuration settings in app/config.py
2. 3-Lane Retrieval Strategy (Fast, Relational, Deep) in rag/nodes/retrieval.py
3. Parallel Neo4j graph ontology expansion (expand_query_via_kg) in rag/kg_expansion.py
4. Strict fail-open and timeout behavior under degraded/slow Neo4j
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from rag.context_graph import plan_context_graph
from rag.kg_expansion import expand_query_via_kg, expand_query_with_ontology
import rag.nodes as nodes
from rag.nodes import _services
from rag.nodes.retrieval import decompose_query


@pytest.fixture
def mock_retrieval_env(monkeypatch):
    """Fixture providing isolated mock services for retrieve_documents."""
    mock_embedder = MagicMock()
    mock_embedder.encode_single_full.return_value = {
        "dense": [0.1] * 1024,
        "sparse": {"1": 0.5},
    }
    mock_embedder.encode_batch.return_value = {
        "dense": [[0.1] * 1024],
        "sparse": [{"1": 0.5}],
    }
    mock_embedder.instruction = "Given a spiritual teaching, retrieve relevant passages: "

    mock_qdrant = MagicMock()
    mock_qdrant.search = MagicMock(
        return_value=[
            {"text": "Found document teaching", "source_url": "url1", "title": "doc1", "score": 0.9}
        ]
    )

    mock_lightrag = MagicMock()
    mock_lightrag.aquery = AsyncMock(return_value="")

    mock_ollama = AsyncMock()
    mock_ollama._generate_fast = AsyncMock(return_value="What is Ekam?")
    mock_ollama.decompose_query = AsyncMock(return_value=["What is karma?", "What is dharma?"])

    monkeypatch.setattr(_services, "_ollama", mock_ollama)
    monkeypatch.setattr(_services, "_embedder", mock_embedder)
    monkeypatch.setattr(_services, "_qdrant", mock_qdrant)
    monkeypatch.setattr(_services, "_lightrag", mock_lightrag)

    mock_container = MagicMock()
    mock_container.neo4j_driver = MagicMock()
    mock_container.neo4j_driver.session.return_value.__enter__.return_value.run.return_value = []
    monkeypatch.setattr("app.dependencies.get_container", lambda: mock_container)

    # Disable OKF and caches to focus on retrieval contract
    monkeypatch.setattr(settings, "rag_okf_injection_enabled", False)
    monkeypatch.setattr(settings, "semantic_cache_enabled", False)
    monkeypatch.setattr(settings, "retrieval_score_delta_enabled", False)
    monkeypatch.setattr(settings, "default_tenant_id", "default")
    monkeypatch.setattr(settings, "default_corpus_id", "default")
    monkeypatch.setattr(settings, "rag_skip_retrieval_expansions", True)

    return mock_embedder, mock_qdrant, mock_ollama


def test_config_phase3_lane_settings():
    """Task 1: Verify all required lane budget and KG expansion settings exist with correct defaults."""
    assert settings.retrieval_fast_lane_budget_ms == 1500
    assert settings.retrieval_relational_budget_ms == 3500
    assert settings.retrieval_deep_budget_ms == 8000
    assert settings.kg_ontology_expansion_timeout == 2.0
    assert settings.kg_max_hops == 2
    assert settings.kg_max_entities == 20
    assert settings.contradiction_resolution_enabled is True


@pytest.mark.asyncio
async def test_fast_lane_bypasses_graph_traversal_and_adheres_to_budget(mock_retrieval_env, monkeypatch):
    """Fast Lane: query_tier in ('fast', 'tier2_simple') completely bypasses graph traversal,
    enforces retrieval_fast_lane_budget_ms, and records lane metrics."""
    mock_embedder, mock_qdrant, _ = mock_retrieval_env

    # Track if graph expansion was ever called
    kg_called = {"called": False}

    async def _mock_kg(*args, **kwargs):
        kg_called["called"] = True
        return ["Dharma"]

    monkeypatch.setattr("rag.kg_expansion.expand_query_via_kg", _mock_kg)
    monkeypatch.setattr("rag.kg_expansion.expand_query_with_ontology", _mock_kg)

    mock_container = MagicMock()
    mock_container.neo4j_driver = object()
    monkeypatch.setattr("app.dependencies.get_container", lambda: mock_container)

    for tier in ("fast", "tier2_simple"):
        kg_called["called"] = False
        state = {
            "question": "What is the beautiful state?",
            "chat_history": [],
            "rewritten_query": None,
            "sub_queries": [],
            "selected_clusters": [],
            "hyde_text": None,
            "intent": "QUERY",
            "query_tier": tier,
            "tenant_id": "default",
            "corpus_id": "default",
        }

        res = await nodes.retrieve_documents(state)

        # Graph traversal must be completely bypassed in fast lane
        assert not kg_called["called"], f"Graph traversal was called in {tier} lane!"

        # Lane budget metrics
        assert res["retrieval_lane"] == "fast"
        assert res["lane_budget_ms"] == 1500
        assert res["lane_budget_consumed_ms"] > 0.0
        assert res["lane_budget_consumed_ms"] <= 1500

        # Timing breakdown in retrieval_stage_times
        stage_times = res["retrieval_stage_times"]
        assert stage_times["retrieval_lane"] == "fast"
        assert stage_times["lane_budget_ms"] == 1500
        assert stage_times["lane_budget_consumed_ms"] > 0.0

        # Context graph plan must bypass
        plan = plan_context_graph(state["question"], query_tier=tier)
        assert plan.mode == "none"

        # Query decomposition bypass
        decomp_res = await decompose_query(state)
        assert decomp_res["sub_queries"] == [state["question"]]
        assert decomp_res["is_complex"] is False


@pytest.mark.asyncio
async def test_relational_lane_parallelizes_vector_and_graph_expansion(mock_retrieval_env, monkeypatch):
    """Relational Lane: executes Qdrant hybrid retrieval and Neo4j graph ontology expansion
    concurrently with asyncio.gather without blocking."""
    mock_embedder, mock_qdrant, _ = mock_retrieval_env

    # Simulate 80ms vector search on the primary call
    vec_start, vec_end = 0.0, 0.0
    kg_start, kg_end = 0.0, 0.0
    search_count = 0

    def _slow_search(*args, **kwargs):
        nonlocal search_count, vec_start, vec_end
        search_count += 1
        if search_count == 1:
            vec_start = time.perf_counter()
            time.sleep(0.08)
            vec_end = time.perf_counter()
        return [{"text": "Found document teaching", "source_url": "url1", "title": "doc1", "score": 0.9}]

    mock_qdrant.search = _slow_search

    # Simulate 80ms KG expansion
    kg_calls = []

    async def _parallel_kg(query, driver, max_hops=2, max_entities=20, timeout=2.0):
        nonlocal kg_start, kg_end
        kg_calls.append({"hops": max_hops, "entities": max_entities, "timeout": timeout})
        kg_start = time.perf_counter()
        await asyncio.sleep(0.08)
        kg_end = time.perf_counter()
        return ["Dharma", "Universal Intelligence"]

    monkeypatch.setattr("rag.kg_expansion.expand_query_via_kg", _parallel_kg)

    mock_container = MagicMock()
    mock_container.neo4j_driver = object()
    monkeypatch.setattr("app.dependencies.get_container", lambda: mock_container)

    state = {
        "question": "What is karma?",
        "chat_history": [],
        "rewritten_query": None,
        "sub_queries": [],
        "selected_clusters": [],
        "hyde_text": None,
        "intent": "RELATIONAL",
        "query_tier": "relational",
        "tenant_id": "default",
        "corpus_id": "default",
    }

    started = time.perf_counter()
    res = await nodes.retrieve_documents(state)
    elapsed = time.perf_counter() - started

    # Overlapping execution: max(start) < min(end) proves true concurrency
    assert max(vec_start, kg_start) < min(vec_end, kg_end), (
        f"Vector search and KG expansion did not overlap! "
        f"vec=[{vec_start:.4f}, {vec_end:.4f}], kg=[{kg_start:.4f}, {kg_end:.4f}]"
    )
    # Total elapsed should be substantially less than sequential (0.08s + 0.08s = 0.16s) + overhead
    assert elapsed < 0.22, f"Expected fast concurrent completion <0.22s, took {elapsed:.3f}s"

    assert res["retrieval_lane"] == "relational"
    assert res["lane_budget_ms"] == 3500
    assert len(kg_calls) == 1
    # Check bounds passed to expand_query_via_kg
    assert kg_calls[0]["hops"] == 2
    assert kg_calls[0]["entities"] == 20
    assert kg_calls[0]["timeout"] == 2.0

    # Neighbors should be incorporated into the evaluation trace
    assert res["evaluation_trace"]["retrieval_lane"] == "relational"
    assert res["evaluation_trace"]["lane_budget_ms"] == 3500


@pytest.mark.asyncio
async def test_relational_lane_via_intent_relationship(mock_retrieval_env, monkeypatch):
    """Verify that intent requiring relationships (e.g. RELATIONAL, COMPARATIVE)
    triggers Relational Lane with 3500ms budget even on standard query tier."""
    mock_container = MagicMock()
    mock_container.neo4j_driver = object()
    monkeypatch.setattr("app.dependencies.get_container", lambda: mock_container)

    state = {
        "question": "How is suffering related to beautiful state?",
        "chat_history": [],
        "rewritten_query": None,
        "sub_queries": [],
        "selected_clusters": [],
        "hyde_text": None,
        "intent": "RELATIONAL",
        "query_tier": "standard",
        "tenant_id": "default",
        "corpus_id": "default",
    }

    res = await nodes.retrieve_documents(state)
    assert res["retrieval_lane"] == "relational"
    assert res["lane_budget_ms"] == 3500


@pytest.mark.asyncio
async def test_deep_lane_budget_and_metrics(mock_retrieval_env, monkeypatch):
    """Deep Lane: query_tier in ('tier3_complex', 'deep') enforces 8000ms budget."""
    for tier in ("deep", "tier3_complex"):
        state = {
            "question": "Compare meditation and contemplation across traditions.",
            "chat_history": [],
            "rewritten_query": None,
            "sub_queries": [],
            "selected_clusters": [],
            "hyde_text": None,
            "intent": "COMPARATIVE",
            "query_tier": tier,
            "tenant_id": "default",
            "corpus_id": "default",
        }

        res = await nodes.retrieve_documents(state)
        assert res["retrieval_lane"] == "deep"
        assert res["lane_budget_ms"] == 8000
        assert res["retrieval_stage_times"]["lane_budget_ms"] == 8000


@pytest.mark.asyncio
async def test_fail_open_when_kg_raises(mock_retrieval_env, monkeypatch):
    """Strict fail-open: when Neo4j/KG raises an error, retrieval succeeds and vector docs are returned."""
    async def _failing_kg(*args, **kwargs):
        raise ConnectionRefusedError("Neo4j database connection refused: bolt://localhost:7687")

    monkeypatch.setattr("rag.kg_expansion.expand_query_via_kg", _failing_kg)

    mock_container = MagicMock()
    mock_container.neo4j_driver = object()
    monkeypatch.setattr("app.dependencies.get_container", lambda: mock_container)

    state = {
        "question": "What is karma?",
        "chat_history": [],
        "rewritten_query": None,
        "sub_queries": [],
        "selected_clusters": [],
        "hyde_text": None,
        "intent": "RELATIONAL",
        "query_tier": "relational",
        "tenant_id": "default",
        "corpus_id": "default",
    }

    # Must NOT raise exception
    res = await nodes.retrieve_documents(state)
    assert len(res["documents"]) > 0
    assert res["documents"][0]["text"] == "Found document teaching"
    assert res["retrieval_lane"] == "relational"


@pytest.mark.asyncio
async def test_fail_open_when_kg_times_out(mock_retrieval_env, monkeypatch):
    """Strict fail-open: when Neo4j expansion times out, retrieval completes within budget without blocking."""
    # Set short timeout of 0.05s
    monkeypatch.setattr(settings, "kg_ontology_expansion_timeout", 0.05)

    async def _hanging_kg(*args, **kwargs):
        await asyncio.sleep(5.0)
        return ["Dharma"]

    monkeypatch.setattr("rag.kg_expansion.expand_query_via_kg", _hanging_kg)

    mock_container = MagicMock()
    mock_container.neo4j_driver = object()
    monkeypatch.setattr("app.dependencies.get_container", lambda: mock_container)

    state = {
        "question": "What is karma?",
        "chat_history": [],
        "rewritten_query": None,
        "sub_queries": [],
        "selected_clusters": [],
        "hyde_text": None,
        "intent": "RELATIONAL",
        "query_tier": "relational",
        "tenant_id": "default",
        "corpus_id": "default",
    }

    started = time.perf_counter()
    # retrieve_documents should not wait for the 5s hang
    res = await asyncio.wait_for(nodes.retrieve_documents(state), timeout=2.0)
    elapsed = time.perf_counter() - started

    assert elapsed < 1.0, f"Retrieval took {elapsed:.2f}s instead of failing fast on timeout"
    assert len(res["documents"]) > 0
    assert res["documents"][0]["text"] == "Found document teaching"


@pytest.mark.asyncio
async def test_expand_query_via_kg_unit_bounds_and_safety():
    """Unit tests for expand_query_via_kg: None driver, no concepts, bounds, and timeouts."""
    # 1. Driver is None -> fail open []
    assert await expand_query_via_kg("What is karma?", None) == []

    # 2. Query has no ontology concepts -> []
    mock_driver = MagicMock()
    assert await expand_query_via_kg("what is the weather today?", mock_driver) == []
    mock_driver.session.assert_not_called()

    # 3. Driver raises on session.run -> fail open []
    mock_driver_failing = MagicMock()
    mock_driver_failing.session.side_effect = RuntimeError("Driver closed")
    res = await expand_query_via_kg("What is karma?", mock_driver_failing)
    assert res == []

    # 4. Driver hangs -> times out fail open []
    mock_driver_hanging = MagicMock()

    def _hang():
        time.sleep(1.0)
        return []

    mock_driver_hanging.session.side_effect = _hang
    started = time.perf_counter()
    res = await expand_query_via_kg("What is karma?", mock_driver_hanging, timeout=0.05)
    elapsed = time.perf_counter() - started
    assert res == []
    assert elapsed < 0.5, f"expand_query_via_kg timeout exceeded: {elapsed:.2f}s"

    # 5. Backward compatibility with expand_query_with_ontology
    assert await expand_query_with_ontology("What is karma?", None) == []


@pytest.mark.asyncio
async def test_expand_query_via_kg_hops_and_entities_clamping():
    """Verify max_hops (max 2) and max_entities (max 20) clamping in expand_query_via_kg."""
    executed_cyphers = []
    executed_params = []

    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session

    mock_records = [{"neighbor": f"Neighbor_{i}"} for i in range(50)]
    mock_session.run.side_effect = lambda cypher, **kwargs: (
        executed_cyphers.append(cypher),
        executed_params.append(kwargs),
        [MagicMock(get=lambda k, rec=r: rec.get(k)) for r in mock_records],
    )[2]

    # Test with hops=10 (should be clamped to 2) and max_entities=100 (clamped to 20)
    neighbors = await expand_query_via_kg("What is karma?", mock_driver, max_hops=10, max_entities=100)

    assert len(neighbors) <= 20
    assert len(executed_params) > 0
    assert executed_params[0]["limit"] == 20
    # Cypher must have hops clamped to 2
    assert "*1..2" in executed_cyphers[0]
