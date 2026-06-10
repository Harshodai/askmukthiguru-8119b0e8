from unittest.mock import AsyncMock, MagicMock

import pytest


# Setup mocks to prevent external network calls
@pytest.mark.asyncio
async def test_retrieve_documents_contract(monkeypatch):
    """Verify retrieve_documents state contract enforcement and query_tier fallback."""
    
    # Mock settings and dependencies
    from app.config import settings
    
    # Mock Qdrant and Embedder services
    mock_embedder = MagicMock()
    # Mock return value for encode_single_full
    mock_embedder.encode_single_full.return_value = {
        "dense": [0.1] * 1024,
        "sparse": {"1": 0.5}
    }
    mock_embedder.instruction = "Given a spiritual teaching, retrieve relevant passages: "
    
    mock_qdrant = MagicMock()
    # Mock search to return some mock documents
    mock_qdrant.search = MagicMock(return_value=[
        {"text": "Found document teaching", "source_url": "url1", "title": "doc1", "score": 0.9}
    ])
    
    # Mock LightRAG if called
    mock_lightrag = MagicMock()
    mock_lightrag.aquery = AsyncMock(return_value="LightRAG wisdom")
    
    # Inject mock services into nodes module
    import rag.nodes as nodes
    mock_ollama = AsyncMock()
    mock_ollama._generate_fast = AsyncMock(return_value="What is Ekam?")
    monkeypatch.setattr(nodes, "_ollama", mock_ollama)
    monkeypatch.setattr(nodes, "_embedder", mock_embedder)
    monkeypatch.setattr(nodes, "_qdrant", mock_qdrant)
    monkeypatch.setattr(nodes, "_lightrag", mock_lightrag)
    
    # Disable cache for simplicity
    monkeypatch.setattr(settings, "semantic_cache_enabled", False)

    # 1. Test missing required key "question"
    invalid_state = {}
    res = await nodes.retrieve_documents(invalid_state)
    assert "error" in res
    assert "NodeContractError" in res["error"]

    # 2. Test valid state without query_tier (should fallback to standard and not crash)
    valid_state = {
        "question": "What is Ekam?",
        "chat_history": [],
        "rewritten_query": None,
        "sub_queries": [],
        "selected_clusters": [],
        "hyde_text": None,
        "intent": "FACTUAL"
    }
    
    # Call retrieve_documents and ensure no crash
    res = await nodes.retrieve_documents(valid_state)
    
    assert "error" not in res
    assert len(res) > 0
    # The returned dictionary is merged into the GraphState. For our mocked call,
    # retrieve_hybrid will return our mock documents.
    # Nodes return the updated/merged state dictionary or list of docs.
    # In retrieve_documents, it returns {"documents": [...]}.
    assert "documents" in res
    assert len(res["documents"]) > 0
    assert any(doc["text"] == "Found document teaching" for doc in res["documents"])
    assert any(doc["text"] == "LightRAG wisdom" for doc in res["documents"])
