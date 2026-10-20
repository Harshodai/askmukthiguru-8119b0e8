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
import math
import re
import time
from typing import Any, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_DEFAULT_DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"

_INTENT_CRITERIA: dict[str, str] = {
    # Keep labels broad and domain-oriented. Speaker identity comes only from
    # the YAML teacher registry and verified source metadata, never from Jev.
    "SPIRITUAL_TEACHING": (
        "The primary request is to understand a spiritual doctrine/concept as taught "
        "in this product's recorded corpus, or it explicitly asks what a registered "
        "teacher taught/said. Do not infer teacher intent from incidental words such "
        "as meditation, anxiety, breath, fear, or relationship alone."
    ),
    "GENERAL_KNOWLEDGE": (
        "A factual, educational, science/health/psychology, software, writing, "
        "calculation, everyday-planning, medical/legal/financial-information, news, "
        "or practical request. A question that merely mentions meditation, anxiety, "
        "breathing, fear, relationships, or inner peace without asking for a recorded "
        "teaching is general knowledge."
    ),
    "CASUAL": (
        "A greeting, farewell, expression of gratitude, small talk, or capability inquiry."
    ),
    "MEDITATION": (
        "A direct request to start, practice, or be guided through a meditation or breathing exercise."
    ),
    # Jev can provide a supplemental signal. It is never the sole safety gate:
    # the deterministic + dedicated distress checks must preempt it.
    "DISTRESS": (
        "A statement expressing acute emotional pain, despair, suicidal ideation, "
        "self-harm intent, or psychological crisis; return this only when strongly evidenced."
    ),
    "LIVE_LOGISTICS": (
        "A question about current event dates, retreat schedules, registration, "
        "or physical-location logistics that requires a live source."
    ),
    "LIVE_RESEARCH": (
        "A time-sensitive or changing factual question about current news, prices, "
        "versions, weather, public events, or other facts requiring up-to-date sources."
    ),
    # Backward-compatibility label for older pinned decision configurations.
    "FACTUAL": (
        "Legacy factual label. Map to a teaching route only when explicit teacher/teaching "
        "intent is present; otherwise choose GENERAL_KNOWLEDGE."
    ),
}

# The legacy FACTUAL label has no reliable domain semantics on its own. Route it
# to the teaching lane only when the question explicitly asks about a teacher or
# recorded teaching; otherwise it is general knowledge. Newer Jev labels remain authoritative.
_LEGACY_TEACHING_INTENT_RE = re.compile(
    r"\b(?:recorded discourse|recorded words|verbatim|exact quote|exact words|"
    r"as taught by|according to (?:the )?teachings|"
    r"what (?:did|has) .{0,60} (?:say|said|teach|taught)|"
    r"what does .{0,60} teach|what do .{0,60} teachings? say|"
    r"teachings? of .{1,60}|said by .{1,60})\b",
    re.IGNORECASE,
)

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

    def parse_response(
        self, data: dict[str, Any], question: str = ""
    ) -> Optional[dict[str, Any]]:
        """Parse decisions response and validate confidence bounds.

        ``question`` is used only for the legacy FACTUAL choice, whose old label
        did not distinguish worldly questions from recorded-teaching intent.
        """
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
        raw_confidence = (
            intent_probabilities.get(intent_choice)
            if isinstance(intent_probabilities, dict)
            else None
        )
        if raw_confidence is None:
            # No calibrated probability for the chosen label: do not guess confidence.
            logger.warning("Jev router: no probability for intent %r; falling back.", intent_choice)
            return None
        try:
            confidence = float(raw_confidence)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            logger.warning("Jev router: invalid probability for intent %r.", intent_choice)
            return None
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
            return None

        # Translate the decision model's domain label to existing graph intents.
        # New routes carry explicit route metadata without creating unhandled
        # LangGraph intent labels.
        if intent_choice == "GENERAL_KNOWLEDGE":
            graph_intent, domain_route = "FACTUAL", "general"
        elif intent_choice == "SPIRITUAL_TEACHING":
            graph_intent, domain_route = "FACTUAL", "teaching"
        elif intent_choice == "LIVE_RESEARCH":
            graph_intent, domain_route = "FACTUAL", "live_research"
        elif intent_choice == "FACTUAL":
            domain_route = (
                "teaching"
                if _LEGACY_TEACHING_INTENT_RE.search(question or "")
                else "general"
            )
            graph_intent = "FACTUAL"
        else:
            graph_intent, domain_route = intent_choice, intent_choice.lower()

        needs_web_search = intent_choice in {"LIVE_LOGISTICS", "LIVE_RESEARCH"}

        return {
            "intent": graph_intent,
            "domain_route": domain_route,
            "general_knowledge_mode": domain_route == "general",
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

        started = time.perf_counter()
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
            decision = self.parse_response(data, question=question)
            elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
            if decision is None:
                logger.info("jev_route outcome=fallback reason=invalid_or_low_confidence elapsed_ms=%.1f", elapsed_ms)
                return None
            decision["latency_ms"] = elapsed_ms
            logger.info(
                "jev_route outcome=accepted domain_route=%s confidence=%.3f tier=%s elapsed_ms=%.1f",
                decision["domain_route"],
                decision["confidence"],
                decision["query_tier"],
                elapsed_ms,
            )
            return decision

        except (TimeoutError, httpx.HTTPError) as exc:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
            logger.warning("jev_route outcome=fallback reason=network_or_timeout elapsed_ms=%.1f error=%s", elapsed_ms, type(exc).__name__)
            return None
        except Exception as exc:  # noqa: BLE001 - non-blocking failover
            elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
            logger.warning("jev_route outcome=fallback reason=unexpected elapsed_ms=%.1f error=%s", elapsed_ms, type(exc).__name__)
            return None
