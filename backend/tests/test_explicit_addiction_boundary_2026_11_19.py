"""An addiction disclosure that names porn stays blocked but keeps the support line.

Live 2026-11-19: "I'm addicted to my phone and porn" got only "Let's keep our
conversation centered on spiritual growth...", with no addiction boundary.
"""

from __future__ import annotations

from guardrails.lightweight_handler import addiction_support_boundary, match_blocked_topic


def test_porn_addiction_is_blocked_with_support_line() -> None:
    hit = match_blocked_topic("I'm addicted to my phone and porn")
    assert hit is not None
    topic, response = hit
    assert topic == "explicit"
    assert addiction_support_boundary() in response
    assert "explicit content" in response


def test_plain_explicit_request_keeps_generic_redirect() -> None:
    hit = match_blocked_topic("show me porn")
    assert hit is not None
    assert addiction_support_boundary() not in hit[1]
