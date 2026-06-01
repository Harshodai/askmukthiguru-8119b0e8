"""
Mukthi Guru — Proposition Service

Implements Proposition Chunking.
Decomposes larger text chunks into atomic, standalone facts (propositions) using the LLM.
Adds intelligence to dynamically check document size thresholds before applying LLM-based parsing.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


class PropositionService:
    """
    Service for splitting text into independent, atomic propositions using LLM inference.
    """

    def __init__(self, ollama_service: Any) -> None:
        """
        Initialize with the injected LLM service (Ollama or Sarvam).
        """
        self._llm = ollama_service
        logger.info("Proposition Service initialized")

    def should_apply_propositions(self, doc_text: str) -> bool:
        """
        Determine if proposition chunking should be applied to this document.

        Rules:
          - If use_proposition_chunking is "always", return True.
          - If use_proposition_chunking is "never", return False.
          - If "auto", return True only if length >= settings.proposition_char_limit.
        """
        strategy = settings.use_proposition_chunking.lower()
        if strategy == "never":
            return False
        if strategy == "always":
            return True

        doc_len = len(doc_text)
        is_above_threshold = doc_len >= settings.proposition_char_limit
        logger.info(
            f"Proposition strategy auto-check: len={doc_len}, limit={settings.proposition_char_limit}. apply={is_above_threshold}"
        )
        return is_above_threshold

    async def extract_propositions(self, text: str) -> list[str]:
        """
        Decompose a chunk of text into atomic, independent propositions.
        Each proposition is a complete, grammatically correct sentence that can
        stand on its own without context or pronoun references.

        Args:
            text: Input chunk text.

        Returns:
            List of individual proposition strings.
        """
        if not text or not text.strip():
            return []

        try:
            prompt = (
                "Decompose the following spiritual teaching into independent, self-contained propositions. "
                "Ensure each proposition is a complete standalone sentence containing full context "
                "(replace pronouns like 'he', 'she', 'it', 'this', 'that' with their corresponding proper nouns "
                "or explicit names from the text). "
                "Return each proposition on a new line prefixed with '- '. "
                "Do not include any intro, outro, headers, or conversational preamble."
            )

            response = await self._llm.generate(
                prompt,
                f"Teaching:\n{text}",
                max_tokens=600,
            )

            # Parse lines starting with '- '
            propositions = []
            for line in response.split("\n"):
                line = line.strip()
                if line.startswith("- "):
                    prop = line[2:].strip()
                    if len(prop) > 20:  # Filter out very short noise
                        propositions.append(prop)
                elif line and not line.startswith("#") and len(line) > 30:
                    # Fallback for LLMs that didn't output prefixes properly
                    propositions.append(line)

            if not propositions:
                logger.warning("LLM returned no propositions. Falling back to original chunk.")
                return [text]

            logger.info(
                f"Proposition chunking succeeded: split chunk into {len(propositions)} propositions."
            )
            return propositions

        except Exception as e:
            logger.error(f"Proposition splitting failed: {e}. Falling back to original chunk.")
            return [text]
