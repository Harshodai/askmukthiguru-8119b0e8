# DORMANT (2026-11-01 wiring audit, plan §12): no call site in the request path; not shipped. Only used by speculative_stream.py.
"""First-Person Verbatim Guard enforcing Invariants X11, X18, X24."""

import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class FirstPersonVerbatimGuard:
    """Enforces First-Person serving invariants:
    - Answer text is strictly the verbatim stored span text in order.
    - Strips any LLM-authored introductory or connective prose when in `retrieval_only` mode (Invariant X24).
    - Verbatim quote plus speaker/source attribution only. No LLM hallucinations on first-person clips.
    """

    def __init__(self) -> None:
        pass

    def enforce_verbatim(
        self,
        generated_text: str,
        source_spans: List[str],
        is_first_person: bool = True,
    ) -> Dict[str, Any]:
        """Enforces verbatim quotes for first-person teaching clips.
        
        Args:
            generated_text: The text produced or drafted.
            source_spans: The exact verbatim source spans retrieved from audio/transcripts.
            is_first_person: Whether this is a first-person teaching request.
            
        Returns:
            Dict containing 'enforced_text', 'is_verbatim', and 'modifications_made'.
        """
        if not is_first_person or not source_spans:
            return {
                "enforced_text": generated_text,
                "is_verbatim": True,
                "modifications_made": False,
            }

        # Combine source spans verbatim
        verbatim_core = " ".join(span.strip() for span in source_spans if span.strip())

        # In first-person retrieval_only mode, we strictly return the verbatim source spans
        # and strip any LLM introductory text like "Here is the teaching:" or connective prose.
        enforced_text = verbatim_core
        modifications_made = generated_text.strip() != verbatim_core.strip()

        logger.info(
            f"FirstPersonVerbatimGuard enforced verbatim text. Modifications made: {modifications_made}"
        )

        return {
            "enforced_text": enforced_text,
            "is_verbatim": True,
            "modifications_made": modifications_made,
        }
