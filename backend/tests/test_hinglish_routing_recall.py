"""Hinglish code-mix must route to Hindi, and English must not follow it.

_check_hinglish requires >=30% of a message's words to match HINDI_WORDS. The
word list omitted several of the commonest Hinglish tokens (gussa, bahut, aata,
karun), so a genuine code-mix sentence scored 4/16 = 0.25 and was routed to
English — real Hinglish seekers got English routing and an English prompt
suffix.

The fix was vocabulary recall, not the threshold. Lowering the threshold would
have bought the same fixture at the cost of misrouting English, so this pins
both directions: raising recall must not cost precision.
"""

from __future__ import annotations

import pytest

from services.language_router import LanguageRouter

HINGLISH = [
    "Mujhe gussa bahut aata hai when my family does not understand me. Aaj kya practise karun?",
    "Mujhe bahut dukh hota hai aaj, kuch shanti chahiye.",
]

# Plain English, including words that overlap the spiritual domain the Hindi
# list also covers (peace, heart, anger) — the precision side of the guard.
ENGLISH = [
    "How do I calm my mind when my family does not understand me?",
    "What is the Beautiful State and how do I practise it today?",
    "I feel a lot of anger and sadness. Can you help me understand why?",
    "My heart is heavy and I want to find peace and happiness again.",
    "Please explain the difference between Soul Sync and Deeksha.",
]


@pytest.fixture(scope="module")
def router() -> LanguageRouter:
    return LanguageRouter()


@pytest.mark.parametrize("text", HINGLISH)
def test_hinglish_is_not_routed_to_english(router: LanguageRouter, text: str):
    detected = router.detect(text).primary.value
    assert detected != "en", (
        f"Hinglish routed to English: {text!r} — the seeker gets an English "
        "prompt suffix and English-tuned retrieval"
    )


@pytest.mark.parametrize("text", ENGLISH)
def test_english_is_not_misrouted_as_hinglish(router: LanguageRouter, text: str):
    assert router.detect(text).primary.value == "en", (
        f"English misrouted: {text!r} — expanding the Hindi vocabulary must not "
        "cost precision on plain English"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
