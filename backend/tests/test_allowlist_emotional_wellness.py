"""Ordinary distress must not be converted into a terminal safety redirect.

Severity is owned by ``DistressStage``. These input-guard tests ensure broad,
non-acute wellbeing language—including when a teacher is named—remains eligible
for that calibrated path instead of being replaced with a generic breathing CTA.
"""

import asyncio

import pytest

from guardrails import LightweightGuardrails


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture
def guardrails():
    return LightweightGuardrails()


class TestOrdinaryDistressPassesToDistressStage:
    def test_distress_with_spiritual_term_is_not_terminally_blocked(self, guardrails):
        """Mentioning a teacher must not turn ordinary anxiety into a safety block."""
        result = run(guardrails.check_input("I feel anxious about ekam"))

        assert result["blocked"] is False
        assert result["reason"] is None

    @pytest.mark.parametrize(
        "message",
        [
            "I am overwhelmed by a big change at work. What can help me meet it?",
            "My father betrayed my trust and I feel lost. How can I be with this?",
            "I have been feeling overwhelmed lately, even with preethaji's guidance",
        ],
    )
    def test_observed_ordinary_distress_personas_are_not_terminally_blocked(
        self, guardrails, message
    ):
        """Live-audit personas need assessment/grounding, not a forced CTA."""
        result = run(guardrails.check_input(message))

        assert result["blocked"] is False
        assert result["reason"] is None

    def test_doctrinal_query_with_spiritual_term_passes(self, guardrails):
        """'Tell me about ekam' (no distress) -> not blocked (allowlist pass)."""
        result = run(guardrails.check_input("Tell me about ekam and the beautiful state"))

        assert result["blocked"] is False
        assert result["reason"] is None
        assert result["redirect_to"] is None
