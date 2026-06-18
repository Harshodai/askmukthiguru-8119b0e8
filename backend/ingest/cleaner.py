"""
Mukthi Guru — Text Cleaner

Design Patterns:
  - Pipeline Pattern: Each cleaning step is a pure function
  - Chain of Responsibility: Steps applied in sequence

Removes noise from transcripts and OCR output:
- Filler words, timestamps, [Music] tags
- Excessive whitespace, special characters
- YouTube auto-caption artifacts
"""

import logging
import re

logger = logging.getLogger(__name__)

# Filler words common in spoken spiritual discourse
FILLER_WORDS = {
    "um",
    "uh",
    "erm",
    "like",
    "you know",
    "i mean",
    "basically",
    "actually",
    "literally",
    "right",
    "so basically",
    "kind of",
    "sort of",
}

# Patterns to remove
NOISE_PATTERNS = [
    r"\[Music\]",
    r"\[Applause\]",
    r"\[Laughter\]",
    r"\[.*?\]",  # Any bracketed annotation
    r"\d{1,2}:\d{2}(:\d{2})?",  # Timestamps (1:23, 01:23:45)
    r">>\s*\w*:?",  # Speaker indicators (>> Speaker:)
    r"♪.*?♪",  # Music notation
    r"<[^>]+>",  # HTML tags (from some caption formats)
]


def clean_transcript(text: str) -> str:
    """
    Clean raw transcript text through a multi-step pipeline.

    Pipeline:
    1. Remove noise patterns (brackets, timestamps, HTML)
    2. Remove filler words
    3. Normalize whitespace
    4. Fix common OCR/caption artifacts

    Args:
        text: Raw transcript or OCR text

    Returns:
        Cleaned text ready for chunking
    """
    if not text:
        return ""

    original_len = len(text)

    # Step 1: Remove noise patterns
    for pattern in NOISE_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)

    # Step 2: Remove filler words (word-boundary aware)
    for filler in FILLER_WORDS:
        pattern = r"\b" + re.escape(filler) + r"\b"
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)

    # Step 3: Normalize whitespace (BEFORE artifact cleanup so that
    # punctuation rules below see single-spaced text)
    text = re.sub(r"\s+", " ", text)  # Multiple spaces → single
    text = re.sub(r"\n\s*\n", "\n", text)  # Multiple newlines → single
    text = text.strip()

    # Step 4: Fix common artifacts
    text = re.sub(r"\.{3,}", "...", text)  # Excessive dots
    text = re.sub(r"\s+([.,!?;:])", r"\1", text)  # Space before punctuation
    text = re.sub(r"([.!?])\s*([A-Z])", r"\1 \2", text)  # Sentence spacing

    cleaned_len = len(text)
    reduction = ((original_len - cleaned_len) / original_len * 100) if original_len > 0 else 0
    logger.debug(f"Cleaned text: {original_len} → {cleaned_len} chars ({reduction:.1f}% reduction)")

    return text


def clean_for_embedding(text: str) -> str:
    """
    Additional cleaning specifically for embedding quality.

    Removes very short segments and ensures meaningful content.
    """
    text = clean_transcript(text)

    # Robust sentence splitting: abbreviations and decimals are protected before
    # splitting on sentence-ending punctuation. This avoids NLTK/SpaCy deps.
    _abbreviation_periods = [
        r"Mr\.", r"Mrs\.", r"Ms\.", r"Dr\.", r"Prof\.", r"Sr\.", r"Jr\.",
        r"e\.g\.", r"i\.e\.", r"vs\.", r"etc\.", r"viz\.", r"Inc\.", r"Ltd\.",
        r"a\.m\.", r"p\.m\.", r"A\.M\.", r"P\.M\.", r"no\.", r"No\.",
        r"fig\.", r"Fig\.", r"et al\.", r"approx\.", r"ca\.", r"Co\.",
    ]

    # Temporarily replace period in abbreviations and decimal numbers
    _protected_text = text
    for abbr in _abbreviation_periods:
        _protected_text = re.sub(abbr, abbr.replace(".", "__DOT__"), _protected_text, flags=re.IGNORECASE)

    # Also protect decimal numbers like 3.14 or 1,000.50
    _protected_text = re.sub(r"(\d)\.(\d)", r"\1__DOT__\2", _protected_text)
    _protected_text = re.sub(r"(\d),(\d{3})", r"\1__COMMA__\2", _protected_text)

    # Split on sentence-ending punctuation followed by whitespace or end of string
    raw_sentences = re.split(r"(?<=[.!?])(?:\s+|$)", _protected_text)

    # Restore original characters and strip whitespace
    sentences = []
    for sentence in raw_sentences:
        sentence = sentence.replace("__DOT__", ".").replace("__COMMA__", ",")
        sentence = sentence.strip()
        if sentence:
            sentences.append(sentence)
    meaningful = [s.strip() for s in sentences if len(s.strip()) > 20]

    return " ".join(meaningful)
