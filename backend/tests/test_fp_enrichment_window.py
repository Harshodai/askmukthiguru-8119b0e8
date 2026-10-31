"""Plan T2b: enrichment window + concept-tagged retrieval on the fp-context store.

No Qdrant, no network. The fake client records every filter it is handed so the
``concept_ids`` filter shape can be asserted directly.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from qdrant_client.http.models import (
    FieldCondition,
    MatchAny,
    PointStruct,
)

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
from services.first_person_context_store import (
    RECORD_TYPE_CHILD,
    FirstPersonContextStore,
    FirstPersonContextStoreError,
    parent_point_id,
)

HASH = "b" * 64
PARENT_ID = "parentWindow"


def span(n: int = 0, **overrides) -> SourceSpan:
    text = overrides.pop("verbatim_text", f"Consciousness is not a thing you can hold ({n}).")
    word_start = overrides.pop("word_start", n * 10)
    word_end = overrides.pop("word_end", word_start + 6)
    guru_id = overrides.get("guru_id", "krishnaji")
    video_id = overrides.get("video_id", "vidW")
    corpus_version = overrides.get("corpus_version", "ctx-v1")
    data: dict[str, object] = {
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
        "parent_unit_id": PARENT_ID,
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
        "voice_verification_method": "ecapa_voxceleb_span_slice_v2",
        # A verified span records what produced the claim (write rule, P2).
        "voice_model_revision": "rev-test",
        "voice_score": 0.71,
        "voice_margin": 0.40,
        "voice_threshold_applied": {"cosine_floor": 0.2828, "margin_threshold": 0.05},
        "voice_calibration_id": "cal-test",
        "voice_window_check": "pass",
        "voice_verified_at": "2026-10-31T00:00:00+00:00",
        "speaker_verification_status": "verified",
        "source_transcript_text": text,
        "verbatim_text": text,
        "transcript_hash": HASH,
        "source_text_hash": clip_text_hash(text),
        "boundary_status": BoundaryStatus.VERIFIED,
        "completeness_status": CompletenessStatus.COMPLETE,
        "rights_cleared": True,
        "caption_status": "auto",
        "provenance_kind": ProvenanceKind.SPEECH_TURN_SPAN,
        "source_url": "https://www.youtube.com/watch?v=vidW",
    }
    data.update(overrides)
    return SourceSpan(**data)


def parent(spans: tuple[SourceSpan, ...] | list[SourceSpan]) -> ParentUnit:
    ordered = tuple(s.source_span_id for s in spans)
    return ParentUnit(
        corpus_version="ctx-v1",
        guru_id=spans[0].guru_id,
        video_id=spans[0].video_id,
        parent_unit_id=PARENT_ID,
        ordered_source_span_ids=ordered,
        start_ms=spans[0].start_ms,
        end_ms=spans[-1].end_ms,
        parent_text_hash=clip_text_hash(" ".join(s.verbatim_text for s in spans)),
        speaker_ids=(spans[0].speaker_id,),
        speaker_continuity=True,
        boundary_status=BoundaryStatus.VERIFIED,
        completeness_status=CompletenessStatus.COMPLETE,
    )


class FakeClient:
    """In-memory stand-in that records the filters it receives."""

    def __init__(self) -> None:
        self.points: dict[str, SimpleNamespace] = {}
        self.query_filters: list[object] = []

    def create_payload_index(self, collection_name, field_name, field_schema, wait=True):
        return None

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
        wanted_parent = None
        for condition in getattr(scroll_filter, "must", []) or []:
            if getattr(condition, "key", None) == "parent_unit_id":
                wanted_parent = condition.match.value
        out = [
            record
            for record in self.points.values()
            if record.payload.get("record_type") == RECORD_TYPE_CHILD
            and record.payload.get("parent_unit_id") == wanted_parent
        ]
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
        self.query_filters.append(query_filter)
        hits = [
            SimpleNamespace(
                id=record.id,
                score=0.9,
                payload={
                    "parent_unit_id": record.payload.get("parent_unit_id"),
                    "source_span_id": record.payload.get("source_span_id"),
                },
            )
            for record in self.points.values()
            if record.payload.get("record_type") == RECORD_TYPE_CHILD
            and self._must_matches(record.payload, query_filter)
        ]
        return SimpleNamespace(points=hits[:limit])

    @staticmethod
    def _must_matches(payload, query_filter) -> bool:
        for condition in getattr(query_filter, "must", []) or []:
            if not isinstance(condition, FieldCondition):
                continue
            if condition.match and payload.get(condition.key) != condition.match.value:
                return False
        return True


def store_with(spans: list[SourceSpan], *, parent_spans: list[SourceSpan] | None = None):
    client = FakeClient()
    adapter = FirstPersonContextStore(client=client, collection="fp_context_test")
    full = parent_spans or spans
    adapter.upsert(parent(full), full)
    return adapter, client


# --------------------------------------------------------------- enrichment


def test_enrich_returns_full_parent_window_preserving_hits_and_score():
    s0, s1, s2 = span(0), span(1), span(2)
    adapter, _ = store_with([s0, s1, s2])
    narrow = ParentContext(
        parent=parent([s0, s1, s2]),
        spans=(s2,),
        hit_span_ids=(s2.source_span_id,),
        score=0.42,
    )

    widened = adapter.enrich_to_parent_window(narrow)

    assert [s.source_span_id for s in widened.spans] == [
        s0.source_span_id,
        s1.source_span_id,
        s2.source_span_id,
    ]
    assert widened.hit_span_ids == narrow.hit_span_ids
    assert widened.score == pytest.approx(0.42)
    assert widened.parent.parent_unit_id == PARENT_ID


def test_enrich_reuses_fetch_parent_context_with_existing_hits_and_score(monkeypatch):
    s0, s1 = span(0), span(1)
    adapter, _ = store_with([s0, s1])
    narrow = ParentContext(
        parent=parent([s0, s1]), spans=(s1,), hit_span_ids=(s1.source_span_id,), score=0.31
    )
    calls: list[tuple[str, tuple[str, ...], float]] = []
    original = adapter.fetch_parent_context

    def spy(parent_unit_id, hit_span_ids, score=0.0):
        calls.append((parent_unit_id, tuple(hit_span_ids), score))
        return original(parent_unit_id, hit_span_ids, score)

    monkeypatch.setattr(adapter, "fetch_parent_context", spy)
    widened = adapter.enrich_to_parent_window(narrow)

    assert calls == [(PARENT_ID, (s1.source_span_id,), 0.31)]
    assert len(widened.spans) == 2


def test_enrich_is_a_noop_when_context_is_already_the_full_parent():
    s0, s1 = span(0), span(1)
    adapter, _ = store_with([s0, s1])
    full = ParentContext(
        parent=parent([s0, s1]),
        spans=(s0, s1),
        hit_span_ids=(s1.source_span_id,),
        score=0.5,
    )

    assert adapter.enrich_to_parent_window(full) is full


def test_enrich_raises_contract_error_when_parent_record_is_missing():
    s0 = span(0)
    adapter, client = store_with([s0])
    narrow = ParentContext(
        parent=parent([s0]), spans=(s0,), hit_span_ids=(s0.source_span_id,), score=0.2
    )
    del client.points[parent_point_id(PARENT_ID)]

    with pytest.raises(FirstPersonContextStoreError, match="parent record missing"):
        adapter.enrich_to_parent_window(narrow)


# ------------------------------------------------------------ concept filter


def test_retrieve_with_concept_ids_adds_should_match_any_over_tags():
    s0 = span(0, topic_ids=("anger",), entity_ids=("Karma",))
    adapter, client = store_with([s0])

    adapter.retrieve([0.1] * 8, concept_ids=[" anger ", "Karma", "anger", "  "])

    query_filter = client.query_filters[-1]
    assert query_filter.should, "concept_ids must add a should group"
    keys = [c.key for c in query_filter.should]
    assert keys == ["topic_ids", "entity_ids"]
    for condition in query_filter.should:
        assert isinstance(condition.match, MatchAny)
    topic_any = query_filter.should[0].match.any
    assert topic_any == ["anger", "Karma"]


def test_retrieve_without_concept_ids_keeps_todays_filter():
    s0 = span(0)
    adapter, client = store_with([s0])

    adapter.retrieve([0.1] * 8, guru_id="krishnaji")
    baseline = client.query_filters[-1]

    adapter.retrieve([0.1] * 8, guru_id="krishnaji", concept_ids=None)
    none_filter = client.query_filters[-1]
    adapter.retrieve([0.1] * 8, guru_id="krishnaji", concept_ids=[])
    empty_filter = client.query_filters[-1]
    adapter.retrieve([0.1] * 8, guru_id="krishnaji", concept_ids=["", "   ", None])
    blank_filter = client.query_filters[-1]

    def must_pairs(query_filter):
        return [(c.key, c.match.value) for c in query_filter.must]

    for candidate in (none_filter, empty_filter, blank_filter):
        assert not candidate.should
        assert must_pairs(candidate) == must_pairs(baseline)

    assert must_pairs(baseline) == [
        ("record_type", RECORD_TYPE_CHILD),
        ("rights_cleared", True),
        ("guru_id", "krishnaji"),
    ]
