"""Mukthi Guru — Node Registry for Config-Driven Graph Building

Design Pattern: Registry + Decorator

Each LangGraph node function is registered with optional metadata:
  - is_llm: does this node make an LLM call? (for cost/latency tracking)
  - default_llm_config: per-node LLM defaults (effort, timeout, model)

Usage:
    from rag.node_registry import registry

    @registry.register("intent_router", is_llm=True)
    async def intent_router(state: GraphState) -> dict:
        ...

This indirection lets us discover node capabilities without importing
nodes.py directly (avoids circular imports during graph building).
"""

from __future__ import annotations

import functools
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NodeSpec:
    """Immutable specification for a graph node."""

    name: str
    func: Callable
    is_llm: bool = True
    default_llm_config: Dict[str, Any] = field(default_factory=dict)


class NodeRegistry:
    """Central registry for all LangGraph node functions.

    Supports decorator-based registration so nodes self-register at
    module import time.
    """

    def __init__(self) -> None:
        self._nodes: Dict[str, NodeSpec] = {}

    def register(
        self,
        name: str,
        *,
        is_llm: bool = True,
        default_llm_config: Optional[Dict[str, Any]] = None,
    ) -> Callable:
        """Return a decorator that registers the decorated function.

        Args:
            name: Unique node name (must match the name used in graph wiring).
            is_llm: Whether this node issues LLM calls.
            default_llm_config: Default LLM config (effort, timeout, model, etc.).
        """

        def decorator(func: Callable) -> Callable:
            if name in self._nodes:
                logger.warning(f"Node '{name}' already registered; overwriting.")

            # Store the function with metadata
            self._nodes[name] = NodeSpec(
                name=name,
                func=func,
                is_llm=is_llm,
                default_llm_config=default_llm_config or {},
            )

            # Preserve original function identity
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)

            wrapper._registry_name = name  # type: ignore[attr-defined]
            return wrapper

        return decorator

    def get(self, name: str) -> NodeSpec:
        """Retrieve a registered node by name."""
        if name not in self._nodes:
            raise KeyError(f"Node '{name}' not found in registry.")
        return self._nodes[name]

    def list(self) -> List[str]:
        """Return all registered node names."""
        return list(self._nodes.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._nodes

    def __len__(self) -> int:
        return len(self._nodes)


# -----------------------------------------------------------------------
# Singleton — import this from anywhere in the rag/ package
# -----------------------------------------------------------------------
registry = NodeRegistry()
