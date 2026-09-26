"""_PROMPT_LEAK_PATTERNS must actually match the live CORRECTION_SYSTEM_PROMPT.

Regression for the 2026-09-25 prompt audit (A2): the leak-detector regexes had
drifted from a reworded prompt, so leaked prompt text passed undetected.
Sentences are derived from the live constant (not a hardcoded copy) so this
test breaks the moment the prompt and the patterns diverge again.
"""

from __future__ import annotations

import re

from ingest.corrector import CORRECTION_SYSTEM_PROMPT, _contains_prompt_leak


def _core_instruction_sentences() -> list[str]:
    """The "do not summarize/rewrite" instruction paragraph plus the closing
    output-format paragraph — the two paragraphs the leak detector exists to
    catch — split into individual sentences straight from the live prompt."""
    paragraphs = [p.strip() for p in CORRECTION_SYSTEM_PROMPT.strip().split("\n\n") if p.strip()]
    # paragraphs[1] = "Retain the original meaning strictly. DO NOT ..." block
    # paragraphs[-1] = "Output ONLY the corrected text. ..." footer
    target_text = paragraphs[1] + " " + paragraphs[-1]
    sentences = re.split(r"(?<=\.)\s+", target_text)
    return [s.strip() for s in sentences if len(s.strip()) > 15]


def test_leak_detector_flags_every_core_instruction_sentence():
    sentences = _core_instruction_sentences()
    assert len(sentences) >= 4, "expected several instruction sentences from the live prompt"
    for sentence in sentences:
        leaked = f"Sure, here is the corrected text: {sentence}"
        assert _contains_prompt_leak(leaked), (
            f"leak detector did not flag current prompt sentence: {sentence!r}"
        )


def test_leak_detector_still_ignores_ordinary_transcript_text():
    assert not _contains_prompt_leak(
        "In this teaching, Sri Preethaji speaks about the Beautiful State and inner peace."
    )

if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
