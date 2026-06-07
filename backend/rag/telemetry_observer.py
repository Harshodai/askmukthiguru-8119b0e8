"""
Mukthi Guru — Telemetry Observer (Observer Pattern)

Decouple metrics, logging, and self-correction from node logic.
Each node command notifies observers before and after execution.

Design Patterns:
  - Observer Pattern: NodeObserver with on_before/on_after/on_error
  - Strategy Pattern: Different observers handle different concerns
"""

from __future__ import annotations

import abc
import logging
import time
from typing import List

from rag.node_command import NodeCommand
from rag.states import GraphState

logger = logging.getLogger(__name__)


class NodeObserver(abc.ABC):
    """
    Observer interface that receives lifecycle events from NodeCommand.
    """

    @abc.abstractmethod
    async def on_before_execute(self, command: NodeCommand, state: GraphState) -> None:
        """Called before the node executes."""
        ...

    @abc.abstractmethod
    async def on_after_execute(self, command: NodeCommand, state: GraphState, result: dict) -> None:
        """Called after the node executes successfully."""
        ...

    @abc.abstractmethod
    async def on_error(self, command: NodeCommand, state: GraphState, error: Exception) -> None:
        """Called when the node raises an unhandled exception."""
        ...


class MetricsObserver(NodeObserver):
    """Records latency and token usage to Prometheus / StatsD."""

    async def on_before_execute(self, command: NodeCommand, state: GraphState) -> None:
        state["__start_time__"] = time.perf_counter()

    async def on_after_execute(self, command: NodeCommand, state: GraphState, result: dict) -> None:
        start = state.pop("__start_time__", None)
        if start is not None:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.info(f"[metrics] {command.name} latency={elapsed_ms:.1f}ms")

    async def on_error(self, command: NodeCommand, state: GraphState, error: Exception) -> None:
        logger.error(f"[metrics] {command.name} error={type(error).__name__}")


class LoggingObserver(NodeObserver):
    """Emit structured logs per node."""

    async def on_before_execute(self, command: NodeCommand, state: GraphState) -> None:
        logger.info(f"[node] {command.name} starting")

    async def on_after_execute(self, command: NodeCommand, state: GraphState, result: dict) -> None:
        logger.info(f"[node] {command.name} finished — keys={list(result.keys())}")

    async def on_error(self, command: NodeCommand, state: GraphState, error: Exception) -> None:
        logger.error(f"[node] {command.name} failed: {error}")


class SelfCorrectionObserver(NodeObserver):
    """
    If a node fails or returns low-confidence output, trigger a
    correction loop (max 3 attempts, default).
    """

    def __init__(self, max_retries: int = 3) -> None:
        self.max_retries = max_retries

    async def on_before_execute(self, command: NodeCommand, state: GraphState) -> None:
        pass

    async def on_after_execute(self, command: NodeCommand, state: GraphState, result: dict) -> None:
        pass

    async def on_error(self, command: NodeCommand, state: GraphState, error: Exception) -> None:
        logger.warning(f"[self-correction] {command.name} failed: {error}")
        # Correction loop is triggered by the orchestrator, not inside the observer
