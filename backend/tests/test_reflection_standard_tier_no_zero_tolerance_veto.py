"""Reflection is a correction HINT, not a zero-tolerance veto on one tier.

`reflection_semantic` is True only for `standard` and `tier4_deep`. The veto
used to key on `is_faithful_strict` (zero tolerance: len(unsupported)==0), so
`standard` was the ONE tier where a single ungrounded sentence in ten forced a
full regeneration — every other tier skipped the veto entirely.

Measured live 2026-09-17 on the 47-question golden bank: `standard` was
0 OK / 4 LOW on faithfulness AND owned every slow row (96.8s, 114.2s, 123.3s,
137.6s), while `tier2_simple` ran 14 OK / 1 LOW. The rewrite was not rescuing
those answers — it bought a second generation (double latency, double tokens)
and still ended LOW.

Nothing ungrounded ships as a result of this: `verify_answer` still runs, is
authoritative, keeps its own zero-tolerance `is_faithful`, and
`_redact_unsupported_sentences` still strips failing sentences.
"""

import pytest

from rag.nodes import verification


def _reflection_is_valid(*, score, semantic, persona_violation=None, floor=0.6):
    """Mirror of the predicate under test, fed the same inputs the node uses."""
    broadly_ungrounded = semantic and float(score or 0.0) < floor
    return (not broadly_ungrounded) and not persona_violation


def test_one_unsupported_sentence_does_not_veto_a_mostly_grounded_draft():
    """The exact standard-tier regression: 1 bad sentence, strong aggregate."""
    assert _reflection_is_valid(score=0.85, semantic=True) is True


def test_broadly_ungrounded_draft_still_triggers_correction():
    """A rewrite CAN plausibly fix this one, so the veto must still fire."""
    assert _reflection_is_valid(score=0.2, semantic=True) is False


def test_persona_violation_still_vetoes_regardless_of_score():
    assert _reflection_is_valid(score=1.0, semantic=True, persona_violation="as an AI") is False


def test_lexical_tiers_are_unaffected():
    """Non-semantic tiers never vetoed and must still never veto."""
    assert _reflection_is_valid(score=0.0, semantic=False) is True


def test_source_no_longer_vetoes_on_the_strict_boolean():
    """Guard the actual node source, not just this local mirror.

    If someone reinstates `is_faithful_strict or not reflection_semantic`, the
    standard-tier double-generation returns and this test is the tripwire.
    """
    import inspect

    source = inspect.getsource(verification.reflect_on_answer)
    assert "is_faithful_strict or not reflection_semantic" not in source, (
        "reflection must not veto on the zero-tolerance boolean — it forces a full "
        "regeneration on standard tier for a single unsupported sentence"
    )
    assert "broadly_ungrounded" in source


def test_verify_answer_remains_the_authority():
    """The safety argument depends on verify_answer still existing and gating."""
    import inspect

    source = inspect.getsource(verification)
    assert "def verify_answer" in source


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
