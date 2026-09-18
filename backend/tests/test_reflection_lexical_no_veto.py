"""Reflection must not veto an answer on a lexical-overlap score alone.

`reflect_on_answer` only runs the semantic scorer for a couple of query tiers;
for every other tier it falls back to per-sentence word overlap (>= 0.45), which
a faithful paraphrase of doctrine routinely fails. Treating that proxy as a hard
gate sent every such answer into the CRAG rewrite loop and, once the budget was
spent, into `handle_fallback` with grounding_state=abstained — measured live on
2026-09-12 for comparative queries. `verify_answer` re-scores with semantic=True
and is the authority; reflection contributes feedback only.
"""

from unittest.mock import MagicMock

import pytest

from rag.nodes import _services, verification

UNFAITHFUL = {
    "is_faithful": False,
    "score": 0.65,
    "details": "Hallucination detected in 2 sentences",
    "unsupported_sentences": ["a", "b"],
}


def _state(tier):
    return {
        "question": "What is the difference between the Beautiful State and the Suffering State?",
        "answer": "The Beautiful State is connection; the Suffering State is separation.",
        "relevant_docs": [{"text": "Sri Preethaji teaches...", "source_url": "url1"}],
        "query_tier": tier,
        "chat_history": [],
        "rewrite_count": 0,
    }


@pytest.fixture
def mock_ld(monkeypatch):
    ld = MagicMock()
    # Fresh dict per call: the scorer stamps the result, and a shared dict would
    # let one call's stamp leak into another's assertion.
    ld.score_faithfulness.side_effect = lambda *a, **k: dict(UNFAITHFUL)
    monkeypatch.setattr(_services, "_lettuce_detect", ld)
    monkeypatch.setattr(_services, "_ollama", MagicMock())
    return ld


@pytest.mark.asyncio
@pytest.mark.parametrize("tier", ["fast", "tier2_simple", "tier3_complex", "deep"])
async def test_lexical_tier_does_not_veto(mock_ld, tier):
    result = await verification.reflect_on_answer(_state(tier))
    assert result["needs_correction"] is False, (
        f"tier={tier} scores lexically; a lexical miss must not force a rewrite"
    )
    assert "lexical-overlap" in result["reflection_feedback"]


@pytest.mark.asyncio
async def test_semantic_tier_vetoes_only_when_broadly_ungrounded(mock_ld, monkeypatch):
    """"standard" runs the embedder, so its verdict is real and still gates —
    but on the AGGREGATE score, not on the zero-tolerance boolean.

    Changed 2026-09-17. The old predicate vetoed whenever `is_faithful` was
    False (len(unsupported)==0), and `reflection_semantic` is True only for
    `standard`/`tier4_deep` — so `standard` was the ONE tier where a single
    ungrounded sentence forced a full regeneration. Measured on the 47-question
    bank: `standard` was 0 OK / 4 LOW AND owned every slow row (96.8s-137.6s)
    while `tier2_simple` ran 14 OK / 1 LOW. The rewrite was not rescuing those
    answers, just buying a second generation. `verify_answer` remains the
    authority and keeps its own zero-tolerance check, so nothing ungrounded
    ships either way.
    """
    # The shared fixture scores 0.65 — above the 0.6 floor, i.e. mostly
    # grounded with one bad sentence. That must NOT force a rewrite now.
    assert (await verification.reflect_on_answer(_state("standard")))["needs_correction"] is False

    # Broadly ungrounded IS still worth a rewrite.
    mock_ld.score_faithfulness.side_effect = lambda *a, **k: {**UNFAITHFUL, "score": 0.2}
    result = await verification.reflect_on_answer(_state("standard"))
    assert result["needs_correction"] is True
    assert "semantic" in result["reflection_feedback"]


@pytest.mark.asyncio
async def test_feedback_reports_the_real_criterion(mock_ld):
    result = await verification.reflect_on_answer(_state("standard"))
    fb = result["reflection_feedback"]
    assert "2 sentence(s) not grounded" in fb
    # The old message claimed "need >= 0.6" while printing 0.65 — a threshold
    # nothing compared against.
    assert "need >=" not in fb


@pytest.mark.asyncio
async def test_bounded_scorer_stamps_scorer_strength(mock_ld):
    """Every verdict records whether the semantic scorer produced it."""
    lex = await verification._score_faithfulness_bounded(mock_ld, "q", "ctx", "ans", semantic=False)
    sem = await verification._score_faithfulness_bounded(mock_ld, "q", "ctx", "ans", semantic=True)
    assert lex["semantic"] is False
    assert sem["semantic"] is True


@pytest.mark.asyncio
async def test_unavailable_scorer_is_not_mistaken_for_semantic():
    result = await verification._score_faithfulness_bounded(None, "q", "ctx", "ans", semantic=True)
    assert result["semantic"] is False
    assert result["is_faithful"] is False


def test_verify_paths_do_not_reuse_a_lexical_verdict():
    """`semantic=True` at the verify sites must be reachable.

    Both verify paths used to reuse `state['lettuce_detect_result']` whenever it
    existed. Self-reflection always populates it, and scores lexically on most
    tiers — so the authoritative semantic pass never ran in production.
    """
    import inspect

    src = inspect.getsource(verification)
    assert src.count('if ld_result is None or not ld_result.get("semantic"):') == 2, (
        "a verify path reuses the cached faithfulness verdict without checking "
        "which scorer produced it"
    )
