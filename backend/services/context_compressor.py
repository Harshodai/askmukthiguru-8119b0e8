"""
Mukthi Guru — Context Window Budget Manager

Prevents context-window overflow by intelligently packing the most relevant
chunks within a token budget. Uses greedy selection by relevance score with
fair-truncation of the last partial chunk.

Algorithm:
  1. Tokenize all inputs (system prompt, conversation history, document chunks)
  2. Reserve portions of budget for system prompt + history (configurable %)
  3. Sort document chunks by relevance score (descending)
  4. Greedy pack chunks until remaining budget is exhausted
  5. Fair-truncate the last chunk — don't drop it entirely, trim its tokens
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.config import settings
from app.metrics import CONTEXT_CHUNKS_AFTER, CONTEXT_CHUNKS_BEFORE, CONTEXT_COMPRESSION_RATIO, CONTEXT_TOKENS_SAVED

logger = logging.getLogger(__name__)


def _estimate_tokens(text: str) -> int:
    """Fast token estimate: ~4 chars per token for English."""
    return max(1, len(text) // 4)


class ContextBudgetManager:
    """Manages context window budget by relevance-greedy packing."""

    def __init__(
        self,
        total_budget: int = 0,
        system_prompt_reserve: float = 0.0,
        history_reserve: float = 0.0,
    ) -> None:
        self.total_budget = total_budget or settings.context_window_total
        self.system_prompt_reserve = system_prompt_reserve or settings.context_system_prompt_reserve
        self.history_reserve = history_reserve or settings.context_history_reserve

    def compress(
        self,
        chunks: list[dict],
        system_prompt: str = "",
        conversation_history: str = "",
    ) -> dict:
        """Compress context by packing most relevant chunks within budget.

        Args:
            chunks: List of dicts with keys "content" and "relevance" (0-1).
            system_prompt: System prompt text.
            conversation_history: Conversation history text.

        Returns:
            dict with keys:
                - compressed_context: str of selected + truncated chunks
                - token_budget_remaining: int
                - chunks_before: int
                - chunks_after: int
                - tokens_saved: int
        """
        chunks_before = len(chunks)

        sys_tokens = _estimate_tokens(system_prompt) if system_prompt else 0
        history_tokens = _estimate_tokens(conversation_history) if conversation_history else 0

        sys_budget = int(self.total_budget * self.system_prompt_reserve)
        history_budget = int(self.total_budget * self.history_reserve)
        docs_budget = self.total_budget - sys_budget - history_budget

        if sys_tokens > sys_budget:
            system_prompt = self._truncate_text(system_prompt, sys_budget)
            sys_tokens = _estimate_tokens(system_prompt)
        if history_tokens > history_budget:
            conversation_history = self._truncate_text(conversation_history, history_budget)
            history_tokens = _estimate_tokens(conversation_history)

        if not chunks:
            packed = []
            tokens_used = 0
        else:
            sorted_chunks = sorted(
                chunks,
                key=lambda c: c.get("relevance", c.get("score", 0.0)),
                reverse=True,
            )

            packed: list[str] = []
            tokens_used = 0

            for chunk in sorted_chunks:
                text = chunk.get("content") or chunk.get("text", "")
                chunk_tokens = _estimate_tokens(text)
                if tokens_used + chunk_tokens <= docs_budget:
                    packed.append(text)
                    tokens_used += chunk_tokens
                elif tokens_used < docs_budget:
                    remaining = docs_budget - tokens_used
                    truncated = self._truncate_text(text, remaining)
                    if truncated:
                        packed.append(truncated)
                        tokens_used += _estimate_tokens(truncated)
                    break
                else:
                    break

        compressed = "\n\n".join(packed)
        total_tokens = sys_tokens + history_tokens + tokens_used
        tokens_before = _estimate_tokens(
            system_prompt + conversation_history + "\n\n".join(
                c.get("content") or c.get("text", "") for c in chunks
            )
        )

        ratio = tokens_used / max(tokens_before, 1)
        try:
            CONTEXT_COMPRESSION_RATIO.observe(ratio)
            CONTEXT_CHUNKS_BEFORE.set(chunks_before)
            CONTEXT_CHUNKS_AFTER.set(len(packed))
            CONTEXT_TOKENS_SAVED.set(tokens_before - total_tokens)
        except Exception:
            pass

        return {
            "compressed_context": compressed,
            "token_budget_remaining": self.total_budget - total_tokens,
            "chunks_before": chunks_before,
            "chunks_after": len(packed),
            "tokens_saved": tokens_before - total_tokens,
        }

    @staticmethod
    def _truncate_text(text: str, target_tokens: int) -> str:
        """Truncate text to approximate target token count."""
        target_chars = target_tokens * 4
        if len(text) <= target_chars:
            return text
        return text[:target_chars] + " [...]"
