"""
Data Corrector Module
---------------------
Part of the 'Council Recommendation' pipeline.
Uses an LLM to correct homophones, spelling errors, and domain-specific terminology
(e.g., "Sri Preethaji" instead of "Sri Pretty Ji") in the raw transcripts.
"""

import logging
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

class TranscriptCorrector:
    def __init__(self, ollama_service: OllamaService):
        self._llm = ollama_service

    async def correct_transcript(self, text: str, source_url: str) -> str:
        """
        Corrects the transcript using the LLM in chunks.
        """
        logger.info(f"Correcting transcript for {source_url}...")
        
        # Split into manageable chunks for the LLM (approx 2000 chars)
        chunk_size = 2000
        chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
        
        corrected_chunks = []
        
        for i, chunk in enumerate(chunks):
            try:
                # Use the existing generate method
                response = await self._llm.generate(
                    system_prompt=CORRECTION_SYSTEM_PROMPT,
                    user_prompt=f"Correct this text:\n\n{chunk}",
                    temperature=0.0,
                )
                corrected_chunks.append(response)
            except Exception as e:
                logger.error(f"Failed to correct chunk {i}: {e}")
                # Fallback: keep original text if correction fails
                corrected_chunks.append(chunk)
                
        full_corrected_text = " ".join(corrected_chunks)
        return full_corrected_text
