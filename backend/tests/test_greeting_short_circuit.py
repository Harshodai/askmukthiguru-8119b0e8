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
