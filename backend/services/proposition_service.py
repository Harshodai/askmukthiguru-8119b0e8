"""
Mukthi Guru — Proposition Service (DEPRECATED / RETIRED).

Notice: Proposition chunking is retired per Decision D3 and Phase 3 Reindexability
specifications. Unified Chunker Protocol (ingest/chunker_protocol.py) is the standard.
This service is maintained as a minimal backward-compatibility stub for legacy
harnesses and existing tests.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from services.text_quality_filter import find_artifact

logger = logging.getLogger(__name__)


class PropositionService:
    """
    Deprecated service for splitting text into atomic propositions using LLM inference.
    Retired per Decision D3.
    """

    def __init__(self, ollama_service: Any) -> None:
        """
        Initialize with the injected LLM service (Ollama or Sarvam).
        """
        self._llm = ollama_service
        logger.info("Proposition Service initialized (deprecated)")

    def should_apply_propositions(self, doc_text: str) -> bool:
        """
        Determine if proposition chunking should be applied to this document.
        Defaults to False as proposition chunking is retired.
        """
        prop_setting = getattr(settings, "use_proposition_chunking", False)
        if isinstance(prop_setting, bool):
            return prop_setting
        strategy = str(prop_setting).lower()
        if strategy in ("never", "false", ""):
            return False
        if strategy in ("always", "true"):
            return True

        doc_len = len(doc_text)
        is_above_threshold = doc_len >= getattr(settings, "proposition_char_limit", 15000)
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

            # L-INGEST-1 / L-INGEST-2: gate every LLM-produced proposition
            # through find_artifact() (CoT leaks, graceful-degradation canned
            # strings, ASR loops) before it can reach Qdrant. Contaminated
            # lines are dropped; length checks alone cannot catch these.
            clean_propositions = []
            for prop in propositions:
                artifact = find_artifact(prop)
                if artifact:
                    logger.warning(
                        "Proposition contaminated (%s) — dropping line: %.80s",
                        artifact,
                        prop,
                    )
                    continue
                clean_propositions.append(prop)
            propositions = clean_propositions

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
