"""T6-02 (MEM-002): Memory signals on the first-person teaching lane.

Tests that FirstPersonPipeline accepts memory_signals, uses them to promote
unseen clips over recently seen clips for returning seekers, and NEVER alters
verbatim_text or clip payloads.
"""

from unittest.mock import MagicMock

from services.first_person_pipeline import FirstPersonPipeline, _apply_memory_reranking


def test_apply_memory_reranking_promotes_unseen_clips():
    """Unseen clips should be placed ahead of already-seen clips."""
    clip1 = {
        "id": "c1",
        "video_id": "vid_seen_1",
        "verbatim_text": "Teaching on meditation by Sri Krishnaji.",
        "teacher_id": "krishnaji",
    }
    clip2 = {
        "id": "c2",
        "video_id": "vid_unseen_2",
        "verbatim_text": "Teaching on relationship awareness by Sri Preethaji.",
        "teacher_id": "preethaji",
    }
    clips = [clip1, clip2]
    memory_signals = {"seen_video_ids": ["vid_seen_1"]}

    reranked = _apply_memory_reranking(clips, memory_signals)

    # clip2 (unseen) should be moved ahead of clip1 (seen)
    assert reranked[0]["id"] == "c2"
    assert reranked[1]["id"] == "c1"


def test_apply_memory_reranking_preserves_verbatim_text_byte_identically():
    """T6-02 invariant: memory signals must never alter verbatim_text or clip attributes."""
    original_text = "Verbatim teaching clip text that must remain exactly as stored."
    clip = {
        "id": "c1",
        "video_id": "vid_1",
        "verbatim_text": original_text,
        "teacher_id": "krishnaji",
        "start_ms": 1000,
        "end_ms": 5000,
    }
    memory_signals = {"seen_video_ids": ["vid_other"], "stated_interests": ["meditation"]}

    reranked = _apply_memory_reranking([clip], memory_signals)

    assert reranked[0]["verbatim_text"] == original_text
    assert reranked[0] == clip


def test_apply_memory_reranking_noop_when_signals_none_or_empty():
    """When memory_signals is None or empty, original order is preserved unchanged."""
    clip1 = {"id": "c1", "video_id": "v1", "verbatim_text": "Text 1"}
    clip2 = {"id": "c2", "video_id": "v2", "verbatim_text": "Text 2"}
    clips = [clip1, clip2]

    assert _apply_memory_reranking(clips, None) == clips
    assert _apply_memory_reranking(clips, {}) == clips
    assert _apply_memory_reranking(clips, {"seen_video_ids": []}) == clips


def test_pipeline_execute_accepts_memory_signals_and_sets_cache_bypass():
    """pipeline.execute should accept memory_signals and bypass shared cache when present."""
    pipeline = FirstPersonPipeline(
        store=MagicMock(),
        llm_service=None,
    )
    # Mock _cache_scope to observe cache_bypass
    scope_mock = MagicMock(return_value=(True, None, None))
    pipeline._cache_scope = scope_mock
    pipeline._crisis_preemption = MagicMock(return_value=None)
    pipeline._topic_rail_block = MagicMock(return_value=None)
    pipeline._serving_contract_refusal = MagicMock(return_value=None)
    pipeline._cached_replay = MagicMock(return_value=None)

    # Mock outcome of retrieval
    from services.first_person_pipeline import FirstPersonPipelineResult, _RetrievalOutcome

    pipeline._retrieve_with_answerability_gate = MagicMock(
        return_value=_RetrievalOutcome(
            result=FirstPersonPipelineResult(
                answer_text="Abstained",
                citations=[],
                status="abstained",
                is_direct_answer=False,
                latency_ms=1.0,
                abstain_reason="no_clips_found",
            )
        )
    )

    memory_signals = {"seen_video_ids": ["vid_previous"]}
    res = pipeline.execute(
        query="What is fear?",
        query_dense_vector=[0.1] * 1024,
        memory_signals=memory_signals,
    )

    assert res.status == "abstained"
    scope_mock.assert_called_once_with(cache_bypass=True)
