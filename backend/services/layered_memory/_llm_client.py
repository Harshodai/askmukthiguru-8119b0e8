from __future__ import annotations

from typing import Any

from app.config import settings


def build_llm_client() -> tuple[Any, str] | None:
    from openai import AsyncOpenAI

    provider = settings.llm_provider.lower()
    if settings.is_sarvam_cloud:
        return (
            AsyncOpenAI(
                base_url=settings.sarvam_base_url,
                api_key="api-key-not-used-by-bearer",
                default_headers={"api-subscription-key": settings.sarvam_api_key},
            ),
            settings.sarvam_cloud_classify_model or "sarvam-30b",
        )
    if provider == "openrouter":
        return AsyncOpenAI(base_url=settings.openrouter_base_url, api_key=settings.openrouter_api_key), settings.model_for_classification
    if provider == "nim":
        return AsyncOpenAI(base_url=settings.nim_base_url, api_key=settings.nim_api_key), settings.nim_classify_model
    if provider == "ollama":
        return AsyncOpenAI(base_url=settings.ollama_base_url, api_key="ollama"), settings.model_for_classification
    return None
