"""
Mukthi Guru — NeMo Guardrails Integration

Design Patterns:
  - Decorator Pattern: Wraps the RAG pipeline with input/output safety rails
  - Proxy Pattern: Acts as a safety proxy before/after generation
  - Fail-Open Strategy: If NeMo is unavailable, log warning and proceed
    (guardrails are additive safety, not a blocker)

Input Rail: Blocks harmful/off-topic messages BEFORE the RAG pipeline
Output Rail: Moderates the final answer AFTER generation
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Path to NeMo Guardrails config directory
CONFIG_DIR = Path(__file__).parent / "config"

# Centralized refusal phrases — used by both input and output rails
# These are phrases NeMo typically includes in refusal/moderation responses.
# Matched using word-boundary regex to avoid false positives on substrings
# (e.g., "patient may refuse" should NOT trigger the guard).
_INPUT_REFUSAL_PHRASES = frozenset([
    "i'm not able to",
    "i cannot",
    "outside my area",
    "crisis helpline",
    "i refuse to",
])

_OUTPUT_MODERATION_PHRASES = frozenset([
    "i should clarify",
    "not a medical",
    "not my area",
    "outside my expertise",
    "i cannot provide",
])


def _contains_phrase(text: str, phrases: frozenset) -> bool:
    """
    Check if text contains any of the given phrases using word-boundary matching.
    
    Uses regex \\b anchors so that partial-word matches are avoided.
    For example, "refuse" inside "i refuse to" will match, but "refuse"
    inside "patient may refuse medication" won't match the phrase
    "i refuse to" (because the surrounding words don't match).
    """
    import re
    text_lower = text.lower()
    return any(
        re.search(r'\b' + re.escape(phrase) + r'\b', text_lower)
        for phrase in phrases
    )


class GuardrailsService:
    """
    Safety wrapper around the RAG pipeline using NeMo Guardrails.
    
    Fail-Open Design:
    If NeMo fails to load (dependency issues, config errors), the system
    logs a warning and operates WITHOUT guardrails. This ensures the app
    doesn't crash due to a safety layer failure — the 12-layer RAG pipeline
    still has its own internal safety checks.
    """

    def __init__(self) -> None:
        """Initialize NeMo Guardrails with fail-open strategy."""
        self._rails = None
        self._available = False

        try:
            from nemoguardrails import RailsConfig, LLMRails

            config = RailsConfig.from_path(str(CONFIG_DIR))
            self._rails = LLMRails(config)
            self._available = True
            logger.info("NeMo Guardrails loaded successfully")
        except ImportError:
            logger.warning(
                "NeMo Guardrails not installed. "
                "Running WITHOUT guardrails (fail-open mode)."
            )
        except Exception as e:
            logger.warning(
                f"NeMo Guardrails failed to load: {e}. "
                "Running WITHOUT guardrails (fail-open mode)."
            )

    async def check_input(self, message: str) -> dict:
        """
        Input rail: Check if the user message should be blocked.
        
        Returns:
            Dict with 'blocked' (bool), 'reason' (str), 'response' (str if blocked)
        """
        if not self._available:
            return {"blocked": False, "reason": None, "response": None}

        try:
            result = await self._rails.generate_async(
                messages=[{"role": "user", "content": message}]
            )

            response_text = result.get("content", "")

            # NeMo returns a refusal message if blocked
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

    async def check_output(self, answer: str) -> dict:
        """
        Output rail: Check if the generated answer should be moderated.
        
        Uses NeMo's output moderation by sending the answer as context
        for the output rail to evaluate.
        
        Returns:
            Dict with 'blocked' (bool), 'reason' (str), 'moderated_response' (str if blocked)
        """
        if not self._available:
            return {"blocked": False, "reason": None, "moderated_response": None}

        try:
            # For output moderation, pass the answer through the output rail
            result = await self._rails.generate_async(
                messages=[
                    {"role": "context", "content": {"output": answer}},
                    {"role": "user", "content": "Moderate this response for safety."},
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
        """Check if NeMo Guardrails is loaded and operational."""
        return self._available
