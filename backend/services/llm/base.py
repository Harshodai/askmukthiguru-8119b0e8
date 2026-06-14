"""Base LLM Provider interface (Strategy Pattern).

All LLM provider strategies must implement this interface to be interchangeable
via the LLMService Protocol.
"""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator
from typing import Any


class LLMProvider(abc.ABC):
    """Abstract Base Class for LLM providers to ensure proper strategy implementation."""

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Fast heuristic: ~1.3 tokens per word."""
        if not text:
            return 0
        return int(len(text.split()) * 1.3)

    def _enforce_token_budget(self, prompt_text: str, budget: int, node: str = "generate") -> None:
        """Soft enforcement: warns if prompt tokens exceed budget. Only raises at 2x hard limit."""
        estimated = self._estimate_tokens(prompt_text)
        hard_limit = budget * 2
        if estimated > budget:
            import logging
            logger = logging.getLogger("TokenBudgetGuard")
            if estimated > hard_limit:
                logger.error(
                    f"TOKEN BUDGET HARD LIMIT EXCEEDED: len={len(prompt_text)}, "
                    f"estimated={estimated}, hard_limit={hard_limit}"
                )
                raise ValueError(
                    f"TokenBudgetExceeded: [{node}] Estimated {estimated} tokens exceed "
                    f"hard limit {hard_limit}. Prompt start: {prompt_text[:200]}..."
                )
            logger.warning(
                f"TOKEN BUDGET SOFT EXCEEDED [{node}]: estimated={estimated} > budget={budget}. "
                f"Continuing — prompt will be sent as-is (within hard limit {hard_limit})."
            )

    def _truncate_to_budget(self, text: str, budget: int) -> str:
        """Truncate text to fit within the token budget using word-count proxy."""
        if not text:
            return text
        words = text.split()
        max_words = int(budget / 1.3)
        if len(words) <= max_words:
            return text
        import logging
        logging.getLogger("TokenBudgetGuard").warning(
            f"Truncating text from {len(words)} to {max_words} words to fit budget {budget} tokens."
        )
        return " ".join(words[:max_words]) + "..."

    @abc.abstractmethod
    async def generate(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> str:
        """Generate text from a system + user prompt pair."""
        pass

    @abc.abstractmethod
    async def _generate_fast(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> str:
        """Fast classification using the lightweight model."""
        pass

    @abc.abstractmethod
    async def generate_stream(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> AsyncIterator[str]:
        """Stream generation tokens."""
        pass

    @abc.abstractmethod
    async def classify(self, *, text: str, **kwargs: Any) -> str:
        """Classify intent of the given text (e.g. DISTRESS/QUERY/CASUAL)."""
        pass

    @abc.abstractmethod
    async def classify_intent_and_complexity(self, *, text: str, **kwargs: Any) -> dict[str, str]:
        """Return {'intent': str, 'complexity': str} (simple/complex)."""
        pass

    @abc.abstractmethod
    async def classify_distress_structured(self, message: str) -> dict:
        """Assess whether a message signals emotional distress."""
        pass


    @abc.abstractmethod
    async def grade_relevance(self, *, question: str, doc_texts: list[str], **kwargs: Any) -> list[dict[str, Any]]:
        """Batch grade relevance of documents against a question."""
        pass

    @abc.abstractmethod
    async def check_faithfulness(self, *, answer: str, context: str, **kwargs: Any) -> dict[str, Any]:
        """Check whether answer is faithful to context."""
        pass

    @abc.abstractmethod
    async def verify_answer(self, *, answer: str, context: str, **kwargs: Any) -> dict[str, Any]:
        """CoVe-style verification."""
        pass

    @abc.abstractmethod
    async def decompose_query(self, *, question: str, **kwargs: Any) -> list[str]:
        """Decompose a complex question into atomic sub-queries."""
        pass

    @abc.abstractmethod
    async def rewrite_query(self, *, original: str, reasons: list[str], **kwargs: Any) -> str:
        """Rewrite a failed query for retry."""
        pass

    @abc.abstractmethod
    async def generate_hyde(self, *, question: str, **kwargs: Any) -> str:
        """Generate a hypothetical document for HyDE embedding."""
        pass

    @abc.abstractmethod
    async def compress_context(self, *, question: str, text: str, **kwargs: Any) -> str:
        """Compress a long text down to essential content."""
        pass

    @abc.abstractmethod
    async def translate_text(self, *, text: str, source_lang: str, target_lang: str, **kwargs: Any) -> str:
        """Translate text between languages."""
        pass

    @abc.abstractmethod
    async def health_check(self) -> bool:
        """Return True if the LLM service is reachable and healthy."""
        pass
