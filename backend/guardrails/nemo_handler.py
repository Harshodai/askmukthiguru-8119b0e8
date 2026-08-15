from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any

from app.config import settings
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
            # options={"rails": ["output"]} runs ONLY the configured output rails
            # against the assistant message below -- it classifies `text` itself,
            # unlike the old call which generated a fresh dialog continuation and
            # inspected THAT for moderation phrases instead of the real output.
            from nemoguardrails.rails.llm.options import GenerationOptions

            nemo_timeout = max(1.0, settings.node_timeout_main + 2.0)
            result = await asyncio.wait_for(
                self._rails.generate_async(
                    messages=[
                        {"role": "user", "content": "Tell me about this topic."},
                        {"role": "assistant", "content": text},
                    ],
                    options=GenerationOptions(rails=["output"]),
                ),
                timeout=nemo_timeout,
            )
            response = result.response
            response_text = (
                response[-1].get("content", "")
                if isinstance(response, list) and response
                else str(response or "")
            )

            # NeMo's output rails substitute the assistant message when they
            # fire, so a changed response means the real `text` was moderated.
            # The phrase check is a belt-and-suspenders fallback, not the
            # primary signal.
            was_moderated = bool(response_text) and response_text.strip() != text.strip()
            if was_moderated or _contains_phrase(text, _OUTPUT_MODERATION_PHRASES):
                return {
                    "blocked": True,
                    "reason": "Output moderated by NeMo guardrails",
                    "moderated_response": response_text or None,
                }
            return {"blocked": False, "reason": None, "moderated_response": None}

        except Exception as e:
            logger.error(f"NeMo output check failed: {e}")
            return {"blocked": False, "reason": None, "moderated_response": None}

    @property
    def is_available(self) -> bool:
        return self._available
