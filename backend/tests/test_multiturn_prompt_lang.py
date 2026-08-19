"""P1-AI-14: MULTI_TURN_PROMPT carries the detected-language directive.

The multi-turn prompt must use the same `lang_suffix` mechanism as the
single-turn system prompt (LanguageRouter.get_system_prompt_suffix), so
multi-turn replies in hi/te/ta/mr chats do not drift back to English.
"""

from __future__ import annotations

from rag.prompts.system import MULTI_TURN_PROMPT
from services.language_router import LanguageCode, LanguageRouter


def test_multiturn_prompt_has_lang_suffix_placeholder():
    """The prompt must declare the {lang_suffix} slot it is formatted with."""
    assert "{lang_suffix}" in MULTI_TURN_PROMPT


def test_multiturn_prompt_lang_directive_tamil():
    """Formatting with the Tamil suffix embeds the Tamil directive."""
    lang_suffix = LanguageRouter().get_system_prompt_suffix(LanguageCode.TA)
    assert lang_suffix  # non-empty for Tamil
    rendered = MULTI_TURN_PROMPT.format(
        history="User: வணக்கம்",
        lang_suffix=lang_suffix,
    )
    assert lang_suffix in rendered
    assert "தமிழில் பதிலளிக்கவும்" in rendered


def test_multiturn_prompt_lang_directive_hindi():
    """Formatting with the Hindi suffix embeds the Hindi directive."""
    lang_suffix = LanguageRouter().get_system_prompt_suffix(LanguageCode.HI)
    assert lang_suffix  # non-empty for Hindi
    rendered = MULTI_TURN_PROMPT.format(
        history="User: नमस्ते",
        lang_suffix=lang_suffix,
    )
    assert lang_suffix in rendered
    assert "हिंदी में जवाब दें" in rendered


def test_multiturn_prompt_defaults_to_no_directive_for_english():
    """English (the router default) adds no directive — matches single-turn."""
    lang_suffix = LanguageRouter().get_system_prompt_suffix(LanguageCode.EN)
    assert lang_suffix == ""
    rendered = MULTI_TURN_PROMPT.format(
        history="User: hello",
        lang_suffix=lang_suffix,
    )
    assert "முக்கியம்" not in rendered
    assert "महत्वपूर्ण" not in rendered
