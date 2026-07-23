"""
Transcript Polisher Service — LLM-driven transcript punctuation & formatting polish.

Ported from AgentReach's --polish pattern (transcribe_xiaoyuzhou.sh), but adapted
to use AskMukthiGuru's native LLM provider gateway (MultiProviderLLMService:
Sarvam Cloud / OpenRouter / NIM / Ollama) instead of external Groq API calls.

Features:
  - Zero-edit prompt: Adds standard punctuation (,.!?:;) and natural paragraph breaks
    without adding, removing, or modifying any words or names.
  - Truncation protection: If LLM completion is truncated due to length limits,
    recursively splits the transcript at the midpoint and polishes both halves.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from services.multi_provider_llm import MultiProviderLLMService

logger = logging.getLogger(__name__)

POLISH_SYSTEM_PROMPT = """You are a precise transcript formatting assistant.
Your task is to take a raw, unpunctuated or poorly punctuated speech-to-text transcript and add proper punctuation (commas, periods, question marks, colons, quotation marks) and natural paragraph breaks.

CRITICAL INVARIANTS:
1. Do NOT modify, delete, or rewrite any words, numbers, or spiritual terms.
2. Do NOT add any preamble, conversational commentary, or explanation.
3. Do NOT add any extra information or summarize.
4. Output ONLY the formatted transcript with added punctuation and paragraph breaks."""


async def polish_transcript(
    raw_transcript: str,
    llm_service: Optional[Any] = None,
    max_depth: int = 3,
    current_depth: int = 0,
) -> str:
    """Format and polish raw transcript using AskMukthiGuru native LLM providers.
    
    If the transcript is empty or too short, returns raw_transcript as-is.
    Handles long transcript completions with recursive midpoint splitting.
    """
    raw_text = raw_transcript.strip()
    if not raw_text or len(raw_text) < 30:
        return raw_text

    svc = llm_service or MultiProviderLLMService()

    try:
        prompt = f"{POLISH_SYSTEM_PROMPT}\n\nFormat this raw transcript:\n\n{raw_text}"
        
        # Flexibly handle MultiProviderLLMService, ChatOpenAI, or mock objects
        if hasattr(svc, "generate"):
            try:
                response = await svc.generate(prompt=prompt, temperature=0.1, max_tokens=4096)
            except TypeError:
                messages = [
                    {"role": "system", "content": POLISH_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Format this raw transcript:\n\n{raw_text}"},
                ]
                response = await svc.generate(messages=messages, temperature=0.1, max_tokens=4096)
        else:
            messages = [
                {"role": "system", "content": POLISH_SYSTEM_PROMPT},
                {"role": "user", "content": f"Format this raw transcript:\n\n{raw_text}"},
            ]
            response = await svc.ainvoke(messages)

        if isinstance(response, dict):
            polished_text = response.get("choices", [{}])[0].get("message", {}).get("content", "") or response.get("text", "")
        elif hasattr(response, "content"):
            polished_text = str(response.content)
        else:
            polished_text = str(response)

        polished_text = polished_text.strip()
        if not polished_text:
            return raw_text

        # Check if output seems severely truncated relative to input length
        if len(polished_text) < len(raw_text) * 0.5 and current_depth < max_depth:
            logger.warning(
                "Polished output truncated (%d chars vs %d input chars). Splitting at midpoint.",
                len(polished_text),
                len(raw_text),
            )
            midpoint = len(raw_text) // 2
            space_idx = raw_text.rfind(" ", 0, midpoint)
            if space_idx != -1:
                midpoint = space_idx

            first_half = await polish_transcript(
                raw_text[:midpoint], llm_service=svc, max_depth=max_depth, current_depth=current_depth + 1
            )
            second_half = await polish_transcript(
                raw_text[midpoint:], llm_service=svc, max_depth=max_depth, current_depth=current_depth + 1
            )
            return f"{first_half}\n\n{second_half}"

        return polished_text

    except Exception as e:
        logger.warning("Transcript polish failed (returning raw text): %s", e)
        return raw_text

