"""An OKF quotation must be speech, not the extractor's own summary in quotes.

Found live 2026-09-17: 26 of 488 quotations in the OKF bundle were the entry's
own machine-written ## Summary repeated verbatim inside quotation marks, and 5
of those were attributed to "Sri Preethaji" by name. Every OKF entry is injected
verbatim into answers, so promoting one fabricates speech and attaches a living
teacher's name to it — the worst output this product can produce.

All 26 were in memory/okf/staging/ (unreviewed); the 43 live entries were clean.
The staging filter caught them. This gate makes sure review cannot let one slip
through even by accident.
"""

import pytest

from services.okf_quality_filter import OKFQualityFilter

_SUMMARY = (
    "Addictions are a cycle of pleasure leading to suffering, with underlying "
    "roots in the desire to escape an inner state of disconnection."
)


def _entry(body: str) -> dict:
    return {"type": "teaching", "title": "T", "source": "YouTube https://x", "body": body}


def test_quote_restating_its_own_summary_is_rejected():
    body = f'## Summary\n{_SUMMARY}\n\n## Quotes\n> "{_SUMMARY}" — Sri Preethaji\n'
    ok, reason = OKFQualityFilter.validate_entry(_entry(body))
    assert ok is False
    assert "Fabricated quote" in reason
    # The attribution must appear, because naming a living teacher is what makes
    # this severe rather than merely sloppy.
    assert "Sri Preethaji" in reason


def test_fabricated_quote_rejected_even_when_unattributed():
    body = f'## Summary\n{_SUMMARY}\n\n## Quotes\n> "{_SUMMARY}"\n'
    ok, reason = OKFQualityFilter.validate_entry(_entry(body))
    assert ok is False and "Fabricated quote" in reason


def test_repunctuated_copy_is_still_caught():
    """The extractor re-punctuates between the two copies, so exact matching misses."""
    restated = _SUMMARY.replace(",", "").replace(".", "").upper()
    body = f'## Summary\n{_SUMMARY}\n\n## Quotes\n> "{restated}" — Sri Krishnaji\n'
    ok, reason = OKFQualityFilter.validate_entry(_entry(body))
    assert ok is False and "Fabricated quote" in reason


def test_genuine_quote_not_in_summary_is_allowed():
    body = (
        f"## Summary\n{_SUMMARY}\n\n## Quotes\n"
        '> "When Sri Krishnaji and I created the Soul Sync meditation years ago, '
        'we did it with a sacred intention to offer humanity this gift."\n'
    )
    ok, reason = OKFQualityFilter.validate_entry(_entry(body))
    assert ok is True, reason


def test_short_shared_line_is_not_treated_as_fabricated():
    """A real teaching can be one short line the summary also uses — must not trip."""
    short = "Suffering is a choice."
    body = f'## Summary\n{short} {_SUMMARY}\n\n## Quotes\n> "{short}" — Sri Preethaji\n'
    ok, reason = OKFQualityFilter.validate_entry(_entry(body))
    assert ok is True, reason


def test_entry_without_summary_section_is_unaffected():
    body = '## Quotes\n> "A teaching long enough to clear the minimum body length gate here."\n' + (
        "Filler prose to clear the 100-character minimum body length requirement. " * 3
    )
    ok, reason = OKFQualityFilter.validate_entry(_entry(body))
    assert ok is True, reason


def test_quote_cut_off_mid_sentence_is_rejected():
    """127 live entries carried one of these on 2026-09-17.

    The extractor slices a fixed character count out of a transcript, so quotes
    stop mid-word ("...step away from all this tumul"). The words are genuinely
    the teacher's, which makes this subtler than fabrication — but quotation
    marks around half a sentence still misquote a living teacher.
    """
    body = (
        f"## Summary\n{_SUMMARY}\n\n## Quotes\n"
        '> "Diwali is a reminder for you to step away from all this tumul"\n'
    )
    ok, reason = OKFQualityFilter.validate_entry(_entry(body))
    assert ok is False
    assert "Truncated quote" in reason


def test_complete_quote_ending_in_terminator_is_allowed():
    body = (
        f"## Summary\n{_SUMMARY}\n\n## Quotes\n"
        '> "Diwali is a reminder for you to step away from all this tumult."\n'
    )
    ok, reason = OKFQualityFilter.validate_entry(_entry(body))
    assert ok is True, reason


def test_short_quoted_term_is_not_treated_as_truncated():
    """A glossed term is legitimately quoted without terminal punctuation."""
    body = f'## Summary\n{_SUMMARY}\n\n## Quotes\n> "the Beautiful State"\n'
    ok, reason = OKFQualityFilter.validate_entry(_entry(body))
    assert ok is True, reason


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
