"""Live-run regressions (Mac run on main b75b6c1, 2026-10-23).

An off-topic question ("capital of France") came back as "allow me to share some
relevant teachings from the sacred knowledge base instead": strip_cot manufactured
that apology when a reasoning model returned only reasoning, and the line promised
teachings that nothing delivered. "What's happening today?" returned a teaching
refusal. Both now get honest copy that names what happened.
"""

from rag.nodes.utils import strip_cot
from services.voice import register


def test_strip_cot_returns_empty_when_only_reasoning_remains():
    raw = "We must check: the capital. We must ensure the answer is short.\n\nNow, we must output."
    assert strip_cot(raw) == ""


def test_strip_cot_keeps_a_real_answer():
    assert strip_cot("The capital of France is Paris.") == "The capital of France is Paris."


def test_general_unavailable_copy_makes_no_false_promise():
    for copy in (register.GENERAL_ANSWER_UNAVAILABLE, register.LIVE_INFO_UNAVAILABLE):
        low = copy.lower()
        assert "share some relevant teachings" not in low
        assert "sacred knowledge base" not in low


def test_live_cue_gets_live_copy_and_plain_question_gets_neutral_copy():
    assert register.general_unavailable_answer("What's happening today?") == (
        register.LIVE_INFO_UNAVAILABLE
    )
    assert register.general_unavailable_answer("What is the capital of France?") == (
        register.GENERAL_ANSWER_UNAVAILABLE
    )


def test_fallback_copy_is_recognised_as_refusal_so_it_is_never_cached():
    assert register.is_refusal_text(register.GENERAL_ANSWER_UNAVAILABLE)
    assert register.is_refusal_text(register.LIVE_INFO_UNAVAILABLE)
    # Old canned line may still sit in Redis.
    assert register.is_refusal_text(
        "I apologize, but I am unable to formulate a complete response right now."
    )
