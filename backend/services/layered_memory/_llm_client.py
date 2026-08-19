from __future__ import annotations

import functools
from typing import Any

from app.config import settings


@functools.lru_cache(maxsize=8)
def _make_client(
    base_url: str,
    api_key: str,
    *,
    subscription_key: str | None = None,
) -> Any:
    """Return a cached AsyncOpenAI instance for the given connection params.

    Keyed by (base_url, api_key, subscription_key) so each unique provider
    endpoint reuses a single client (and its connection pool) across calls.
    """
    from openai import AsyncOpenAI

    default_headers = {}
    if subscription_key:
        default_headers["api-subscription-key"] = subscription_key
    return AsyncOpenAI(
        base_url=base_url,
        api_key=api_key,
        default_headers=default_headers or None,
    )


def build_llm_client() -> tuple[Any, str] | None:
    """Return *(client, model_name)* for the active LLM provider, or *None*.

    All provider branches reuse a cached AsyncOpenAI instance so connection
    pools survive multiple calls within the same process lifetime.
    """
    provider = settings.llm_provider.lower()

    if settings.is_sarvam_cloud:
        client = _make_client(
            settings.sarvam_base_url,
            "api-key-not-used-by-bearer",
            subscription_key=settings.sarvam_api_key,
        )
        return client, settings.sarvam_cloud_classify_model or "sarvam-30b"

    if provider == "openrouter":
        return (
            _make_client(settings.openrouter_base_url, settings.openrouter_api_key),
            settings.model_for_classification,
        )

    if provider == "nim":
        return (
            _make_client(settings.nim_base_url, settings.nim_api_key),
            settings.nim_classify_model,
        )

    if provider == "ollama":
        # Use the ollama-specific classify model, falling back to the primary
        # ollama model, then the OllamaService default (sarvam-30b:latest).
        model = settings.ollama_classify_model or settings.ollama_model or "sarvam-30b:latest"
        return _make_client(settings.ollama_base_url, "ollama"), model

    return None


if __name__ == "__main__":
    result = build_llm_client()
    print(
        "build_llm_client() →",
        "None" if result is None else f"({type(result[0]).__name__}, {result[1]!r})",
    )
