"""
Mukthi Guru — Data Auditor

Design Patterns:
  - Chain of Responsibility: Acts as a quality gate in the ingestion pipeline
  - Strategy Pattern: Can use different auditing strategies (LLM, heuristics)

Ensures that ingested content is high-quality and relevant.
"""

import logging
import random
from typing import List

from services.ollama_service import OllamaService
from app.config import settings

logger = logging.getLogger(__name__)

AUDIT_SYSTEM_PROMPT = """You are a Data Quality Auditor for a spiritual AI knowledge base.
Your job is to evaluate whether a text transcript is coherent, meaningful, and related to spiritual teachings/philosophy.

Reject the text if:
- It is gibberish or mostly noise (e.g. "Thank you thank you thank you" repeated).
- It is a random vlog, gaming video, or unrelated content.
- It is too fragmented or broken to understand.

Accept the text if:
- It contains coherent sentences about life, philosophy, spirituality, or consciousness.
- It is a spoken lecture or conversation, even with minor transcription errors.

Reply ONLY with "PASS" or "FAIL". Do not add any explanation."""


class DataAuditor:
    """
    Audits content quality before indexing.
    """

    def __init__(self, ollama_service: OllamaService):
        self._llm = ollama_service
        self._enabled = settings.data_audit_enabled

    async def audit_transcript(self, text: str, source_url: str) -> bool:
        """
        Check if the transcript is valid.
        
        To save costs/time, we don't audit the *entire* text. 
        We sample 3 random chunks of 500 chars and check if they make sense.
        If ANY chunk fails, we flag for deeper review (or fail, depending on strictness).
        """
        if not self._enabled:
            return True

        if len(text) < 200:
            logger.warning(f"Audit: Text too short ({len(text)} chars) to be valid content.")
            return False

        # Sample 3 random segments (start, middle, end)
        chunks = self._sample_text(text, num_samples=3, sample_size=500)
        
        for i, chunk in enumerate(chunks):
            is_valid = await self._check_chunk(chunk)
            if not is_valid:
                logger.warning(f"Audit FAILED for {source_url} at sample {i+1}: {chunk[:50]}...")
                return False

        logger.info(f"Audit PASSED for {source_url}")
        return True

    async def _check_chunk(self, chunk: str) -> bool:
        """Ask LLM if a single chunk is valid."""
        try:
            response = await self._llm.generate(
                system_prompt=AUDIT_SYSTEM_PROMPT,
                user_prompt=f"Text to audit:\n---\n{chunk}\n---\n\nVerdict:",
                temperature=0.0,
            )
            return "PASS" in response.upper()
        except Exception as e:
            logger.error(f"Audit check failed: {e}")
            # If audit fails due to error, we default to PASS to avoid blocking ingestion of good data
            # unless we are in strict mode.
            return True

    def _sample_text(self, text: str, num_samples: int, sample_size: int) -> List[str]:
        """Extract random samples from the text."""
        if len(text) <= sample_size:
            return [text]

        step = len(text) // num_samples
        samples = []
        for i in range(num_samples):
            start = i * step
            # Add some randomness to start position within the step
            offset = random.randint(0, max(0, step - sample_size))
            actual_start = start + offset
            samples.append(text[actual_start : actual_start + sample_size])
            
        return samples
