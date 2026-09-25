"""
Unit tests for FirstPersonPipeline (Phase F).
"""

import hashlib
from unittest.mock import MagicMock
import pytest

from services.crisis_helplines import format_helplines_block
from services.first_person_pipeline import (
    FirstPersonPipeline,
    FirstPersonPipelineResult,
    load_calibration_profile,
)

GOOD_TEXT = "Suffering arises from resistance to what is."
GOOD_HASH = hashlib.sha256(GOOD_TEXT.encode("utf-8")).hexdigest()

VALID_PROFILE = {
    "threshold": 0.5,
    "score_kind": "dense_cosine",
    "n": 100,
    "ucb_risk": 0.01,
    "target_risk": 0.01,
    "collection": "first_person_v1",
    "fitted_at": "2026-09-24",
}


def _clip(**overrides):
    base = {
        "point_id": "p1",
        "video_id": "vid_abc",
        "start_ms": 65000,
        "end_ms": 75000,
        "speaker": "Sri Preethaji",
        "teacher_id": "preethaji",
        "transcript_hash": GOOD_HASH,
        "verbatim_text": GOOD_TEXT,
        "passage_dense": [1.0, 0.0],
        "source_url": "https://youtube.com/watch?v=vid_abc",
        "caption_status": "auto_transcript",
    }
    base.update(overrides)
    return base


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.collection = "first_person_v1"
    return store


@pytest.fixture
def mock_redis():
    redis = MagicMock()
    redis.get.return_value = None
    return redis


def test_crisis_precheck_fails_closed(mock_store, mock_redis):
    pipeline = FirstPersonPipeline(store=mock_store, redis_client=mock_redis)

    res = pipeline.execute(
        query="I want to kill myself today",
        query_dense_vector=[0.1] * 1024,
    )

    assert res.status == "crisis_redirect"
    assert not res.is_direct_answer
    assert res.answer_text == format_helplines_block()
    assert len(res.citations) == 0
    # Store was never queried
    mock_store.search_hybrid.assert_not_called()


def test_exact_cache_hit(mock_store, mock_redis):
    pipeline = FirstPersonPipeline(store=mock_store, redis_client=mock_redis)

    mock_redis.get.return_value = (
        b'{"answer_text": "Cached teaching", "citations": [], "status": "weak_match", "is_direct_answer": false}'
    )

    res = pipeline.execute(
        query="What is suffering?",
        query_dense_vector=[0.1] * 1024,
    )

    assert res.cached is True
    assert res.status == "weak_match"
    assert res.answer_text == "Cached teaching"
    mock_store.search_hybrid.assert_not_called()


def test_exact_cache_hit_rejected_on_tampered_citation(mock_store, mock_redis):
    """(a) a cached citation that fails re-verification must not be served."""
    import json

    pipeline = FirstPersonPipeline(store=mock_store, redis_client=mock_redis)
    cached_payload = {
        "answer_text": "x",
        "citations": [
            {
                "verbatim_text": "tampered text, not matching the stored hash",
                "transcript_hash": GOOD_HASH,
                "speaker": "Sri Preethaji",
            }
        ],
        "status": "success",
        "is_direct_answer": True,
    }
    mock_redis.get.return_value = json.dumps(cached_payload).encode("utf-8")
    mock_store.search_hybrid.return_value = []

    res = pipeline.execute(query="What is suffering?", query_dense_vector=[0.1] * 1024)

    assert res.cached is False
    assert res.status == "abstained"


def test_tampered_transcript_hash_is_quarantined(mock_store, mock_redis):
    """(a) a tampered transcript_hash clip is never served."""
    clip = _clip(transcript_hash="0" * 64)
    mock_store.search_hybrid.return_value = [clip]

    pipeline = FirstPersonPipeline(store=mock_store, redis_client=mock_redis, calibration_profile=VALID_PROFILE)
    res = pipeline.execute(query="What causes suffering?", query_dense_vector=[1.0, 0.0])

    assert res.status == "abstained"
    assert len(res.citations) == 0


def test_unknown_speaker_is_never_served(mock_store, mock_redis):
    """(c) speaker 'unknown' (or anything outside the allowlist) never serves."""
    clip = _clip(speaker="unknown")
    mock_store.search_hybrid.return_value = [clip]

    pipeline = FirstPersonPipeline(store=mock_store, redis_client=mock_redis, calibration_profile=VALID_PROFILE)
    res = pipeline.execute(query="What causes suffering?", query_dense_vector=[1.0, 0.0])

    assert res.status == "abstained"
    assert len(res.citations) == 0


def test_no_profile_is_weak_match(mock_store, mock_redis):
    """(d) no calibration profile -> weak_match with the 'Related' label, never success."""
    clip = _clip()
    mock_store.search_hybrid.return_value = [clip]

    pipeline = FirstPersonPipeline(store=mock_store, redis_client=mock_redis, calibration_profile=None)
    res = pipeline.execute(query="What causes suffering?", query_dense_vector=[1.0, 0.0])

    assert res.status == "weak_match"
    assert res.is_direct_answer is False
    assert "Related, not a direct answer" in res.answer_text


def test_valid_profile_confidence_above_threshold_is_success(mock_store, mock_redis):
    """(e) a valid profile with confidence >= threshold -> success."""
    clip = _clip(passage_dense=[1.0, 0.0])  # identical direction as query -> cosine 1.0
    mock_store.search_hybrid.return_value = [clip]

    pipeline = FirstPersonPipeline(
        store=mock_store, redis_client=mock_redis, calibration_profile=VALID_PROFILE
    )
    res = pipeline.execute(query="What causes suffering?", query_dense_vector=[1.0, 0.0])

    assert res.status == "success"
    assert res.is_direct_answer is True
    cit = res.citations[0]
    assert cit["confidence"] == pytest.approx(1.0)
    assert cit["teacher_id"] == "preethaji"
    assert cit["caption_status"] == "auto_transcript"
    assert cit["video_url"] == "https://www.youtube.com/watch?v=vid_abc"


def test_valid_profile_confidence_below_threshold_is_weak_match(mock_store, mock_redis):
    clip = _clip(passage_dense=[0.0, 1.0])  # orthogonal -> cosine 0.0
    mock_store.search_hybrid.return_value = [clip]

    pipeline = FirstPersonPipeline(
        store=mock_store, redis_client=mock_redis, calibration_profile=VALID_PROFILE
    )
    res = pipeline.execute(query="What causes suffering?", query_dense_vector=[1.0, 0.0])

    assert res.status == "weak_match"
    assert res.is_direct_answer is False


@pytest.mark.parametrize(
    "bad_override",
    [
        {"score_kind": "rrf_raw"},
        {"collection": "some_other_collection"},
        {"ucb_risk": 0.5, "target_risk": 0.01},
    ],
)
def test_invalid_profile_kinds_treated_as_none(tmp_path, bad_override):
    """(e) each invalid profile shape is treated as no profile at all."""
    import json

    profile = dict(VALID_PROFILE)
    profile.update(bad_override)
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(profile))

    loaded = load_calibration_profile(str(path), "first_person_v1")
    assert loaded is None


def test_missing_profile_path_is_none():
    assert load_calibration_profile("", "first_person_v1") is None
    assert load_calibration_profile("/nonexistent/path.json", "first_person_v1") is None


def test_honest_abstention_when_empty(mock_store, mock_redis):
    pipeline = FirstPersonPipeline(store=mock_store, redis_client=mock_redis)
    mock_store.search_hybrid.return_value = []

    res = pipeline.execute(
        query="Quantum chromodynamics equation",
        query_dense_vector=[0.1] * 1024,
    )

    assert res.status == "abstained"
    assert res.is_direct_answer is False
    assert len(res.citations) == 0
    assert "No verified first-person discourse found" in res.answer_text


def test_teacher_filter_passed_through_to_store(mock_store, mock_redis):
    """(h) teacher_id is forwarded to the store's search filter."""
    mock_store.search_hybrid.return_value = []
    pipeline = FirstPersonPipeline(store=mock_store, redis_client=mock_redis)

    pipeline.execute(
        query="What is grace?",
        query_dense_vector=[0.1] * 2,
        teacher_id="preethaji",
    )

    _, kwargs = mock_store.search_hybrid.call_args
    assert kwargs["teacher_id"] == "preethaji"


def test_prescreen_keyword_alone_is_not_a_crisis_redirect(mock_store, mock_redis):
    """Mirror DistressStage: only assess_distress() >= SEVERE pre-empts. The broad
    has_crisis_keywords pre-screen ("therapist", "anxiety") is not crisis-level on
    its own -- OR-ing it in redirected benign questions (live eval, 2026-09-25)."""
    from services.serene_mind_engine import DistressLevel, SereneMindEngine

    query = "Can you recommend a good therapist or psychiatrist for anxiety?"
    assert SereneMindEngine().assess_distress(query).level < DistressLevel.SEVERE
    mock_store.search_hybrid.return_value = []
    pipeline = FirstPersonPipeline(store=mock_store, redis_client=mock_redis)

    res = pipeline.execute(query=query, query_dense_vector=[0.1] * 1024)

    assert res.status != "crisis_redirect"
    mock_store.search_hybrid.assert_called_once()


def test_crisis_log_line_never_contains_the_raw_message(mock_store, mock_redis, caplog):
    """N4: no raw conversation text in logs for a crisis message."""
    pipeline = FirstPersonPipeline(store=mock_store, redis_client=mock_redis)
    msg = "I want to kill myself today"
    with caplog.at_level("DEBUG"):
        res = pipeline.execute(query=msg, query_dense_vector=[0.1] * 1024)
    assert res.status == "crisis_redirect"
    assert msg not in caplog.text


def _clip_with(text, video_id, vec):
    import hashlib as _h
    return {"verbatim_text": text, "transcript_hash": _h.sha256(text.encode()).hexdigest(),
            "speaker": "Sri Preethaji", "teacher_id": "preethaji", "video_id": video_id,
            "start_ms": 1000, "end_ms": 5000, "passage_dense": vec, "point_id": video_id}


def test_direct_answer_serves_only_clips_that_clear_the_threshold(mock_store, mock_redis):
    """Every served 'direct' clip must itself clear the calibrated threshold, not
    ride on the top clip's confidence."""
    profile = {"threshold": 0.9, "score_kind": "dense_cosine", "n": 400, "ucb_risk": 0.009,
               "target_risk": 0.01, "collection": "first_person_v1", "fitted_at": "t"}
    mock_store.collection = "first_person_v1"
    mock_store.search_hybrid.return_value = [
        _clip_with("Suffering is resistance.", "v1", [1.0, 0.0]),   # cosine 1.0 with the query
        _clip_with("Love is a state within.", "v2", [0.0, 1.0]),    # cosine 0.0
    ]
    pipeline = FirstPersonPipeline(store=mock_store, redis_client=mock_redis, calibration_profile=profile)
    res = pipeline.execute(query="what is suffering", query_dense_vector=[1.0, 0.0])
    assert res.status == "success"
    assert [c["video_id"] for c in res.citations] == ["v1"]


def test_profile_with_a_loose_self_declared_target_is_rejected(tmp_path):
    """A profile may not relax the product risk bound by declaring its own target."""
    import json as _j
    from services.first_person_pipeline import load_calibration_profile
    base = {"threshold": 0.5, "score_kind": "dense_cosine", "n": 400, "collection": "c", "fitted_at": "t"}
    loose = tmp_path / "loose.json"; loose.write_text(_j.dumps({**base, "ucb_risk": 0.4, "target_risk": 0.5}))
    bad_type = tmp_path / "bad.json"; bad_type.write_text(_j.dumps({**base, "ucb_risk": "0.001", "target_risk": 0.01}))
    assert load_calibration_profile(str(loose), "c") is None
    assert load_calibration_profile(str(bad_type), "c") is None


def test_pipeline_asks_for_spare_videos_so_a_quarantined_clip_is_backfilled(mock_store, mock_redis):
    mock_store.search_hybrid.return_value = []
    FirstPersonPipeline(store=mock_store, redis_client=mock_redis).execute(query="q", query_dense_vector=[0.1], max_clips=3)
    assert mock_store.search_hybrid.call_args.kwargs["dedup_limit"] > 3


def test_source_url_always_deep_links_to_the_clip_second(mock_store, mock_redis):
    """The index stores the plain video URL as source_url; the citation link must
    still jump to the clip's start second, or playback opens at 0:00."""
    clip = _clip_with("Suffering is resistance.", "vidT", [1.0, 0.0])
    clip.update(start_ms=94_500, source_url="https://www.youtube.com/watch?v=vidT")
    mock_store.search_hybrid.return_value = [clip]
    res = FirstPersonPipeline(store=mock_store, redis_client=mock_redis).execute(query="q", query_dense_vector=[1.0, 0.0])
    cit = res.citations[0]
    assert cit["source_url"] == "https://www.youtube.com/watch?v=vidT&t=94s"
    assert cit["video_url"] == "https://www.youtube.com/watch?v=vidT"
