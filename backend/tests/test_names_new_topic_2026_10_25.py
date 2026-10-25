"""A follow-up phrase that names its own topic must not be glued to the previous question."""

import pytest

from rag.resolve_followup import names_new_topic


@pytest.mark.parametrize(
    "question",
    [
        "tell me more about the Beautiful State",
        "what about the Beautiful State?",
        "can you explain more about inner peace and awareness",
    ],
)
def test_question_with_its_own_topic_is_standalone(question):
    assert names_new_topic(question) is True


@pytest.mark.parametrize(
    "question",
    [
        "tell me more",
        "what about that",
        "can you elaborate on that",
        "what about my husband",
        "tell me more about it",
        "explain that",
        "",
    ],
)
def test_bare_followup_still_resolves(question):
    assert names_new_topic(question) is False
