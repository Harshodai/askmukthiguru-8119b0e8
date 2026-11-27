"""Which LLM object the first-person path (scorer, answerability gate, HyDE, judge) calls.

Default ``first_person_llm_provider="openrouter"`` keeps the historical resolution exactly:
``container.openrouter``, else ``container.nim``, else ``container.ollama`` (the deprecated
alias for the canonical ``container.llm``). ``"nim"`` and ``"vllm"`` are strict: the named
provider must exist on the container or this raises. There is no fallback to OpenRouter.
"""

from __future__ import annotations

from typing import Any

from app.config import settings


class FirstPersonLLMProviderUnavailable(RuntimeError):
    """The configured first-person LLM provider is not available on the container."""


def resolve_first_person_llm(container: Any) -> Any:
    choice = settings.first_person_llm_provider
    if choice == "openrouter":
        return (
            getattr(container, "openrouter", None)
            or getattr(container, "nim", None)
            or getattr(container, "ollama", None)
        )
    service = getattr(container, choice, None)
    if service is None:
        raise FirstPersonLLMProviderUnavailable(
            f"first_person_llm_provider={choice!r} but container.{choice} is not configured "
            f"(vllm needs VLLM_BASE_URL, nim needs NIM_API_KEY)"
        )
    return service
