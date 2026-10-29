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
    CANONICAL_VIDEO_IDS,
    FirstPersonStore,
    canonical_video_id,
    deduplicate_clips_by_video,
    make_first_person_point_id,
    store_canonical_clip_key,
    store_point_id_for_clip,
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


def test_store_point_id_for_clip_matches_written_id_when_cleaner_changes_text():
    """W1 tripwire regression (2026-10-11, clip idx 638 gQiIwfA3mlk): the mass
    driver derived expected IDs from the clip's raw pre-store transcript_hash
    while upsert_clips wrote cleaned-hash IDs. For the one clip with
    clean(raw)!=raw this yielded an unproducible expected ID vs the stored
    ID, firing the missing-point tripwire forever with pending=1.
    store_point_id_for_clip() must equal the written point ID, so a driver
    expected-set built from it trips nothing."""
    from ingest.verbatim.asr_cleaner import clean_verbatim_text

    raw = (
        "Earth communicates to the the trees, the trees communicate to the fellow "
        "trees and they also communicate to the mushrooms on the forest floor"
    )
    assert clean_verbatim_text(raw) != raw  # fixture must exercise the skew path
    clip = {
        "video_id": "gQiIwfA3mlk",
        "start_ms": 155120,
        "end_ms": 217640,
        "speaker": "Sri Preethaji",
        "transcript_hash": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "verbatim_text": raw,
        "teacher_id": "preethaji",
        "teacher_ids": ["preethaji"],
        "rights_cleared": True,
    }

    # The pre-fix driver derivation (raw hash) is unproducible by the store.
    stale_id = make_first_person_point_id(clip["transcript_hash"], clip["start_ms"], clip["end_ms"])

    client = MagicMock()
    store = FirstPersonStore(collection="first_person_v1", client=client)
    _stub_r2_readback(client)
    assert store.upsert_clips([clip], passage_dense_vectors=[[0.1] * 1024]) == 1
    point = client.upsert.call_args.kwargs["points"][0]

    assert point.id != stale_id  # the skew is real on this fixture
    assert point.id == store_point_id_for_clip(clip)  # helper agrees with store
    # Driver tripwire simulation: expected set from the helper is fully served.
    assert {store_point_id_for_clip(clip)} - {str(point.id)} == set()
    # Canonical key carries the cleaned write image.
    vid, text, thash = store_canonical_clip_key(clip)
    assert (vid, text, thash) == (
        "gQiIwfA3mlk",
        point.payload["verbatim_text"],
        point.payload["transcript_hash"],
    )


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
    assert all(p.limit >= 30 for p in prefetch)


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


def _jitter_clip(video_id, text, start_ms, end_ms):
    return {
        "video_id": video_id,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "speaker": "Sri Krishnaji",
        "transcript_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "verbatim_text": text,
        "teacher_id": "krishnaji",
        "teacher_ids": ["krishnaji"],
        "rights_cleared": True,
    }


def test_upsert_clips_drops_same_video_exact_duplicate_within_batch():
    """Audit 2026-10-04 §4 fix #1: same-video jitter twins (identical text,
    ±200 ms spans, hence distinct point IDs) collapse to the first in-batch."""
    client = MagicMock()
    store = FirstPersonStore(collection="first_person_v1", client=client)

    text = "Suffering is not a fact; it is only a perception."
    clips = [
        _jitter_clip("v1", text, 3040, 15200),
        _jitter_clip("v1", text, 3240, 15000),  # jitter twin of clips[0]
        _jitter_clip("v1", "Desire is the root of movement in thought.", 20000, 26000),
    ]
    vectors = [[0.1] * 1024, [0.2] * 1024, [0.3] * 1024]

    _stub_r2_readback(client)
    assert store.upsert_clips(clips, passage_dense_vectors=vectors) == 2
    points = client.upsert.call_args.kwargs["points"]
    assert len(points) == 2
    # Kept twin is the FIRST, with its own positional vector (no misalignment).
    assert points[0].payload["start_ms"] == 3040
    assert points[0].vector["passage_dense"] == [0.1] * 1024
    assert points[1].payload["start_ms"] == 20000
    assert points[1].vector["passage_dense"] == [0.3] * 1024


def test_upsert_clips_keeps_cross_video_identical_text():
    """Same teaching reused across discourses is legitimate repetition — the
    batch guard keys on (video_id, text), never bare text."""
    client = MagicMock()
    store = FirstPersonStore(collection="first_person_v1", client=client)

    text = "Suffering is not a fact; it is only a perception."
    clips = [
        _jitter_clip("v1", text, 3000, 15000),
        _jitter_clip("v2", text, 3000, 15000),
    ]

    _stub_r2_readback(client)
    assert store.upsert_clips(clips, passage_dense_vectors=[[0.1] * 1024] * 2) == 2


def test_upsert_clips_does_not_dedupe_across_batches():
    """Cross-batch twins are index-level dedup's job — a second upsert_clips
    call must still write (idempotent same-ID overwrite at worst)."""
    client = MagicMock()
    store = FirstPersonStore(collection="first_person_v1", client=client)

    text = "Suffering is not a fact; it is only a perception."
    _stub_r2_readback(client)
    assert (
        store.upsert_clips(
            [_jitter_clip("v1", text, 3000, 15000)],
            passage_dense_vectors=[[0.1] * 1024],
        )
        == 1
    )
    assert (
        store.upsert_clips(
            [_jitter_clip("v1", text, 3200, 15200)],
            passage_dense_vectors=[[0.1] * 1024],
        )
        == 1
    )
    assert client.upsert.call_count == 2


def test_upsert_clips_empty_batch_returns_zero_without_write():
    client = MagicMock()
    store = FirstPersonStore(collection="first_person_v1", client=client)
    assert store.upsert_clips([], passage_dense_vectors=[]) == 0
    client.upsert.assert_not_called()


def test_canonical_video_id_map_covers_reupload_pair():
    assert canonical_video_id("AQUZcU5L9xE") == "9id3ygnEhh8"
    assert canonical_video_id("9id3ygnEhh8") == "9id3ygnEhh8"  # canonical is fixed point
    assert canonical_video_id("unrelated123") == "unrelated123"
    assert CANONICAL_VIDEO_IDS  # map must not be empty


def test_upsert_clips_remaps_reupload_to_canonical_id():
    """Audit 2026-10-04 §4 fix #2: re-upload clip lands with canonical
    video_id/group_id/source_url; point ID is unchanged (video_id not in ID)."""
    client = MagicMock()
    store = FirstPersonStore(collection="first_person_v1", client=client)

    text = "When you actually get back from work, observe yourself."
    clip = _jitter_clip("AQUZcU5L9xE", text, 3900, 25500)
    clip["source_url"] = "https://www.youtube.com/watch?v=AQUZcU5L9xE"

    _stub_r2_readback(client)
    assert store.upsert_clips([clip], passage_dense_vectors=[[0.1] * 1024]) == 1
    point = client.upsert.call_args.kwargs["points"][0]
    assert point.payload["video_id"] == "9id3ygnEhh8"
    assert point.payload["group_id"] == "9id3ygnEhh8"
    assert point.payload["source_url"] == "https://www.youtube.com/watch?v=9id3ygnEhh8"
    # Identity remap never touches text/hash/ID derivation.
    assert point.payload["transcript_hash"] == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert point.id == make_first_person_point_id(point.payload["transcript_hash"], 3900, 25500)
    # Caller-owned dict is not mutated (copy-on-remap).
    assert clip["video_id"] == "AQUZcU5L9xE"


def test_upsert_clips_reupload_twin_collapses_with_canonical():
    """Re-upload twin listed FIRST still collapses: remap runs before the
    (video_id, text) dedupe key, so both twins share one key."""
    client = MagicMock()
    store = FirstPersonStore(collection="first_person_v1", client=client)

    text = "When you actually get back from work, observe yourself."
    clips = [
        _jitter_clip("AQUZcU5L9xE", text, 3900, 25500),
        _jitter_clip("9id3ygnEhh8", text, 4100, 25300),
    ]

    _stub_r2_readback(client)
    assert store.upsert_clips(clips, passage_dense_vectors=[[0.1] * 1024] * 2) == 1
    point = client.upsert.call_args.kwargs["points"][0]
    assert point.payload["video_id"] == "9id3ygnEhh8"


def test_payload_indexes_declare_bool_for_boolean_fields():
    """Audit 2026-10-04 §1: keyword indexes on JSON booleans never fire
    (live: 0 indexed points) — declarations must be bool."""
    declared = dict(FirstPersonStore.PAYLOAD_INDEXES)
    for field in ("is_verbatim", "first_person_eligible", "rights_cleared"):
        assert declared[field] == "bool", f"{field} must be bool-indexed"


def test_init_collection_creates_bool_indexes_for_boolean_fields():
    client = MagicMock()
    client.get_collections.return_value = MagicMock(collections=[])
    FirstPersonStore(collection="first_person_v1", client=client).init_collection()

    created = {
        call.kwargs["field_name"]: call.kwargs["field_schema"]
        for call in client.create_payload_index.call_args_list
    }
    for field in ("is_verbatim", "first_person_eligible", "rights_cleared"):
        assert created[field] == "bool"
    # Non-boolean declarations are untouched.
    assert created["video_id"] == "keyword"
    assert created["start_ms"] == "integer"
    assert created["verbatim_text"] == "text"


class _FakePoint:
    def __init__(self, pid, payload):
        self.id = pid
        self.payload = payload


class _FakeScrollClient:
    def __init__(self, points):
        self._points = points

    def scroll(self, **kwargs):
        return self._points, None


def _store_with(points):
    from services.first_person_store import FirstPersonStore

    return FirstPersonStore(collection="first_person_v1", client=_FakeScrollClient(points))


def test_lookup_prefers_clip_flooring_to_requested_second():
    """Two clips equidistant in ms: the one whose start floors to the
    requested second wins (playback seeks whole seconds)."""
    base = {"first_person_eligible": True}
    pts = [
        _FakePoint("a", {**base, "start_ms": 9499}),  # diff 501, floors to 9
        _FakePoint("b", {**base, "start_ms": 10501}),  # diff 501, floors to 10
    ]
    best = _store_with(pts).get_clip_by_video_and_start("vid", 10.0, tolerance_s=1.5)
    assert best is not None and best["point_id"] == "b"


def test_lookup_tie_breaks_hold_after_floor_preference():
    """Same floor: smaller distance wins; same distance: earlier start wins."""
    base = {"first_person_eligible": True}
    pts = [
        _FakePoint("a", {**base, "start_ms": 10300}),  # diff 300
        _FakePoint("b", {**base, "start_ms": 10200}),  # diff 200 wins
    ]
    best = _store_with(pts).get_clip_by_video_and_start("vid", 10.0, tolerance_s=1.5)
    assert best is not None and best["point_id"] == "b"


def test_upsert_clips_persists_context_and_okf_payload_fields():
    from services.first_person_store import FirstPersonStore

    class _CaptureClient:
        def __init__(self):
            self.upserted_points = []

        def upsert(self, collection_name, points, **kwargs):
            self.upserted_points.extend(points)

        def retrieve(self, collection_name, ids, **kwargs):
            from unittest.mock import MagicMock

            ret = []
            for p in self.upserted_points:
                if str(p.id) in ids:
                    m = MagicMock()
                    m.id = p.id
                    m.payload = p.payload
                    m.vector = p.vector
                    ret.append(m)
            return ret

    client = _CaptureClient()
    store = FirstPersonStore(collection="first_person_v1", client=client)

    clip = {
        "video_id": "test_vid_i2",
        "start_ms": 1000,
        "end_ms": 5000,
        "speaker": "Sri Krishnaji",
        "transcript_hash": "a" * 64,
        "verbatim_text": "verbatim words without context",
        # I2 context fields:
        "discourse_context": "Discourse on overcoming spiritual suffering and anxiety",
        "tags": ["suffering", "peace", "ekam"],
        "okf_concept_id": "concept_beautiful_state",
        "okf_title": "The Beautiful State",
    }
    # Mock hashlib to match transcript_hash
    import hashlib

    clip["transcript_hash"] = hashlib.sha256(clip["verbatim_text"].encode("utf-8")).hexdigest()

    dense_vec = [0.1] * 1024
    store.upsert_clips([clip], passage_dense_vectors=[dense_vec])

    assert len(client.upserted_points) == 1
    pt = client.upserted_points[0]
    # passage_dense vector holds pure verbatim embedding
    assert pt.vector["passage_dense"] == dense_vec
    assert "question_dense" not in pt.vector

    # Context fields exist in payload
    assert (
        pt.payload["discourse_context"] == "Discourse on overcoming spiritual suffering and anxiety"
    )
    assert pt.payload["tags"] == ["suffering", "peace", "ekam"]
    assert pt.payload["okf_concept_id"] == "concept_beautiful_state"
    assert pt.payload["okf_title"] == "The Beautiful State"
    assert pt.payload["verbatim_text"] == "verbatim words without context"
    assert pt.payload["is_verbatim"] is True

    # Check payload indexes include the 4 fields
    index_dict = dict(FirstPersonStore.PAYLOAD_INDEXES)
    assert index_dict["discourse_context"] == "text"
    assert index_dict["tags"] == "keyword"
    assert index_dict["okf_concept_id"] == "keyword"
    assert index_dict["okf_title"] == "keyword"
