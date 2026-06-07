"""
Mukthi Guru — RAG Node Command (Command Pattern)

Each LangGraph node becomes a small, testable command object with a
uniform interface.  This replaces the monolithic function-based nodes with
disciplined objects that can be logged, retried, and unit-tested.

Design Patterns:
  - Command Pattern: NodeCommand with execute(), undo(), retry()
  - Single Responsibility: Each command does ONE thing with the state
"""

from __future__ import annotations

import abc
import logging
import time
from typing import Any

from rag.states import GraphState

logger = logging.getLogger(__name__)


class NodeCommand(abc.ABC):
    """
    Base class for every pipeline node.

    Subclasses implement ``execute()`` and (optionally) ``undo()``.
    The builder in graph.py registers concrete commands into the graph.
    """

    name: str = ""  # Human-readable identifier
    description: str = ""  # Short purpose for docs / debug

    def __call__(self, state: GraphState) -> dict:
        """
        Callable entry-point so commands can be dropped directly into
        LangGraph's ``add_node``.
        """
        return self.execute(state)

    @abc.abstractmethod
    def execute(self, state: GraphState) -> dict:
        """
        Perform the node logic and return a *partial* state dict.
        LangGraph merges this dict into the full ``GraphState``.
        """
        ...

    def undo(self, state: GraphState) -> dict:
        """
        Optional rollback.  Default implementation is a no-op.
        Override only when a node makes side-effects that must be reversed.
        """
        logger.debug(f"[{self.name}] undo() is a no-op")
        return {}

    def retry(self, state: GraphState, attempt: int = 1) -> dict:
        """
        Execute with a fresh state copy, enabling idempotent retries.
        Subclasses can override to tweak behaviour per attempt.
        """
        logger.debug(f"[{self.name}] retry() attempt={attempt}")
        return self.execute(state)

    def _log_start(self, state: GraphState) -> None:
        logger.debug(f"[{self.name}] execute start")

    def _log_end(self, state: GraphState, result: dict) -> None:
        logger.debug(f"[{self.name}] execute end — returned keys={list(result.keys())}")


class TimedCommand(NodeCommand):
    """
    Decorator Command that times the inner command and logs latency.
    """

    def __init__(self, wrapped: NodeCommand) -> None:
        self._wrapped = wrapped
        self.name = f"timed:{wrapped.name}"

    def execute(self, state: GraphState) -> dict:
        start = time.perf_counter()
        self._log_start(state)
        result = self._wrapped.execute(state)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(f"[{self._wrapped.name}] elapsed={elapsed_ms:.1f}ms")
        self._log_end(state, result)
        return result
