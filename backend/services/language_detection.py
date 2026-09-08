"""Unified language detection with Hinglish support.

Single detect_language() used by serene_mind_engine, metadata_extractor,
backfill_language, and the generation pipeline.
"""

from __future__ import annotations

import re
from typing import Optional

SCRIPT_RANGES: dict[str, tuple[str, str]] = {
    "Devanagari": ("\u0900", "\u097f"),
    "Tamil": ("\u0b80", "\u0bff"),
    "Telugu": ("\u0c00", "\u0c7f"),
    "Kannada": ("\u0c80", "\u0cff"),
    "Bengali": ("\u0980", "\u09ff"),
    "Gujarati": ("\u0a80", "\u0aff"),
    "Gurmukhi": ("\u0a00", "\u0a7f"),
    "Malayalam": ("\u0d00", "\u0d7f"),
    "Oriya": ("\u0b00", "\u0b7f"),
    "Arabic": ("\u0600", "\u06ff"),
}

SCRIPT_TO_LANG: dict[str, str] = {
    "Devanagari": "hi",
    "Tamil": "ta",
    "Telugu": "te",
    "Kannada": "kn",
    "Bengali": "bn",
    "Gujarati": "gu",
    "Gurmukhi": "pa",
    "Malayalam": "ml",
    "Oriya": "or",
    "Arabic": "ur",
}

HINDU_WORDS: list[str] = [
    "mujhe", "kaise", "karni", "hai", "nahi", "acha", "achha", "theek",
    "bilkul", "kar", "ho", "se", "mein", "main", "mera", "meri", "tere",
    "tum", "aap", "kya", "yeh", "woh", "ek", "do", "teen",
    "aur", "bhi", "par", "pe", "ko", "ki", "ka", "ke",
    "ke liye", "ke baare mein", "karna", "hota", "hain", "tha", "thi",
    "the", "hoga", "hogi", "honge",
    "bol", "bolo", "bata", "sun", "dekh", "le", "ja", "aa",
    "piya", "raha", "rahi", "rahe", "gaya", "gayi", "gaye",
    "kyun", "kyunki", "agar", "lekin", "haan", "hoon", "bas", "yaar",
    "bhai", "dost", "dil", "mann", "zindagi", "khush", "dukhi", "pyaar",
    "abhi", "kal", "aaj", "subah", "raat", "din", "waqt", "ghar",
    "kaun", "kab", "kahan", "kyun", "matlab", "sach", "galat",
]

_HINDU_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in HINDU_WORDS) + r")\b",
    re.IGNORECASE,
)

_HINGLISH_THRESHOLD = 0.3


def detect_language(
    text: str,
    user_preference: Optional[str] = None,
) -> dict:
    """Detect language, confidence, and whether text is code-switched.

    Args:
        text: Input text to classify.
        user_preference: User's preferred language code (e.g. "hi", "te").
            Used as tiebreaker when script-based confidence is low.

    Returns:
        dict with keys: language, confidence, is_code_switched.
    """
    if not text or not text.strip():
        return {"language": "en", "confidence": 0.3, "is_code_switched": False}

    scripts = _detect_scripts(text)

    for script_name, lang_code in SCRIPT_TO_LANG.items():
        if script_name in scripts:
            return {
                "language": lang_code,
                "confidence": 0.95,
                "is_code_switched": False,
            }

    non_latin = any(ord(c) > 0x02FF and not ("\u00c0" <= c <= "\u024f") for c in text)
    if non_latin:
        return {"language": "en", "confidence": 0.5, "is_code_switched": False}

    hinglish_result = _check_hinglish(text)
    if hinglish_result:
        return hinglish_result

    if user_preference and user_preference not in ("en", ""):
        return {
            "language": user_preference,
            "confidence": 0.4,
            "is_code_switched": False,
        }

    return {"language": "en", "confidence": 0.8, "is_code_switched": False}


def _detect_scripts(text: str) -> list[str]:
    """Return list of Unicode script names found in text."""
    found: list[str] = []
    for script_name, (start, end) in SCRIPT_RANGES.items():
        if any(start <= c <= end for c in text):
            found.append(script_name)
    if not found:
        found.append("Latin")
    return found


def _check_hinglish(text: str) -> Optional[dict]:
    """Check if text is Hinglish (Latin-script Hindi code-mix).

    Returns dict if >30% of words match common Hindi words, else None.
    """
    words = re.findall(r"[a-zA-Z]+", text.lower())
    if not words:
        return None
    matches = len(_HINDU_PATTERN.findall(text.lower()))
    ratio = matches / len(words)
    if ratio >= _HINGLISH_THRESHOLD:
        confidence = min(0.5 + ratio * 0.5, 0.9)
        return {
            "language": "hi",
            "confidence": round(confidence, 2),
            "is_code_switched": True,
        }
    return None


if __name__ == "__main__":
    test_cases = [
        ("नमस्ते, आप कैसे हैं?", None),
        ("Mujhe meditation kaise karni chahiye?", None),
        ("What is the meaning of stillness?", None),
        ("Aap kaise ho? Main theek hoon", None),
        ("Hello how are you", None),
        ("", None),
        ("meditation karna chahta hoon", "en"),
        ("meditation karna chahta hoon", "hi"),
    ]
    for text, pref in test_cases:
        result = detect_language(text, user_preference=pref)
        print(f"  {text!r:55s} -> {result}")
