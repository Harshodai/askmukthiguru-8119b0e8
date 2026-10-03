"""
Unit tests for FirstPersonStore (D3 Versioned Store).
"""

import hashlib
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from qdrant_client.http import models

from app.config import settings
from services.first_person_store import (
    FirstPersonStore,
    deduplicate_clips_by_video,
    make_first_person_point_id,
    validate_clip_entry,
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
    text = "Suffering is not a fact; it is only a perception."
    valid_clip = {
        "video_id": "vid123",
        "start_ms": 12000,
        "end_ms": 18000,
        "speaker": "Sri Preethaji",
        "transcript_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "verbatim_text": text,
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


def test_deduplicate_clips_by_video_distinct_spans():
    clips = [
        {"video_id": "vid_A", "score": 0.95, "text": "A_doctrine", "start_ms": 10000},
        {
            "video_id": "vid_A",
            "score": 0.90,
            "text": "A_close",
            "start_ms": 25000,
        },  # gap 15s < 30s -> rejected
        {
            "video_id": "vid_A",
            "score": 0.88,
            "text": "A_practice",
            "start_ms": 90000,
        },  # gap 80s >= 30s -> accepted
        {
            "video_id": "vid_A",
            "score": 0.85,
            "text": "A_third",
            "start_ms": 180000,
        },  # already have 2 -> rejected
        {"video_id": "vid_B", "score": 0.80, "text": "B1", "start_ms": 5000},
    ]

    deduped = deduplicate_clips_by_video(
        clips, max_clips=4, allow_same_video_distinct_spans=True, min_span_gap_ms=30000
    )
    assert len(deduped) == 3
    assert [d["text"] for d in deduped] == ["A_doctrine", "A_practice", "B1"]
    assert [d["video_id"] for d in deduped] == ["vid_A", "vid_A", "vid_B"]


def test_upsert_clips(monkeypatch):
    client = MagicMock()
    store = FirstPersonStore(collection="first_person_v1", client=client)

    text = "Life is a flow of relationships."
    clips = [
        {
            "video_id": "v1",
            "start_ms": 1000,
            "end_ms": 5000,
            "speaker": "Sri Krishnaji",
            "transcript_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "verbatim_text": text,
            "teacher_id": "krishnaji",
            "teacher_ids": ["krishnaji"],
            "rights_cleared": True,
            "caption_status": "auto_transcript",
        }
    ]
    passage_dense = [[0.1] * 1024]

    _stub_r2_readback(client)
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


def test_upsert_clips_recomputes_hash_when_cleaner_changes_text():
    """Binding rule (lessons.md L-INTEGRITY-HASH-MISMATCH-1): if the ASR cleaner
    modifies verbatim_text during indexing, transcript_hash and the point ID must
    both derive from the CLEANED text — a stale hash fails the serve-time gate."""
    client = MagicMock()
    store = FirstPersonStore(collection="first_person_v1", client=client)

    raw = "So, So the truth is simply this: you are not your thoughts."
    # Stale hash of the RAW text, as an upstream producer might hand us.
    clip = {
        "video_id": "v1",
        "start_ms": 1000,
        "end_ms": 5000,
        "speaker": "Sri Krishnaji",
        "transcript_hash": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "verbatim_text": raw,
        "teacher_id": "krishnaji",
        "teacher_ids": ["krishnaji"],
        "rights_cleared": True,
    }
    from ingest.verbatim.asr_cleaner import clean_verbatim_text

    cleaned = clean_verbatim_text(raw)
    assert cleaned != raw  # fixture must actually exercise the recompute path

    _stub_r2_readback(client)
    count = store.upsert_clips([clip], passage_dense_vectors=[[0.1] * 1024])
    assert count == 1
    point = client.upsert.call_args.kwargs["points"][0]
    assert point.payload["verbatim_text"] == cleaned
    assert point.payload["transcript_hash"] == hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
    assert point.id == make_first_person_point_id(
        point.payload["transcript_hash"], point.payload["start_ms"], point.payload["end_ms"]
    )


def test_upsert_clips_teacher_id_has_no_default():
    """teacher_id/teacher_ids come from the clip itself — no 'both' default."""
    client = MagicMock()
    store = FirstPersonStore(collection="first_person_v1", client=client)

    text = "Life is a flow of relationships."
    clips = [
        {
            "video_id": "v1",
            "start_ms": 1000,
            "end_ms": 5000,
            "speaker": "Sri Krishnaji",
            "transcript_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "verbatim_text": text,
        }
    ]
    _stub_r2_readback(client)
    store.upsert_clips(clips, passage_dense_vectors=[[0.1] * 1024])
    points = client.upsert.call_args.kwargs["points"]
    assert points[0].payload["teacher_id"] is None
    assert points[0].payload["teacher_ids"] is None


def _stub_r2_readback(client):
    """R2 post-write read-back for mocked clients: echo the points from the last
    upsert call, exactly as a real Qdrant would return them."""

    def _retrieve(**kwargs):
        pts = client.upsert.call_args.kwargs["points"]
        wanted = set(kwargs["ids"])
        return [
            SimpleNamespace(id=str(p.id), payload=p.payload, vector=p.vector)
            for p in pts
            if str(p.id) in wanted
        ]

    client.retrieve.side_effect = _retrieve


def _r2_clip(text="Life is a flow of relationships."):
    return {
        "video_id": "v1",
        "start_ms": 1000,
        "end_ms": 5000,
        "speaker": "Sri Krishnaji",
        "transcript_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "verbatim_text": text,
        "teacher_id": "krishnaji",
        "teacher_ids": ["krishnaji"],
        "rights_cleared": True,
    }


def test_upsert_clips_r2_rejects_wrong_dense_dim():
    """R2 pre-write guard: a dense vector that does not match the declared
    collection dimension fails closed before any write (audit A-5)."""
    client = MagicMock()
    store = FirstPersonStore(collection="first_person_v1", client=client)

    with pytest.raises(ValueError, match=r"\[R2\] passage_dense dim"):
        store.upsert_clips([_r2_clip()], passage_dense_vectors=[[0.1] * 512])
    client.upsert.assert_not_called()


def test_upsert_clips_r2_catches_payload_id_drift(monkeypatch):
    """R2 pre-write guard: point ID must equal uuid5 recomputation from the
    payload actually being written (audit A-10 class drift fails closed)."""
    import services.first_person_store as fps

    real = fps.make_first_person_point_id
    calls = {"n": 0}

    def drifted(transcript_hash, start_ms, end_ms):
        calls["n"] += 1
        if calls["n"] == 1:
            return real(transcript_hash, start_ms, end_ms)
        return "00000000-0000-5000-8000-000000000000"

    monkeypatch.setattr(fps, "make_first_person_point_id", drifted)
    client = MagicMock()
    store = FirstPersonStore(collection="first_person_v1", client=client)

    with pytest.raises(ValueError, match=r"\[R2\] point id"):
        store.upsert_clips([_r2_clip()], passage_dense_vectors=[[0.1] * 1024])
    client.upsert.assert_not_called()


def test_upsert_clips_r2_readback_missing_point_fails_closed():
    """R2 read-back guard: if the written point does not come back after the
    upsert, raise — never return a success for a silently dropped point."""
    client = MagicMock()
    client.retrieve.return_value = []  # simulates silent drop post-write
    store = FirstPersonStore(collection="first_person_v1", client=client)

    with pytest.raises(ValueError, match=r"\[R2\] read-back missing"):
        store.upsert_clips([_r2_clip()], passage_dense_vectors=[[0.1] * 1024])
    client.upsert.assert_called_once()


def test_upsert_clips_r2_readback_wrong_dim_fails_closed():
    """R2 read-back guard: dense dim must still match after the write."""
    client = MagicMock()

    def _retrieve_with_short_vectors(**kwargs):
        pts = client.upsert.call_args.kwargs["points"]
        return [
            SimpleNamespace(
                id=str(p.id),
                payload=p.payload,
                vector={"passage_dense": [0.1] * 512},
            )
            for p in pts
        ]

    client.retrieve.side_effect = _retrieve_with_short_vectors
    store = FirstPersonStore(collection="first_person_v1", client=client)

    with pytest.raises(ValueError, match=r"\[R2\] read-back passage_dense dim"):
        store.upsert_clips([_r2_clip()], passage_dense_vectors=[[0.1] * 1024])


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
        query_dense_vector=[0.1] * 4,
        query_sparse_vector={"indices": [1], "values": [0.5]},
        limit=6,
        dedup_limit=3,
    )
    prefetch = client.query_points.call_args.kwargs["prefetch"]
    assert all(p.limit >= 60 for p in prefetch)


def _point(pid, **payload):
    return models.Record(
        id=pid, payload={"first_person_eligible": True, "rights_cleared": True, **payload}
    )


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
