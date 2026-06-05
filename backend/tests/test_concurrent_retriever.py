from unittest.mock import AsyncMock

import pytest

from services.concurrent_retriever import ConcurrentRetriever


@pytest.mark.asyncio
async def test_concurrent_retrieve_calls_both_sources():
    mock_vector = AsyncMock(return_value=["vector_doc1", "vector_doc2"])
    mock_graph = AsyncMock(return_value=["graph_doc2", "graph_doc3"])

    retriever = ConcurrentRetriever(vector_fetcher=mock_vector, graph_fetcher=mock_graph)
    results = await retriever.retrieve("What is division?")

    assert "vector_doc1" in results["vector"]
    assert "graph_doc3" in results["graph"]
    mock_vector.assert_called_once_with("What is division?")
    mock_graph.assert_called_once_with("What is division?")


@pytest.mark.asyncio
async def test_concurrent_retriever_empty_results():
    mock_vector = AsyncMock(return_value=[])
    mock_graph = AsyncMock(return_value=[])

    retriever = ConcurrentRetriever(vector_fetcher=mock_vector, graph_fetcher=mock_graph)
    results = await retriever.retrieve("test query")

    assert results["vector"] == []
    assert results["graph"] == []