"""LLM Service Protocol — defines the contract for language model providers.

Design Patterns:
  - Protocol (duck typing): allows swapping Ollaservice, Sarvamcloudservice,
    or future providers without changing consumers.
  - Interface Segregation: each method has a focused purpose rather than
    a single monolithic generate() with all options.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol


class LLMService(Protocol):
    """Unified interface for all LLM providers (Ollama, Sarvam Cloud, Krutrim, etc.)."""

    # ── Core generation ──────────────────────────────────────────────────

    async def generate(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> str:
        """Generate text from a system + user prompt pair."""
        ...

    async def _generate_fast(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> str:
        """Fast classification using the lightweight model."""
        ...

    async def generate_stream(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> AsyncIterator[str]:
        """Stream generation tokens (returns async generator / iterable)."""
        ...

    # ── Classification ─────────────────────────────────────────────────

    async def classify(self, *, text: str, **kwargs: Any) -> str:
        """Classify intent of the given text (e.g., DISTRESS/QUERY/CASUAL)."""
        ...

    async def classify_intent_and_complexity(self, *, text: str, **kwargs: Any) -> dict[str, str]:
        """Return {'intent': str, 'complexity': str} (simple/complex)."""
        ...

    async def classify_distress_structured(self, message: str) -> dict:
        """Assess whether a message signals emotional distress."""
        ...


    # ── Relevance / grading ──────────────────────────────────────────────

    async def grade_relevance(self, *, question: str, doc_texts: list[str], **kwargs: Any) -> list[dict[str, Any]]:
        """Batch grade relevance of documents against a question.

        Returns a list where each item is:
            {'relevant': bool, 'reason': str}
        """
        ...

    # ── Faithfulness / verification ──────────────────────────────────────

    async def check_faithfulness(self, *, answer: str, context: str, **kwargs: Any) -> dict[str, Any]:
        """Check whether `answer` is faithful to `context`.

        Returns:
            {'is_faithful': bool, 'score': float, ...}
        """
        ...

    async def verify_answer(self, *, answer: str, context: str, **kwargs: Any) -> dict[str, Any]:
        """CoVe-style verification."""
        ...

    # ── Query decomposition / rewriting ──────────────────────────────────

    async def decompose_query(self, *, question: str, **kwargs: Any) -> list[str]:
        """Decompose a complex question into atomic sub-queries."""
        ...

    async def rewrite_query(self, *, original: str, reasons: list[str], **kwargs: Any) -> str:
        """Rewrite a failed query for retry (CRAG loop)."""
        ...

    # ── Retrieval helpers ────────────────────────────────────────────────

    async def generate_hyde(self, *, question: str, **kwargs: Any) -> str:
        """Generate a hypothetical document for HyDE embedding."""
        ...

    async def compress_context(self, *, question: str, text: str, **kwargs: Any) -> str:
        """Compress a long text down to essential content."""
        ...

    # ── Translation ────────────────────────────────────────────────────

    async def translate_text(self, *, text: str, source_lang: str, target_lang: str, **kwargs: Any) -> str:
        """Translate text between languages."""
        ...

    # ── Health ───────────────────────────────────────────────────────────

    async def health_check(self) -> bool:
        """Return True if the LLM service is reachable and healthy."""
        ...
