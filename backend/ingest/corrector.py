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

from services.doctrine_terms import apply_corrections, correction_term_lines
from services.ollama_service import OllamaService

logger = logging.getLogger(__name__)

CORRECTION_SYSTEM_PROMPT = f"""You are a Text Correction Expert for the 'Mukthi Guru' spiritual platform.
Your task is to fix transcription errors in the provided text, specifically focusing on:
1. Homophones and misheard words.
2. Domain-specific names and terms (see list below).
3. Punctuation and capitalization for readability.

DO NOT retain the original meaning absolutely. DO NOT summarize or rewrite the style. ONLY fix errors.

Important Terms to Correct:
{correction_term_lines()}

Output ONLY the corrected text. Do not add any conversational filler.
"""

# Doctrine-term corrections now live in the single source of truth
# (services.doctrine_terms.DEFAULT_DOCTRINE_TERMS, admin-editable). They are applied
# deterministically via apply_corrections() in correct_transcript() below — no local dict here,
# so the correction map can never drift between the whisper, ingest and output layers again.

# Max concurrent correction tasks
_MAX_CONCURRENT = 3

# Phrases from CORRECTION_SYSTEM_PROMPT that indicate LLM prompt leakage
# — when the LLM echoes its own instructions instead of correcting text.
_PROMPT_LEAK_PATTERNS: list[str] = [
    r"You are a Text Correction Expert",
    r"Your task is to fix transcription errors",
    r"DO NOT retain the original meaning absolutely",
    r"DO NOT summarize or rewrite the style",
    r"ONLY fix errors",
    r"Important Terms to Correct",
    r"Output ONLY the corrected text",
    r"Sri Preethaji.*often misheard",
    r"Ekam.*often misheard",
    r"often misheard as",
    r"Correct this text",
    r"TEXT TO CORRECT",
    r"I need to summarize the given text passages",
    r"The instruction is to not retain",
    r"One must not summarize or rewrite",
    r"However, I notice that the text passages",
]

_MIN_MEANINGFUL_CHARS = 80  # skip LLM correction below this (avoid empty-input hallucination)

# A corrector fixes spellings/punctuation. It does not summarize, translate, or
# paraphrase — so its output length tracks its input length closely. These bounds
# exist because the previous guard (`< min(50, len(chunk)//2)`) evaluated to the
# constant 50 for any chunk over 100 chars, and on 2026-08-01 silently accepted
# LLM stubs in place of a full transcript: 22,487 chars in, 7,876 stored (-65%).
# Slightly asymmetric: expanding contractions and adding punctuation legitimately
# grows text a little, while a correction has no reason to shrink it much.
_MIN_LENGTH_RATIO = 0.90
_MAX_LENGTH_RATIO = 1.15

# Ceiling on how much of the token stream may change. Length alone cannot catch a
# same-length paraphrase, which is the other way an LLM "corrects" a passage into
# something the gurus did not say.
_MAX_TOKEN_CHANGE_RATIO = 0.15


def _rewrote_too_much(original: str, corrected: str) -> bool:
    """True when the correction changed more of the token stream than a correction should.

    Uses difflib's ratio over word tokens rather than characters: a doctrine-term
    fix ("soul sink" -> "Soul Sync") touches one or two tokens, while a paraphrase
    touches most of them. Character-level similarity would be dominated by shared
    punctuation and short function words and would miss exactly that distinction.
    """
    import difflib

    orig_tokens = original.split()
    corr_tokens = corrected.split()
    if not orig_tokens:
        return False
    similarity = difflib.SequenceMatcher(None, orig_tokens, corr_tokens).ratio()
    return (1.0 - similarity) > _MAX_TOKEN_CHANGE_RATIO


def _is_content_too_short(text: str) -> bool:
    """Return True if text is too short/empty to benefit from LLM correction.
    Short/empty inputs cause the LLM to echo its system prompt — prompt leakage."""
    cleaned = text.strip()
    if len(cleaned) < _MIN_MEANINGFUL_CHARS:
        return True
    # Count actual words (excluding punctuation-only strings)
    words = [w for w in cleaned.split() if any(c.isalpha() for c in w)]
    return len(words) < 8


def _contains_prompt_leak(text: str) -> bool:
    """Check if the LLM response contains phrases from its own system prompt."""
    for pattern in _PROMPT_LEAK_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


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
        for match in re.finditer(r"[.!?]\s+|\n", segment):
            last_boundary = match.end()

        if last_boundary > chunk_size // 2:
            # Good boundary found in second half of chunk
            actual_end = start + last_boundary
        else:
            # No good boundary — fall back to space boundary
            space_pos = segment.rfind(" ", chunk_size // 2)
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

        # overlap=0, deliberately. The split used to overlap by 100 chars "to preserve
        # cross-boundary names", but the pieces are rejoined below with a plain
        # `" ".join(...)` that never removes the overlap — so every 4,000-char seam
        # duplicated ~100 chars of doctrine into the stored text (~5 injected
        # duplications per 22k-char transcript). The stated benefit is already covered
        # twice over: the split lands on sentence boundaries, and `apply_corrections()`
        # runs over the fully rejoined text at the end, so a doctrine term straddling a
        # seam is still normalised. Re-introducing overlap requires stripping it on
        # rejoin, not just adding it here.
        chunks = _sentence_aware_split(text, chunk_size=4000, overlap=0)
        logger.info(f"Correction: split into {len(chunks)} chunks (4000-char, sentence-aware)")

        # Process chunks with bounded concurrency
        semaphore = asyncio.Semaphore(_MAX_CONCURRENT)

        async def _correct_chunk(i: int, chunk: str) -> str:
            async with semaphore:
                # Guard 1: skip LLM for near-empty input — causes prompt leakage
                if _is_content_too_short(chunk):
                    logger.info(
                        f"Chunk {i} too short/empty ({len(chunk)} chars) — skipping LLM correction"
                    )
                    return chunk

                try:
                    response = await self._llm.generate(
                        system_prompt=CORRECTION_SYSTEM_PROMPT,
                        user_prompt=f"Correct this text:\n\n{chunk}",
                        temperature=0.0,
                        operation="correction",
                        is_structured=True,
                    )
                    # Guard 2: length RATIO check.
                    #
                    # This guard used to read `< min(50, len(chunk)//2)`, which for any
                    # chunk over 100 chars collapses to the constant 50 — i.e. a 50-char
                    # stub was accepted as a faithful correction of a 4,000-char chunk.
                    # On 2026-08-01 that silently destroyed 65% of a transcript
                    # (22,487 chars in, 7,876 chars stored) and NOTHING caught it:
                    # find_artifact passed 6/6, corpus_audit scored 0.0% contaminated.
                    # Truncation leaves no artifact — it leaves fluent, on-topic doctrine
                    # with two thirds of the teaching missing, which is a strictly worse
                    # failure than the chain-of-thought contamination this pipeline was
                    # built to stop, because it is invisible to every gate built for that.
                    #
                    # A corrector fixes spellings and punctuation; it does not change
                    # length materially. Bound it in BOTH directions.
                    original = chunk.strip()
                    corrected = (response or "").strip()
                    ratio = len(corrected) / max(len(original), 1)
                    if not corrected or not (_MIN_LENGTH_RATIO <= ratio <= _MAX_LENGTH_RATIO):
                        logger.warning(
                            "Chunk %d correction length ratio %.2f outside [%.2f, %.2f] "
                            "(%d chars in, %d out) — LLM summarized or padded instead of "
                            "correcting. Using original.",
                            i, ratio, _MIN_LENGTH_RATIO, _MAX_LENGTH_RATIO,
                            len(original), len(corrected),
                        )
                        return chunk

                    # Guard 2b: edit-distance ceiling. Length can match while the content
                    # is a paraphrase, so bound how much of the text may change too. A
                    # real correction touches a small fraction of tokens.
                    if _rewrote_too_much(original, corrected):
                        logger.warning(
                            "Chunk %d correction rewrote more than %.0f%% of tokens — "
                            "paraphrase, not correction. Using original.",
                            i, _MAX_TOKEN_CHANGE_RATIO * 100,
                        )
                        return chunk

                    # Guard 3: prompt leakage detection (root-cause fix)
                    if _contains_prompt_leak(response):
                        logger.warning(
                            f"Chunk {i} response contains LLM prompt leakage — "
                            f"LLM echoed its own system prompt. Using original."
                        )
                        return chunk

                    return response
                except Exception as e:
                    logger.error(f"Failed to correct chunk {i}: {e}")
                    return chunk

        corrected_chunks = await asyncio.gather(
            *[_correct_chunk(i, chunk) for i, chunk in enumerate(chunks)]
        )

        full_corrected_text = " ".join(corrected_chunks)

        # Apply the shared doctrine-term corrections (single source of truth) to catch LLM misses
        full_corrected_text = apply_corrections(full_corrected_text)

        return full_corrected_text
