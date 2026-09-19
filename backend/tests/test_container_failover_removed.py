"""Regression test for AMK-E-003: Inert failover machinery removed from container."""

from unittest.mock import MagicMock


def test_container_inert_failover_not_constructed(monkeypatch):
    """Container _build_llm_services must not instantiate multi_provider_llm or model_registry."""
    from app.container import ServiceContainer

    # Create container instance without running __init__
    container = ServiceContainer.__new__(ServiceContainer)
    container.ollama = MagicMock()
    container.krutrim = MagicMock()

    container._build_llm_services()

    assert container.multi_provider_llm is None, (
        "multi_provider_llm should not be eagerly constructed"
    )
    assert container.model_registry is None, "model_registry should not be eagerly constructed"
