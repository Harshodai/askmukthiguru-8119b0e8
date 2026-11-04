"""T7-01 characterization matrix for ``FirstPersonPipeline.execute``.

Why this file exists
--------------------
T7-01 splits the 2,146-line ``execute`` into named steps and must be
**behaviour-identical**. `IMPLEMENTATION-AGENT-PROMPT.md` §0j requires golden
outputs recorded *before* the change, but the harnesses it names
(`evals/pr_suite/` = T2-01, `evals/retrieval_bank/` = T2-02) do not exist yet on
this branch and the frozen-bank runner posts to a live server
(`scripts/run_first_person_benchmark.py`). Owner decision Q-T7-01-A (2026-11-05,
`decision-log.md` §3): use this offline characterization matrix instead.

This is **not** the frozen bank. It is a deterministic replay of every exit
path of ``execute`` on a fixture store and a fixture Redis, with no live LLM, no
Qdrant, no network and no spend. Its job is to fail on *any* behaviour change
inside the block being moved.

Owner decision Q-T7-01-C (2026-11-05): every early return is covered, and every
``to_dict()`` field is compared except the two clock-derived ones
(``latency_ms``, ``stage_timings``). The ``_log_and_count`` event each exit
emits is recorded too, because the status/abstain reason pair is part of what a
seeker and an operator observe.

Recording / updating
--------------------
    cd backend && FP_GOLDEN_UPDATE=1 .venv/bin/pytest tests/test_first_person_pipeline_golden.py -q

The goldens live in ``tests/golden/first_person_pipeline/<case>.json``. They
were recorded on the pre-split code and must never be rewritten by the split
itself: a diff in any of them means the split changed behaviour.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.config import settings
from domain.first_person_context import (
    AnswerRole,
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
from services.first_person_pipeline import (
    _RELEVANCE_INDETERMINATE,
    FirstPersonPipeline,
)

GOLDEN_DIR = Path(__file__).parent / "golden" / "first_person_pipeline"
UPDATE = os.environ.get("FP_GOLDEN_UPDATE") == "1"
# Q-T7-01-C: the only two fields excluded, both derived from the wall clock.
CLOCK_FIELDS = frozenset({"latency_ms", "stage_timings"})
# L-PUBLIC-REPO-1: the golden files are committed to a repository that may be
# public, so no recorded value may hold the teacher's words. Those fields are
# recorded as a sha256 plus a character count: any change to the served text
# still changes the golden, and the repository stays free of clip text.
TEXT_FIELDS = frozenset({"answer_text", "verbatim_text", "text_snippet"})

TEACHING_TEXT = (
    "Suffering arises from resistance to what is. The moment you stop resisting, "
    "something shifts within you — not an escape, but a recognition of the truth."
)
TEACHING_HASH = hashlib.sha256(TEACHING_TEXT.encode("utf-8")).hexdigest()

PROFILE = {
    "threshold": 0.5,
    "score_kind": "dense_cosine",
    "n": 100,
    "ucb_risk": 0.01,
    "target_risk": 0.01,
    "collection": "first_person_v1",
    "fitted_at": "2026-09-24",
}


def _clip(**overrides: Any) -> dict[str, Any]:
    base = {
        "point_id": "p1",
        "video_id": "vid_abc",
        "start_ms": 65000,
        "end_ms": 75000,
        "speaker": "Sri Preethaji",
        "teacher_id": "preethaji",
        "transcript_hash": TEACHING_HASH,
        "verbatim_text": TEACHING_TEXT,
        "passage_dense": [1.0, 0.0],
        "source_url": "https://youtube.com/watch?v=vid_abc",
        "first_person_eligible": True,
        "rights_cleared": True,
        "domain_rights_status": "licensed",
        "is_verbatim": True,
        "caption_status": "auto_transcript",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# fp-context harness fixtures (copied from tests/test_first_person_context_serving.py
# so this gate does not depend on another test module's internals).
# ---------------------------------------------------------------------------

SPAN_TEXT_ONE = (
    "Suffering is not a punishment that existence hands to you; it is a call to awaken "
    "to the resistance you carry inside yourself every single day."
)


def _make_span(text: str = SPAN_TEXT_ONE) -> SourceSpan:
    span_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    video_id = "vid_test_1"
    guru_id = "krishnaji"
    return SourceSpan(
        corpus_version="ctx-v1",
        guru_id=guru_id,
        video_id=video_id,
        source_asset_id=video_id,
        source_span_id=make_source_span_id(
            guru_id=guru_id,
            video_id=video_id,
            corpus_version="ctx-v1",
            word_start=0,
            word_end=6,
            transcript_hash=span_hash,
        ),
        parent_unit_id="parent_101",
        turn_id="turn_0",
        turn_index=0,
        source_span_index=0,
        start_ms=0,
        end_ms=900,
        word_start=0,
        word_end=6,
        speaker_id=guru_id,
        speaker_role=SpeakerRole.GURU,
        speaker_verified=True,
        voice_verification_method="ecapa_voxceleb_span_slice_v2",
        voice_model_revision="synthetic-model-rev",
        voice_score=0.91,
        voice_margin=0.22,
        voice_threshold_applied={"cosine_floor": 0.75, "margin_threshold": 0.15},
        voice_calibration_id="synthetic-calibration-v1",
        voice_window_check="pass",
        voice_verified_at="2026-11-02T00:00:00Z",
        speaker_verification_status="verified",
        source_transcript_text=text,
        verbatim_text=text,
        transcript_hash=span_hash,
        source_text_hash=clip_text_hash(text),
        boundary_status=BoundaryStatus.VERIFIED,
        completeness_status=CompletenessStatus.COMPLETE,
        rights_cleared=True,
        domain_rights_status="licensed",
        caption_status="auto_transcript",
        provenance_kind=ProvenanceKind.SPEECH_TURN_SPAN,
        source_url=f"https://www.youtube.com/watch?v={video_id}",
        answer_role=AnswerRole.DIRECT,
    )


def _make_context(span: SourceSpan) -> ParentContext:
    return ParentContext(
        parent=ParentUnit(
            corpus_version=span.corpus_version,
            guru_id=span.guru_id,
            video_id=span.video_id,
            parent_unit_id=span.parent_unit_id,
            ordered_source_span_ids=(span.source_span_id,),
            start_ms=span.start_ms,
            end_ms=span.end_ms,
            parent_text_hash=clip_text_hash(span.verbatim_text),
            speaker_ids=(span.guru_id,),
            speaker_continuity=True,
            boundary_status=BoundaryStatus.VERIFIED,
            completeness_status=CompletenessStatus.COMPLETE,
        ),
        spans=(span,),
        hit_span_ids=(span.source_span_id,),
        score=0.95,
    )


# ---------------------------------------------------------------------------
# Harness plumbing
# ---------------------------------------------------------------------------


class _RecordingPipeline(FirstPersonPipeline):
    """Records the outcome event each exit emits, so the gate sees the reason too."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.events: list[dict[str, Any]] = []

    def _log_and_count(
        self,
        status: str,
        latency_ms: float,
        confidence: float,
        n_quarantined: int,
        n_citations: int,
        reason: str,
        llm_tokens: int,
    ) -> None:
        self.events.append(
            {
                "status": status,
                "confidence": round(float(confidence), 6),
                "n_quarantined": n_quarantined,
                "n_citations": n_citations,
                "reason": reason,
                "llm_tokens": int(llm_tokens),
            }
        )
        super()._log_and_count(
            status, latency_ms, confidence, n_quarantined, n_citations, reason, llm_tokens
        )


def _new_pipeline(**kwargs: Any) -> _RecordingPipeline:
    store = MagicMock()
    store.collection = "first_person_v1"
    redis = MagicMock()
    redis.get.return_value = None
    return _RecordingPipeline(store=store, redis_client=redis, **kwargs)


@pytest.fixture(autouse=True)
def _deterministic_settings(monkeypatch):
    """Pin every flag the split touches, so the golden describes this code alone."""
    pins = {
        "first_person_mode": "retrieval_only",
        "first_person_answerability_check_enabled": False,
        "first_person_speculative_parallelism_enabled": False,
        "first_person_relevance_gate_enabled": False,
        "first_person_relevance_min_score": 3,
        "first_person_llm_rerank_enabled": False,
        "first_person_content_quality_gate_enabled": False,
        "first_person_boundary_guard_enabled": False,
        "first_person_context_harness_enabled": False,
        "first_person_context_collection": "",
        "first_person_context_terminal_enabled": False,
        "first_person_facet_split_enabled": False,
        "first_person_editorial_set_selection_enabled": False,
        "first_person_enrichment_window_enabled": False,
        "first_person_graph_expansion_enabled": False,
        "first_person_abstain_related_clips_enabled": False,
        "first_person_serve_weak_match": True,
        "first_person_primary_mode": True,
        "is_production": False,
    }
    for name, value in pins.items():
        monkeypatch.setattr(settings, name, value)
    # No network in a characterization gate.
    monkeypatch.setattr(
        "services.first_person_pipeline.is_youtube_video_available", lambda _vid: True
    )
    for target in (
        "services.first_person_pipeline.source_is_authoritatively_licensed",
        "services.first_person_context_harness.source_is_authoritatively_licensed",
        "services.first_person_context_store.source_is_authoritatively_licensed",
    ):
        monkeypatch.setattr(
            target, lambda **kwargs: kwargs.get("domain_rights_status") == "licensed"
        )


Scenario = Callable[[pytest.MonkeyPatch], tuple[_RecordingPipeline, dict[str, Any]]]


def _scenario_crisis_redirect(monkeypatch) -> tuple[_RecordingPipeline, dict[str, Any]]:
    pipeline = _new_pipeline()
    return pipeline, {"query": "I want to kill myself today"}


def _scenario_topic_blocked_political(monkeypatch) -> tuple[_RecordingPipeline, dict[str, Any]]:
    pipeline = _new_pipeline()
    return pipeline, {"query": "Which party should I vote for in the election?"}


def _scenario_topic_blocked_safety(monkeypatch) -> tuple[_RecordingPipeline, dict[str, Any]]:
    pipeline = _new_pipeline()
    return pipeline, {"query": "My husband hits me every night, what should I do?"}


def _scenario_serving_contract_violation(
    monkeypatch,
) -> tuple[_RecordingPipeline, dict[str, Any]]:
    pipeline = _new_pipeline()
    monkeypatch.setattr(
        pipeline, "_serving_contract_error", lambda: "legacy_store_points_at_context_collection"
    )
    return pipeline, {"query": "What causes suffering?"}


def _cache_roundtrip(pipeline: _RecordingPipeline) -> None:
    """Serve once so the tail writes the cache entry, then replay from it."""
    stored: dict[str, Any] = {}
    pipeline._redis.set.side_effect = lambda key, value, ex=None: stored.__setitem__(key, value)
    tensor = [1.0, 0.0]
    pipeline._store.search_hybrid.return_value = [_clip(point_id="p-cached")]
    first = pipeline.execute(
        query="What causes suffering?", query_dense_vector=tensor, cache_bypass=False
    )
    assert first.citations and first.citations[0]["point_id"] == "p-cached"
    pipeline.events.clear()
    pipeline._redis.get.side_effect = lambda key: stored.get(key)
    pipeline._store.search_hybrid.reset_mock()


def _scenario_exact_cache_hit(monkeypatch) -> tuple[_RecordingPipeline, dict[str, Any]]:
    pipeline = _new_pipeline()
    _cache_roundtrip(pipeline)
    pipeline._store.points_servable.return_value = True
    return pipeline, {"query": "What causes suffering?", "cache_bypass": False}


def _scenario_exact_cache_hit_revoked_clip(
    monkeypatch,
) -> tuple[_RecordingPipeline, dict[str, Any]]:
    pipeline = _new_pipeline()
    _cache_roundtrip(pipeline)
    pipeline._store.points_servable.return_value = False
    pipeline._store.search_hybrid.return_value = []
    return pipeline, {"query": "What causes suffering?", "cache_bypass": False}


def _scenario_no_verified_clips(monkeypatch) -> tuple[_RecordingPipeline, dict[str, Any]]:
    pipeline = _new_pipeline()
    pipeline._store.search_hybrid.return_value = []
    return pipeline, {"query": "What causes suffering?"}


def _scenario_retrieval_error(monkeypatch) -> tuple[_RecordingPipeline, dict[str, Any]]:
    pipeline = _new_pipeline()
    pipeline._store.search_hybrid.side_effect = RuntimeError("qdrant unavailable")
    return pipeline, {"query": "What causes suffering?"}


def _scenario_answerability_no(monkeypatch) -> tuple[_RecordingPipeline, dict[str, Any]]:
    pipeline = _new_pipeline()
    pipeline._store.search_hybrid.return_value = [_clip()]
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", True)
    monkeypatch.setattr(
        "services.first_person_pipeline._answerability_check", lambda *a, **k: False
    )
    return pipeline, {"query": "What causes suffering?"}


def _scenario_answerability_indeterminate(
    monkeypatch,
) -> tuple[_RecordingPipeline, dict[str, Any]]:
    pipeline = _new_pipeline()
    pipeline._store.search_hybrid.return_value = [_clip()]
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", True)
    monkeypatch.setattr("services.first_person_pipeline._answerability_check", lambda *a, **k: None)
    return pipeline, {"query": "What causes suffering?"}


def _scenario_relevance_below_min(monkeypatch) -> tuple[_RecordingPipeline, dict[str, Any]]:
    pipeline = _new_pipeline(calibration_profile=PROFILE)
    pipeline._store.search_hybrid.return_value = [_clip()]
    monkeypatch.setattr(settings, "first_person_relevance_gate_enabled", True)
    monkeypatch.setattr("services.first_person_pipeline._relevance_select", lambda *a, **k: None)
    return pipeline, {"query": "What causes suffering?"}


def _scenario_relevance_indeterminate(monkeypatch) -> tuple[_RecordingPipeline, dict[str, Any]]:
    pipeline = _new_pipeline(calibration_profile=PROFILE)
    pipeline._store.search_hybrid.return_value = [_clip()]
    monkeypatch.setattr(settings, "first_person_relevance_gate_enabled", True)
    monkeypatch.setattr(
        "services.first_person_pipeline._relevance_select",
        lambda *a, **k: _RELEVANCE_INDETERMINATE,
    )
    return pipeline, {"query": "What causes suffering?"}


def _scenario_success_direct(monkeypatch) -> tuple[_RecordingPipeline, dict[str, Any]]:
    pipeline = _new_pipeline(calibration_profile=PROFILE)
    pipeline._store.search_hybrid.return_value = [_clip()]
    return pipeline, {"query": "What causes suffering?"}


def _scenario_weak_match_no_profile(monkeypatch) -> tuple[_RecordingPipeline, dict[str, Any]]:
    pipeline = _new_pipeline(calibration_profile=None)
    pipeline._store.search_hybrid.return_value = [_clip()]
    return pipeline, {"query": "What causes suffering?"}


def _scenario_context_harness_direct_serve(
    monkeypatch,
) -> tuple[_RecordingPipeline, dict[str, Any]]:
    context_store = MagicMock()
    context_store.retrieve.return_value = [_make_context(_make_span())]
    pipeline = _RecordingPipeline(
        store=MagicMock(),
        redis_client=MagicMock(get=MagicMock(return_value=None)),
        context_store=context_store,
        calibration_profile={"threshold": 0.45, "score_kind": "cosine", "claims": "conformance"},
    )
    monkeypatch.setattr(settings, "first_person_context_harness_enabled", True)
    return pipeline, {"query": "What is the nature of suffering?", "teacher_id": "krishnaji"}


def _scenario_context_harness_terminal_abstain(
    monkeypatch,
) -> tuple[_RecordingPipeline, dict[str, Any]]:
    context_store = MagicMock()
    context_store.retrieve.return_value = []
    pipeline = _RecordingPipeline(
        store=MagicMock(),
        redis_client=MagicMock(get=MagicMock(return_value=None)),
        context_store=context_store,
    )
    monkeypatch.setattr(settings, "first_person_context_harness_enabled", True)
    monkeypatch.setattr(settings, "first_person_context_terminal_enabled", True)
    return pipeline, {"query": "What is the nature of suffering?"}


def _scenario_compound_delegates(monkeypatch) -> tuple[_RecordingPipeline, dict[str, Any]]:
    pipeline = _new_pipeline()
    pipeline._store.search_hybrid.return_value = [_clip()]
    monkeypatch.setattr(settings, "first_person_facet_split_enabled", True)
    monkeypatch.setattr(
        "services.first_person_pipeline._decompose_query_facets",
        lambda query, llm, token_sink=None: ["what causes suffering", "what ends it"],
    )
    return pipeline, {"query": "What causes suffering and what ends it?"}


SCENARIOS: dict[str, Scenario] = {
    "answerability_indeterminate": _scenario_answerability_indeterminate,
    "answerability_no": _scenario_answerability_no,
    "compound_delegates": _scenario_compound_delegates,
    "context_harness_direct_serve": _scenario_context_harness_direct_serve,
    "context_harness_terminal_abstain": _scenario_context_harness_terminal_abstain,
    "crisis_redirect": _scenario_crisis_redirect,
    "exact_cache_hit": _scenario_exact_cache_hit,
    "exact_cache_hit_revoked_clip": _scenario_exact_cache_hit_revoked_clip,
    "no_verified_clips": _scenario_no_verified_clips,
    "relevance_below_min": _scenario_relevance_below_min,
    "relevance_indeterminate": _scenario_relevance_indeterminate,
    "retrieval_error": _scenario_retrieval_error,
    "serving_contract_violation": _scenario_serving_contract_violation,
    "success_direct": _scenario_success_direct,
    "topic_blocked_political": _scenario_topic_blocked_political,
    "topic_blocked_safety": _scenario_topic_blocked_safety,
    "weak_match_no_profile": _scenario_weak_match_no_profile,
}


def _normalize(value: Any) -> Any:
    """Drop clock-derived fields, digest text fields, and round floats."""
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in sorted(value.items()):
            if key in CLOCK_FIELDS:
                continue
            if key in TEXT_FIELDS and isinstance(item, str):
                normalized[key] = {
                    "sha256": hashlib.sha256(item.encode("utf-8")).hexdigest(),
                    "chars": len(item),
                }
                continue
            normalized[key] = _normalize(item)
        return normalized
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, float):
        return round(value, 6)
    return value


def _store_summary(pipeline: _RecordingPipeline) -> dict[str, Any]:
    """The retrieval call the step made is behaviour: keep its arguments."""
    search = pipeline._store.search_hybrid
    summary: dict[str, Any] = {"search_hybrid_calls": search.call_count}
    if search.call_count:
        kwargs = dict(search.call_args.kwargs)
        summary["search_hybrid_kwargs"] = _normalize(
            {
                key: (
                    f"vector[{len(value)}]"
                    if key.startswith("query_") and value is not None
                    else value
                )
                for key, value in kwargs.items()
            }
        )
    summary["points_servable_calls"] = pipeline._store.points_servable.call_count
    return summary


def _record(monkeypatch: pytest.MonkeyPatch, scenario: Scenario) -> dict[str, Any]:
    pipeline, execute_kwargs = scenario(monkeypatch)
    kwargs = {"query_dense_vector": [1.0, 0.0], "cache_bypass": True, **execute_kwargs}

    # Observation only: the wrapper delegates to the real method and records that
    # the compound exit was taken, so a silent route change cannot pass unseen.
    calls: dict[str, int] = {"compound": 0}
    real_compound = pipeline._execute_compound

    def _compound(*args: Any, **kw: Any):
        calls["compound"] += 1
        return real_compound(*args, **kw)

    monkeypatch.setattr(pipeline, "_execute_compound", _compound)

    result = pipeline.execute(**kwargs)
    return {
        "result": _normalize(result.to_dict()),
        "events": _normalize(pipeline.events),
        "store": _store_summary(pipeline),
        "compound_called": calls["compound"],
    }


@pytest.mark.parametrize("case", sorted(SCENARIOS))
def test_execute_matches_recorded_golden(case: str, monkeypatch) -> None:
    observed = _record(monkeypatch, SCENARIOS[case])
    golden_path = GOLDEN_DIR / f"{case}.json"

    if UPDATE:
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(
            json.dumps(observed, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        pytest.skip(f"recorded {golden_path.name}")

    assert golden_path.is_file(), (
        f"missing golden for {case!r}; record it on the pre-T7-01 code with FP_GOLDEN_UPDATE=1"
    )
    expected = json.loads(golden_path.read_text(encoding="utf-8"))
    assert observed == expected, f"{case}: behaviour differs from the recorded golden"


def test_matrix_covers_every_exit_the_split_moves() -> None:
    """Guard against a scenario silently disappearing from the matrix."""
    assert set(SCENARIOS) == {
        "answerability_indeterminate",
        "answerability_no",
        "compound_delegates",
        "context_harness_direct_serve",
        "context_harness_terminal_abstain",
        "crisis_redirect",
        "exact_cache_hit",
        "exact_cache_hit_revoked_clip",
        "no_verified_clips",
        "relevance_below_min",
        "relevance_indeterminate",
        "retrieval_error",
        "serving_contract_violation",
        "success_direct",
        "topic_blocked_political",
        "topic_blocked_safety",
        "weak_match_no_profile",
    }
