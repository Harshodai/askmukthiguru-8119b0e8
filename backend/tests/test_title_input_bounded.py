"""The anonymous title endpoint must bound what it forwards to the LLM.

POST /api/chat/title takes get_optional_user, so anonymous callers reach it. It
is rate-limited by request count (20/minute) but sits OUTSIDE the anonymous
chat quota, and its `first_message` field was an unbounded `str` that went
straight into the prompt. One caller could therefore bill 20 LLM calls a minute
on arbitrarily large inputs — a cost-amplification vector, not an isolation
break.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.chat import _TITLE_INPUT_MAX_CHARS, TitleRequest


def test_normal_message_is_accepted():
    body = TitleRequest(first_message="What is the Beautiful State?")
    assert body.first_message


def test_oversized_message_is_rejected_at_the_boundary():
    with pytest.raises(ValidationError):
        TitleRequest(first_message="x" * (_TITLE_INPUT_MAX_CHARS + 1))


def test_bound_is_small_enough_to_matter():
    """A bound larger than a normal chat turn would not constrain cost."""
    assert _TITLE_INPUT_MAX_CHARS <= 4000


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
