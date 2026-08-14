import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from starlette.requests import Request

from app.config import settings
from ingest.pipeline import IngestionPipeline
from services.memory_service_v2 import MemoryServiceV2


def test_neo4j_pool_defaults_are_bounded():
    assert 1 <= settings.neo4j_max_connection_pool_size <= 200
    assert settings.neo4j_connection_timeout_s > 0
    assert settings.neo4j_connection_acquisition_timeout_s > 0
    assert 0 <= settings.neo4j_max_transaction_retry_time_s <= 300
    assert settings.kg_subgraph_max_edges > 0


@pytest.mark.asyncio
async def test_memory_service_does_not_close_container_owned_driver():
    driver = MagicMock()
    service = MemoryServiceV2(
        MagicMock(),
        MagicMock(),
        neo4j_driver_accessor=lambda: driver,
    )
    assert service._get_neo4j() is driver
    await service.close()
    driver.close.assert_not_called()


def test_ingestion_pipeline_uses_injected_driver_accessor():
    driver = MagicMock()
    pipeline = IngestionPipeline(
        qdrant_service=MagicMock(),
        embedding_service=MagicMock(),
        ollama_service=None,
        neo4j_driver_accessor=lambda: driver,
    )
    assert pipeline._get_neo4j_driver() is driver


def test_cross_teacher_prefers_container_driver(monkeypatch):
    cross_module = sys.modules["rag.nodes.cross_teacher_reasoning"]
    import app.dependencies as dependencies

    driver = MagicMock()
    monkeypatch.setattr(
        dependencies,
        "_container",
        SimpleNamespace(neo4j_driver=driver),
    )
    cross_module._driver = None
    cross_module._owns_driver = False
    try:
        assert cross_module._get_driver() is driver
    finally:
        cross_module._driver = None
        cross_module._owns_driver = False


@pytest.mark.asyncio
async def test_kg_subgraph_caps_edges_per_matched_node(monkeypatch):
    import app.api.kg as kg_module

    class Session:
        def __init__(self):
            self.query = None
            self.kwargs = None

        def run(self, query, **kwargs):
            self.query = query
            self.kwargs = kwargs
            return iter([])

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    session = Session()
    driver = MagicMock()
    driver.session.return_value = session
    monkeypatch.setattr(
        kg_module,
        "get_container",
        lambda: SimpleNamespace(neo4j_driver=driver),
    )
    request = Request({"type": "http", "client": ("127.0.0.1", 1234)})
    result = await kg_module.kg_subgraph(
        request=request,
        query="beautiful state",
        limit=5,
        user={},
    )
    assert result.count == 0
    assert session.kwargs["edge_cap"] == settings.kg_subgraph_max_edges // 5
    assert "CALL" in session.query
    assert "LIMIT $edge_cap" in session.query
