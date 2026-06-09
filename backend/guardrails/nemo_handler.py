from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from guardrails.base import BaseGuardrailHandler

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).parent / "config"

_INPUT_REFUSAL_PHRASES = frozenset(
    [
        "i'm not able to",
        "i cannot",
        "outside my area",
        "crisis helpline",
        "i refuse to",
    ]
)

_OUTPUT_MODERATION_PHRASES = frozenset(
    [
        "i should clarify",
        "not a medical",
        "not my area",
        "outside my expertise",
        "i cannot provide",
    ]
)


def _contains_phrase(text: str, phrases: frozenset) -> bool:
    """Check if text contains any of the given phrases."""
    text_lower = text.lower()
    return any(re.search(r"\b" + re.escape(phrase) + r"\b", text_lower) for phrase in phrases)


class NeMoGuardrailHandler(BaseGuardrailHandler):
    """
    NeMo Guardrails handler for production-grade safety check.
    """

    def __init__(self) -> None:
        super().__init__()
        self._rails = None
        self._available = False

        try:
            from nemoguardrails import LLMRails, RailsConfig

            config = RailsConfig.from_path(str(CONFIG_DIR))
            self._rails = LLMRails(config)
            self._available = True
            logger.info("NeMo Guardrails loaded successfully in handler")
        except ImportError:
            logger.warning(
                "NeMo Guardrails not installed. NeMo handler will act as a pass-through."
            )
        except Exception as e:
            logger.warning(
                f"NeMo Guardrails failed to load in handler: {e}. "
                "NeMo handler will act as a pass-through."
            )

    async def _handle_input(self, text: str, **kwargs: Any) -> dict[str, Any]:
        if not self._available:
            return {"blocked": False, "reason": None, "response": None}

        try:
            result = await self._rails.generate_async(messages=[{"role": "user", "content": text}])
            response_text = result.get("content", "")

            if _contains_phrase(response_text, _INPUT_REFUSAL_PHRASES):
                return {
                    "blocked": True,
                    "reason": "Input blocked by NeMo guardrails",
                    "response": response_text,
                }
            return {"blocked": False, "reason": None, "response": None}

        except Exception as e:
            logger.error(f"NeMo input check failed: {e}")
            return {"blocked": False, "reason": None, "response": None}

    async def _handle_output(self, text: str, **kwargs: Any) -> dict[str, Any]:
        if not self._available:
            return {"blocked": False, "reason": None, "moderated_response": None}

        try:
            result = await self._rails.generate_async(
                messages=[
                    {"role": "user", "content": "Tell me about this topic."},
                    {"role": "assistant", "content": text},
                ]
            )
            response_text = result.get("content", "")

            if _contains_phrase(response_text, _OUTPUT_MODERATION_PHRASES):
                return {
                    "blocked": True,
                    "reason": "Output moderated by NeMo guardrails",
                    "moderated_response": response_text,
                }
            return {"blocked": False, "reason": None, "moderated_response": None}

        except Exception as e:
            logger.error(f"NeMo output check failed: {e}")
            return {"blocked": False, "reason": None, "moderated_response": None}

    @property
    def is_available(self) -> bool:
        return self._available
