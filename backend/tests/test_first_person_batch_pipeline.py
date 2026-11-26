from __future__ import annotations

from qdrant_client.http.models import SparseVector

from services.first_person_batch_pipeline import (
    CHUNKER_VERSION,
    MAX_PARENT_DURATION_MS,
    SHARED_GURU_ID,
    _persist_rejection,
    build_context_records,
    build_sentence_closing_windows,
    encode_vectors,
    upsert_video,
)
from services.first_person_context_store import SPAN_INDEXES

SEGMENTS = [
    {"start_ms": 0, "end_ms": 9000, "text": "Awareness begins when we pause"},
    {"start_ms": 9000, "end_ms": 18000, "text": "Then we see the movement of thought"},
    {"start_ms": 18000, "end_ms": 24000, "text": "This seeing brings freedom."},
]


def _build(**overrides):
    kwargs = {
        "video_id": "video-1",
        "segments": SEGMENTS,
        "rights_resolver": lambda **_: "licensed",
    }
    kwargs.update(overrides)
    return build_context_records(**kwargs)


def test_windows_close_at_sentence_after_minimum_duration():
    windows = build_sentence_closing_windows(SEGMENTS)
    assert len(windows) == 1
    assert windows[0].start_ms == 0
    assert windows[0].end_ms == 24000
    assert windows[0].text.endswith("freedom.")


def test_context_records_are_deterministic_namespaced_and_unverified():
    artifact_hash = "a" * 64
    parents_a, spans_a, rejected_a = _build(
        ingest_namespace="official_channel_shadow_20261122",
        source_artifact_sha256=artifact_hash,
    )
    parents_b, spans_b, rejected_b = _build(
        ingest_namespace="official_channel_shadow_20261122",
        source_artifact_sha256=artifact_hash,
    )
    assert len(parents_a) == len(parents_b) == 1
    assert parents_a[0].parent_unit_id == parents_b[0].parent_unit_id
    assert [s.source_span_id for s in spans_a] == [s.source_span_id for s in spans_b]
    assert parents_a[0].guru_id == SHARED_GURU_ID
    assert parents_a[0].ingest_namespace == "official_channel_shadow_20261122"
    assert spans_a[0].ingest_namespace == "official_channel_shadow_20261122"
    assert spans_a[0].speaker_verified is False
    assert spans_a[0].speaker_verification_status == "pending_voice_check"
    assert spans_a[0].speaker_role.value == "unknown"
    assert spans_a[0].source_url == "https://www.youtube.com/watch?v=video-1"
    assert spans_a[0].chunker_version == CHUNKER_VERSION
    assert spans_a[0].source_artifact_sha256 == artifact_hash
    assert spans_a[0].first_person_eligible is True
    assert spans_a[0].quality_status == "auto_asr_candidate"
    assert rejected_a == rejected_b == 0
    assert parents_a[0].to_payload()["record_type"] == "parent_unit"
    assert spans_a[0].to_payload()["record_type"] == "retrieval_child"
    assert parents_a[0].to_payload()["ingest_namespace"] == "official_channel_shadow_20261122"
    assert spans_a[0].to_payload()["ingest_namespace"] == "official_channel_shadow_20261122"


def test_unscoped_payload_serialization_omits_optional_namespace():
    parents, spans, _ = _build()
    assert "ingest_namespace" not in parents[0].to_payload()
    assert "ingest_namespace" not in spans[0].to_payload()


def test_namespace_has_a_qdrant_payload_index():
    assert ("ingest_namespace", "keyword") in SPAN_INDEXES


def test_parent_groups_are_bounded_not_video_wide():
    segments = [
        {
            "start_ms": i * 20_000,
            "end_ms": (i + 1) * 20_000,
            "text": f"A complete thought number {i}.",
        }
        for i in range(6)
    ]
    parents, spans, rejected = build_context_records(
        video_id="video-groups",
        segments=segments,
        rights_resolver=lambda **_: "licensed",
    )
    assert len(parents) == 2
    assert len(spans) == 6
    assert rejected == 0
    for parent in parents:
        children = [span for span in spans if span.parent_unit_id == parent.parent_unit_id]
        assert len(children) <= 4
        assert parent.end_ms - parent.start_ms <= MAX_PARENT_DURATION_MS
        assert parent.ordered_source_span_ids == tuple(span.source_span_id for span in children)


def test_title_or_source_metadata_cannot_change_shared_attribution():
    parents, spans, _ = _build(source_url="/tmp/teacher-preethaji.wav")
    assert parents[0].guru_id == SHARED_GURU_ID
    assert all(span.speaker_id == "shared_unverified" for span in spans)
    assert spans[0].source_url == "https://www.youtube.com/watch?v=video-1"


def test_unlicensed_source_fails_closed():
    try:
        build_context_records(
            video_id="video-3", segments=SEGMENTS, rights_resolver=lambda **_: "unverified"
        )
    except ValueError as exc:
        assert "not licensed" in str(exc)
    else:
        raise AssertionError("unlicensed source was accepted")


def test_incomplete_window_must_be_persisted_before_any_write():
    incomplete = [{"start_ms": 0, "end_ms": 20_000, "text": "An unfinished thought"}]
    rejected = []
    try:
        build_context_records(
            video_id="video-incomplete",
            segments=incomplete,
            rights_resolver=lambda **_: "licensed",
            rejection_persistor=lambda **row: rejected.append(row) or True,
        )
    except ValueError as exc:
        assert "all ASR windows" in str(exc)
    else:
        raise AssertionError("incomplete ASR window was accepted")
    assert len(rejected) == 1
    assert rejected[0]["chunk_index"] == 0
    assert rejected[0]["source_url"].endswith("video-incomplete")
    assert rejected[0]["source_coordinates"] == "start_ms=0;end_ms=20000;word_start=0;word_end=3"


def test_out_of_range_window_is_rejected_with_source_coordinates():
    short_complete = [{"start_ms": 1000, "end_ms": 12000, "text": "A complete short thought."}]
    rejected = []
    try:
        build_context_records(
            video_id="video-short-window",
            segments=short_complete,
            rights_resolver=lambda **_: "licensed",
            rejection_persistor=lambda **row: rejected.append(row) or True,
        )
    except ValueError as exc:
        assert "all ASR windows" in str(exc)
    else:
        raise AssertionError("out-of-range ASR window was accepted")
    assert len(rejected) == 1
    assert "window_duration_out_of_range:11000ms" in rejected[0]["reason"]
    assert rejected[0]["source_coordinates"].startswith("start_ms=1000;end_ms=12000;")


def test_rejection_persistence_failure_aborts_batch():
    incomplete = [{"start_ms": 0, "end_ms": 20_000, "text": "An unfinished thought"}]
    try:
        build_context_records(
            video_id="video-no-ledger",
            segments=incomplete,
            rights_resolver=lambda **_: "licensed",
            rejection_persistor=lambda **_: False,
        )
    except RuntimeError as exc:
        assert "could not be persisted" in str(exc)
    else:
        raise AssertionError("batch continued without durable rejection evidence")


def test_rejection_row_stores_tier_reason_and_coordinates_without_new_columns(monkeypatch):
    import app.telemetry_db

    captured = {}

    class Insert:
        def insert(self, rows):
            captured["table"] = "corpus_gate_rejections"
            captured["row"] = rows[0]
            return self

        def execute(self):
            return None

    class Client:
        def table(self, name):
            assert name == "corpus_gate_rejections"
            return Insert()

    monkeypatch.setattr(app.telemetry_db, "_get_client", lambda: Client())
    assert _persist_rejection(
        source_url="https://www.youtube.com/watch?v=video-1",
        reason="window_duration_out_of_range:11000ms",
        chunk_index=0,
        matched_span="A complete short thought.",
        source_coordinates="start_ms=1000;end_ms=12000;word_start=0;word_end=5",
    )
    row = captured["row"]
    assert captured["table"] == "corpus_gate_rejections"
    assert row["gate_layer"] == "fp_context_batch_pipeline_tier_1"
    assert row["reason"] == "window_duration_out_of_range:11000ms"
    assert "start_ms=1000;end_ms=12000;word_start=0;word_end=5" in row["gate_reason"]
    assert set(row) <= {
        "source_url",
        "chunk_index",
        "gate_layer",
        "gate_verdict",
        "reason",
        "gate_reason",
        "matched_span",
        "point_id",
    }


def test_vector_mapping_uses_named_dense_and_sparse_vectors():
    _, spans, _ = _build(video_id="video-4")

    class Encoder:
        def encode_batch(self, texts):
            assert len(texts) == len(spans)
            return {"dense": [[1.0, 2.0] for _ in texts], "sparse": [{"3": 0.5} for _ in texts]}

    vectors = encode_vectors(Encoder(), spans)
    assert set(vectors) == {span.source_span_id for span in spans}
    assert vectors[spans[0].source_span_id]["passage_dense"] == [1.0, 2.0]
    assert isinstance(vectors[spans[0].source_span_id]["passage_sparse"], SparseVector)


def test_vector_mapping_rejects_mismatched_rows_and_dimensions():
    _, spans, _ = _build(
        video_id="video-5",
        segments=SEGMENTS
        + [{"start_ms": 24_000, "end_ms": 42_000, "text": "A second complete thought."}],
    )

    class ShortEncoder:
        def encode_batch(self, texts):
            return {"dense": [[0.1, 0.2]], "sparse": [{}]}

    class RaggedEncoder:
        def encode_batch(self, texts):
            return {"dense": [[0.1, 0.2], [0.3]], "sparse": [{}, {}]}

    for encoder in (ShortEncoder(), RaggedEncoder()):
        try:
            encode_vectors(encoder, spans)
        except ValueError:
            pass
        else:
            raise AssertionError("malformed encoder output was accepted")


def test_upsert_video_calls_indexes_and_upserts_typed_parent_groups():
    calls = {"upserts": []}

    class Store:
        def ensure_indexes(self):
            calls["indexes"] = True

        def upsert(self, parent, spans, vectors):
            calls["upserts"].append((parent, spans, vectors))
            return len(spans) + 1

    class Encoder:
        def encode_batch(self, texts):
            return {"dense": [[0.1, 0.2] for _ in texts], "sparse": [{} for _ in texts]}

    result = upsert_video(
        store=Store(),
        embedding_service=Encoder(),
        video_id="video-6",
        segments=SEGMENTS,
        source_url="https://example.invalid",
        ingest_namespace="official_channel_shadow_20261122",
        rights_resolver=lambda **_: "licensed",
    )
    assert calls["indexes"] is True
    assert result["status"] == "ok"
    assert result["points_written"] == result["spans_indexed"] + result["parent_units_indexed"]
    assert len(calls["upserts"]) == result["parent_units_indexed"]
    parent, spans, vectors = calls["upserts"][0]
    assert parent.ordered_source_span_ids == tuple(span.source_span_id for span in spans)
    assert all(span.ingest_namespace == "official_channel_shadow_20261122" for span in spans)
    assert set(vectors) == {span.source_span_id for span in spans}
