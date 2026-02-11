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

import re
import logging

logger = logging.getLogger(__name__)

# Filler words common in spoken spiritual discourse
FILLER_WORDS = {
    "um", "uh", "erm", "like", "you know", "i mean",
    "basically", "actually", "literally", "right",
    "so basically", "kind of", "sort of",
}

# Patterns to remove
NOISE_PATTERNS = [
    r'\[Music\]',
    r'\[Applause\]',
    r'\[Laughter\]',
    r'\[.*?\]',                     # Any bracketed annotation
    r'\d{1,2}:\d{2}(:\d{2})?',     # Timestamps (1:23, 01:23:45)
    r'>>\s*\w*:?',                   # Speaker indicators (>> Speaker:)
    r'♪.*?♪',                       # Music notation
    r'<[^>]+>',                     # HTML tags (from some caption formats)
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
        text = re.sub(pattern, ' ', text, flags=re.IGNORECASE)

    # Step 2: Remove filler words (word-boundary aware)
    for filler in FILLER_WORDS:
        pattern = r'\b' + re.escape(filler) + r'\b'
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)

    # Step 3: Normalize whitespace (BEFORE artifact cleanup so that
    # punctuation rules below see single-spaced text)
    text = re.sub(r'\s+', ' ', text)       # Multiple spaces → single
    text = re.sub(r'\n\s*\n', '\n', text)  # Multiple newlines → single
    text = text.strip()

    # Step 4: Fix common artifacts
    text = re.sub(r'\.{3,}', '...', text)  # Excessive dots
    text = re.sub(r'\s+([.,!?;:])', r'\1', text)  # Space before punctuation
    text = re.sub(r'([.!?])\s*([A-Z])', r'\1 \2', text)  # Sentence spacing

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
    
    # Remove segments that are too short to be meaningful.
    # NOTE: This regex splits on sentence-ending punctuation (., !, ?)
    # followed by whitespace. It does NOT handle abbreviations (e.g.,
    # "Dr.", "e.g.") or decimals — those will cause false splits.
    # TODO: For production accuracy, replace with nltk.sent_tokenize
    # or spaCy's sentence segmenter (e.g., `nlp(text).sents`).
    sentences = re.split(r'(?<=[.!?])\s+', text)
    meaningful = [s.strip() for s in sentences if len(s.strip()) > 20]
    
    return ' '.join(meaningful)
