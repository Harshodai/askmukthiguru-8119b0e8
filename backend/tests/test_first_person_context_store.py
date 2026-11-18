"""Tests for the fp-context-v1 Qdrant adapter (phase D storage contract)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from qdrant_client.http.models import FieldCondition, PointStruct

from app.config import settings
from domain.first_person_context import (
    BoundaryStatus,
    CompletenessStatus,
    ParentUnit,
    ProvenanceKind,
    SourceSpan,
    SpeakerRole,
    ValidatedCrossParentEdge,
    clip_text_hash,
    make_source_span_id,
)
from domain.speaker_provenance import AUTOMATED_PROVENANCE_KEYS, HUMAN_REVIEW_KEYS
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
        "domain_rights_status": "licensed",
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


def citation_evidence(source: SourceSpan) -> dict:
    """The complete evidence snapshot emitted by the context citation builder."""
    return {
        "point_id": point_id_for_record(source.source_span_id),
        "source_span_id": source.source_span_id,
        "source_asset_id": source.source_asset_id,
        "parent_unit_id": source.parent_unit_id,
        "corpus_version": source.corpus_version,
        "video_id": source.video_id,
        "guru_id": source.guru_id,
        "speaker_id": source.speaker_id,
        "speaker_role": source.speaker_role.value,
        "speaker_verified": source.speaker_verified,
        "start_ms": source.start_ms,
        "end_ms": source.end_ms,
        "word_start": source.word_start,
        "word_end": source.word_end,
        "verbatim_text": source.verbatim_text,
        "source_text_hash": source.source_text_hash,
        # Context citation cache replay intentionally compares this field to
        # the clip-level source_text_hash, not the video-level payload hash.
        "transcript_hash": source.source_text_hash,
        "video_transcript_hash": source.transcript_hash,
        "is_verbatim": source.is_verbatim,
        "boundary_status": source.boundary_status.value,
        "completeness_status": source.completeness_status.value,
        "rights_cleared": source.rights_cleared,
        "domain_rights_status": source.domain_rights_status,
        "quality_status": source.quality_status,
        "quarantine_reason": source.quarantine_reason,
        "source_url": source.source_url,
        **{key: getattr(source, key) for key in (*AUTOMATED_PROVENANCE_KEYS, *HUMAN_REVIEW_KEYS)},
    }


class FakeClient:
    def __init__(self) -> None:
        self.points: dict[str, SimpleNamespace] = {}
        self.indexes: list[str] = []
        self.filters: list[object] = []
        self.retrieve_payloads: list[object] = []

    def create_payload_index(self, collection_name, field_name, field_schema, wait=True):
        self.indexes.append(field_name)

    def upsert(self, collection_name, points, wait=True):
        for point in points:
            assert isinstance(point, PointStruct)
            self.points[str(point.id)] = SimpleNamespace(
                id=str(point.id), payload=dict(point.payload or {})
            )

    def retrieve(self, collection_name, ids, with_payload=True, with_vectors=False):
        self.retrieve_payloads.append(with_payload)
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


@pytest.fixture(autouse=True)
def _registered_synthetic_sources(monkeypatch):
    """Serving fixtures model an explicitly registered source; focused writer tests override it."""
    monkeypatch.setattr(
        "services.qdrant.indexer.resolve_source_rights_status",
        lambda **_kwargs: "licensed",
    )
    monkeypatch.setattr(
        "services.first_person_context_store.source_is_authoritatively_licensed",
        lambda **kwargs: kwargs.get("domain_rights_status") == "licensed",
    )


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
    assert payload["domain_rights_status"] == "licensed"


def test_upsert_overwrites_caller_rights_status_from_register(monkeypatch):
    monkeypatch.setattr(
        "services.qdrant.indexer.resolve_source_rights_status",
        lambda **_kwargs: "unverified",
    )
    source = span(domain_rights_status="licensed")
    client = FakeClient()

    store(client).upsert(parent([source]), [source])

    payload = client.points[point_id_for_record(source.source_span_id)].payload
    assert payload["domain_rights_status"] == "unverified"


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
    assert {
        "parent_unit_id",
        "record_type",
        "rights_cleared",
        "domain_rights_status",
    } <= set(created)


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
    assert conditions["domain_rights_status"] == "licensed"


def test_retrieve_rechecks_canonical_rights_after_qdrant_returns_hit():
    source = span()
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([source]), [source])
    client.points[point_id_for_record(source.source_span_id)].payload["domain_rights_status"] = (
        "revoked"
    )
    client.query_points = lambda **_kwargs: SimpleNamespace(
        points=[
            SimpleNamespace(
                id=point_id_for_record(source.source_span_id),
                score=1.0,
                payload={
                    "parent_unit_id": source.parent_unit_id,
                    "source_span_id": source.source_span_id,
                },
            )
        ]
    )

    assert adapter.retrieve([0.1] * 8) == []


def test_points_servable_rejects_revoked_status_even_when_legacy_boolean_is_true():
    source = span()
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([source]), [source])
    point_id = point_id_for_record(source.source_span_id)
    evidence = [citation_evidence(source)]

    assert adapter.points_servable([point_id], expected_evidence=evidence) is True
    client.points[point_id].payload["domain_rights_status"] = "revoked"
    assert adapter.points_servable([point_id], expected_evidence=evidence) is False


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


def test_fetch_rejects_parent_text_hash_mismatch():
    s1, s2 = span(0), span(1)
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([s1, s2]), [s1, s2])
    parent_record = client.points[parent_point_id("parentA")]
    parent_record.payload["parent_text_hash"] = "b" * 64

    with pytest.raises(FirstPersonContextStoreError, match="parent_text_hash"):
        adapter.fetch_parent_context("parentA", [s1.source_span_id])


def test_fetch_rejects_child_outside_parent_bounds():
    s1, s2 = span(0), span(1)
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([s1, s2]), [s1, s2])
    child_record = client.points[point_id_for_record(s2.source_span_id)]
    child_record.payload.update(start_ms=2500, end_ms=3400)

    with pytest.raises(FirstPersonContextStoreError, match="outside parent bounds"):
        adapter.fetch_parent_context("parentA", [s1.source_span_id])


def test_fetch_rejects_non_chronological_parent_ordered_ids():
    s1, s2 = span(0), span(1)
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([s1, s2]), [s1, s2])
    parent_record = client.points[parent_point_id("parentA")]
    parent_record.payload["ordered_source_span_ids"] = (
        s2.source_span_id,
        s1.source_span_id,
    )
    parent_record.payload["parent_text_hash"] = clip_text_hash(
        " ".join((s2.verbatim_text, s1.verbatim_text))
    )

    with pytest.raises(FirstPersonContextStoreError, match="strictly chronological"):
        adapter.fetch_parent_context("parentA", [s1.source_span_id])


def test_every_harness_filter_field_has_a_declared_payload_index():
    """A filter on an unindexed field is a full scan on a large collection.

    The concept-filtered retrieval (plan T3) is unusable at scale without these,
    so the index declaration is pinned rather than trusted to review.
    """
    from services.first_person_context_store import SPAN_INDEXES

    declared = {key for key, _schema in SPAN_INDEXES}
    for field in (
        "record_type",
        "rights_cleared",
        "domain_rights_status",
        "guru_id",
        "parent_unit_id",
        "source_span_id",
        "corpus_version",
        "topic_ids",
        "entity_ids",
    ):
        assert field in declared, f"{field} is filtered but has no declared payload index"


def test_upsert_refuses_verified_without_method():
    bad = span(0, speaker_verified=True, voice_verification_method=None)
    client = FakeClient()
    with pytest.raises(FirstPersonContextStoreError, match="speaker_verified_without_method"):
        store(client).upsert(parent([bad]), [bad])
    assert client.points == {}  # nothing was written


def test_upsert_accepts_verified_with_method_and_unverified_without():
    ok = span(0, speaker_verified=True, voice_verification_method="ecapa_voxceleb_span_slice_v2")
    pending = span(1, speaker_verified=False, voice_verification_method=None)
    client = FakeClient()
    assert store(client).upsert(parent([ok, pending]), [ok, pending]) == 3


def test_a_live_payload_with_the_defect_can_still_be_read_back():
    """The check is write-time only: the 732 live spans must keep loading for serving."""
    from domain.first_person_context import SourceSpan

    legacy = span(0, speaker_verified=True, voice_verification_method=None)
    from services.first_person_context_store import _strip_record_type

    restored = SourceSpan.model_validate(_strip_record_type(legacy.to_payload()))
    assert restored.speaker_verified is True and restored.voice_verification_method is None


# ── I3: a promotion is refused as a whole, before any write ──────────────────


def test_a_manifest_with_one_bare_flag_span_refuses_the_whole_promotion():
    from services.first_person_context_store import (
        FirstPersonContextStoreError,
        assert_no_bare_flag_speakers,
    )

    good = span(0, speaker_verified=True, voice_verification_method="ecapa_voxceleb_span_slice_v2")
    bad = span(1, speaker_verified=True, voice_verification_method=None)
    payloads = [good.to_payload(), bad.to_payload()]
    assert [p.get("record_type") for p in payloads] == ["retrieval_child", "retrieval_child"]
    with pytest.raises(FirstPersonContextStoreError, match="1 span"):
        assert_no_bare_flag_speakers(payloads, where="test")
    assert_no_bare_flag_speakers([good.to_payload()], where="test")  # no raise


def test_unverified_spans_and_parents_are_not_bare_flag_violations():
    from services.first_person_context_store import assert_no_bare_flag_speakers

    pending = span(0, speaker_verified=False, voice_verification_method=None)
    parent_payload = {"record_type": "parent_unit", "parent_unit_id": "p1"}
    assert_no_bare_flag_speakers([pending.to_payload(), parent_payload], where="test")


def test_the_v9_builder_refuses_before_creating_the_target_collection(monkeypatch):
    """A guard that runs after create_collection would still have mutated the cluster."""
    import scripts.ops.build_fp_context_from_v9 as build
    from services.first_person_context_store import FirstPersonContextStoreError

    manifest = [
        {
            "record_type": "retrieval_child",
            "source_span_id": "a" * 64,
            "speaker_verified": True,
            "voice_verification_method": None,
        }
    ]
    with pytest.raises(FirstPersonContextStoreError, match="speaker_verified=true"):
        build._apply(manifest, [], qdrant_url="http://127.0.0.1:1", target="never_created")


@pytest.mark.parametrize(
    "overrides,reason",
    [
        ({"voice_score": None}, "ecapa_missing:voice_score"),
        ({"voice_calibration_id": None}, "ecapa_missing:voice_calibration_id"),
        ({"voice_model_revision": None}, "ecapa_missing:voice_model_revision"),
        ({"voice_threshold_applied": None}, "ecapa_missing:voice_threshold_applied"),
        ({"voice_score": 0.1}, "ecapa_score_below_floor"),
        ({"voice_window_check": "fail"}, "window_check_failed"),
        ({"voice_verification_method": "human_listen_v1"}, "human_missing:reviewer_id"),
        ({"voice_verification_method": "trust_me"}, "voice_method_unknown:trust_me"),
    ],
)
def test_upsert_refuses_each_incomplete_speaker_record_and_issues_no_write(overrides, reason):
    """P2: a method alone is not evidence. One refusal per rule; the client sees nothing."""
    bad = span(0, **overrides)
    client = FakeClient()
    with pytest.raises(FirstPersonContextStoreError, match=reason):
        store(client).upsert(parent([bad]), [bad])
    assert client.points == {}


def test_upsert_accepts_a_complete_human_listen_record():
    ok = span(
        0,
        voice_verification_method="human_listen_v1",
        voice_score=None,
        voice_calibration_id=None,
        voice_model_revision=None,
        voice_threshold_applied=None,
        voice_window_check=None,
        speaker_verification_status="verified",
        reviewer_id="reviewer-1",
        reviewed_at="2026-10-31T10:00:00+00:00",
        reviewed_audio_sha256="a" * 64,
        review_choice="sri_krishnaji",
        start_ms=0,
        end_ms=3000,
    )
    assert store(FakeClient()).upsert(parent([ok]), [ok]) == 2


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"review_choice": "host_or_interviewer"}, "human_choice_not_teacher"),
        ({"review_choice": "sri_preethaji"}, "human_choice_not_teacher"),
        ({"review_choice": "unclear"}, "human_choice_not_teacher"),
        ({"end_ms": 1900}, "human_clip_too_short"),
    ],
)
def test_upsert_refuses_a_human_listen_that_does_not_confirm_the_teacher(overrides, reason):
    fields = {
        "voice_verification_method": "human_listen_v1",
        "voice_score": None,
        "voice_calibration_id": None,
        "voice_model_revision": None,
        "voice_threshold_applied": None,
        "voice_window_check": None,
        "speaker_verification_status": "verified",
        "reviewer_id": "reviewer-1",
        "reviewed_at": "2026-10-31T10:00:00+00:00",
        "reviewed_audio_sha256": "a" * 64,
        "review_choice": "sri_krishnaji",
        "start_ms": 0,
        "end_ms": 3000,
    }
    bad = span(0, **{**fields, **overrides})
    client = FakeClient()
    with pytest.raises(FirstPersonContextStoreError, match=reason):
        store(client).upsert(parent([bad]), [bad])
    assert client.points == {}


def test_upsert_refuses_a_new_write_claiming_the_legacy_centroid_method():
    bad = span(0, voice_verification_method="ecapa_voxceleb_centroid_v1")
    client = FakeClient()
    with pytest.raises(FirstPersonContextStoreError, match="legacy_method_refused"):
        store(client).upsert(parent([bad]), [bad])
    assert client.points == {}


def test_the_collection_level_check_reports_violators_by_span_without_loading_the_model():
    from services.first_person_context_store import speaker_provenance_violations

    payloads = [
        span(0).to_payload(),
        span(1, voice_score=None).to_payload(),
        span(2, speaker_verified=False, voice_verification_method=None).to_payload(),
        {"record_type": "parent_unit", "speaker_verified": True},
    ]
    found = speaker_provenance_violations(payloads)
    assert list(found.values()) == [["ecapa_missing:voice_score"]]


def test_calculate_temporal_quality_weighting():
    from types import SimpleNamespace

    from services.first_person_context_store import _calculate_temporal_quality

    # Neutral base span
    hit_base = SimpleNamespace(
        score=0.8,
        payload={
            "verbatim_text": "Inner peace is discovered when you observe the mind without judgment.",
            "start_ms": 60000,
        },
    )
    assert _calculate_temporal_quality(hit_base) == pytest.approx(0.8)

    # Promo outro downweighting
    hit_promo = SimpleNamespace(
        score=0.8,
        payload={
            "verbatim_text": "Congratulations on completing this mystic secrets course available at ekam online.",
            "start_ms": 60000,
        },
    )
    assert _calculate_temporal_quality(hit_promo) == pytest.approx(0.8 * 0.40)

    # Intro banter downweighting at t=0s
    hit_intro = SimpleNamespace(
        score=0.8,
        payload={
            "verbatim_text": "Good morning everyone, welcome to this beautiful talk today.",
            "start_ms": 0,
        },
    )
    assert _calculate_temporal_quality(hit_intro) == pytest.approx(0.8 * 0.65)

    # Meditation directive boost
    hit_meditation = SimpleNamespace(
        score=0.8,
        payload={
            "verbatim_text": "Inhale deeply, observe the breath, and feel the sound of a bee humming.",
            "start_ms": 60000,
        },
    )
    assert _calculate_temporal_quality(hit_meditation) == pytest.approx(0.8 * 1.25)


def test_temporal_quality_is_inactive_without_the_explicit_setting(monkeypatch):
    from types import SimpleNamespace

    from services.first_person_context_store import _ranking_score

    hit = SimpleNamespace(
        score=0.8,
        payload={
            "verbatim_text": "Congratulations on completing this mystic secrets course.",
            "start_ms": 60000,
        },
    )
    monkeypatch.delattr(settings, "first_person_context_temporal_quality_enabled", raising=False)
    assert _ranking_score(hit) == pytest.approx(0.8)

    monkeypatch.setattr(
        settings, "first_person_context_temporal_quality_enabled", True, raising=False
    )
    assert _ranking_score(hit) == pytest.approx(0.8 * 0.40)


def test_fetches_only_immediate_same_parent_previous_and_next_siblings():
    s1 = span(0, start_ms=10000, end_ms=25000)
    s2 = span(1, start_ms=25500, end_ms=40000)
    s3 = span(2, start_ms=40500, end_ms=55000)
    s1 = s1.model_copy(update={"next_span_id": s2.source_span_id})
    s2 = s2.model_copy(
        update={"previous_span_id": s1.source_span_id, "next_span_id": s3.source_span_id}
    )
    s3 = s3.model_copy(update={"previous_span_id": s2.source_span_id})
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([s1, s2, s3]), [s1, s2, s3])

    assert adapter.fetch_preceding_span(s2) == s1
    assert adapter.fetch_succeeding_span(s2) == s3
    assert adapter.fetch_preceding_span(s1) is None
    assert adapter.fetch_succeeding_span(s3) is None


def test_legacy_timestamp_adjacency_call_fails_closed_without_scanning():
    client = FakeClient()
    adapter = store(client)
    assert adapter.fetch_succeeding_span("vidA", after_end_ms=25000) is None
    assert adapter.fetch_preceding_span("vidA", before_start_ms=25000) is None
    assert client.filters == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"parent_unit_id": "other-parent"},
        {"video_id": "other-video"},
        {"guru_id": "other-guru", "speaker_id": "other-guru"},
        {"corpus_version": "other-corpus"},
        {"speaker_id": "other-speaker"},
        {"speaker_verified": False},
        {"rights_cleared": False},
    ],
)
def test_adjacency_rejects_current_span_identity_and_serve_gate_mismatches(overrides):
    current = span(0)
    sibling = span(1)
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([current, sibling]), [current, sibling])

    candidate = span(0, **overrides)
    assert adapter.fetch_succeeding_span(candidate) is None


def test_adjacency_rejects_unservable_adjacent_span(monkeypatch):
    current = span(0)
    sibling = span(1)
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([current, sibling]), [current, sibling])
    monkeypatch.setattr(
        "services.first_person_context_store.video_is_blocked",
        lambda video_id: video_id == sibling.video_id,
    )

    assert adapter.fetch_succeeding_span(current) is None


def test_adjacency_rejects_invalid_adjacent_hash_payload():
    current = span(0)
    sibling = span(1)
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([current, sibling]), [current, sibling])
    sibling_record = client.points[point_id_for_record(sibling.source_span_id)]
    sibling_record.payload["source_text_hash"] = "b" * 64

    assert adapter.fetch_succeeding_span(current) is None


def test_adjacency_rejects_a_host_role_neighbor():
    current = span(0)
    sibling = span(1)
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([current, sibling]), [current, sibling])
    sibling_record = client.points[point_id_for_record(sibling.source_span_id)]
    sibling_record.payload["speaker_role"] = SpeakerRole.HOST.value

    assert adapter.fetch_succeeding_span(current) is None


@pytest.mark.parametrize(
    "provenance_override",
    [
        {"voice_score": None},
        {"voice_verification_method": "unknown_voice_method"},
    ],
)
def test_adjacency_rejects_incomplete_or_unknown_voice_evidence(provenance_override):
    current = span(0)
    sibling = span(1)
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([current, sibling]), [current, sibling])
    sibling_record = client.points[point_id_for_record(sibling.source_span_id)]
    sibling_record.payload.update(provenance_override)

    assert adapter.fetch_succeeding_span(current) is None


def test_points_servable_revalidates_complete_exact_cache_provenance():
    child = span(0)
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([child]), [child])
    point_id = point_id_for_record(child.source_span_id)

    assert adapter.points_servable([point_id]) is True
    requested_keys = set(client.retrieve_payloads[-1])
    assert {
        "speaker_id",
        "guru_id",
        "start_ms",
        "end_ms",
        "speaker_role",
        "speaker_verified",
        "rights_cleared",
        "domain_rights_status",
        "voice_verification_method",
        "voice_model_revision",
        "voice_score",
        "voice_margin",
        "voice_threshold_applied",
        "voice_calibration_id",
        "voice_window_check",
        "voice_verified_at",
        "speaker_verification_status",
        "reviewer_id",
        "reviewed_at",
        "reviewed_audio_sha256",
        "review_choice",
    } <= requested_keys

    record = client.points[point_id]
    record.payload["voice_score"] = None
    assert adapter.points_servable([point_id]) is False

    record.payload.update(
        voice_score=child.voice_score, voice_verification_method="unknown_voice_method"
    )
    assert adapter.points_servable([point_id]) is False


def test_points_servable_rejects_stale_licensed_status_after_register_change(monkeypatch):
    child = span(0)
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([child]), [child])
    point_id = point_id_for_record(child.source_span_id)
    evidence = [citation_evidence(child)]
    monkeypatch.setattr(
        "services.first_person_context_store.source_is_authoritatively_licensed",
        lambda **_kwargs: False,
    )

    assert adapter.points_servable([point_id], expected_evidence=evidence) is False


@pytest.mark.parametrize(
    "payload_update",
    [
        {"verbatim_text": "A changed current payload."},
        {"source_text_hash": "b" * 64},
        {"boundary_status": BoundaryStatus.UNCERTAIN.value},
        {"completeness_status": CompletenessStatus.UNCERTAIN.value},
        {"start_ms": 2000},
        {"guru_id": "preethaji"},
        {"speaker_id": "preethaji"},
        {"source_url": "https://evil.example/not-the-source"},
        {"quality_status": "quarantined"},
    ],
)
def test_points_servable_rejects_current_payload_evidence_changes(payload_update):
    child = span(0)
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([child]), [child])
    point_id = point_id_for_record(child.source_span_id)
    evidence = citation_evidence(child)
    assert adapter.points_servable([point_id], expected_evidence=[evidence]) is True

    client.points[point_id].payload.update(payload_update)

    assert adapter.points_servable([point_id], expected_evidence=[evidence]) is False


def test_points_servable_rejects_a_changed_or_revoked_second_child():
    first, second = span(0), span(1)
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([first, second]), [first, second])
    point_ids = [
        point_id_for_record(first.source_span_id),
        point_id_for_record(second.source_span_id),
    ]
    evidence = [citation_evidence(first), citation_evidence(second)]

    client.points[point_ids[1]].payload["verbatim_text"] = "Changed second child."
    assert adapter.points_servable(point_ids, expected_evidence=evidence) is False

    client.points[point_ids[1]].payload.update(
        verbatim_text=second.verbatim_text,
        source_text_hash=second.source_text_hash,
        rights_cleared=False,
    )
    assert adapter.points_servable(point_ids, expected_evidence=evidence) is False


def test_fresh_cache_validation_uses_parent_order_for_a_valid_subset():
    first, middle, last = span(0), span(1), span(2)
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([first, middle, last]), [first, middle, last])
    point_ids = [
        point_id_for_record(first.source_span_id),
        point_id_for_record(last.source_span_id),
    ]
    evidence = [citation_evidence(first), citation_evidence(last)]

    fresh = adapter.fresh_spans_for_citations(point_ids, expected_evidence=evidence)

    assert fresh == [first, last]


def test_fresh_cache_validation_rejects_mixed_parent_evidence():
    first = span(0)
    foreign = span(1, parent_unit_id="parentB")
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([first]), [first])
    adapter.upsert(parent([foreign], parent_unit_id="parentB"), [foreign])
    point_ids = [
        point_id_for_record(first.source_span_id),
        point_id_for_record(foreign.source_span_id),
    ]

    assert (
        adapter.fresh_spans_for_citations(
            point_ids,
            expected_evidence=[citation_evidence(first), citation_evidence(foreign)],
        )
        is None
    )


def test_fresh_cache_validation_rejects_reordered_cached_span_ids():
    first, second = span(0), span(1)
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([first, second]), [first, second])
    point_ids = [
        point_id_for_record(second.source_span_id),
        point_id_for_record(first.source_span_id),
    ]

    assert (
        adapter.fresh_spans_for_citations(
            point_ids,
            expected_evidence=[citation_evidence(second), citation_evidence(first)],
        )
        is None
    )


def test_fragment_predecessor_requires_immediate_order_and_reciprocal_pointers():
    predecessor = span(0, completeness_status=CompletenessStatus.FRAGMENT)
    current = span(
        1,
        previous_span_id=predecessor.source_span_id,
        start_ms=10000,
        end_ms=10900,
    )
    predecessor = predecessor.model_copy(update={"next_span_id": current.source_span_id})
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([predecessor, current]), [predecessor, current])

    assert adapter.fetch_preceding_span(current) == predecessor

    client.points[point_id_for_record(predecessor.source_span_id)].payload["next_span_id"] = (
        "not-the-current-child"
    )
    assert adapter.fetch_preceding_span(current) is None


def test_adjacency_requires_explicit_pointer_consistency():
    current = span(0, next_span_id="not-the-sibling")
    sibling = span(1)
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([current, sibling]), [current, sibling])

    assert adapter.fetch_succeeding_span(current) is None


@pytest.mark.parametrize("direction", ["preceding", "succeeding"])
def test_adjacency_rejects_same_id_caller_with_stale_pointer(direction):
    predecessor = span(0, start_ms=10000, end_ms=10900)
    current = span(1, start_ms=11000, end_ms=11900)
    predecessor = predecessor.model_copy(update={"next_span_id": current.source_span_id})
    current = current.model_copy(update={"previous_span_id": predecessor.source_span_id})
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([predecessor, current]), [predecessor, current])

    caller = (
        current.model_copy(update={"previous_span_id": "stale-predecessor"})
        if direction == "preceding"
        else predecessor.model_copy(update={"next_span_id": "stale-successor"})
    )

    result = (
        adapter.fetch_preceding_span(caller)
        if direction == "preceding"
        else adapter.fetch_succeeding_span(caller)
    )
    assert result is None


@pytest.mark.parametrize(
    ("direction", "missing_pointer"),
    [
        ("preceding", "current_previous_span_id"),
        ("preceding", "sibling_next_span_id"),
        ("succeeding", "current_next_span_id"),
        ("succeeding", "sibling_previous_span_id"),
    ],
)
def test_same_parent_adjacency_requires_both_reciprocal_pointers(direction, missing_pointer):
    predecessor = span(0, start_ms=10000, end_ms=10900)
    current = span(1, start_ms=11000, end_ms=11900)
    predecessor = predecessor.model_copy(update={"next_span_id": current.source_span_id})
    current = current.model_copy(update={"previous_span_id": predecessor.source_span_id})
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([predecessor, current]), [predecessor, current])

    if direction == "succeeding":
        target = predecessor if missing_pointer.startswith("current_") else current
    else:
        target = current if missing_pointer.startswith("current_") else predecessor
    field = missing_pointer.removeprefix("current_").removeprefix("sibling_")
    client.points[point_id_for_record(target.source_span_id)].payload[field] = None

    result = (
        adapter.fetch_preceding_span(current)
        if direction == "preceding"
        else adapter.fetch_succeeding_span(predecessor)
    )
    assert result is None


def _cross_parent_pair(**overrides):
    predecessor = span(
        0,
        parent_unit_id="previous-parent",
        start_ms=1000,
        end_ms=1900,
        word_start=0,
        word_end=6,
    )
    opener = span(
        1,
        parent_unit_id="current-parent",
        start_ms=2000,
        end_ms=2900,
        word_start=10,
        word_end=16,
        previous_span_id=predecessor.source_span_id,
        **overrides,
    )
    predecessor = predecessor.model_copy(update={"next_span_id": opener.source_span_id})
    return predecessor, opener


def test_fetch_preceding_span_recovers_only_the_validated_immediate_cross_parent_edge():
    predecessor, opener = _cross_parent_pair()
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([predecessor]), [predecessor])
    adapter.upsert(parent([opener]), [opener])

    edge = adapter.fetch_preceding_span(opener)
    assert isinstance(edge, ValidatedCrossParentEdge)
    assert edge.predecessor == predecessor
    assert edge.opener == opener
    assert edge.predecessor_parent_unit_id == "previous-parent"
    assert edge.opener_parent_unit_id == "current-parent"
    assert edge.predecessor.next_span_id == edge.opener.source_span_id
    assert edge.opener.previous_span_id == edge.predecessor.source_span_id


def test_cross_parent_predecessor_allows_indices_reset_at_parent_boundary():
    predecessor, opener = _cross_parent_pair()
    predecessor = predecessor.model_copy(update={"source_span_index": 0})
    opener = opener.model_copy(update={"source_span_index": 0})
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([predecessor]), [predecessor])
    adapter.upsert(parent([opener]), [opener])

    edge = adapter.fetch_preceding_span(opener)

    assert isinstance(edge, ValidatedCrossParentEdge)
    assert edge.predecessor.source_span_index == edge.opener.source_span_index == 0
    assert edge.predecessor.end_ms < edge.opener.start_ms
    assert edge.predecessor.word_end < edge.opener.word_start


@pytest.mark.parametrize(
    "mutate",
    [
        lambda predecessor, opener: {"next_span_id": "wrong-child"},
        lambda predecessor, opener: {"previous_span_id": "wrong-child"},
        lambda predecessor, opener: {"parent_unit_id": "same-parent"},
        lambda predecessor, opener: {"speaker_id": "other-speaker"},
        lambda predecessor, opener: {"rights_cleared": False},
        lambda predecessor, opener: {"boundary_status": BoundaryStatus.UNCERTAIN.value},
    ],
)
def test_cross_parent_predecessor_refuses_bad_pointer_boundary_speaker_or_rights(mutate):
    predecessor, opener = _cross_parent_pair()
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([predecessor]), [predecessor])
    adapter.upsert(parent([opener]), [opener])
    update = mutate(predecessor, opener)
    target = predecessor if "next_span_id" in update else opener
    client.points[point_id_for_record(target.source_span_id)].payload.update(update)

    assert adapter.fetch_preceding_span(opener) is None


def test_cross_parent_predecessor_must_be_the_previous_parent_last_child():
    predecessor, opener = _cross_parent_pair()
    trailing = span(
        2,
        parent_unit_id="previous-parent",
        start_ms=3000,
        end_ms=3900,
        word_start=20,
        word_end=26,
    )
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([predecessor, trailing]), [predecessor, trailing])
    adapter.upsert(parent([opener]), [opener])

    assert adapter.fetch_preceding_span(opener) is None


def test_cross_parent_predecessor_rejects_an_unservable_non_edge_child():
    predecessor, opener = _cross_parent_pair()
    trailing = span(
        2,
        parent_unit_id="current-parent",
        start_ms=3000,
        end_ms=3900,
        word_start=20,
        word_end=26,
        boundary_status=BoundaryStatus.UNCERTAIN,
    )
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([predecessor]), [predecessor])
    adapter.upsert(parent([opener, trailing]), [opener, trailing])

    assert adapter.fetch_preceding_span(opener) is None


def test_cross_parent_predecessor_rejects_an_artifact_in_a_hydrated_child():
    predecessor, opener = _cross_parent_pair()
    bad_text = "I need to analyze the user prompt."
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([predecessor]), [predecessor])
    adapter.upsert(parent([opener]), [opener])
    child_payload = client.points[point_id_for_record(opener.source_span_id)].payload
    child_payload.update(
        source_transcript_text=bad_text,
        verbatim_text=bad_text,
        source_text_hash=clip_text_hash(bad_text),
    )
    client.points[parent_point_id("current-parent")].payload["parent_text_hash"] = clip_text_hash(
        bad_text
    )

    assert adapter.fetch_preceding_span(opener) is None


def test_cross_parent_predecessor_refuses_overlapping_parent_boundaries():
    predecessor, opener = _cross_parent_pair()
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([predecessor]), [predecessor])
    adapter.upsert(parent([opener]), [opener])
    client.points[parent_point_id("previous-parent")].payload["end_ms"] = 2500

    assert adapter.fetch_preceding_span(opener) is None


@pytest.mark.parametrize("blocked_identity", ["video", "point"])
def test_cross_parent_predecessor_rejects_canonical_h4_blocked_endpoint(
    monkeypatch, blocked_identity
):
    predecessor, opener = _cross_parent_pair()
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([predecessor]), [predecessor])
    adapter.upsert(parent([opener]), [opener])

    blocked = (
        opener.video_id
        if blocked_identity == "video"
        else point_id_for_record(opener.source_span_id)
    )
    monkeypatch.setattr("services.first_person_store.BLOCKED_PROMISE_POINT_IDS", {blocked})

    assert adapter.fetch_preceding_span(opener) is None


def test_cross_parent_predecessor_rejects_canonical_h4_outcome_promise_endpoint():
    predecessor, opener = _cross_parent_pair()
    promise = "This guaranteed miracle will solve every problem."
    opener = opener.model_copy(
        update={
            "source_transcript_text": promise,
            "verbatim_text": promise,
            "source_text_hash": clip_text_hash(promise),
        }
    )
    predecessor = predecessor.model_copy(update={"next_span_id": opener.source_span_id})
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([predecessor]), [predecessor])
    adapter.upsert(parent([opener]), [opener])

    assert adapter.fetch_preceding_span(opener) is None


def test_cross_parent_predecessor_rejects_canonical_h4_outcome_promise_in_non_edge_child():
    predecessor, opener = _cross_parent_pair()
    trailing = span(
        2,
        parent_unit_id="current-parent",
        start_ms=3000,
        end_ms=3900,
        word_start=20,
        word_end=26,
    )
    promise = "This guaranteed miracle will solve every problem."
    trailing = trailing.model_copy(
        update={
            "source_transcript_text": promise,
            "verbatim_text": promise,
            "source_text_hash": clip_text_hash(promise),
        }
    )
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([predecessor]), [predecessor])
    adapter.upsert(parent([opener, trailing]), [opener, trailing])

    assert adapter.fetch_preceding_span(opener) is None


def test_cross_parent_predecessor_rejects_lowercase_severed_preposition_opener():
    predecessor, opener = _cross_parent_pair()
    text = "in the quiet attention of the present moment."
    opener = opener.model_copy(
        update={
            "source_transcript_text": text,
            "verbatim_text": text,
            "source_text_hash": clip_text_hash(text),
        }
    )
    predecessor = predecessor.model_copy(update={"next_span_id": opener.source_span_id})
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([predecessor]), [predecessor])
    adapter.upsert(parent([opener]), [opener])

    assert adapter.fetch_preceding_span(opener) is None


@pytest.mark.parametrize("parent_id", ["previous-parent", "current-parent"])
@pytest.mark.parametrize("status", [CompletenessStatus.UNCERTAIN, CompletenessStatus.FRAGMENT])
def test_cross_parent_predecessor_requires_complete_hydrated_parent_records(parent_id, status):
    predecessor, opener = _cross_parent_pair()
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(
        parent(
            [predecessor],
            completeness_status=status
            if parent_id == "previous-parent"
            else CompletenessStatus.COMPLETE,
        ),
        [predecessor],
    )
    adapter.upsert(
        parent(
            [opener],
            completeness_status=status
            if parent_id == "current-parent"
            else CompletenessStatus.COMPLETE,
        ),
        [opener],
    )

    assert adapter.fetch_preceding_span(opener) is None


def test_cross_parent_predecessor_rejects_uncertain_non_edge_child():
    predecessor, opener = _cross_parent_pair()
    trailing = span(
        2,
        parent_unit_id="current-parent",
        start_ms=3000,
        end_ms=3900,
        word_start=20,
        word_end=26,
        completeness_status=CompletenessStatus.UNCERTAIN,
    )
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([predecessor]), [predecessor])
    adapter.upsert(parent([opener, trailing]), [opener, trailing])

    assert adapter.fetch_preceding_span(opener) is None


def test_cross_parent_predecessor_requires_complete_actual_predecessor():
    predecessor, opener = _cross_parent_pair()
    predecessor = predecessor.model_copy(
        update={"completeness_status": CompletenessStatus.FRAGMENT}
    )
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([predecessor]), [predecessor])
    adapter.upsert(parent([opener]), [opener])

    assert adapter.fetch_preceding_span(opener) is None


def test_cross_parent_predecessor_allows_fragment_opener_when_predecessor_completes_it():
    predecessor, opener = _cross_parent_pair()
    opener = opener.model_copy(update={"completeness_status": CompletenessStatus.FRAGMENT})
    client = FakeClient()
    adapter = store(client)
    adapter.upsert(parent([predecessor]), [predecessor])
    adapter.upsert(parent([opener]), [opener])

    assert isinstance(adapter.fetch_preceding_span(opener), ValidatedCrossParentEdge)


# --- Original-query confidence read path (2026-11-18) -----------------------
# HyDE replaces the retrieval vector, so the retrieval score no longer describes the
# seeker's question. The pipeline recomputes confidence from the stored child vectors;
# that read is read-only and must never widen a candidate set.


class _VectorClient:
    """Minimal client that answers ``retrieve`` with named dense vectors only."""

    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self.vectors = vectors
        self.calls: list[tuple[object, ...]] = []
        self.raise_on_call = False

    def retrieve(self, collection_name, ids, with_payload=True, with_vectors=False):
        self.calls.append((collection_name, list(ids), with_payload, with_vectors))
        if self.raise_on_call:
            raise RuntimeError("qdrant unavailable")
        return [
            SimpleNamespace(id=i, vector={"passage_dense": self.vectors[i]})
            for i in ids
            if i in self.vectors
        ]


def test_dense_vectors_for_spans_reads_named_dense_vectors_without_payload():
    sample = span(3)
    point_id = point_id_for_record(sample.source_span_id)
    client = _VectorClient({point_id: [0.25, 0.5]})
    adapter = store(client)

    got = adapter.dense_vectors_for_spans([sample.source_span_id, "missing-span"])

    assert got == {sample.source_span_id: [0.25, 0.5]}
    assert client.calls == [
        ("fp_context_test", [point_id, point_id_for_record("missing-span")], False, ["passage_dense"])
    ]


def test_dense_vectors_for_spans_fails_open_on_transport_error():
    sample = span(4)
    client = _VectorClient({point_id_for_record(sample.source_span_id): [1.0, 0.0]})
    client.raise_on_call = True

    assert store(client).dense_vectors_for_spans([sample.source_span_id]) == {}


def test_dense_vectors_for_spans_with_no_ids_never_calls_the_client():
    client = _VectorClient({})
    assert store(client).dense_vectors_for_spans([]) == {}
    assert client.calls == []


class _NoSparseVectorClient(FakeClient):
    """A collection built before `passage_sparse` existed: the lane must degrade."""

    def query_points(  # type: ignore[override]
        self,
        collection_name,
        query,
        using=None,
        query_filter=None,
        limit=10,
        with_payload=True,
        prefetch=None,
        **kwargs,
    ):
        if prefetch:
            raise RuntimeError("Wrong input: Not existing vector name error: passage_sparse")
        return super().query_points(
            collection_name,
            query,
            using=using,
            query_filter=query_filter,
            limit=limit,
            with_payload=with_payload,
            **kwargs,
        )


def test_retrieve_degrades_to_dense_when_the_collection_has_no_sparse_vector():
    s1, s2 = span(0), span(1)
    client = _NoSparseVectorClient()
    adapter = store(client)
    adapter.upsert(parent([s1, s2]), [s1, s2])

    contexts = adapter.retrieve(
        [0.1] * 8,
        query_sparse={"indices": [1, 2], "values": [0.5, 0.5]},
        limit_parents=3,
    )

    assert [c.parent.parent_unit_id for c in contexts] == ["parentA"]
    assert {s.source_span_id for s in contexts[0].spans} == {s1.source_span_id, s2.source_span_id}
