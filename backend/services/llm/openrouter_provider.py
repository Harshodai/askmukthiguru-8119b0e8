"""OpenRouter LLM Provider strategy implementation."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from services.llm.base import LLMProvider
from services.openrouter_service import OpenRouterService


class OpenRouterProvider(LLMProvider):
    """Adapter strategy wrapping OpenRouterService to match the LLMProvider/LLMService contract."""

    def __init__(self, service: OpenRouterService) -> None:
        self._service = service

    async def generate(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> str:
        from app.config import settings
        full_prompt_text = f"{system_prompt} {user_prompt}"
        max_budget = getattr(settings, "max_tokens_per_request", 2000)
        self._enforce_token_budget(full_prompt_text, max_budget, node="generate")
        return await self._service.generate(system_prompt, user_prompt, **kwargs)

    async def _generate_fast(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> str:
        return await self._service._generate_fast(system_prompt, user_prompt, **kwargs)

    async def generate_stream(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> AsyncIterator[str]:
        from app.config import settings
        full_prompt_text = f"{system_prompt} {user_prompt}"
        max_budget = getattr(settings, "max_tokens_per_request", 2000)
        self._enforce_token_budget(full_prompt_text, max_budget, node="generate_stream")
        async for token in self._service.generate_stream(system_prompt, user_prompt, **kwargs):
            yield token

    async def classify(self, text: str, **kwargs: Any) -> str:
        return await self._service.classify_intent(text, **kwargs)

    async def classify_intent_and_complexity(self, text: str, **kwargs: Any) -> dict[str, str]:
        return await self._service.classify_intent_and_complexity(text, **kwargs)

    async def classify_distress_structured(self, message: str) -> dict:
        return await self._service.classify_distress_structured(message)

    async def grade_relevance(self, question: str, doc_texts: list[str], **kwargs: Any) -> list[dict[str, Any]]:
        return await self._service.batch_grade_relevance(question, doc_texts)

    async def check_faithfulness(self, answer: str, context: str, **kwargs: Any) -> dict[str, Any]:
        is_faithful = await self._service.check_faithfulness(answer, context)
        return {"is_faithful": is_faithful, "details": "Faithfulness score via check_faithfulness"}

    async def verify_answer(self, answer: str, context: str, **kwargs: Any) -> dict[str, Any]:
        return await self._service.combined_verify(answer, context)

    async def decompose_query(self, question: str, **kwargs: Any) -> list[str]:
        return await self._service.decompose_query(question)

    async def rewrite_query(self, original: str, reasons: list[str], **kwargs: Any) -> str:
        return await self._service.rewrite_query(original, reasons, **kwargs)

    async def generate_hyde(self, question: str, **kwargs: Any) -> str:
        return await self._service.generate_hypothetical_answer(question)

    async def compress_context(self, question: str, text: str, **kwargs: Any) -> str:
        return await self._service.compress_context(question, text)

    async def translate_text(self, text: str, source_lang: str, target_lang: str, **kwargs: Any) -> str:
        return await self._service.translate_text(text, source_lang, target_lang)

    async def health_check(self) -> bool:
        return await self._service.health_check()
