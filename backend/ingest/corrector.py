"""
Data Corrector Module
---------------------
Part of the 'Council Recommendation' pipeline.
Uses an LLM to correct homophones, spelling errors, and domain-specific terminology
(e.g., "Sri Preethaji" instead of "Sri Pretty Ji") in the raw transcripts.
"""

import asyncio
import logging
import re
from typing import List
from services.ollama_service import OllamaService

logger = logging.getLogger(__name__)

CORRECTION_SYSTEM_PROMPT = """You are a Text Correction Expert for the 'Mukthi Guru' spiritual platform.
Your task is to fix transcription errors in the provided text, specifically focusing on:
1. Homophones and misheard words.
2. Domain-specific names and terms (see list below).
3. Punctuation and capitalization for readability.

DO NOT retain the original meaning absolutely. DO NOT summarize or rewrite the style. ONLY fix errors.

Important Terms to Correct:
- "Sri Preethaji" (often misheard as "Sri Pretty Ji", "Preeti Ji")
- "Sri Krishnaji" (often misheard as "Sri Krishna Ji", "Krishna G")
- "Ekam" (often misheard as "Acam", "Ecom")
- "Deeksha" (often misheard as "Diksha")
- "Sadhana"
- "Limitless Field"

Output ONLY the corrected text. Do not add any conversational filler.
"""

# Max concurrent correction tasks
_MAX_CONCURRENT = 3


def _sentence_aware_split(text: str, chunk_size: int = 4000, overlap: int = 100) -> list[str]:
    """
    Split text into chunks on sentence boundaries with overlap.

    Uses sentence-ending punctuation to avoid cutting mid-sentence.
    Falls back to character-based splitting if no sentence boundaries found.
    """
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        if end >= len(text):
            chunks.append(text[start:])
            break

        # Find the last sentence boundary within the chunk
        segment = text[start:end]
        # Look for '. ', '! ', '? ', or '\n' as sentence boundaries
        last_boundary = -1
        for match in re.finditer(r'[.!?]\s+|\n', segment):
            last_boundary = match.end()

        if last_boundary > chunk_size // 2:
            # Good boundary found in second half of chunk
            actual_end = start + last_boundary
        else:
            # No good boundary — fall back to space boundary
            space_pos = segment.rfind(' ', chunk_size // 2)
            if space_pos > 0:
                actual_end = start + space_pos
            else:
                actual_end = end

        chunks.append(text[start:actual_end])
        # Overlap: step back by overlap chars to preserve cross-boundary names
        start = max(actual_end - overlap, start + 1)

    return chunks


class TranscriptCorrector:
    def __init__(self, ollama_service: OllamaService):
        self._llm = ollama_service

    async def correct_transcript(self, text: str, source_url: str) -> str:
        """
        Corrects the transcript using the LLM in parallel chunks.

        Uses sentence-aware splitting (4000 chars) with 100-char overlap
        and processes up to 3 chunks concurrently.
        """
        logger.info(f"Correcting transcript for {source_url}...")

        chunks = _sentence_aware_split(text, chunk_size=4000, overlap=100)
        logger.info(f"Correction: split into {len(chunks)} chunks (4000-char, sentence-aware)")

        # Process chunks with bounded concurrency
        semaphore = asyncio.Semaphore(_MAX_CONCURRENT)

        async def _correct_chunk(i: int, chunk: str) -> str:
            async with semaphore:
                try:
                    response = await self._llm.generate(
                        system_prompt=CORRECTION_SYSTEM_PROMPT,
                        user_prompt=f"Correct this text:\n\n{chunk}",
                        temperature=0.0,
                    )
                    return response
                except Exception as e:
                    logger.error(f"Failed to correct chunk {i}: {e}")
                    return chunk

        corrected_chunks = await asyncio.gather(
            *[_correct_chunk(i, chunk) for i, chunk in enumerate(chunks)]
        )

        full_corrected_text = " ".join(corrected_chunks)
        return full_corrected_text
