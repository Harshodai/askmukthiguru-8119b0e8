"""SRS Service — Spaced Repetition System using the SM-2 algorithm.

Manages active recall flashcard generation and reviews.
"""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import UTC, datetime, timedelta
from typing import Any, Optional

from fastapi import HTTPException

from app.config import settings
from app.language_utils import guardrail_text_for
from services.injection_scanner import InjectionScanner

logger = logging.getLogger(__name__)


class SRSService:
    def __init__(
        self,
        supabase_client: Optional[Any] = None,
        ollama_service: Optional[Any] = None,
        guardrails_service: Optional[Any] = None,
        translation_service: Optional[Any] = None,
    ) -> None:
        self._supabase = supabase_client
        self._ollama = ollama_service
        self._guardrails = guardrails_service
        self._translation = translation_service

    @property
    def available(self) -> bool:
        return self._supabase is not None

    async def list_due_cards(self, user_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Fetch flashcards that are due for review."""
        if not self.available:
            return []
        try:
            now = datetime.now(UTC).isoformat()
            resp = await asyncio.to_thread(
                self._supabase.table("user_retention_cards")
                .select("*")
                .eq("user_id", user_id)
                .lte("next_review_at", now)
                .order("next_review_at", desc=False)
                .limit(limit)
                .execute
            )
            return resp.data or []
        except Exception as e:
            logger.error(f"Failed to list due SRS cards for {user_id}: {e}")
            return []

    async def create_card(
        self,
        user_id: str,
        question: str,
        answer: str,
        source_type: str,
        source_id: Optional[str] = None,
    ) -> dict[str, Any] | None:
        """Create a new flashcard in the database."""
        if not self.available:
            return None
        try:
            payload = {
                "user_id": user_id,
                "question": question.strip(),
                "answer": answer.strip(),
                "source_type": source_type,
                "source_id": source_id,
                "easiness_factor": 2.5,
                "interval_days": 0,
                "repetitions": 0,
                "next_review_at": datetime.now(UTC).isoformat(),
            }
            resp = await asyncio.to_thread(
                self._supabase.table("user_retention_cards").insert(payload).execute
            )
            return resp.data[0] if resp.data else None
        except Exception as e:
            logger.error(f"Failed to create SRS card for {user_id}: {e}")
            return None

    async def review_card(self, card_id: str, user_id: str, rating: int) -> dict[str, Any] | None:
        """
        Record a review response and update scheduling parameters using SM-2 algorithm.

        Rating scale: 0-5.
        - 0-2: Incorrect / forgotten response. Repetitions reset.
        - 3-5: Correct response. Repetitions increment.
        """
        if not self.available or rating < 0 or rating > 5:
            return None
        try:
            # Fetch current card parameters scoped to the authenticated user
            card_resp = await asyncio.to_thread(
                self._supabase.table("user_retention_cards")
                .select("*")
                .eq("id", card_id)
                .eq("user_id", user_id)
                .execute
            )
            if not card_resp.data:
                logger.warning(f"Card {card_id} not found for review.")
                return None

            card = card_resp.data[0]
            ef = card.get("easiness_factor", 2.5)
            interval = card.get("interval_days", 0)
            repetitions = card.get("repetitions", 0)

            # SM-2 Algorithm
            if rating >= 3:
                # Correct response
                if repetitions == 0:
                    interval = 1
                elif repetitions == 1:
                    interval = 6
                else:
                    interval = int(math.ceil(interval * ef))
                repetitions += 1
            else:
                # Incorrect response
                repetitions = 0
                interval = 1

            # Adjust easiness factor: EF' = EF + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
            q = rating
            ef = ef + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
            if ef < 1.3:
                ef = 1.3
            if ef > 3.0:
                ef = 3.0

            next_review = datetime.now(UTC) + timedelta(days=interval)

            update_payload = {
                "easiness_factor": round(ef, 3),
                "interval_days": interval,
                "repetitions": repetitions,
                "next_review_at": next_review.isoformat(),
            }

            resp = await asyncio.to_thread(
                self._supabase.table("user_retention_cards")
                .update(update_payload)
                .eq("id", card_id)
                .eq("user_id", user_id)
                .eq("interval_days", interval)
                .execute
            )
            if not resp.data:
                logger.warning(
                    f"Concurrent review conflict for card {card_id} — stale state detected"
                )
                return None
            return resp.data[0]
        except Exception as e:
            logger.error(f"Failed to review SRS card {card_id}: {e}")
            return None

    async def generate_cards_from_notebook_item(
        self, user_id: str, query: str, answer: str, source_id: str
    ) -> list[dict]:
        """Use Ollama service to generate active recall flashcards from a notebook Q&A turn."""
        if not self._ollama:
            logger.warning("Ollama service not available for flashcard generation.")
            return []

        # P1-AI-7: screen user notebook content BEFORE it reaches the LLM prompt.
        # The InjectionScanner catches instruction-override/jailbreak phrasing;
        # the guardrails chain additionally catches "system prompt" style leaks.
        for field_name, field_value in (("query", query), ("answer", answer)):
            scan = InjectionScanner.scan_chunk(field_value)
            if scan["injection_detected"]:
                logger.warning(
                    f"SRS generation blocked: injection patterns in {field_name}: {scan['patterns']}"
                )
                raise HTTPException(
                    status_code=400,
                    detail="Notebook content contains prompt-injection patterns and cannot be used for flashcard generation.",
                )
            if self._guardrails and getattr(settings, "multilingual_guardrails", True):
                gr_text = await guardrail_text_for(
                    field_value, self._translation, preferred_lang="en"
                )
                pre_check = await self._guardrails.check_input(gr_text)
                if pre_check.get("blocked"):
                    logger.warning(
                        f"SRS generation blocked: guardrails flagged {field_name}: {pre_check.get('reason')}"
                    )
                    raise HTTPException(
                        status_code=400,
                        detail=f"Notebook content was blocked by content guardrails ({pre_check.get('reason')}).",
                    )

        # P1-AI-7: escape braces in user content before interpolation so a user's
        # "{...}" cannot break out of the template (or crash it). Escaped braces
        # survive format() as literal characters.
        safe_query = query.replace("{", "{{").replace("}", "}}")
        safe_answer = answer.replace("{", "{{").replace("}", "}}")

        prompt = f"""Generate exactly 2 high-quality active recall study flashcards (Question & Answer pairs)
based on the following spiritual dialogue. Keep the questions focused on critical spiritual insights, practices, or wisdom.

Dialogue:
Question: {safe_query}
Answer: {safe_answer}

Format your output exactly as a JSON list of objects:
[
  {{"question": "Question text here?", "answer": "Answer text here"}},
  ...
]"""

        try:
            response = await self._ollama.generate(
                system_prompt="You are a wise spiritual teacher helper. Output only raw JSON lists.",
                user_prompt=prompt,
                temperature=0.4,
                # P1-AI-1: flashcards are short JSON — bound the call so a
                # runaway model cannot emit unbounded tokens before the JSON
                # parse fails downstream.
                max_tokens=400,
            )
            import json

            # Handle markdown fence wrappers if any
            clean_resp = response.strip()
            if clean_resp.startswith("```"):
                clean_resp = clean_resp.split("```")[1]
                if clean_resp.startswith("json"):
                    clean_resp = clean_resp[4:]

            pairs = json.loads(clean_resp.strip())
            if not isinstance(pairs, list) or len(pairs) > 2:
                logger.warning(
                    f"Generated flashcards are not a list of at most 2 items: {type(pairs).__name__}"
                )
                return []

            created_cards = []
            for pair in pairs:
                if not isinstance(pair, dict):
                    continue
                q = pair.get("question")
                a = pair.get("answer")
                if (
                    not isinstance(q, str)
                    or not q.strip()
                    or not isinstance(a, str)
                    or not a.strip()
                ):
                    logger.warning("Skipping flashcard with missing or non-string question/answer.")
                    continue
                q = q.strip()
                a = a.strip()
                if self._guardrails and getattr(settings, "multilingual_guardrails", True):
                    # CRIT-5: translate non-EN flashcard text so EN injection
                    # regexes fire; falls back to the raw text on failure.
                    # Flag-gated: multilingual_guardrails=False restores the old
                    # latent-dead-code behavior (no flashcard guardrail check).
                    gr_text = await guardrail_text_for(
                        q + " " + a, self._translation, preferred_lang="en"
                    )
                    input_check = await self._guardrails.check_input(gr_text)
                    if input_check.get("blocked"):
                        logger.warning(
                            f"Flashcard content blocked by guardrails: {input_check.get('reason')}"
                        )
                        continue
                    output_check = await self._guardrails.check_output(a)
                    if output_check.get("blocked"):
                        logger.warning(
                            f"Flashcard answer blocked by guardrails: {output_check.get('reason')}"
                        )
                        continue
                    moderated_answer = output_check.get("moderated_response")
                    if moderated_answer is not None:
                        a = moderated_answer.strip()
                card = await self.create_card(
                    user_id=user_id,
                    question=q,
                    answer=a,
                    source_type="notebook_item",
                    source_id=source_id,
                )
                if card:
                    created_cards.append(card)
            return created_cards
        except Exception as e:
            logger.error(f"Failed to generate flashcards from notebook item: {e}")
            return []
