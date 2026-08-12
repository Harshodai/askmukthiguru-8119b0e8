"""Regression coverage for Roman-script Indian language routing."""
from services.language_router import LanguageCode, LanguageRouter


def test_hinglish_detected_from_multiple_romanised_hindi_tokens() -> None:
    result = LanguageRouter().detect("mujhe kya karna hai when I feel stressed")

    assert result.primary == LanguageCode.HINGLISH
    assert result.is_codemixed is True


def test_tanglish_detected_from_multiple_romanised_tamil_tokens() -> None:
    result = LanguageRouter().detect("enna epdi peaceful ah irukka mudiyum")

    assert result.primary == LanguageCode.TANGLISH
    assert result.is_codemixed is True


def test_single_sanskrit_term_does_not_imply_hinglish() -> None:
    result = LanguageRouter().detect("What does karma mean in this teaching?")

    assert result.primary == LanguageCode.EN
    assert result.is_codemixed is False
