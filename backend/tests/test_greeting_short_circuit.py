from app.pipeline.stages.glue_stages import _GREETING_RE, _GREETING_VOCATIVE_RE


def test_vocative_greeting_is_bounded_and_question_safe():
    assert _GREETING_VOCATIVE_RE.match("Namaste Guruji")
    assert _GREETING_VOCATIVE_RE.match("Hello seeker!")
    assert not _GREETING_VOCATIVE_RE.match("Hello dear seeker!")
    assert _GREETING_RE.match("Namaste")
    assert not _GREETING_VOCATIVE_RE.match("Namaste Guruji what is the Beautiful State?")
    assert not _GREETING_VOCATIVE_RE.match("Hello, can you explain stillness?")
