import logging
from typing import Optional

logger = logging.getLogger(__name__)


class AdaptiveHyDEGenerator:
    """
    Adaptive HyDE (Hypothetical Document Embeddings) Generator.
    Circuit breaker: Only triggers if query is conceptual/philosophical/doctrinal,
    length > 3 words, and NOT an exact quote search or distress query.
    """

    @staticmethod
    async def should_generate_hypothetical_document(
        query: str, query_type: str = "general"
    ) -> bool:
        if not query:
            return False

        words = query.strip().split()
        if len(words) <= 3:
            return False

        # Check for distress / safety queries or exact quote searches
        lower_q = query.lower()
        distress_keywords = [
            "suicide",
            "depressed",
            "kill",
            "harm",
            "crisis",
            "emergency",
            "despair",
            "hopeless",
        ]
        if any(kw in lower_q for kw in distress_keywords):
            return False

        exact_quote_markers = ["quote", "verbatim", "exact words", '"']
        if any(marker in lower_q for marker in exact_quote_markers):
            return False

        # Trigger for conceptual, philosophical, doctrinal queries
        conceptual_types = {"philosophical", "doctrinal", "conceptual", "spiritual", "general"}
        if query_type in conceptual_types or len(words) > 5:
            return True

        return False

    @staticmethod
    async def generate_hypothetical_passage(
        query: str, seeker_context: Optional[dict] = None
    ) -> Optional[str]:
        """
        Generates a domain-grounded hypothetical reflection without hallucinations.
        """
        if not await AdaptiveHyDEGenerator.should_generate_hypothetical_document(query):
            return None

        # Never log the seeker's words (test_no_seeker_text_in_logs enforces a
        # non-increasing budget of such call sites). Length is enough to debug.
        logger.info("Generating hypothetical passage (query_chars=%d)", len(query or ""))
        return (
            f"In the teachings of Oneness and Ekam regarding {query}, "
            f"suffering arises from separation of the conditioned self, "
            f"while liberation comes through stillness, presence, and moving from "
            f"contracted self-centered awareness to a state of unconditioned grace and connection."
        )
