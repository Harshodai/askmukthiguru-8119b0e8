"""
TypeSafe Jev Structured Decision Service for Intent and Query Routing.

Interacts with OpenRouter's Decisions API (POST https://openrouter.ai/api/alpha/decisions)
using TypeSafe Jev (e.g. typesafe/jev-1.14 or typesafe/jev-router).

Jev is a System One decision model that provides structured enum choices and calibrated
probabilities directly without generating free-form conversational text, reducing routing
latency to sub-300ms while eliminating prompt-jailbreak and CoT contamination risks.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_DEFAULT_DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"

_INTENT_CRITERIA: dict[str, str] = {
    "FACTUAL": (
        "A question asking about spiritual teachings, philosophy, inner transformation, "
        "consciousness, beautiful state, suffering, or Sri Preethaji and Sri Krishnaji doctrine."
    ),
    "CASUAL": (
        "A greeting, farewell, expression of gratitude (thank you), conversational small talk, "
        "or capability inquiry about the assistant."
    ),
    "MEDITATION": (
        "A direct request to start, practice, or be guided through a meditation or breathing exercise."
    ),
    "DISTRESS": (
        "A statement expressing acute emotional pain, despair, overwhelming sadness, or psychological crisis."
    ),
    "LIVE_LOGISTICS": (
        "A question about event dates, retreat schedules, Ekam festivals, or physical location logistics."
    ),
}

_TIER_CRITERIA: dict[str, str] = {
    "tier2_simple": "A single, focused spiritual question, definition, or straightforward inquiry.",
    "tier3_complex": "A multi-part question, detailed comparative analysis, or deep philosophical query.",
}


class JevRouterService:
    """Async client for TypeSafe Jev structured decision models via OpenRouter."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_s: Optional[float] = None,
        confidence_threshold: Optional[float] = None,
        endpoint_url: str = _DEFAULT_DECISIONS_URL,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._api_key = api_key or getattr(settings, "openrouter_api_key", None)
        self._model = model or getattr(settings, "intent_router_jev_model", "typesafe/jev-1.14")
        self._timeout_s = (
            timeout_s
            if timeout_s is not None
            else getattr(settings, "intent_router_jev_timeout_s", 2.0)
        )
        self._confidence_threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else getattr(settings, "intent_router_jev_confidence_threshold", 0.70)
        )
        self._endpoint_url = endpoint_url
        self._client = client

    def build_payload(self, question: str) -> dict[str, Any]:
        """Construct the TypeSafe Jev structured decision request payload."""
        return {
            "model": self._model,
            "state": {
                "question": question,
            },
            "questions": {
                "intent": {
                    "type": "choice",
                    "instructions": "Classify the primary intent of the seeker's question.",
                    "criteria": _INTENT_CRITERIA,
                },
                "complexity": {
                    "type": "choice",
                    "instructions": "Assess the depth and complexity of the question.",
                    "criteria": _TIER_CRITERIA,
                },
            },
        }

    def parse_response(self, data: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Parse decisions response and validate confidence bounds."""
        answers = data.get("answers")
        if not isinstance(answers, dict):
            # In case the provider returns a completions response format
            choices = data.get("choices", [])
            if choices and isinstance(choices[0], dict):
                text = choices[0].get("message", {}).get("content", "")
                logger.debug("Jev router received completions fallback: %s", text)
            return None

        intent_data = answers.get("intent", {})
        intent_choice = intent_data.get("choice")
        if not intent_choice or intent_choice not in _INTENT_CRITERIA:
            logger.warning("Jev router: unknown or missing intent choice: %r", intent_choice)
            return None

        intent_probabilities = intent_data.get("probabilities", {})
        confidence = float(intent_probabilities.get(intent_choice, 1.0))
        if confidence < self._confidence_threshold:
            logger.info(
                "Jev router: intent confidence %.3f below threshold %.3f; falling back.",
                confidence,
                self._confidence_threshold,
            )
            return None

        complexity_data = answers.get("complexity", {})
        tier_choice = complexity_data.get("choice", "tier2_simple")
        if tier_choice not in _TIER_CRITERIA:
            tier_choice = "tier2_simple"

        needs_web_search = intent_choice == "LIVE_LOGISTICS"

        return {
            "intent": intent_choice,
            "query_tier": tier_choice,
            "confidence": confidence,
            "needs_web_search": needs_web_search,
            "model": self._model,
            "routing_reason": f"jev_router_{self._model}",
        }

    async def classify(self, question: str) -> Optional[dict[str, Any]]:
        """Classify user question using TypeSafe Jev on OpenRouter.

        Returns a structured dictionary on success or None on failure/low-confidence
        so the caller can fall back seamlessly to legacy routers.
        """
        api_key = self._api_key or getattr(settings, "openrouter_api_key", None)
        if not api_key:
            logger.debug("Jev router: OPENROUTER_API_KEY not configured; skipping.")
            return None

        payload = self.build_payload(question)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://askmukthiguru.com",
            "X-Title": "AskMukthiGuru",
        }

        try:
            if self._client is not None:
                resp = await self._client.post(
                    self._endpoint_url,
                    json=payload,
                    headers=headers,
                    timeout=self._timeout_s,
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                    resp = await client.post(
                        self._endpoint_url,
                        json=payload,
                        headers=headers,
                    )

            if resp.status_code != 200:
                logger.warning(
                    "Jev router HTTP error: status=%d body=%s",
                    resp.status_code,
                    resp.text[:200],
                )
                return None

            data = resp.json()
            return self.parse_response(data)

        except (TimeoutError, httpx.HTTPError) as exc:
            logger.warning("Jev router request failed or timed out: %s", exc)
            return None
        except Exception as exc:  # noqa: BLE001 - non-blocking failover
            logger.warning("Jev router unexpected error: %s", exc)
            return None
