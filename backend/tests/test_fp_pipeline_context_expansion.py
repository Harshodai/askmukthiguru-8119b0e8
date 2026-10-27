"""Plan T2b + T3: context-candidate expansion at the first-person call site.

Covers ``FirstPersonPipeline._expand_context_candidates`` (enrichment window and
graph-guided candidate expansion) plus the T5 ``fp_served`` marker.

No Qdrant, no Neo4j, no Redis, no network, no LLM. The pipeline instance is built
with ``__new__``: the helper reads only ``settings`` and the store it is handed,
so no constructor dependency (store, weaver, serene-mind engine) is exercised.

Patch target: ``expand_query_concepts`` is imported into this module's namespace
at the top of ``services/first_person_pipeline.py``, so it is patched as
``services.first_person_pipeline.expand_query_concepts`` (module attribute),
never on the graph-expansion module itself.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.config import settings
from domain.first_person_context import (
    BoundaryStatus,
    CompletenessStatus,
    ParentContext,
    ParentUnit,
    ProvenanceKind,
    SourceSpan,
    SpeakerRole,
    clip_text_hash,
    make_source_span_id,
)
from services.first_person_context_store import FirstPersonContextStoreError
from services.first_person_pipeline import FirstPersonPipeline, FirstPersonPipelineResult

HASH = "c" * 64


def _span(parent_id: str, n: int, *, video_id: str = "vidT") -> SourceSpan:
    text = f"The mind settles when it is watched, part {n} of {parent_id}."
    word_start = n * 10
    word_end = word_start + 6
    return SourceSpan(
        corpus_version="ctx-v1",
        guru_id="krishnaji",
        video_id=video_id,
        source_asset_id=video_id,
        source_span_id=make_source_span_id(
            guru_id="krishnaji",
            video_id=video_id,
            corpus_version="ctx-v1",
            word_start=word_start,
            word_end=word_end,
            transcript_hash=HASH,
        ),
        parent_unit_id=parent_id,
        turn_id=f"turn{n}",
        turn_index=n,
        source_span_index=n,
        start_ms=1000 * n,
        end_ms=1000 * n + 900,
        word_start=word_start,
        word_end=word_end,
        speaker_id="krishnaji",
        speaker_role=SpeakerRole.GURU,
        speaker_verified=True,
        source_transcript_text=text,
        verbatim_text=text,
        transcript_hash=HASH,
        source_text_hash=clip_text_hash(text),
        boundary_status=BoundaryStatus.VERIFIED,
        completeness_status=CompletenessStatus.COMPLETE,
        rights_cleared=True,
        caption_status="auto",
        provenance_kind=ProvenanceKind.SPEECH_TURN_SPAN,
        source_url=f"https://www.youtube.com/watch?v={video_id}",
    )


def _context(parent_id: str, n_spans: int, *, score: float = 0.5) -> ParentContext:
    """A parent of ``n_spans`` ordered spans, narrowed to its last span only."""
    spans = tuple(_span(parent_id, i) for i in range(n_spans))
    parent = ParentUnit(
        corpus_version="ctx-v1",
        guru_id=spans[0].guru_id,
        video_id=spans[0].video_id,
        parent_unit_id=parent_id,
        ordered_source_span_ids=tuple(s.source_span_id for s in spans),
        start_ms=spans[0].start_ms,
        end_ms=spans[-1].end_ms,
        parent_text_hash=clip_text_hash(" ".join(s.verbatim_text for s in spans)),
        speaker_ids=(spans[0].speaker_id,),
        speaker_continuity=True,
        boundary_status=BoundaryStatus.VERIFIED,
        completeness_status=CompletenessStatus.COMPLETE,
    )
    return ParentContext(
        parent=parent,
        spans=(spans[-1],),
        hit_span_ids=(spans[-1].source_span_id,),
        score=score,
    )


def _context_ids(contexts: list[ParentContext]) -> list[str]:
    return [c.parent.parent_unit_id for c in contexts]


class FakeStore:
    """Minimal context store: records calls, returns scripted results."""

    def __init__(
        self,
        contexts: list[ParentContext] | None = None,
        *,
        graph_contexts: list[ParentContext] | None = None,
        graph_error: Exception | None = None,
        enrich_error: Exception | None = None,
        enrich_map: dict[str, ParentContext] | None = None,
    ) -> None:
        self._contexts = list(contexts or [])
        self._graph_contexts = list(graph_contexts or [])
        self._graph_error = graph_error
        self._enrich_error = enrich_error
        self._enrich_map = dict(enrich_map or {})
        self.retrieve_calls: list[dict[str, object]] = []
        self.enrich_calls: list[str] = []

    def retrieve(
        self,
        query_dense: list[float],
        *,
        query_sparse: dict[str, object] | None = None,
        guru_id: str | None = None,
        limit_parents: int = 5,
        spans_per_parent: int = 8,
        concept_ids: list[str] | None = None,
    ) -> list[ParentContext]:
        self.retrieve_calls.append(
            {
                "concept_ids": concept_ids,
                "guru_id": guru_id,
                "limit_parents": limit_parents,
                "spans_per_parent": spans_per_parent,
            }
        )
        if not concept_ids:
            return list(self._contexts)
        if self._graph_error is not None:
            raise self._graph_error
        return list(self._graph_contexts)

    def enrich_to_parent_window(self, context: ParentContext) -> ParentContext:
        self.enrich_calls.append(context.parent.parent_unit_id)
        if self._enrich_error is not None:
            raise self._enrich_error
        return self._enrich_map.get(context.parent.parent_unit_id, context)


def _pipeline() -> FirstPersonPipeline:
    """Helper-only instance: ``__new__`` skips every constructor dependency."""
    return FirstPersonPipeline.__new__(FirstPersonPipeline)


def _expand(
    contexts: list[ParentContext],
    store: FakeStore,
    *,
    max_clips: int = 5,
    max_spans: int = 3,
    retrieval_query: str = "how do I deal with anger",
    teacher_id: str = "krishnaji",
) -> list[ParentContext]:
    return _pipeline()._expand_context_candidates(
        contexts,
        ctx_store=store,
        query_dense_vector=[0.1] * 8,
        query_sparse_vector=None,
        retrieval_query=retrieval_query,
        teacher_id=teacher_id,
        max_clips=max_clips,
        max_spans=max_spans,
    )


@pytest.fixture
def both_flags_off(monkeypatch):
    monkeypatch.setattr(settings, "first_person_enrichment_window_enabled", False)
    monkeypatch.setattr(settings, "first_person_graph_expansion_enabled", False)


@pytest.fixture
def graph_expander(monkeypatch):
    """Patch the module attribute the pipeline actually calls."""
    spy = MagicMock(return_value=[])
    monkeypatch.setattr("services.first_person_pipeline.expand_query_concepts", spy)
    return spy


# ------------------------------------------------------- 1. today-behaviour


def test_both_flags_off_is_a_pure_pass_through(both_flags_off, graph_expander):
    primary = [_context("p1", 2), _context("p2", 1)]
    store = FakeStore(primary)

    merged = _expand(primary, store)

    assert _context_ids(merged) == ["p1", "p2"]
    assert all(out is orig for out, orig in zip(merged, primary))
    assert store.enrich_calls == []
    assert store.retrieve_calls == []
    graph_expander.assert_not_called()


# --------------------------------------------------- 2. enrichment window on


def test_enrichment_replaces_each_narrow_context_with_its_wider_window(
    both_flags_off, graph_expander, monkeypatch
):
    monkeypatch.setattr(settings, "first_person_enrichment_window_enabled", True)
    narrow = [_context("p1", 2), _context("p2", 2)]
    wide = [
        ParentContext(
            parent=ctx.parent,
            spans=tuple(_span(ctx.parent.parent_unit_id, i) for i in range(2)),
            hit_span_ids=ctx.hit_span_ids,
            score=ctx.score,
        )
        for ctx in narrow
    ]
    store = FakeStore(narrow, enrich_map={c.parent.parent_unit_id: c for c in wide})

    merged = _expand(narrow, store)

    assert store.enrich_calls == ["p1", "p2"]
    assert _context_ids(merged) == ["p1", "p2"]
    assert all(len(ctx.spans) == 2 for ctx in merged)
    assert all(out is not orig for out, orig in zip(merged, narrow))
    graph_expander.assert_not_called()


# ------------------------------------------- 3. enrichment contract violation


def test_enrichment_contract_error_keeps_the_original_context(
    both_flags_off, graph_expander, monkeypatch
):
    monkeypatch.setattr(settings, "first_person_enrichment_window_enabled", True)
    primary = [_context("p1", 1), _context("p2", 1)]
    store = FakeStore(primary, enrich_error=FirstPersonContextStoreError("parent record missing"))

    merged = _expand(primary, store)

    assert _context_ids(merged) == ["p1", "p2"]
    assert all(out is orig for out, orig in zip(merged, primary))
    assert store.enrich_calls == ["p1", "p2"]


# ----------------------------------------------------- 4. graph expansion on


def test_graph_expansion_appends_filtered_contexts_and_dedupes_parents(
    both_flags_off, graph_expander, monkeypatch
):
    monkeypatch.setattr(settings, "first_person_graph_expansion_enabled", True)
    graph_expander.return_value = ["mind", "craving"]

    primary = [_context("p1", 1), _context("p2", 1)]
    graph_only = [_context("p1", 1), _context("p3", 1), _context("p4", 1)]
    store = FakeStore(primary, graph_contexts=graph_only)

    # The call site performs the primary retrieval itself, once.
    contexts = store.retrieve([0.1] * 8, guru_id="krishnaji", limit_parents=5, spans_per_parent=3)
    merged = _expand(contexts, store)

    assert len(store.retrieve_calls) == 2
    assert store.retrieve_calls[0]["concept_ids"] is None
    assert store.retrieve_calls[1]["concept_ids"] == ["mind", "craving"]
    # Appended after the originals, de-duped by parent_unit_id, order preserved.
    assert _context_ids(merged) == ["p1", "p2", "p3", "p4"]
    assert merged[0] is primary[0] and merged[1] is primary[1]
    graph_expander.assert_called_once()
    assert graph_expander.call_args.kwargs["max_neighbors"] == int(
        settings.first_person_graph_expansion_max_neighbors
    )
    assert graph_expander.call_args.kwargs["timeout_s"] == float(
        settings.first_person_graph_expansion_timeout_s
    )


def test_graph_expansion_enriches_only_when_the_window_flag_is_also_on(
    both_flags_off, graph_expander, monkeypatch
):
    monkeypatch.setattr(settings, "first_person_graph_expansion_enabled", True)
    monkeypatch.setattr(settings, "first_person_enrichment_window_enabled", True)
    graph_expander.return_value = ["craving"]

    primary = [_context("p1", 1)]
    extra = _context("p2", 2)
    store = FakeStore(primary, graph_contexts=[extra])

    merged = _expand(primary, store)

    assert _context_ids(merged) == ["p1", "p2"]
    # Both the primary and the appended context get one enrichment call each.
    assert store.enrich_calls == ["p1", "p2"]


# --------------------------------------------------- 5. graph returns nothing


def test_graph_expansion_with_no_concepts_costs_no_extra_retrieval(
    both_flags_off, graph_expander, monkeypatch
):
    monkeypatch.setattr(settings, "first_person_graph_expansion_enabled", True)
    graph_expander.return_value = []

    primary = [_context("p1", 1)]
    store = FakeStore(primary)
    contexts = store.retrieve([0.1] * 8, guru_id="krishnaji", limit_parents=5, spans_per_parent=3)

    merged = _expand(contexts, store)

    assert len(store.retrieve_calls) == 1  # the call site's own retrieval only
    assert _context_ids(merged) == ["p1"]
    graph_expander.assert_called_once()


# ------------------------------------------------ 6. filtered retrieval fails


def test_graph_expansion_retrieval_failure_keeps_primary_contexts(
    both_flags_off, graph_expander, monkeypatch
):
    monkeypatch.setattr(settings, "first_person_graph_expansion_enabled", True)
    graph_expander.return_value = ["mind"]

    primary = [_context("p1", 1), _context("p2", 1)]
    store = FakeStore(primary, graph_error=RuntimeError("qdrant unavailable"))

    merged = _expand(primary, store)

    assert _context_ids(merged) == ["p1", "p2"]
    assert all(out is orig for out, orig in zip(merged, primary))
    assert len(store.retrieve_calls) == 1


# ----------------------------------------------------------- 7. fp_served


def test_fp_served_true_on_served_result_and_false_on_abstain():
    served = FirstPersonPipelineResult(
        answer_text='"The mind settles."',
        citations=[{"point_id": "p1", "video_id": "vidT"}],
        status="weak_match",
        is_direct_answer=False,
        latency_ms=12.0,
        fp_served=True,
    )
    assert served.fp_served is True

    abstain = FirstPersonPipelineResult(
        answer_text="No verified first-person discourse found for this question.",
        citations=[],
        status="abstained",
        is_direct_answer=False,
        latency_ms=12.0,
        abstain_reason="no_verified_clips",
    )
    assert abstain.fp_served is False

    # The new keyword is appended: the existing positional order is unchanged.
    positional = FirstPersonPipelineResult("text", [], "error", False, 1.0)
    assert positional.fp_served is False
    assert positional.status == "error"


# ------------------------------------------------------------ 8. flag defaults


def test_expansion_flags_default_off():
    assert settings.first_person_enrichment_window_enabled is False
    assert settings.first_person_graph_expansion_enabled is False
