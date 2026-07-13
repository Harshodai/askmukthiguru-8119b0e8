"""SRS Service — Spaced Repetition System using the SM-2 algorithm.

Manages active recall flashcard generation and reviews.
"""

from __future__ import annotations

import logging
import math
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

class SRSService:
    def __init__(self, supabase_client: Optional[Any] = None, ollama_service: Optional[Any] = None) -> None:
        self._supabase = supabase_client
        self._ollama = ollama_service

    @property
    def available(self) -> bool:
        return self._supabase is not None

    async def list_due_cards(self, user_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Fetch flashcards that are due for review."""
        if not self.available:
            return []
        try:
            now = datetime.now(timezone.utc).isoformat()
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
        source_id: Optional[str] = None
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
                "next_review_at": datetime.now(timezone.utc).isoformat()
            }
            resp = await asyncio.to_thread(
                self._supabase.table("user_retention_cards")
                .insert(payload)
                .execute
            )
            return resp.data[0] if resp.data else None
        except Exception as e:
            logger.error(f"Failed to create SRS card for {user_id}: {e}")
            return None

    async def review_card(self, card_id: str, rating: int) -> dict[str, Any] | None:
        """
        Record a review response and update scheduling parameters using SM-2 algorithm.
        
        Rating scale: 0-5.
        - 0-2: Incorrect / forgotten response. Repetitions reset.
        - 3-5: Correct response. Repetitions increment.
        """
        if not self.available or rating < 0 or rating > 5:
            return None
        try:
            # Fetch current card parameters
            card_resp = await asyncio.to_thread(
                self._supabase.table("user_retention_cards")
                .select("*")
                .eq("id", card_id)
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

            next_review = datetime.now(timezone.utc) + timedelta(days=interval)

            update_payload = {
                "easiness_factor": round(ef, 3),
                "interval_days": interval,
                "repetitions": repetitions,
                "next_review_at": next_review.isoformat()
            }

            resp = await asyncio.to_thread(
                self._supabase.table("user_retention_cards")
                .update(update_payload)
                .eq("id", card_id)
                .execute
            )
            return resp.data[0] if resp.data else None
        except Exception as e:
            logger.error(f"Failed to review SRS card {card_id}: {e}")
            return None

    async def generate_cards_from_notebook_item(self, user_id: str, query: str, answer: str, source_id: str) -> list[dict]:
        """Use Ollama service to generate active recall flashcards from a notebook Q&A turn."""
        if not self._ollama:
            logger.warning("Ollama service not available for flashcard generation.")
            return []
        
        prompt = f"""Generate exactly 2 high-quality active recall study flashcards (Question & Answer pairs) 
based on the following spiritual dialogue. Keep the questions focused on critical spiritual insights, practices, or wisdom.

Dialogue:
Question: {query}
Answer: {answer}

Format your output exactly as a JSON list of objects:
[
  {{"question": "Question text here?", "answer": "Answer text here"}},
  ...
]"""

        try:
            response = await self._ollama.generate(
                system_prompt="You are a wise spiritual teacher helper. Output only raw JSON lists.",
                user_prompt=prompt,
                temperature=0.4
            )
            import json
            # Handle markdown fence wrappers if any
            clean_resp = response.strip()
            if clean_resp.startswith("```"):
                clean_resp = clean_resp.split("```")[1]
                if clean_resp.startswith("json"):
                    clean_resp = clean_resp[4:]
            
            pairs = json.loads(clean_resp.strip())
            created_cards = []
            for pair in pairs:
                q = pair.get("question")
                a = pair.get("answer")
                if q and a:
                    card = await self.create_card(
                        user_id=user_id,
                        question=q,
                        answer=a,
                        source_type="notebook_item",
                        source_id=source_id
                    )
                    if card:
                        created_cards.append(card)
            return created_cards
        except Exception as e:
            logger.error(f"Failed to generate flashcards from notebook item: {e}")
            return []
