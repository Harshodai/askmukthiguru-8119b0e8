"""Tests for the fp-context-v1 Qdrant adapter (phase D storage contract)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from qdrant_client.http.models import FieldCondition, PointStruct

from domain.first_person_context import (
    BoundaryStatus,
    CompletenessStatus,
    ParentUnit,
    ProvenanceKind,
    SourceSpan,
    SpeakerRole,
    clip_text_hash,
    make_source_span_id,
)
from services.first_person_context_store import (
    RECORD_TYPE_CHILD,
    FirstPersonContextStore,
    FirstPersonContextStoreError,
    parent_point_id,
    point_id_for_record,
)

HASH = "a" * 64


def span(n=0, **overrides):
    text = overrides.pop("verbatim_text", f"Suffering is a call to awaken ({n}).")
    word_start = overrides.pop("word_start", n * 10)
    word_end = overrides.pop("word_end", word_start + 6)
    guru_id = overrides.get("guru_id", "krishnaji")
    video_id = overrides.get("video_id", "vidA")
    corpus_version = overrides.get("corpus_version", "ctx-v1")
    data = {
        "corpus_version": corpus_version,
        "guru_id": guru_id,
        "video_id": video_id,
        "source_asset_id": video_id,
        "source_span_id": make_source_span_id(
            guru_id=guru_id,
            video_id=video_id,
            corpus_version=corpus_version,
            word_start=word_start,
            word_end=word_end,
            transcript_hash=HASH,
        ),
        "parent_unit_id": "parentA",
        "turn_id": f"turn{n}",
        "turn_index": n,
        "source_span_index": n,
        "start_ms": 1000 * n,
        "end_ms": 1000 * n + 900,
        "word_start": word_start,
        "word_end": word_end,
        "speaker_id": "krishnaji",
        "speaker_role": SpeakerRole.GURU,
        "speaker_verified": True,
        "source_transcript_text": text,
        "verbatim_text": text,
        "transcript_hash": HASH,
        "source_text_hash": clip_text_hash(text),
        "boundary_status": BoundaryStatus.VERIFIED,
        "completeness_status": CompletenessStatus.COMPLETE,
        "rights_cleared": True,
        "caption_status": "auto",
        "provenance_kind": ProvenanceKind.SPEECH_TURN_SPAN,
        "source_url": "https://www.youtube.com/watch?v=vidA",
    }
    data.update(overrides)
    return SourceSpan(**data)


def parent(spans, **overrides):
    data = {
        "corpus_version": "ctx-v1",
        "guru_id": spans[0].guru_id,
        "video_id": spans[0].video_id,
        "parent_unit_id": spans[0].parent_unit_id,
        "ordered_source_span_ids": tuple(s.source_span_id for s in spans),
        "start_ms": spans[0].start_ms,
        "end_ms": spans[-1].end_ms,
        "parent_text_hash": clip_text_hash(" ".join(s.verbatim_text for s in spans)),
        "speaker_ids": (spans[0].speaker_id,),
        "speaker_continuity": True,
        "boundary_status": BoundaryStatus.VERIFIED,
        "completeness_status": CompletenessStatus.COMPLETE,
    }
    data.update(overrides)
    return ParentUnit(**data)


class FakeClient:
    def __init__(self) -> None:
        self.points: dict[str, SimpleNamespace] = {}
        self.indexes: list[str] = []
        self.filters: list[object] = []

    def create_payload_index(self, collection_name, field_name, field_schema, wait=True):
        self.indexes.append(field_name)

    def upsert(self, collection_name, points, wait=True):
        for point in points:
            assert isinstance(point, PointStruct)
            self.points[str(point.id)] = SimpleNamespace(
                id=str(point.id), payload=dict(point.payload or {})
            )

    def retrieve(self, collection_name, ids, with_payload=True, with_vectors=False):
        return [self.points[i] for i in ids if i in self.points]

    def scroll(
        self,
        collection_name,
        scroll_filter,
        limit,
        offset=None,
        with_payload=True,
        with_vectors=False,
        **kwargs,
    ):
        self.filters.append(scroll_filter)
        out = []
        for record in self.points.values():
            if self._matches(record.payload, scroll_filter):
                out.append(record)
        return out[:limit], None

    def query_points(
        self,
        collection_name,
        query,
        using=None,
        query_filter=None,
        limit=10,
        with_payload=True,
        **_,
    ):
        self.filters.append(query_filter)
        matches = [
            SimpleNamespace(
                id=record.id,
                score=1.0,
                payload={
                    "parent_unit_id": record.payload.get("parent_unit_id"),
                    "source_span_id": record.payload.get("source_span_id"),
                },
            )
            for record in self.points.values()
            if record.payload.get("record_type") == RECORD_TYPE_CHILD
            and self._matches(record.payload, query_filter)
        ]
        return SimpleNamespace(points=matches[:limit])

    @staticmethod
    def _matches(payload, query_filter) -> bool:
        for condition in getattr(query_filter, "must", []) or []:
            if not isinstance(condition, FieldCondition):
                continue
            value = payload.get(condition.key)
            if condition.match and value != condition.match.value:
                return False
        return True


def store(client=None, collection="fp_context_test"):
    return FirstPersonContextStore(client or FakeClient(), collection)


def test_upsert_writes_uuid_point_ids_for_children_and_parent():
    s1, s2 = span(0), span(1)
    client = FakeClient()
    written = store(client).upsert(parent([s1, s2]), [s1, s2])
    assert written == 3
    assert point_id_for_record(s1.source_span_id) in client.points
    assert parent_point_id("parentA") in client.points
    payload = client.points[point_id_for_record(s1.source_span_id)].payload
    assert payload["record_type"] == RECORD_TYPE_CHILD
    assert payload["verbatim_text"] == s1.verbatim_text


def test_upsert_rejects_out_of_order_spans():
    s1, s2 = span(0), span(1)
    with pytest.raises(FirstPersonContextStoreError, match="ordered_source_span_ids"):
        store().upsert(parent([s1, s2]), [s2, s1])


def test_upsert_rejects_span_from_another_parent():
    s1 = span(0)
    foreign = span(1, parent_unit_id="parentB")
    ordered = parent([s1], ordered_source_span_ids=(s1.source_span_id, foreign.source_span_id))
    with pytest.raises(FirstPersonContextStoreError, match="does not belong"):
        store().upsert(ordered, [s1, foreign])


def test_upsert_rejects_span_from_another_guru():
    s1 = span(0)
    other = span(1, guru_id="preethaji", speaker_id="preethaji")
    ordered = parent([s1], ordered_source_span_ids=(s1.source_span_id, other.source_span_id))
    with pytest.raises(FirstPersonContextStoreError, match="guru_id"):
        store().upsert(ordered, [s1, other])


def test_ensure_indexes_creates_expected_keys():
    client = FakeClient()
    created = store(client).ensure_indexes()
    assert {"parent_unit_id", "record_type", "rights_cleared"} <= set(created)


def test_retrieve_falls_back_to_client_side_grouping_and_hydrates_parent():
    s1, s2 = span(0), span(1)
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([s1, s2]), [s1, s2])

    contexts = adapter.retrieve([0.1] * 8, limit_parents=3)
    assert len(contexts) == 1
    context = contexts[0]
    assert context.parent.parent_unit_id == "parentA"
    assert [s.source_span_id for s in context.spans] == [
        s1.source_span_id,
        s2.source_span_id,
    ]


def test_retrieve_filter_requires_rights_cleared_and_child_record():
    client = FakeClient()
    adapter = store(client)
    s1 = span(0)
    adapter.upsert(parent([s1]), [s1])
    adapter.retrieve([0.1] * 8)

    query_filter = client.filters[0]
    conditions = {c.key: c.match.value for c in query_filter.must}
    assert conditions["record_type"] == RECORD_TYPE_CHILD
    assert conditions["rights_cleared"] is True


def test_retrieve_scopes_to_requested_guru():
    client = FakeClient()
    adapter = store(client)
    s1 = span(0)
    adapter.upsert(parent([s1]), [s1])
    adapter.retrieve([0.1] * 8, guru_id="preethaji")
    conditions = {c.key: c.match.value for c in client.filters[0].must}
    assert conditions["guru_id"] == "preethaji"


def test_retrieve_drops_parent_whose_children_are_missing():
    s1 = span(0)
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([s1]), [s1])
    del client.points[point_id_for_record(s1.source_span_id)]

    assert adapter.retrieve([0.1] * 8) == []


def test_fetch_rejects_point_id_that_does_not_match_payload():
    s1 = span(0)
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([s1]), [s1])
    record = client.points[point_id_for_record(s1.source_span_id)]
    client.points[point_id_for_record(s1.source_span_id)] = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000000", payload=record.payload
    )

    with pytest.raises(FirstPersonContextStoreError, match="point id does not match"):
        adapter.fetch_parent_context("parentA", [s1.source_span_id])


def test_fetch_rejects_parent_payload_from_another_parent():
    s1 = span(0)
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([s1]), [s1])
    record = client.points[parent_point_id("parentA")]
    payload = dict(record.payload)
    payload["parent_unit_id"] = "parentB"
    client.points[parent_point_id("parentA")] = SimpleNamespace(
        id=parent_point_id("parentA"), payload=payload
    )

    with pytest.raises(FirstPersonContextStoreError, match="id mismatch"):
        adapter.fetch_parent_context("parentA", [s1.source_span_id])


def test_grouped_api_is_used_when_available():
    s1 = span(0)
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([s1]), [s1])
    calls = {"groups": 0}

    def query_points_groups(**kwargs):
        calls["groups"] += 1
        return SimpleNamespace(
            groups=[
                SimpleNamespace(
                    id="parentA",
                    hits=[
                        SimpleNamespace(
                            id=point_id_for_record(s1.source_span_id),
                            score=0.8,
                            payload={"source_span_id": s1.source_span_id},
                        )
                    ],
                )
            ]
        )

    client.query_points_groups = query_points_groups
    contexts = adapter.retrieve([0.1] * 8)
    assert calls["groups"] == 1
    assert len(contexts) == 1


def test_missing_parent_record_is_an_error_not_an_empty_answer():
    s1 = span(0)
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([s1]), [s1])
    del client.points[parent_point_id("parentA")]
    with pytest.raises(FirstPersonContextStoreError, match="parent record missing"):
        adapter.fetch_parent_context("parentA", [s1.source_span_id])
