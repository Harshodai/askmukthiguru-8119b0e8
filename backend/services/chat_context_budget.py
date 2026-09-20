"""Server-owned conversation context budget contract.

Measures client-visible conversation history before the expensive pipeline.
The hard stop prevents silent history trimming once a durable conversation
grows beyond the safe input budget. Provider-specific context failures are
mapped separately.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import settings
from rag.compressor import estimate_tokens

CONTEXT_ERROR_CODE = "conversation_context_exhausted"


@dataclass(frozen=True)
class ConversationContextBudget:
    """Stable, JSON-safe context budget projection for chat clients."""

    estimated_tokens: int
    max_input_tokens: int
    remaining_tokens: int
    warn_at_tokens: int
    warning: bool
    exhausted: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "estimated_tokens": self.estimated_tokens,
            "max_input_tokens": self.max_input_tokens,
            "remaining_tokens": self.remaining_tokens,
            "warn_at_tokens": self.warn_at_tokens,
            "warning": self.warning,
            "exhausted": self.exhausted,
        }


def max_chat_input_tokens() -> int:
    """Return the single server-owned safe chat input budget.

    context_window_total is the repository's total context budget; the existing
    context_system_prompt_reserve protects the system/prompt layer. The result
    is the admission budget for history plus the current user message.
    """

    total = max(1, int(getattr(settings, "context_window_total", 8192)))
    system_reserve = min(
        0.90,
        max(0.0, float(getattr(settings, "context_system_prompt_reserve", 0.20))),
    )
    history_reserve = min(
        0.40,
        max(0.0, float(getattr(settings, "context_history_reserve", 0.10))),
    )
    output_reserve = max(
        1,
        int(getattr(settings, "llm_max_tokens_deep", 1500)),
    )
    # Reserve explicit headroom for both the system/persona layer and the
    # conversation-history layer. The returned budget is for dynamic request
    # inputs (hydrated history + current turn + continuation/attachment context).
    reserved = min(0.90, system_reserve + history_reserve)
    available = int(total * (1.0 - reserved)) - output_reserve
    return max(256, available)


def assess_conversation_context(
    messages: list[dict[str, Any]] | None,
    user_message: str,
    language: str = "en",
    conversation_summary: str | None = None,
    attachment_context: str | None = None,
) -> ConversationContextBudget:
    """Estimate current conversation input size conservatively."""

    parts: list[str] = []
    for message in messages or []:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue
        content = str(message.get("content") or "")
        if content:
            parts.append(content)

    if user_message.strip():
        parts.append(user_message.strip())

    estimated = estimate_tokens("\n".join(parts), language or "en")
    maximum = max_chat_input_tokens()
    warn_at = max(1, int(maximum * 0.80))
    remaining = max(0, maximum - estimated)

    return ConversationContextBudget(
        estimated_tokens=estimated,
        max_input_tokens=maximum,
        remaining_tokens=remaining,
        warn_at_tokens=warn_at,
        warning=estimated >= warn_at,
        exhausted=estimated >= maximum,
    )
