"""
Mukthi Guru — RAGGraphBuilder facade (C3b)

Thin facade over the existing Fast/Standard/Deep graph strategies
(`rag.graph_strategies`). Hides strategy selection, service-bundle
wiring, and compile caching behind a one-line-dispatch API.

Ponytail: zero graph construction logic lives here. The strategies
already assemble the LangGraph themselves; this module only picks the
right strategy, injects services into the module globals the nodes
read at invoke time (via `init_services`), and returns the cached
compiled graph.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Literal

from langgraph.graph.state import CompiledStateGraph

from app.dependencies import ServiceContainer
from rag.graph_strategies import (
    DeepGraphStrategy,
    FastGraphStrategy,
    StandardGraphStrategy,
)
from rag.nodes import init_services

if TYPE_CHECKING:
    pass


Tier = Literal["fast", "standard", "deep"]

_STRATEGY_FACTORIES = {
    "fast": FastGraphStrategy,
    "standard": StandardGraphStrategy,
    "deep": DeepGraphStrategy,
}


class RAGGraphBuilder:
    """Thin facade over existing Fast/Standard/Deep graph strategies.

    Hides: strategy selection, service-bundle wiring, graph caching.
    """

    def __init__(self, services: ServiceContainer) -> None:
        self._services = services

    def build(self, tier: Tier) -> CompiledStateGraph:
        """Compile (and cache) the graph for the given tier.

        Services are injected into the node module globals via
        ``init_services`` before the strategy builds, so nodes read the
        right singletons at invoke time. The compiled graph is cached by
        tier so repeated calls return the same instance.
        """
        return _build_cached(self, tier)

    def build_all(self) -> dict[str, CompiledStateGraph]:
        """Build every tier and return ``{tier: compiled_graph}``."""
        return {tier: self.build(tier) for tier in _STRATEGY_FACTORIES}

    @staticmethod
    def _prepare_kwargs(services: ServiceContainer) -> dict:
        return {
            "ollama_service": services.ollama,
            "embedding_service": services.embedding,
            "qdrant_service": services.qdrant,
            "lightrag_service": services.lightrag,
            "serene_mind_engine": getattr(services, "serene_mind_engine", None),
            "web_search": getattr(services, "web_search", None),
            "semantic_cache": getattr(services, "semantic_cache", None),
            "sarvam_cloud": getattr(services, "sarvam_cloud", None),
        }


@lru_cache(maxsize=4)
def _build_cached(builder: "RAGGraphBuilder", tier: Tier) -> CompiledStateGraph:
    """Compile a strategy ONCE per tier and return the cached graph.

    ``lru_cache`` keys on (builder id, tier). The builder instance is
    stable for the lifetime of the container, so per-process we compile
    each tier at most once. Services are NOT baked into the compiled
    graph — nodes read module globals set by ``init_services`` at
    invoke time, so caching the compiled graph by tier alone is safe.
    """
    try:
        factory = _STRATEGY_FACTORIES[tier]
    except KeyError as exc:
        raise ValueError(f"RAGGraphBuilder.build: unknown tier {tier!r}") from exc

    init_services(**RAGGraphBuilder._prepare_kwargs(builder._services))
    return factory().build()


def clear_graph_builder_cache() -> None:
    """Reset the compile cache (tests / container rebuild)."""
    _build_cached.cache_clear()


if __name__ == "__main__":
    print("Strategy classes:")
    print(f"  - {FastGraphStrategy.__name__}")
    print(f"  - {StandardGraphStrategy.__name__}")
    print(f"  - {DeepGraphStrategy.__name__}")

    print("\nRAGGraphBuilder public API:")
    print("  __init__(self, services: ServiceContainer)")
    print("  build(self, tier: Literal['fast','standard','deep']) -> CompiledStateGraph")
    print("  build_all(self) -> dict[str, CompiledStateGraph]")

    print("\nC3b OK")