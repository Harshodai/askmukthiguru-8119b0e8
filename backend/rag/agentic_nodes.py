"""
Mukthi Guru — Agentic Node Wrappers (ReAct, CoT, Self-Correction)

Wraps NodeCommand objects with agentic design patterns that enable
the pipeline to think-act-observe and self-correct.

Design Patterns:
  - Decorator: ReActNode wraps any NodeCommand
  - Chain of Responsibility: ReAct loop chains multiple thought-action cycles
  - Strategy: Pluggable thought / action / observation steps
"""

from __future__ import annotations

import logging

from rag.node_command import NodeCommand
from rag.states import GraphState

logger = logging.getLogger(__name__)


class ReActNode(NodeCommand):
    """
    Decorator that wraps any NodeCommand in a ReAct (Reasoning + Acting) loop.

    Steps (up to max_steps):
      1. Think — formulate what the node should do
      2. Act  — execute the wrapped command
      3. Observe — parse the result
      4. Conditionally repeat until done or max steps reached
    """

    MAX_STEPS = 3

    def __init__(self, wrapped: NodeCommand, max_steps: int = MAX_STEPS) -> None:
        self._wrapped = wrapped
        self._max_steps = max_steps
        self.name = f"react:{wrapped.name}"

    def execute(self, state: GraphState) -> dict:
        step = 0
        accumulated = {}

        while step < self._max_steps:
            logger.debug(f"[ReAct] step={step + 1}/{self._max_steps} for {self._wrapped.name}")
            result = self._wrapped.execute(state)
            accumulated.update(result)

            # Simple stop criterion: if the wrapped command produced a 'done' flag, exit
            if result.get("react_done"):
                break
            step += 1

        return accumulated


class SelfCorrectionNode(NodeCommand):
    """
    Decorator that retries the wrapped command on failure,
    enriching the state with richer context each time.
    """

    MAX_RETRIES = 3

    def __init__(self, wrapped: NodeCommand, max_retries: int = MAX_RETRIES) -> None:
        self._wrapped = wrapped
        self._max_retries = max_retries
        self.name = f"self-correct:{wrapped.name}"

    def execute(self, state: GraphState) -> dict:
        last_error = None

        for attempt in range(1, self._max_retries + 1):
            try:
                result = self._wrapped.execute(state)
                if attempt > 1:
                    logger.info(f"[SelfCorrection] {self._wrapped.name} succeeded on attempt {attempt}")
                return result
            except Exception as exc:
                last_error = exc
                logger.warning(f"[SelfCorrection] {self._wrapped.name} attempt {attempt} failed: {exc}")
                state.setdefault("__correction_context__", []).append(str(exc))

        raise last_error
