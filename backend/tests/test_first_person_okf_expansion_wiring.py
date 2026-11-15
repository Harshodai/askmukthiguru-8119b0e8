"""WS7 / Component 3+4 wiring: OKF concept expansion and cross-video diversity.

Both stages are additive and flag-gated. These tests pin the contract the pipeline
promises (serving invariant #3):

* flag off -> pure pass-through, no store call, no settings read beyond the flag;
* flag on  -> extra parents are APPENDED after the vector results, never reordering
  or dropping a primary context;
* a duplicate parent id is never appended twice;
* a failing expansion (store error, similarity error) keeps the primary list intact.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.config import settings
from services.first_person_pipeline import FirstPersonPipeline

TEACHER = "krishnaji"


def _context(parent_id: str, video_id: str, score: float = 0.9, text: str = "verbatim span"):
    span = SimpleNamespace(source_span_id=f"span-{parent_id}", verbatim_text=text)
    return SimpleNamespace(
        parent=SimpleNamespace(parent_unit_id=parent_id, video_id=video_id, guru_id=TEACHER),
        spans=(span,),
        score=score,
        hit_span_ids=(f"span-{parent_id}",),
    )


@pytest.fixture()
def pipeline() -> FirstPersonPipeline:
    store = MagicMock()
    store.collection = "first_person_v10"
    return FirstPersonPipeline(store=store, redis_client=None, calibration_profile=None)


@pytest.fixture(autouse=True)
def _flags_off(monkeypatch):
    """Every expansion flag starts off so each test proves one thing."""
    monkeypatch.setattr(settings, "first_person_okf_expansion_enabled", False)
    monkeypatch.setattr(settings, "first_person_enrichment_window_enabled", False)
    monkeypatch.setattr(settings, "first_person_graph_expansion_enabled", False)
    monkeypatch.setattr(settings, "first_person_teaching_unit_graph_enabled", False)
    monkeypatch.setattr(settings, "first_person_cross_video_diversity_enabled", False)


def _call(pipeline, contexts, ctx_store, *, max_clips=4, max_spans=3):
    return pipeline._expand_context_candidates(
        contexts,
        ctx_store=ctx_store,
        query_dense_vector=[0.1] * 1024,
        query_sparse_vector={"indices": [1], "values": [0.5]},
        retrieval_query="what is the beautiful state",
        teacher_id=TEACHER,
        max_clips=max_clips,
        max_spans=max_spans,
    )


# ---------------------------------------------------------------------- OKF wiring


def test_all_flags_off_is_a_pure_pass_through(pipeline):
    store = MagicMock()
    contexts = [_context("p1", "vidA")]
    out = _call(pipeline, contexts, store)
    assert out == contexts
    store.retrieve.assert_not_called()


def test_okf_expansion_appends_without_reordering(pipeline, monkeypatch):
    monkeypatch.setattr(settings, "first_person_okf_expansion_enabled", True)
    primary = [_context("p1", "vidA", 0.92), _context("p2", "vidB", 0.88)]
    extra = _context("p9", "vidC", 0.40)
    store = MagicMock()
    store.retrieve.return_value = [extra]

    with patch(
        "services.first_person_okf_expansion.expand_concepts_via_okf",
        return_value=["beautiful state", "inner peace"],
    ):
        out = _call(pipeline, primary, store)

    assert [c.parent.parent_unit_id for c in out] == ["p1", "p2", "p9"]
    store.retrieve.assert_called_once()
    kwargs = store.retrieve.call_args.kwargs
    assert kwargs["concept_ids"] == ["beautiful state", "inner peace"]
    assert kwargs["guru_id"] == TEACHER


def test_okf_expansion_never_appends_a_duplicate_parent(pipeline, monkeypatch):
    monkeypatch.setattr(settings, "first_person_okf_expansion_enabled", True)
    primary = [_context("p1", "vidA")]
    store = MagicMock()
    store.retrieve.return_value = [_context("p1", "vidA")]

    with patch(
        "services.first_person_okf_expansion.expand_concepts_via_okf",
        return_value=["beautiful state"],
    ):
        out = _call(pipeline, primary, store)

    assert [c.parent.parent_unit_id for c in out] == ["p1"]


def test_okf_no_concepts_costs_no_store_call(pipeline, monkeypatch):
    monkeypatch.setattr(settings, "first_person_okf_expansion_enabled", True)
    primary = [_context("p1", "vidA")]
    store = MagicMock()

    with patch("services.first_person_okf_expansion.expand_concepts_via_okf", return_value=[]):
        out = _call(pipeline, primary, store)

    assert out == primary
    store.retrieve.assert_not_called()


def test_okf_store_error_keeps_primary_contexts(pipeline, monkeypatch):
    monkeypatch.setattr(settings, "first_person_okf_expansion_enabled", True)
    primary = [_context("p1", "vidA")]
    store = MagicMock()
    store.retrieve.side_effect = RuntimeError("qdrant down")

    with patch(
        "services.first_person_okf_expansion.expand_concepts_via_okf",
        return_value=["beautiful state"],
    ):
        out = _call(pipeline, primary, store)

    assert out == primary


# ------------------------------------------------------------- diversity wiring


def test_diversity_flag_off_keeps_retrieval_order(pipeline):
    contexts = [_context("p1", "vidA", 0.9), _context("p2", "vidA", 0.8)]
    assert pipeline._diversify_candidate_pool(contexts) == contexts


def test_diversity_caps_one_video_and_keeps_every_candidate(pipeline, monkeypatch):
    monkeypatch.setattr(settings, "first_person_cross_video_diversity_enabled", True)
    monkeypatch.setattr(settings, "first_person_cross_video_max_per_video", 1)
    contexts = [
        _context("p1", "vidA", 0.9, "the mind is a warring state"),
        _context("p2", "vidA", 0.8, "the mind is a warring state"),
        _context("p3", "vidB", 0.4, "observe the breath gently"),
    ]
    out = pipeline._diversify_candidate_pool(contexts)
    ids = [c.parent.parent_unit_id for c in out]
    assert len(out) == 3, "diversity must never drop a candidate"
    assert ids[0] == "p1"
    assert ids[1] == "p3", "the second video is evaluated before the redundant sibling"
    assert "p2" in ids
