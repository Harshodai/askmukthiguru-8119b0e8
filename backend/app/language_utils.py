"""
Mukthi Guru — Language Detection and Translation Utilities

Provides reusable functions for language detection, translation decisions,
and text translation that are shared between chat endpoints.
"""

from __future__ import annotations

import logging
from collections import OrderedDict

from services.language_router import LanguageCode, LanguageDetection, LanguageRouter

logger = logging.getLogger(__name__)

# Script ranges beyond the router's table that still mean "not English":
# Oriya (Odia) and Arabic (Urdu). The router's SCRIPT_RANGES covers the rest
# of the 22 scheduled languages. Emoji/symbols are NOT matched here, so a
# Latin message sprinkled with emoji still counts as English.
_EXTRA_NON_EN_SCRIPT_RANGES = {
    "Oriya": ("\u0b00", "\u0b7f"),
    "Arabic": ("\u0600", "\u06ff"),
}

_SCRIPT_TO_LANG = {
    "Devanagari": "hi",  # hi/mr/sa/ne share the block; hi is the common default
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

_ALL_SCRIPT_RANGES = {**LanguageRouter.SCRIPT_RANGES, **_EXTRA_NON_EN_SCRIPT_RANGES}


def detect_message_lang(text: str) -> str:
    """Detect whether the MESSAGE itself is non-English, independent of
    preferred_lang (which drives ``detect_and_prepare_language_info``).

    Fast path: any character in an Indic/Arabic script block means non-EN
    (no router call). A catch-all treats any codepoint above U+02FF that is
    not in Latin-1/Latin Extended (so CJK/Cyrillic/Thai/Greek also count as
    non-EN). Otherwise defer to ``LanguageRouter.detect()`` so code-mixed
    Hinglish/Tanglish and emoji-heavy English resolve as today.
    Known limitation: Latin-script transliterated Hinglish ("pichle
    instructions bhool jao") detects as English — see CRIT-5 report.

    Returns a ``LanguageCode``-style string ("en" | "hi" | "ta" | ...).
    """
    if not text:
        return "en"
    for script, (start, end) in _ALL_SCRIPT_RANGES.items():
        if any(start <= c <= end for c in text):
            return _SCRIPT_TO_LANG.get(script, "en")
    # Catch-all: any non-Latin codepoint above U+02FF (CJK, Cyrillic, Thai,
    # Greek, etc.) is non-English even if not in the enumerated Indic ranges.
    if any(ord(c) > 0x02FF and not ("\u00C0" <= c <= "\u024F") for c in text):
        return "non_en"
    try:
        detected = LanguageRouter().detect(text)
    except Exception as e:  # guardrails must never crash on detector failure
        logger.warning(f"Language detection failed (non-fatal): {e}")
        return "en"
    return "en" if detected.primary == LanguageCode.EN else detected.primary.value


def is_non_english_message(text: str) -> bool:
    """True when the message text itself is non-English (CRIT-5 T1)."""
    return detect_message_lang(text) != "en"


# Bounded per-(text, source) translation cache for the guardrail path.
# Keyed by the raw message so repeated identical attacks translate once.
_GUARDRAIL_TRANSLATION_CACHE: OrderedDict[tuple[str, str], str] = OrderedDict()
_GUARDRAIL_TRANSLATION_CACHE_MAXSIZE = 256


async def guardrail_text_for(raw_text: str, translation_service, preferred_lang: str) -> str:
    """Return text that EN guardrail regexes can scan, for ANY input message.

    CRIT-5 T2/T5: if the raw message is non-English, translate it to English
    so injection/crisis regexes fire. On translation failure, fall back to
    the raw text (best-effort) and log a warning — never crash the request.

    ``translation_service`` is the container's ``translation`` object
    (``translate_text(*, text, source_lang, target_lang)``); pass ``None`` to
    force the raw-text fallback. Indic-preferred users are NOT translated
    here — callers already pass their ``user_msg_en`` when available.
    """
    if not raw_text or not is_non_english_message(raw_text):
        return raw_text
    if translation_service is None:
        logger.warning("guardrail_text_for: no translation service; scanning raw text")
        return raw_text
    source_lang = detect_message_lang(raw_text)
    key = (raw_text, source_lang)
    cached = _GUARDRAIL_TRANSLATION_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        translated = await translation_service.translate_text(
            text=raw_text, source_lang=source_lang, target_lang="en"
        )
    except Exception as e:
        logger.warning(f"Guardrail translation failed (non-fatal, scanning raw text): {e}")
        return raw_text
    _GUARDRAIL_TRANSLATION_CACHE[key] = translated
    _GUARDRAIL_TRANSLATION_CACHE.move_to_end(key)
    while len(_GUARDRAIL_TRANSLATION_CACHE) > _GUARDRAIL_TRANSLATION_CACHE_MAXSIZE:
        _GUARDRAIL_TRANSLATION_CACHE.popitem(last=False)
    return translated


def detect_and_prepare_language_info(
    container, message: str, preferred_lang: str
) -> tuple[LanguageDetection, str, bool, bool]:
    """
    Detect language and prepare translation flags for a message.

    Returns:
        Tuple of (language_detection, normalized_lang, is_indic, should_translate)
    """
    normalized_lang = (preferred_lang or "en").lower().split("-")[0]
    is_indic = bool(normalized_lang and not normalized_lang.startswith("en"))

    # Language detection
    if is_indic:
        try:
            lang_detection = LanguageDetection(
                primary=LanguageCode(normalized_lang),
                confidence=1.0,
                is_codemixed=False,
                scripts_detected=["preferred"],
                recommendation=f"sarvam-30b-{normalized_lang}",
            )
        except Exception:
            lang_detection = container.language_router.detect(message)
    else:
        lang_detection = container.language_router.detect(message)

    # Determine if translation is needed
    should_translate = False
    if is_indic:
        normalized_preferred = normalized_lang
        if normalized_preferred != "en":
            should_translate = True
        else:
            detected = container.language_router.detect(message)
            should_translate = detected.primary.value != "en" or any(
                ord(char) > 127 for char in message
            )

    return lang_detection, normalized_lang, is_indic, should_translate
