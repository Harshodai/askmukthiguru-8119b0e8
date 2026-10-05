"""R3 claim→source ledger + CitationFaithfulness-style audit (eval-only).

Covers the pure-stdlib helpers in scripts/eval/run_ragas_eval.py. The hard
invariant under test: FP (first-person guru-voice) spans stay context-only —
zero FP citations in audit output.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_RUNNER = Path(__file__).resolve().parents[2] / "scripts" / "eval" / "run_ragas_eval.py"
_spec = importlib.util.spec_from_file_location("run_ragas_eval", _RUNNER)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

CTXS = [
    "Sri Preethaji teaches that a Beautiful State is free from suffering, "
    "marked by stillness, joy, and connectedness.",
    "Sri Krishnaji teaches the Serene Mind practice: breath, emotion, and "
    "thought direction with attention at the eyebrow center.",
]


@pytest.mark.unit
def test_grounded_claim_links_to_supporting_span():
    audit = _mod.citation_faithfulness_audit(
        "A Beautiful State is free from suffering and marked by stillness [1].",
        CTXS,
    )
    assert audit["n_claims"] == 1
    assert audit["n_grounded"] == 1
    row = audit["ledger"][0]
    assert row["best_context_idx"] == 0
    assert row["citable"] is True
    assert audit["cited_but_ungrounded"] == []


@pytest.mark.unit
def test_cited_but_ungrounded_flagged():
    # Out-of-range target.
    audit = _mod.citation_faithfulness_audit(
        "A Beautiful State requires strict fasting every new moon [5].", CTXS
    )
    assert len(audit["cited_but_ungrounded"]) == 1
    assert audit["cited_but_ungrounded"][0]["reason"] == "target_out_of_range"
    # In-range target that does not support the claim.
    audit2 = _mod.citation_faithfulness_audit(
        "A Beautiful State requires strict fasting every new moon [2].", CTXS
    )
    assert len(audit2["cited_but_ungrounded"]) == 1
    assert audit2["cited_but_ungrounded"][0]["reason"] == "cited_span_does_not_support_claim"


@pytest.mark.unit
def test_fp_spans_are_context_only_zero_citations():
    """Hard invariant: FP audit output carries zero citations; rows uncitable."""
    audit = _mod.citation_faithfulness_audit(
        "I am with you. Rest your attention in stillness.",
        CTXS,
        is_first_person=True,
    )
    assert audit["fp_citations"] == []
    assert audit["ledger"] and all(r["citable"] is False for r in audit["ledger"])


@pytest.mark.unit
def test_fp_citation_marker_is_violation():
    audit = _mod.citation_faithfulness_audit(
        "I am with you in stillness [1].", CTXS, is_first_person=True
    )
    assert len(audit["fp_citations"]) == 1
    assert audit["fp_citations"][0]["reason"] == "fp_never_cites"


@pytest.mark.unit
def test_detect_first_person_voice_and_heuristic():
    assert _mod.detect_first_person("Some teaching text.", voice="first_person") is True
    assert _mod.detect_first_person("I am with you in stillness.") is True
    assert _mod.detect_first_person("Sri Preethaji teaches that stillness heals the mind.") is False
