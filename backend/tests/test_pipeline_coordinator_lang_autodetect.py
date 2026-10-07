"""Regression test for the Indic-script auto-detect fallback (defect 1a/1b).

``preferred_lang`` is ``chat_body.language or "en"`` -- "en" whenever a caller
omits the field, not only when it explicitly wants English. Every downstream
language gate (query-to-English translation before retrieval/CRAG grading,
and every response-side answer-translation gate) keys off this same string
via ``PipelineContext.is_indic``/``preferred_lang``. A caller that omits
``language`` but asks in native Indic script previously got retrieval run
against the untranslated native-script text and never had its answer
translated back. See root CLAUDE.md "Defect 1" and
``app/pipeline/pipeline_coordinator.py::_resolve_effective_preferred_lang``.
"""

from __future__ import annotations

from app.pipeline.pipeline_coordinator import _resolve_effective_preferred_lang

TELUGU_DEEKSHA_QUESTION = "దీక్ష (Deeksha) అంటే ఏమిటి? దాని వల్ల మెదడులో ఏమి మార్పులు వస్తాయి?"
KANNADA_SECRETS_QUESTION = "ನಾಲ್ಕು ಪವಿತ್ರ ರಹಸ್ಯಗಳು ಯಾವುವು?"


def test_native_script_question_is_detected_when_language_field_omitted():
    """golden_024 (Telugu) / golden_028 (Kannada): no explicit `language` field."""
    assert _resolve_effective_preferred_lang(TELUGU_DEEKSHA_QUESTION, "en") == "te"
    assert _resolve_effective_preferred_lang(KANNADA_SECRETS_QUESTION, "en") == "kn"
    # `chat_body.language` defaults to None, which chat.py turns into "en".
    assert _resolve_effective_preferred_lang(TELUGU_DEEKSHA_QUESTION, None) == "te"


def test_english_question_stays_english():
    assert _resolve_effective_preferred_lang("What is Ekam?", "en") == "en"


def test_explicit_client_language_choice_is_never_overridden():
    """A client that explicitly asked for Telugu output, but typed English this
    turn, keeps its explicit choice -- auto-detect only fills in a MISSING
    declaration, it never overrides one."""
    assert _resolve_effective_preferred_lang("Some english text", "te") == "te"


def test_unsupported_script_falls_back_to_client_value():
    """CJK/Cyrillic/etc. ('non_en' catch-all) has no translation-service
    language code, so the client's declared value (default 'en') is kept
    rather than passing an unusable code downstream."""
    assert _resolve_effective_preferred_lang("日本語のテキスト", "en") == "en"


if __name__ == "__main__":
    test_native_script_question_is_detected_when_language_field_omitted()
    test_english_question_stays_english()
    test_explicit_client_language_choice_is_never_overridden()
    test_unsupported_script_falls_back_to_client_value()
    print("pipeline_coordinator lang-autodetect self-check OK")
