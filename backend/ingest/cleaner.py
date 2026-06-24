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

from rag.nodes.utils import DOCTRINE_SYNONYMS

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

# Captions that are purely non-speech markers
MUSIC_CAPTION_PATTERNS = [
    r"\b(music|bgm|background music|instrumental)\b",
    r"\b(singing|song playing)\b",
    r"\[.*?(music|song|applause|laughter).*?\]",
]

# Repeated caption artifacts (same token repeated 3+ times, e.g. timestamp spam)
_REPEATED_TOKEN_RE = re.compile(r"(\S+(?:\s+\S+){0,3})(?:\s+\1){2,}", re.IGNORECASE)


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

    # Step 1b: Remove music/non-speech caption markers
    for pattern in MUSIC_CAPTION_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)

    # Step 1c: Collapse repeated tokens (e.g. spammy repeated captions/timestamps)
    text = _REPEATED_TOKEN_RE.sub(r"\1", text)

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

    # Step 5: Normalize spiritual terminology so different forms map to a canonical term
    text = normalize_spiritual_terms(text)

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


def normalize_spiritual_terms(text: str) -> str:
    """
    Normalize alternate spellings/forms of spiritual terms to canonical forms.

    Uses the project's DOCTRINE_SYNONYMS map so that queries and indexed chunks
    share a common vocabulary, improving retrieval recall.

    Example:
        "preethaji and krishna ji spoke about dhyan" ->
        "sri preethaji and sri krishnaji spoke about meditation"

    Only whole-word replacements are performed to avoid accidental overwrites.
    """
    if not text:
        return ""

    # Build a mapping from each alternate form to the canonical term.
    # Prefer longer alternates first to avoid partial replacements.
    replacements: list[tuple[str, str]] = []
    for canonical, alternates in DOCTRINE_SYNONYMS.items():
        for alt in alternates:
            if alt != canonical:
                replacements.append((alt, canonical))

    # Sort by length descending so multi-word phrases are matched before sub-phrases
    replacements.sort(key=lambda pair: len(pair[0]), reverse=True)

    # Replace alternates with canonical forms, but be careful not to replace an
    # already-canonical term with itself. We use word-boundary aware matching.
    for alt, canonical in replacements:
        pattern = r"(?i)\b" + re.escape(alt) + r"\b"
        text = re.sub(pattern, canonical, text)

    return text
