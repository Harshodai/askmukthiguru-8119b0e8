"""Whisper decode hardening shared by every direct transcribe() call site.

The vocabulary is the doctrine glossary from ``services.doctrine_terms`` (the
single source of canonical spellings), never a second hand-kept list.
"""

from __future__ import annotations

from typing import Any

from services.doctrine_terms import get_whisper_initial_prompt

# Whisper keeps only the last ~224 tokens of a prompt, silently dropping the
# front of the glossary, which is where the teachers' names are. Cap by terms
# (same cap as scripts/ingestion/parallel_corpus_extractor.py).
WHISPER_PROMPT_MAX_TERMS = 30


def _capped_glossary_prompt(max_terms: int = WHISPER_PROMPT_MAX_TERMS) -> str:
    prefix, sep, terms_str = get_whisper_initial_prompt().partition(": ")
    if not sep:
        return prefix
    terms = [t.strip() for t in terms_str.rstrip(".").split(",") if t.strip()]
    return f"{prefix}: {', '.join(terms[:max_terms])}."


SACRED_VOCABULARY_PROMPT: str = _capped_glossary_prompt()

# condition_on_previous_text=False stops one hallucinated window from being fed
# into the next as context (the hallucination cascade).
WHISPER_HARDENING_KWARGS: dict[str, Any] = {
    "initial_prompt": SACRED_VOCABULARY_PROMPT,
    "condition_on_previous_text": False,
}


if __name__ == "__main__":
    assert WHISPER_HARDENING_KWARGS["condition_on_previous_text"] is False
    assert "Sri Preethaji" in SACRED_VOCABULARY_PROMPT
    print("speech_config self-check ok")
