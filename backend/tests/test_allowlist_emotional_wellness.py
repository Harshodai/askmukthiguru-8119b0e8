"""
P1-AI-6 — emotional wellness must run before the spiritual-domain allowlist.

A distressed seeker whose message contains a spiritual allowlist term (e.g.
"ekam", "preethaji") must still receive the Serene Mind wellness redirect.
The allowlist may only bypass *topic* checks — never the wellness redirect.

Tests pin:
  - Distress + spiritual term -> emotional wellness redirect (not allowlist pass).
  - Pure doctrinal query with spiritual term -> passes (not blocked).
"""

import asyncio

import pytest

from guardrails import LightweightGuardrails


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture
def guardrails():
    return LightweightGuardrails()


class TestAllowlistEmotionalWellness:
    def test_distress_with_spiritual_term_still_redirects(self, guardrails):
        """'I feel anxious about ekam' -> serene_mind wellness redirect, NOT allowlist pass."""
        result = run(guardrails.check_input("I feel anxious about ekam"))

        assert result["blocked"] is True
        assert "Emotional wellness" in result["reason"], (
            f"expected emotional wellness reason, got {result['reason']!r}"
        )
        assert result["redirect_to"] == "serene_mind", (
            f"expected serene_mind redirect, got {result['redirect_to']!r}"
        )
        assert "Serene Mind" in result["response"], (
            f"expected Serene Mind wellness response, got {result['response']!r}"
        )

    def test_distress_with_teacher_name_still_redirects(self, guardrails):
        """A second spiritual term variant — 'preethaji' — must behave identically."""
        result = run(guardrails.check_input("I have been feeling overwhelmed lately, even with preethaji's guidance"))

        assert result["blocked"] is True
        assert "Emotional wellness" in result["reason"], (
            f"expected emotional wellness reason, got {result['reason']!r}"
        )
        assert result["redirect_to"] == "serene_mind"

    def test_doctrinal_query_with_spiritual_term_passes(self, guardrails):
        """'Tell me about ekam' (no distress) -> not blocked (allowlist pass)."""
        result = run(guardrails.check_input("Tell me about ekam and the beautiful state"))

        assert result["blocked"] is False
        assert result["reason"] is None
        assert result["redirect_to"] is None
