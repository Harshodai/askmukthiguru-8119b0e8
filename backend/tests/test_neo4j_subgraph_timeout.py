import asyncio
import time
from unittest.mock import MagicMock, patch
import pytest

from rag.nodes.retrieval import query_neo4j_subgraph
from app.config import settings


@pytest.mark.asyncio
async def test_query_neo4j_subgraph_times_out_gracefully():
    """Verify that a slow or hanging Neo4j session.run degrades to empty string within timeout."""
    def hanging_session():
        time.sleep(2.0)
        return []

    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_session.run.side_effect = lambda *args, **kwargs: hanging_session()
    mock_session.__enter__.return_value = mock_session
    mock_session.__exit__.return_value = None
    mock_driver.session.return_value = mock_session

    mock_container = MagicMock()
    mock_container.neo4j_driver = mock_driver

    with patch("app.dependencies.get_container", return_value=mock_container), \
         patch.object(settings, "neo4j_uri", "bolt://localhost:7687"), \
         patch.object(settings, "lightrag_retrieval_timeout", 0.2):
        
        start = time.monotonic()
        result = await query_neo4j_subgraph("What is the Beautiful State?")
        duration = time.monotonic() - start

        assert result == ""
        assert duration < 1.5, f"Expected timeout under 1.5s, took {duration}s"


@pytest.mark.asyncio
async def test_query_neo4j_subgraph_success():
    """Verify normal successful Neo4j subgraph returns formatted context."""
    mock_record = {
        "source": "beautiful state",
        "rel": "LEADS_TO",
        "desc": "Transcendence of suffering",
        "target": "ananda",
    }
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_session.run.return_value = [mock_record]
    mock_session.__enter__.return_value = mock_session
    mock_session.__exit__.return_value = None
    mock_driver.session.return_value = mock_session

    mock_container = MagicMock()
    mock_container.neo4j_driver = mock_driver

    with patch("app.dependencies.get_container", return_value=mock_container), \
         patch.object(settings, "neo4j_uri", "bolt://localhost:7687"), \
         patch.object(settings, "lightrag_retrieval_timeout", 5.0):
        
        result = await query_neo4j_subgraph("What is the Beautiful State?")
        assert "[Targeted Subgraph Context]:" in result
        assert "beautiful state -[LEADS_TO]-> ananda" in result
