"""
Mukthi Guru — Self-Correction Loop

Standalone helper that orchestrates the ReAct / self-correction cycle
for a single node or a chain of nodes.

Design Patterns:
  - Strategy: Pluggable correction strategies
  - Template Method: Detect → Diagnose → Repair → Verify
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class CorrectionStrategy:
    """Base class for how to repair a failed node."""

    async def repair(self, state: Dict[str, Any], error: Exception) -> Dict[str, Any]:
        """Return a new state dict that should succeed on retry."""
        raise NotImplementedError


class RewriteQueryCorrection(CorrectionStrategy):
    """Repair by rewriting the user query to be clearer."""

    async def repair(self, state: Dict[str, Any], error: Exception) -> Dict[str, Any]:
        state["rewrite_count"] = state.get("rewrite_count", 0) + 1
        state["needs_rewrite"] = True
        return state


class FallbackCorrection(CorrectionStrategy):
    """Repair by falling back to a simpler graph or default response."""

    async def repair(self, state: Dict[str, Any], error: Exception) -> Dict[str, Any]:
        state["use_fallback"] = True
        return state


class SelfCorrectionOrchestrator:
    """
    Orchestrates a correction loop over a node command.

    Usage:
        orchestrator = SelfCorrectionOrchestrator(max_retries=3)
        result = await orchestrator.run(node_command, initial_state)
    """

    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
        self.strategies: List[CorrectionStrategy] = [
            RewriteQueryCorrection(),
            FallbackCorrection(),
        ]

    async def run(self, command, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the command, retrying with corrections on failure.

        Args:
            command: A callable or NodeCommand instance.
            state:   Mutable state dict (will be mutated in place on retries).

        Returns:
            The result dict on success.
        """
        last_error = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug(f"[SelfCorrection] attempt {attempt}/{self.max_retries}")
                result = command(state)
                if attempt > 1:
                    logger.info(f"[SelfCorrection] succeeded on attempt {attempt}")
                return result
            except Exception as exc:
                last_error = exc
                logger.warning(f"[SelfCorrection] attempt {attempt} failed: {exc}")

                if attempt < self.max_retries:
                    strategy = self.strategies[(attempt - 1) % len(self.strategies)]
                    state = await strategy.repair(state, exc)

        # All retries exhausted
        raise last_error
