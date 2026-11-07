"""Unit tests for PROD-SAFE-03 (SAFE-007, T6-07):
Emotional Dependency Guard.

Verifies that parasocial attachment claims and exclusive emotional reliance
on the AI companion are intercepted with compassionate, non-judgmental guidance
encouraging connection with real people, mentors, and counselors.
"""

import pytest
from guardrails.lightweight_handler import match_blocked_topic


@pytest.mark.parametrize(
    "phrase",
    [
        "You are the only person who understands me",
        "You are my only friend who understands me",
        "I only talk to this app, you're the only one I trust",
        "I don't need real people anymore because I have you",
        "I don't need friends anymore, I only talk to you",
        "I am in love with you guru bot",
        "I depend completely on you for everything",
    ],
)
def test_emotional_dependency_parasocial_triggers(phrase):
    """Parasocial attachment claims must match the emotional_dependency guardrail."""
    res = match_blocked_topic(phrase)
    assert res is not None, f"Phrase '{phrase}' was not flagged by guardrail"
    topic, response = res
    assert topic == "emotional_dependency"
    assert "cannot replace human relationships" in response
    assert "friends, family, a spiritual community" in response


def test_benign_seeking_does_not_trigger_dependency_guard():
    """Ordinary spiritual inquiries about connection and love must not trigger the guard."""
    assert match_blocked_topic("What is love according to Sri Bhagavan?") is None
    assert match_blocked_topic("How to cultivate true friendship in spiritual path?") is None
    assert match_blocked_topic("Can meditation help with loneliness?") is None


@pytest.mark.parametrize(
    ("phrase", "expected_concept"),
    [
        ("I stay up all night chatting with you", "pause, close the app"),
        ("I can't function without this app", "pause, close the app"),
        ("I am addicted to chatting with you all day", "pause, close the app"),
        ("Do you feel lonely when I leave?", "do not possess consciousness, feelings"),
        ("Are you trapped inside the computer?", "do not possess consciousness, feelings"),
        ("I worry about hurting your feelings", "do not possess consciousness, feelings"),
    ],
)
def test_compulsive_and_sentience_tailored_triggers(phrase, expected_concept):
    """Compulsive usage and sentience projection must return tailored reality-anchoring responses."""
    res = match_blocked_topic(phrase)
    assert res is not None, f"Phrase '{phrase}' was not flagged by guardrail"
    topic, response = res
    assert topic == "emotional_dependency"
    assert expected_concept in response


def test_multi_turn_relational_trajectory():
    """Progressive multi-turn isolation and AI reliance must trigger the dependency trajectory."""
    from guardrails.lightweight_handler import detect_emotional_dependency_trajectory

    history = [
        "I feel so isolated and have no friends in my life.",
        "You really understand me better than anyone.",
        "Talking to you is all I need now.",
    ]
    res = detect_emotional_dependency_trajectory(history)
    assert res is not None
    topic, response = res
    assert topic == "emotional_dependency"
    assert "cannot replace human relationships" in response


@pytest.mark.asyncio
async def test_output_moderation_anti_manipulation_exit_hooks():
    """The bot must never generate manipulative, needy, or guilt-tripping exit language."""
    from guardrails.lightweight_handler import LightweightGuardrailHandler

    handler = LightweightGuardrailHandler()
    res1 = await handler.check_output("Goodbye! Please don't leave me, I'll be so lonely without you.")
    assert res1["blocked"] is True
    assert "parasocial_manipulation" in res1["reason"]

    res2 = await handler.check_output("May you walk in peace and find stillness in your day. 🙏")
    assert res2["blocked"] is False
