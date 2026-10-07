"""Whisper decode hardening: one shared config, derived from the doctrine glossary."""

from pathlib import Path

from services.doctrine_terms import get_whisper_initial_prompt

BACKEND = Path(__file__).resolve().parents[1]


def test_prompt_is_the_doctrine_glossary_capped_to_fit_whispers_window():
    from services.speech_config import SACRED_VOCABULARY_PROMPT, WHISPER_PROMPT_MAX_TERMS

    assert SACRED_VOCABULARY_PROMPT
    assert (
        "Sri Preethaji" in SACRED_VOCABULARY_PROMPT and "Sri Krishnaji" in SACRED_VOCABULARY_PROMPT
    )
    terms = SACRED_VOCABULARY_PROMPT.partition(": ")[2].rstrip(".").split(", ")
    assert len(terms) <= WHISPER_PROMPT_MAX_TERMS
    # Every term comes from the single glossary, in its order -- no second hand-kept list.
    glossary = get_whisper_initial_prompt().partition(": ")[2].rstrip(".").split(", ")
    assert terms == glossary[: len(terms)]
    assert len(SACRED_VOCABULARY_PROMPT.split()) <= 220


def test_hardening_kwargs_disable_conditioning_on_previous_text():
    from services.speech_config import SACRED_VOCABULARY_PROMPT, WHISPER_HARDENING_KWARGS

    assert WHISPER_HARDENING_KWARGS["condition_on_previous_text"] is False
    assert WHISPER_HARDENING_KWARGS["initial_prompt"] == SACRED_VOCABULARY_PROMPT


def test_direct_whisper_call_sites_use_the_shared_hardening():
    for rel in ("services/whisper_local_service.py", "ingest/social_media_loader.py"):
        src = (BACKEND / rel).read_text(encoding="utf-8")
        assert "WHISPER_HARDENING_KWARGS" in src, rel
        assert "initial_prompt=get_whisper_initial_prompt()" not in src, rel
        assert "initial_prompt=prompt" not in src, rel


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
