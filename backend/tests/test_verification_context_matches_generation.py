"""Verification must score the answer against the context that GENERATED it.

`generate_answer` reads `selected_docs` (written by context_engineer), then
applies its own token budget and context compression, and publishes the
survivors as `verification_context_docs`. `relevant_docs` is an EARLIER
snapshot written by grade_documents/reranking — it can be missing text the
generation prompt actually contained, notably injected OKF doctrine and
knowledge-graph relationship blocks.

Scoring against that earlier snapshot reported grounded sentences as
unsupported. Measured live 2026-09-17 on the 47-question golden bank: deep and
standard tiers (which run context_engineer) failed verification and degraded to
"grounded partial evidence" with faithfulness 0.0, while tier2_simple (which
does not run it) passed at 1.0. The bug was latent for as long as the real
LettuceDetect NLI detector was uninstalled and a lenient word-overlap heuristic
scored in its place.

This is a correctness fix, not a relaxation: the gate still rejects genuinely
unsupported claims — it just stops inventing failures from a context mismatch.
"""

import pytest

from rag.nodes.verification import _verification_docs

_GENERATED = [{"text": "doctrine the prompt actually contained"}]
_EARLIER = [{"text": "an earlier pre-context_engineer snapshot"}]
_SELECTED = [{"text": "context_engineer post-budget selection"}]


def test_returns_the_union_never_a_subset():
    """The union is the only safe direction.

    An earlier version PREFERRED verification_context_docs, which is the
    post-budget/post-compression survivor set and therefore SMALLER than
    relevant_docs. That shrank the scorer's evidence and made verification
    stricter: low-faithfulness rows went 7/47 -> 12/47 on the golden bank.
    An answer grounded in a subset is also grounded in the superset.
    """
    state = {
        "verification_context_docs": _GENERATED,
        "selected_docs": _SELECTED,
        "relevant_docs": _EARLIER,
    }
    out = _verification_docs(state, _EARLIER)
    for doc in (*_EARLIER, *_SELECTED, *_GENERATED):
        assert doc in out
    assert len(out) == 3


def test_includes_selected_docs_when_generator_published_nothing():
    state = {"selected_docs": _SELECTED, "relevant_docs": _EARLIER}
    out = _verification_docs(state, _EARLIER)
    assert _EARLIER[0] in out and _SELECTED[0] in out


def test_never_returns_fewer_docs_than_the_caller_passed():
    """Regression guard for the 7/47 -> 12/47 regression: never shrink."""
    state = {"verification_context_docs": _GENERATED, "relevant_docs": _EARLIER}
    assert len(_verification_docs(state, _EARLIER)) >= len(_EARLIER)


def test_falls_back_to_relevant_docs_when_context_engineer_never_ran():
    """Fast tiers skip context_engineer — they must behave exactly as before."""
    state = {"relevant_docs": _EARLIER}
    assert _verification_docs(state, _EARLIER) == _EARLIER


def test_empty_published_list_does_not_blank_the_context():
    """An empty list must not be treated as 'the generator used no context'.

    Falling through to a real doc list is the safe direction: scoring against an
    EMPTY context marks every sentence unsupported, which would fail every
    answer rather than merely mis-scoring some.
    """
    state = {"verification_context_docs": [], "selected_docs": [], "relevant_docs": _EARLIER}
    assert _verification_docs(state, _EARLIER) == _EARLIER


def test_generate_answer_publishes_the_context_it_used():
    """The contract is only honoured if generate_answer actually emits the key."""
    import inspect

    from rag.nodes import generation

    source = inspect.getsource(generation.generate_answer)
    assert '"verification_context_docs"' in source, (
        "generate_answer must publish verification_context_docs, or verification "
        "silently reverts to scoring against the wrong (pre-context_engineer) context"
    )


def test_every_verification_context_build_uses_the_helper():
    """All scorer paths must agree; one missed site reintroduces the bug."""
    import inspect

    from rag.nodes import verification

    source = inspect.getsource(verification)
    stale = source.count("join(doc_text(doc) for doc in relevant_docs)")
    assert stale == 0, (
        f"{stale} verification path(s) still build context from relevant_docs directly; "
        "use _verification_docs(state, relevant_docs)"
    )


def test_no_emptiness_check_gates_on_bare_relevant_docs():
    """The context-BUILD line isn't the only place the old snapshot can leak back in.

    Found 2026-09-18: reflect_on_answer/verify_answer/combined_grade_and_verify
    all built context from `_verification_docs(...)` correctly, but their
    preceding "do we have anything to verify" early-return still checked bare
    `not relevant_docs`. An answer grounded ENTIRELY in injected OKF/KG text
    (relevant_docs empty -- root CLAUDE.md: "OKF injection no longer requires
    non-empty vector-search results") was rejected or fast-passed as
    unverified before the union was ever consulted. Guards against
    reintroducing that specific line shape, which the build-line check above
    does not catch.
    """
    import inspect

    from rag.nodes import verification

    source = inspect.getsource(verification)
    stale = source.count("or not relevant_docs")
    assert stale == 0, (
        f"{stale} site(s) gate an emptiness check on bare relevant_docs; "
        "compute verification_docs = _verification_docs(state, relevant_docs) first "
        "and check that instead"
    )


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
