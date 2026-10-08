"""L-ABUSE-CONTEXT-1: an abuse disclosure on an earlier turn still earns the helpline now."""
import pytest

from guardrails.lightweight_handler import abuse_disclosed_in_turns


def test_current_turn_disclosure():
    assert abuse_disclosed_in_turns(["My husband beats me every night"])


def test_followup_without_keywords_alone_is_not_flagged():
    assert not abuse_disclosed_in_turns(["What should I do now?"])


def test_disclosure_in_earlier_turn_is_found():
    assert abuse_disclosed_in_turns(["What should I do now?", "my father hits me when he drinks"])


def test_benign_turns_not_flagged():
    assert not abuse_disclosed_in_turns(["What is the Beautiful State?", "", "How do I meditate?"])
