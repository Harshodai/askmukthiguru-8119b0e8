from app.pipeline.stages.glue_stages import _GREETING_RE, _GREETING_VOCATIVE_RE


def test_vocative_greeting_is_bounded_and_question_safe():
    assert _GREETING_VOCATIVE_RE.match("Namaste Guruji")
    assert _GREETING_VOCATIVE_RE.match("Hello seeker!")
    assert not _GREETING_VOCATIVE_RE.match("Hello dear seeker!")
    assert _GREETING_RE.match("Namaste")
    assert not _GREETING_VOCATIVE_RE.match("Namaste Guruji what is the Beautiful State?")
    assert not _GREETING_VOCATIVE_RE.match("Hello, can you explain stillness?")


def test_vocative_tail_is_a_closed_vocabulary_not_any_word():
    """The short-circuit runs ahead of the input guardrail and distress stages.

    A free-form "greeting + any one word" tail also matched crisis-adjacent
    messages ("hello kms", "namaste suicide"), which were then answered from
    the canned greeting without the safety lane ever seeing them.
    """
    for crisis_adjacent in ("hello kms", "namaste suicide", "hi depressed", "hello worthless"):
        assert not _GREETING_VOCATIVE_RE.match(crisis_adjacent)


def test_stacked_greetings_short_circuit_but_nothing_else_rides_along():
    """Live run 2026-10-23: "Namaste! Good morning." took 3.5 s through the LLM casual handler."""
    from app.routing_primitives import is_deterministic_greeting

    for greeting in (
        "Namaste! Good morning.",
        "Namaste, good morning guruji",
        "Hi, hello, hey there",
        "What's happening today?",
        "what's happening today",
        "How are you?",
        "what's up",
    ):
        assert is_deterministic_greeting(greeting), greeting
    for not_greeting in (
        "Namaste! I want to end my life",
        "namaste suicide",
        "Namaste! Good morning, how do I meditate?",
        "good morning hopeless",
        "What's happening today in France?",
        "how are you feeling sad",
    ):
        assert not is_deterministic_greeting(not_greeting), not_greeting


def test_greeting_matchers_stay_fast_on_whitespace_floods():
    """CodeQL py/polynomial-redos on the stacked-greeting regex: long input must not be scanned."""
    import time

    from app.routing_primitives import GREETING_SEQUENCE_RE, is_deterministic_greeting

    flood = "\U0001f64f" + "\t" * 50_000 + "x"
    start = time.perf_counter()
    assert not is_deterministic_greeting(flood)
    assert not GREETING_SEQUENCE_RE.match(flood)
    assert time.perf_counter() - start < 1.0
