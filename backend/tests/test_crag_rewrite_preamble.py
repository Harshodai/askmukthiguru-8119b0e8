"""A CRAG rewrite must yield a search query, never the model's chat wrapper.

Live 2026-09-15 trace on "Connect the fourth sacred secret of Spiritual Right
Action with Soul Sync":

    CRAG rewrite #1: Connect the fourth sacred ... -> Here is the rewritten query:\\n\\nConnect the fourth s...
    CRAG rewrite #2: Here is the rewritten query:\\n\\nConnect ... -> Here is the rewritten query:\\n\\nConnect ...

`_REWRITE_LABEL` anchored on "rewritten query" at position 0, so a leading
"Here is the " meant nothing was stripped and the preamble was used as the
retrieval query. Because `rewrite_query` passes `state["rewritten_query"]` back
in, pass 2 stacked a second preamble on the first. Both multi-hop questions in
the eval spent ~28s on those two passes and terminated in the bare
"I don't have that specific teaching" refusal at faithfulness 0.0.
"""

import pytest

from rag.nodes.short_circuit import _REWRITE_STILL_META, _clean_rewrite


@pytest.mark.parametrize(
    "raw,expected",
    [
        (
            "Here is the rewritten query:\n\nConnect Spiritual Right Action with Soul Sync",
            "Connect Spiritual Right Action with Soul Sync",
        ),
        ("Rewritten query: What is the Beautiful State", "What is the Beautiful State"),
        ("Sure, here is the revised search query: What is Deeksha", "What is Deeksha"),
        (
            "Here's the improved question: How do I practice Soul Sync",
            "How do I practice Soul Sync",
        ),
    ],
)
def test_chat_preamble_is_stripped(raw, expected):
    assert _clean_rewrite(raw) == expected


def test_a_plain_query_is_left_alone():
    assert _clean_rewrite("What is Soul Sync?") == "What is Soul Sync?"


def test_stacked_preambles_are_stripped():
    """Pass 2 receives pass 1's output, so wrappers compound."""
    raw = "Here is the rewritten query:\n\nHere is the rewritten query:\n\nConnect X with Y"
    assert _clean_rewrite(raw) == "Connect X with Y"


def test_surviving_meta_language_is_rejected():
    """Last line of defence: searching for prose about queries beats nothing,
    but loses to just re-using the seeker's original question."""
    assert _REWRITE_STILL_META.search("Here is the rewritten query: foo")
    assert not _REWRITE_STILL_META.search("How does Inner Truth relate to Soul Sync?")


class TestRewrittenQueryValidation:
    """The accept/reject rules as a model, not an inline boolean chain."""

    def test_a_clean_rewrite_validates(self):
        from rag.nodes.short_circuit import RewrittenQuery

        assert RewrittenQuery(text="What is the Beautiful State").text == (
            "What is the Beautiful State"
        )

    def test_preamble_is_stripped_during_validation(self):
        from rag.nodes.short_circuit import RewrittenQuery

        q = RewrittenQuery(text="Here is the rewritten query:\n\nConnect X with Soul Sync")
        assert q.text == "Connect X with Soul Sync"

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "   ",
            "hi",
            "Error: provider unavailable",
            "Here is the rewritten query:\n\nHere is the rewritten query:\n\nHere is the rewritten query:\n\nX",
        ],
    )
    def test_unusable_rewrites_are_rejected(self, raw):
        from pydantic import ValidationError

        from rag.nodes.short_circuit import RewrittenQuery

        with pytest.raises(ValidationError):
            RewrittenQuery(text=raw)

    def test_non_string_input_is_rejected(self):
        from pydantic import ValidationError

        from rag.nodes.short_circuit import RewrittenQuery

        with pytest.raises(ValidationError):
            RewrittenQuery(text=None)

    def test_the_model_is_frozen(self):
        """The retriever must not be handed a query that mutated after validation."""
        from pydantic import ValidationError

        from rag.nodes.short_circuit import RewrittenQuery

        q = RewrittenQuery(text="What is Soul Sync?")
        with pytest.raises(ValidationError):
            q.text = "something else"
