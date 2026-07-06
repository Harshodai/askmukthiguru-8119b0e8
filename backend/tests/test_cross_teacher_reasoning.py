import sys

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from rag.states import GraphState
from rag.nodes.cross_teacher_reasoning import cross_teacher_reasoning

# rag/nodes/__init__.py does `from .cross_teacher_reasoning import cross_teacher_reasoning`,
# which shadows the `cross_teacher_reasoning` submodule attribute on the `rag.nodes`
# package with the function itself — so `import rag.nodes.cross_teacher_reasoning as x`
# would resolve to the function, not the module. Go through sys.modules instead.
cross_teacher_module = sys.modules["rag.nodes.cross_teacher_reasoning"]


@pytest.fixture(autouse=True)
def _reset_cross_teacher_module_state():
    """Each test patches GraphDatabase.driver independently — reset the shared
    driver singleton and query cache so they don't leak a stale mock/result
    across tests."""
    cross_teacher_module._driver = None
    cross_teacher_module._neo4j_query_cache.clear()
    yield
    cross_teacher_module._driver = None
    cross_teacher_module._neo4j_query_cache.clear()


@pytest.mark.asyncio
async def test_cross_teacher_reasoning_skipped_for_single_teacher():
    state = GraphState(
        question="What is Sadhguru's view on Karma?",
        relevant_docs=[]
    )
    result = await cross_teacher_reasoning(state)
    # Should skip since only Sadhguru is mentioned
    assert result == {}

@pytest.mark.asyncio
async def test_cross_teacher_reasoning_fires_for_multi_teacher_with_mock_neo4j():
    state = GraphState(
        question="How does Sadhguru's view on Karma compare to Sri Preethaji's?",
        relevant_docs=[{"content": "existing doc", "score": 0.5}]
    )
    
    # Mock Neo4j driver and session
    mock_record = {
        "teacher1": "Sadhguru",
        "teacher2": "Sri Preethaji",
        "concept": "Karma",
        "description": "Spiritual cause and effect."
    }
    
    mock_session = MagicMock()
    mock_session.execute_read.return_value = [mock_record]
    
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session
    
    with patch("rag.nodes.cross_teacher_reasoning.GraphDatabase.driver", return_value=mock_driver), \
         patch("app.config.settings.neo4j_uri", "bolt://mock:7687"):
         
        result = await cross_teacher_reasoning(state)
        
        assert "relevant_docs" in result
        assert len(result["relevant_docs"]) == 2
        assert result["is_cross_teacher"] is True
        assert "Sadhguru" in result["compared_teachers"]
        assert "Sri Preethaji" in result["compared_teachers"]
        assert "Ontology Connection" in result["relevant_docs"][0]["content"]
        assert result["relevant_docs"][0]["content_type"] == "ontology_comparison"


@pytest.mark.asyncio
async def test_cross_teacher_reasoning_krishnaji_vs_iskcon_guard():
    # If the question only mentions Krishnaji and Sadhguru,
    # it should NOT detect ISKCON (even though "krishnaji" contains "krishna").
    # It should also NOT detect Sri Preethaji (they are now separate).
    state = GraphState(
        question="How does Sadhguru's view compare to Krishnaji's?",
        relevant_docs=[]
    )
    
    mock_record = {
        "teacher1": "Sadhguru",
        "teacher2": "Sri Krishnaji",
        "concept": "Beautiful State",
        "description": "State of peace."
    }
    
    mock_session = MagicMock()
    mock_session.execute_read.return_value = [mock_record]
    
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session
    
    with patch("rag.nodes.cross_teacher_reasoning.GraphDatabase.driver", return_value=mock_driver), \
         patch("app.config.settings.neo4j_uri", "bolt://mock:7687"):
         
        result = await cross_teacher_reasoning(state)
        
        assert result.get("is_cross_teacher") is True
        compared = result["compared_teachers"]
        
        # Should only contain Sadhguru and Sri Krishnaji
        assert "Sadhguru" in compared
        assert "Sri Krishnaji" in compared
        assert "Sri Preethaji" not in compared
        assert "ISKCON" not in compared


@pytest.mark.asyncio
async def test_cross_teacher_reasoning_reuses_shared_driver_across_calls():
    """The Neo4j driver does a handshake/routing-table fetch on construction —
    it must be created once per process and reused, not opened per request."""
    mock_session = MagicMock()
    mock_session.execute_read.return_value = []

    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session

    with patch("rag.nodes.cross_teacher_reasoning.GraphDatabase.driver", return_value=mock_driver) as mock_ctor, \
         patch("app.config.settings.neo4j_uri", "bolt://mock:7687"):

        state1 = GraphState(
            question="How does Sadhguru's view on Karma compare to Sri Preethaji's?",
            relevant_docs=[]
        )
        await cross_teacher_reasoning(state1)

        state2 = GraphState(
            question="How does Sadhguru's view compare to Krishnaji's?",
            relevant_docs=[]
        )
        await cross_teacher_reasoning(state2)

        assert mock_ctor.call_count == 1
        mock_driver.close.assert_not_called()
