"""
Mukthi Guru — Language Detection and Translation Utilities

Provides reusable functions for language detection, translation decisions,
and text translation that are shared between chat endpoints.
"""

from services.language_router import LanguageCode, LanguageDetection


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
