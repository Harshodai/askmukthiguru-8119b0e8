"""The background graph build must be joined at interpreter exit.

A daemon thread still inside native code at finalization aborts the process
("terminate called without an active exception", exit 134). See lessons.md
L-GRAPH-WARMUP-EXIT-1.
"""

from unittest.mock import MagicMock

from app import container as container_module
from app.container import GRAPH_WARMUP_EXIT_JOIN_TIMEOUT_S, ServiceContainer


def test_graph_warmup_thread_is_joined_at_exit(monkeypatch):
    registered: list[tuple] = []
    for name in ("build_fast_graph", "build_rag_graph", "build_deep_graph"):
        monkeypatch.setattr(container_module, name, MagicMock())
    monkeypatch.setattr(
        container_module.atexit, "register", lambda fn, *args: registered.append((fn, args))
    )
    container = ServiceContainer.__new__(ServiceContainer)
    for attr in (
        "ollama",
        "embedding",
        "qdrant",
        "lightrag",
        "serene_mind",
        "web_search",
        "doctrine_service",
        "llm_gateway",
        "graphrag_fusion",
    ):
        setattr(container, attr, MagicMock())

    container._build_graphs()

    assert len(registered) == 1
    join, args = registered[0]
    assert join.__self__.name == "graph-warmup"
    assert join.__name__ == "join"
    assert args == (GRAPH_WARMUP_EXIT_JOIN_TIMEOUT_S,)
    join(*args)  # must return: the stubbed build finishes
    assert not join.__self__.is_alive()
