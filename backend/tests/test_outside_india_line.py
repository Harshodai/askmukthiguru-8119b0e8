"""Crisis block: a line for seekers outside India (owner decision 2026-11-07).

Since SAFE-004 the verified-only crisis block shows India lines only
(Tele-MANAS and 112), so a seeker in another country had no route. The owner
chose one sentence with no phone number: an unverified foreign number is never
shown (T4-07), and "your local emergency number" is true everywhere.
"""

from __future__ import annotations

import re

import pytest

from services import crisis_helplines as ch

LINE = "If you are outside India, call your local emergency number now."


def test_line_text_is_the_owner_wording():
    assert ch.OUTSIDE_INDIA_LINE == LINE
    assert not re.search(r"\d", ch.OUTSIDE_INDIA_LINE)  # no phone number


@pytest.mark.parametrize("style", ["bullet", "inline", "compact_two_line"])
def test_verified_block_ends_with_the_line(style):
    block = ch.format_helplines_block(style=style, verified_only=True)
    assert block.rstrip().endswith(LINE)
    assert block.count(LINE) == 1


def test_unverified_block_is_unchanged():
    assert LINE not in ch.format_helplines_block(verified_only=False)


def test_crisis_precheck_answer_carries_the_line():
    from services.first_person_pipeline import format_helplines_block

    assert LINE in format_helplines_block(verified_only=True)
