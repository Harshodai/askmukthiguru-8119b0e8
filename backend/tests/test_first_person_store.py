"""
Unit tests for FirstPersonStore (D3 Versioned Store).
"""

from unittest.mock import MagicMock
import pytest
from qdrant_client.http import models

from app.config import settings
from services.first_person_store import (
    FirstPersonStore,
    make_first_person_point_id,
    validate_clip_entry,
    deduplicate_clips_by_video,
)


def test_make_first_person_point_id_deterministic():
    h = "a" * 64
    id1 = make_first_person_point_id(h, 1000, 5000)
    id2 = make_first_person_point_id(h, 1000, 5000)
    id3 = make_first_person_point_id(h, 1000, 6000)

    assert id1 == id2
    assert id1 != id3
    assert len(id1) == 36  # Standard UUID string representation


def test_validate_clip_entry_success():
    valid_clip = {
        "video_id": "vid123",
        "start_ms": 12000,
        "end_ms": 18000,
        "speaker": "Sri Preethaji",
        "transcript_hash": "f" * 64,
        "verbatim_text": "Suffering is not a fact; it is only a perception.",
    }
    # Should not raise
    validate_clip_entry(valid_clip)


@pytest.mark.parametrize("speaker", ["Host / Questioner", "both", "unknown", "Host"])
def test_validate_clip_entry_rejects_speaker_outside_allowlist(speaker):
    """(c) speaker outside {Sri Preethaji, Sri Krishnaji} is never indexable."""
    clip = {
        "video_id": "vid123",
        "start_ms": 12000,
        "end_ms": 18000,
        "speaker": speaker,
        "transcript_hash": "f" * 64,
        "verbatim_text": "Can you explain what suffering is?",
    }
    with pytest.raises(ValueError, match="speaker must be one of"):
        validate_clip_entry(clip)


def test_validate_clip_entry_rejects_negative_or_inverted_timestamps():
    clip_neg = {
        "video_id": "vid123",
        "start_ms": -10,
        "end_ms": 1000,
        "speaker": "Sri Krishnaji",
        "transcript_hash": "f" * 64,
        "verbatim_text": "Peace is within you.",
    }
    with pytest.raises(ValueError, match="start_ms must be non-negative"):
        validate_clip_entry(clip_neg)

    clip_inv = {
        "video_id": "vid123",
        "start_ms": 5000,
        "end_ms": 4000,
        "speaker": "Sri Krishnaji",
        "transcript_hash": "f" * 64,
        "verbatim_text": "Peace is within you.",
    }
    with pytest.raises(ValueError, match="end_ms .* must be strictly greater"):
        validate_clip_entry(clip_inv)


def test_validate_clip_entry_rejects_bad_hash():
    clip_bad_hash = {
        "video_id": "vid123",
        "start_ms": 1000,
        "end_ms": 2000,
        "speaker": "Sri Krishnaji",
        "transcript_hash": "short_hash",
        "verbatim_text": "Peace.",
    }
    with pytest.raises(ValueError, match="transcript_hash must be a 64-char"):
        validate_clip_entry(clip_bad_hash)


def test_deduplicate_clips_by_video():
    clips = [
        {"video_id": "vid_A", "score": 0.95, "text": "A1"},
        {"video_id": "vid_A", "score": 0.90, "text": "A2"},
        {"video_id": "vid_B", "score": 0.85, "text": "B1"},
        {"video_id": "vid_C", "score": 0.80, "text": "C1"},
        {"video_id": "vid_B", "score": 0.75, "text": "B2"},
    ]

    deduped = deduplicate_clips_by_video(clips, max_clips=3)
    assert len(deduped) == 3
    assert [d["video_id"] for d in deduped] == ["vid_A", "vid_B", "vid_C"]
    assert [d["text"] for d in deduped] == ["A1", "B1", "C1"]


def test_upsert_clips(monkeypatch):
    client = MagicMock()
    store = FirstPersonStore(collection="first_person_v1", client=client)

    clips = [
        {
            "video_id": "v1",
            "start_ms": 1000,
            "end_ms": 5000,
            "speaker": "Sri Krishnaji",
            "transcript_hash": "0" * 64,
            "verbatim_text": "Life is a flow of relationships.",
            "teacher_id": "krishnaji",
            "teacher_ids": ["krishnaji"],
            "rights_cleared": True,
            "caption_status": "auto_transcript",
        }
    ]
    passage_dense = [[0.1] * 1024]

    count = store.upsert_clips(clips, passage_dense_vectors=passage_dense)
    assert count == 1
    client.upsert.assert_called_once()
    args, kwargs = client.upsert.call_args
    assert kwargs["collection_name"] == "first_person_v1"
    points = kwargs["points"]
    assert len(points) == 1
    assert "passage_dense" in points[0].vector
    # question_dense is never set when no real question embedding is provided.
    assert "question_dense" not in points[0].vector
    assert points[0].payload["video_id"] == "v1"
    assert points[0].payload["teacher_id"] == "krishnaji"
    assert points[0].payload["rights_cleared"] is True
    assert points[0].payload["caption_status"] == "auto_transcript"


def test_upsert_clips_teacher_id_has_no_default():
    """teacher_id/teacher_ids come from the clip itself — no 'both' default."""
    client = MagicMock()
    store = FirstPersonStore(collection="first_person_v1", client=client)

    clips = [
        {
            "video_id": "v1",
            "start_ms": 1000,
            "end_ms": 5000,
            "speaker": "Sri Krishnaji",
            "transcript_hash": "0" * 64,
            "verbatim_text": "Life is a flow of relationships.",
        }
    ]
    store.upsert_clips(clips, passage_dense_vectors=[[0.1] * 1024])
    points = client.upsert.call_args.kwargs["points"]
    assert points[0].payload["teacher_id"] is None
    assert points[0].payload["teacher_ids"] is None


def _mock_point(point_id, score, video_id, vector=None):
    p = MagicMock()
    p.id = point_id
    p.score = score
    p.payload = {"video_id": video_id, "verbatim_text": f"Text {video_id}"}
    p.vector = vector or {}
    return p


def test_search_hybrid():
    client = MagicMock()
    store = FirstPersonStore(collection="first_person_v1", client=client)

    p1 = _mock_point("id1", 0.92, "vid_1", vector={"passage_dense": [0.1] * 4})
    p2 = _mock_point("id2", 0.88, "vid_1", vector={"passage_dense": [0.2] * 4})
    p3 = _mock_point("id3", 0.85, "vid_2", vector={"passage_dense": [0.3] * 4})

    client.query_points.return_value = MagicMock(points=[p1, p2, p3])

    res = store.search_hybrid(
        query_dense_vector=[0.1] * 1024,
        query_sparse_vector={"indices": [1, 2], "values": [0.5, 0.8]},
        limit=5,
        dedup_limit=2,
    )

    assert len(res) == 2
    assert res[0]["video_id"] == "vid_1"
    assert res[0]["passage_dense"] == [0.1] * 4
    assert res[1]["video_id"] == "vid_2"
    client.query_points.assert_called_once()
    call_kwargs = client.query_points.call_args.kwargs
    assert call_kwargs["with_vectors"] == ["passage_dense"]


def test_search_hybrid_prefetches_only_passage_dense_and_sparse():
    """question_dense must never be prefetched (it double-counts passage RRF)."""
    client = MagicMock()
    store = FirstPersonStore(collection="first_person_v1", client=client)
    client.query_points.return_value = MagicMock(points=[])

    store.search_hybrid(
        query_dense_vector=[0.1] * 1024,
        query_sparse_vector={"indices": [1], "values": [0.5]},
    )

    prefetch = client.query_points.call_args.kwargs["prefetch"]
    used = {p.using for p in prefetch}
    assert used == {"passage_dense", "passage_sparse"}


def test_search_hybrid_filters_rights_cleared_by_default(monkeypatch):
    """(i) rights_cleared filter present by default, absent when serve_unregistered=True."""
    client = MagicMock()
    store = FirstPersonStore(collection="first_person_v1", client=client)
    client.query_points.return_value = MagicMock(points=[])

    monkeypatch.setattr(settings, "first_person_serve_unregistered", False)
    store.search_hybrid(query_dense_vector=[0.1] * 1024)
    prefetch = client.query_points.call_args.kwargs["prefetch"]
    keys = {c.key for c in prefetch[0].filter.must}
    assert "rights_cleared" in keys

    monkeypatch.setattr(settings, "first_person_serve_unregistered", True)
    store.search_hybrid(query_dense_vector=[0.1] * 1024)
    prefetch = client.query_points.call_args.kwargs["prefetch"]
    keys = {c.key for c in prefetch[0].filter.must}
    assert "rights_cleared" not in keys


def test_search_hybrid_teacher_filter_uses_teacher_id(monkeypatch):
    """(h) the teacher filter matches on the clip's own teacher_id value."""
    client = MagicMock()
    store = FirstPersonStore(collection="first_person_v1", client=client)
    client.query_points.return_value = MagicMock(points=[])
    monkeypatch.setattr(settings, "first_person_serve_unregistered", True)

    store.search_hybrid(query_dense_vector=[0.1] * 1024, teacher_id="preethaji")
    prefetch = client.query_points.call_args.kwargs["prefetch"]
    conditions = {c.key: c.match.value for c in prefetch[0].filter.must}
    assert conditions["teacher_id"] == "preethaji"


def test_rrf_prefetch_depth_matches_bakeoff_b_r0():
    """B.R0 fused dense+sparse ranks at depth 60; a 12-deep prefetch fuses a much
    smaller candidate pool than the benchmarked retriever."""
    from unittest.mock import MagicMock

    from services.first_person_store import FirstPersonStore

    client = MagicMock()
    client.query_points.return_value.points = []
    FirstPersonStore(collection="first_person_v1", client=client).search_hybrid(
        query_dense_vector=[0.1] * 4, query_sparse_vector={"indices": [1], "values": [0.5]}, limit=6, dedup_limit=3
    )
    prefetch = client.query_points.call_args.kwargs["prefetch"]
    assert all(p.limit >= 60 for p in prefetch)


def _point(pid, **payload):
    return models.Record(id=pid, payload={"first_person_eligible": True, "rights_cleared": True, **payload})


@pytest.mark.parametrize(
    "records, expected",
    [
        ([_point("a"), _point("b")], True),
        ([_point("a")], False),  # b was deleted from the index
        ([_point("a"), _point("b", rights_cleared=False)], False),  # rights revoked
        ([_point("a"), _point("b", first_person_eligible=False)], False),  # quarantined
    ],
)
def test_points_servable_mirrors_the_search_filter(records, expected, monkeypatch):
    monkeypatch.setattr(settings, "first_person_serve_unregistered", False)
    client = MagicMock()
    client.retrieve.return_value = records
    store = FirstPersonStore(collection="first_person_v1", client=client)
    assert store.points_servable(["a", "b"]) is expected
