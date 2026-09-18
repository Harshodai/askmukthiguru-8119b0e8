"""Canonical memory is its own evidence class (AMK-B-006).

Phase 6 of the 2026-09-18 audit found canonical memory stored correctly and
isolated correctly (36 cross-user probes, 0 leaks) — and then silently deleted
from every answer, including its owner's. User A stored "My favourite colour is
chartreuse and I live in Erode, Tamil Nadu", asked "what is my favourite colour
and where do I live?", got `memory_used: true` and a reply byte-identical to the
one User B (who had no memories at all) received: unrelated doctrine about
parenting. The faithfulness scorer only ever saw retrieved teachings, found no
chunk supporting a claim about the seeker, and the redaction pass dropped the
sentence.

The fix admits a SECOND evidence class rather than lowering the doctrine bar.
These tests pin both halves of that: memory must reach the scorer, and it must
never become citable as a teaching.
"""

from __future__ import annotations

from rag.nodes.verification import MEMORY_EVIDENCE_LABEL, _verification_context

_DOC = {"text": "The Beautiful State is a state of calm, joy and connection."}
_MEMORY = "- My favourite colour is chartreuse and I live in Erode, Tamil Nadu."


def _state(**overrides) -> dict:
    base = {"selected_docs": [], "verification_context_docs": []}
    base.update(overrides)
    return base


def test_canonical_memory_reaches_the_faithfulness_scorer():
    """Without this, a recall answer is redacted as ungrounded — AMK-B-006."""
    context = _verification_context(_state(canonical_memory_evidence=_MEMORY), [_DOC])

    assert "chartreuse" in context, (
        "the seeker's own stored fact is absent from the verification evidence, "
        "so any sentence recalling it scores as unsupported and gets redacted"
    )
    assert _DOC["text"] in context, "doctrine evidence must still be present"


def test_memory_evidence_is_labelled_as_not_doctrine():
    context = _verification_context(_state(canonical_memory_evidence=_MEMORY), [_DOC])
    assert MEMORY_EVIDENCE_LABEL in context
    label_at = context.index(MEMORY_EVIDENCE_LABEL)
    assert context.index("chartreuse") > label_at, "memory must sit under its own label"


def test_legacy_memory_context_is_not_admitted_as_evidence():
    """Grounding an answer in prior assistant output would be circular.

    `memory_context` blends persona summaries and previous ASSISTANT turns. If
    it were evidence, the system could restate a doctrinal claim it made earlier
    and score it as grounded — in itself. Only user-stated canonical facts are
    admitted.
    """
    state = _state(
        memory_context="EARLIER YOU SAID: The Beautiful State dissolves all suffering forever.",
        canonical_memory_evidence="",
    )
    context = _verification_context(state, [_DOC])
    assert "dissolves all suffering forever" not in context
    assert "EARLIER YOU SAID" not in context


def test_absent_memory_leaves_the_doctrine_context_byte_identical():
    """No memory => the gate behaves exactly as it did before this change."""
    with_key = _verification_context(_state(canonical_memory_evidence=""), [_DOC])
    without_key = _verification_context(_state(), [_DOC])
    assert with_key == without_key == _DOC["text"]


def test_memory_evidence_never_enters_the_citable_document_set():
    """It may ground a sentence; it must never source one.

    `extract_citations` maps answer sentences onto retrieved documents. A memory
    that reached that list would be attributable to Sri Preethaji or Sri
    Krishnaji — misattribution, the one failure this system ranks above every
    other. The helper returns a string and must not touch the doc list.
    """
    docs = [_DOC]
    before = list(docs)
    _verification_context(_state(canonical_memory_evidence=_MEMORY), docs)
    assert docs == before, "verification must not mutate the citable document set"
    assert all("chartreuse" not in d["text"] for d in docs)


def test_prepare_user_memory_only_emits_evidence_on_the_canonical_branch():
    """Provenance is decided at the source, not guessed downstream."""
    import inspect

    from app import orchestrator_utils

    src = inspect.getsource(orchestrator_utils.prepare_user_memory)
    # Every legacy return path yields an empty evidence slot.
    assert (
        src.count('distress_history, None, ""') + src.count('distress_history, profile, ""') >= 2
    ), "a legacy return path is emitting memory as evidence"
    assert "distress_history, None, canonical_block" in src, (
        "the canonical branch must emit its block as evidence"
    )


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))


def test_memory_evidence_is_capped():
    """Unbounded evidence makes an entailment scorer permissive.

    The canonical retriever is bounded at 2000 tokens, which is larger than the
    graph-context injection that measurably dropped faithfulness 1.0 -> 0.50
    when uncapped. The gate's own evidence is the one place that must stay small.
    """
    from rag.nodes.verification import MEMORY_EVIDENCE_MAX_CHARS, _trim_memory_evidence

    huge = "\n".join(f"- recorded fact {i} about the seeker" for i in range(200))
    assert len(huge) > MEMORY_EVIDENCE_MAX_CHARS

    trimmed = _trim_memory_evidence(huge)
    assert len(trimmed) <= MEMORY_EVIDENCE_MAX_CHARS
    # Whole facts only — a half-sentence handed to an entailment scorer is not a
    # smaller truth, it is a different one.
    assert all(line.startswith("- recorded fact ") for line in trimmed.split("\n"))
    assert huge.split("\n")[0] in trimmed

    context = _verification_context(_state(canonical_memory_evidence=huge), [_DOC])
    assert trimmed in context
    assert len(huge) > len(trimmed)


def test_memory_is_placed_ahead_of_doctrine():
    """The detector drops the tail when its input ceiling is hit.

    Doctrine is the bulk of the evidence string, so memory appended after it is
    what disappears on a long deep-tier answer — silently re-breaking AMK-B-006
    for exactly the answers carrying the most context.
    """
    context = _verification_context(_state(canonical_memory_evidence=_MEMORY), [_DOC])
    assert context.index(MEMORY_EVIDENCE_LABEL) < context.index(_DOC["text"])
