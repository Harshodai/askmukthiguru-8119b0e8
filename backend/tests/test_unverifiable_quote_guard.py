"""Quotation marks are an attribution claim, and nothing was checking them.

LettuceDetect scores whether a CLAIM is entailed by the retrieved context. A
claim entailed in substance passes even when the quotation itself was invented,
so an answer could score faithfulness 1.0 while putting words in a living
teacher's mouth. Measured live 2026-09-17 on the 47-question golden bank:
`"the mind's tendency to suffer is not your true nature..."` shipped inside
quotation marks and appears nowhere in the 12,904-point corpus or the doctrine
bundle.

The guard demotes rather than deletes — the false attribution is removed, the
grounded prose survives (see L-INVARIANT-1).
"""

import pytest

from rag.nodes.generation import _unquote_unverifiable_spans, strip_all_attributed_quotes

_DOCS = [
    {
        "text": (
            "An unagitated consciousness is the seat of abundance and fortune. "
            "A complaining mind is rooted in judgment."
        )
    }
]


def test_quote_absent_from_context_loses_its_quotation_marks():
    answer = (
        "Sri Krishnaji teaches: \"the mind's tendency to suffer is not your true "
        'nature, it is merely a pattern that has taken root within you."'
    )
    out, removed = _unquote_unverifiable_spans(answer, _DOCS)
    assert removed == 1
    assert '"' not in out
    # The prose survives — only the attribution claim was removed.
    assert "merely a pattern that has taken root within you" in out


def test_verbatim_quote_from_context_is_preserved():
    answer = (
        'As the teaching puts it, "An unagitated consciousness is the seat of '
        'abundance and fortune."'
    )
    out, removed = _unquote_unverifiable_spans(answer, _DOCS)
    assert removed == 0
    assert out == answer


def test_repunctuated_quote_still_counts_as_verbatim():
    """The model re-punctuates faithfully reproduced quotes; that is not fabrication."""
    answer = '"An unagitated consciousness is the seat of abundance and fortune"'
    _out, removed = _unquote_unverifiable_spans(answer, _DOCS)
    assert removed == 0


def test_short_quoted_term_is_left_alone():
    """Glossed terms are quoted legitimately and are not attribution claims."""
    answer = 'The teachings speak of the "Beautiful State" often.'
    out, removed = _unquote_unverifiable_spans(answer, _DOCS)
    assert removed == 0
    assert out == answer


def test_no_docs_is_a_no_op():
    answer = '"some long quoted sentence that is not anywhere in any context at all"'
    out, removed = _unquote_unverifiable_spans(answer, [])
    assert (out, removed) == (answer, 0)


def test_multiple_spans_mixed():
    answer = (
        '"An unagitated consciousness is the seat of abundance and fortune." '
        'and also "a completely invented sentence the teachers never once said."'
    )
    out, removed = _unquote_unverifiable_spans(answer, _DOCS)
    assert removed == 1
    assert "An unagitated consciousness is the seat of abundance and fortune." in out
    assert '"a completely invented sentence' not in out


def test_strip_all_attributed_quotes_strips_even_with_zero_context():
    """handle_casual never runs retrieval, so an empty docs list would make
    `_unquote_unverifiable_spans` a no-op (correct default for every OTHER
    caller). This is the dedicated variant for callers with genuinely no
    possible source to check against -- any quote is unverifiable by
    construction, so it strips unconditionally.
    """
    answer = 'As Sri Preethaji once said, "walk gently and the world walks with you."'
    out, removed = strip_all_attributed_quotes(answer)
    assert removed == 1
    assert '"' not in out
    assert "walk gently and the world walks with you" in out


def test_strip_all_attributed_quotes_leaves_short_glossed_terms_alone():
    out, removed = strip_all_attributed_quotes('We often speak of the "Beautiful State".')
    assert removed == 0
    assert out == 'We often speak of the "Beautiful State".'


def test_strip_all_attributed_quotes_noop_on_unquoted_text():
    answer = "Namaste, dear one. Welcome to this sacred space."
    assert strip_all_attributed_quotes(answer) == (answer, 0)


def test_handle_casual_calls_the_zero_context_guard():
    """Source-scan guard: handle_casual must strip quotes unconditionally,
    not by calling _unquote_unverifiable_spans with an empty docs list (that
    call is a documented no-op and would silently let a casual-path
    fabrication straight through).
    """
    import inspect

    from rag.nodes import intent

    source = inspect.getsource(intent.handle_casual)
    assert "strip_all_attributed_quotes" in source


def test_format_final_answer_checks_quotes_against_the_verification_union():
    """Source-scan guard: the quote-attribution guard in format_final_answer
    must score against the same union _verification_docs already gives the
    faithfulness verifier, not the earlier bare relevant_docs snapshot --
    otherwise a genuine OKF/KG-grounded quote can be silently stripped.
    """
    import inspect

    from rag.nodes import generation

    source = " ".join(inspect.getsource(generation.format_final_answer).split())
    assert "_unquote_unverifiable_spans( answer, _verification_docs(state" in source


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
