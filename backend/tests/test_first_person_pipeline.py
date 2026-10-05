"""
Unit tests for FirstPersonPipeline (Phase F).
"""

import hashlib
from unittest.mock import MagicMock

import pytest

from services.crisis_helplines import format_helplines_block
from services.first_person_pipeline import (
    FirstPersonPipeline,
    load_calibration_profile,
)

GOOD_TEXT = (
    "Suffering arises from resistance to what is. The moment you stop resisting, "
    "something shifts within you — not an escape, but a recognition of the truth."
)
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

    mock_redis.get.return_value = b'{"answer_text": "Cached teaching", "citations": [], "status": "weak_match", "is_direct_answer": false}'

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

    pipeline = FirstPersonPipeline(
        store=mock_store, redis_client=mock_redis, calibration_profile=VALID_PROFILE
    )
    res = pipeline.execute(query="What causes suffering?", query_dense_vector=[1.0, 0.0])

    assert res.status == "abstained"
    assert len(res.citations) == 0


def test_unknown_speaker_is_never_served(mock_store, mock_redis):
    """(c) speaker 'unknown' (or anything outside the allowlist) never serves."""
    clip = _clip(speaker="unknown")
    mock_store.search_hybrid.return_value = [clip]

    pipeline = FirstPersonPipeline(
        store=mock_store, redis_client=mock_redis, calibration_profile=VALID_PROFILE
    )
    res = pipeline.execute(query="What causes suffering?", query_dense_vector=[1.0, 0.0])

    assert res.status == "abstained"
    assert len(res.citations) == 0


def test_no_profile_is_weak_match(mock_store, mock_redis):
    """(d) no calibration profile -> weak_match with the 'Related' label, never success."""
    clip = _clip()
    mock_store.search_hybrid.return_value = [clip]

    pipeline = FirstPersonPipeline(
        store=mock_store, redis_client=mock_redis, calibration_profile=None
    )
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

    return {
        "verbatim_text": text,
        "transcript_hash": _h.sha256(text.encode()).hexdigest(),
        "speaker": "Sri Preethaji",
        "teacher_id": "preethaji",
        "video_id": video_id,
        "start_ms": 1000,
        "end_ms": 5000,
        "passage_dense": vec,
        "point_id": video_id,
    }


def test_direct_answer_serves_only_clips_that_clear_the_threshold(mock_store, mock_redis):
    """Every served 'direct' clip must itself clear the calibrated threshold, not
    ride on the top clip's confidence."""
    profile = {
        "threshold": 0.9,
        "score_kind": "dense_cosine",
        "n": 400,
        "ucb_risk": 0.009,
        "target_risk": 0.01,
        "collection": "first_person_v1",
        "fitted_at": "t",
    }
    mock_store.collection = "first_person_v1"
    mock_store.search_hybrid.return_value = [
        _clip_with("Suffering is resistance.", "v1", [1.0, 0.0]),  # cosine 1.0 with the query
        _clip_with("Love is a state within.", "v2", [0.0, 1.0]),  # cosine 0.0
    ]
    pipeline = FirstPersonPipeline(
        store=mock_store, redis_client=mock_redis, calibration_profile=profile
    )
    res = pipeline.execute(query="what is suffering", query_dense_vector=[1.0, 0.0])
    assert res.status == "success"
    assert [c["video_id"] for c in res.citations] == ["v1"]


def test_profile_with_a_loose_self_declared_target_is_rejected(tmp_path):
    """A profile may not relax the product risk bound by declaring its own target."""
    import json as _j

    from services.first_person_pipeline import load_calibration_profile

    base = {
        "threshold": 0.5,
        "score_kind": "dense_cosine",
        "n": 400,
        "collection": "c",
        "fitted_at": "t",
    }
    loose = tmp_path / "loose.json"
    loose.write_text(_j.dumps({**base, "ucb_risk": 0.4, "target_risk": 0.5}))
    bad_type = tmp_path / "bad.json"
    bad_type.write_text(_j.dumps({**base, "ucb_risk": "0.001", "target_risk": 0.01}))
    assert load_calibration_profile(str(loose), "c") is None
    assert load_calibration_profile(str(bad_type), "c") is None


def test_pipeline_asks_for_spare_videos_so_a_quarantined_clip_is_backfilled(mock_store, mock_redis):
    mock_store.search_hybrid.return_value = []
    FirstPersonPipeline(store=mock_store, redis_client=mock_redis).execute(
        query="q", query_dense_vector=[0.1], max_clips=3
    )
    assert mock_store.search_hybrid.call_args.kwargs["dedup_limit"] > 3


def test_malformed_cache_entry_missing_keys_is_treated_as_miss(mock_store, mock_redis):
    """A cache entry written by an older schema (or corrupted) must never raise
    KeyError -- it is treated as a miss and retrieval runs normally."""
    mock_redis.get.return_value = (
        b'{"answer_text": "x"}'  # missing citations/status/is_direct_answer
    )
    mock_store.search_hybrid.return_value = []

    pipeline = FirstPersonPipeline(store=mock_store, redis_client=mock_redis)
    res = pipeline.execute(query="What is suffering?", query_dense_vector=[0.1, 0.2])

    assert res.cached is False
    assert res.status == "abstained"
    mock_store.search_hybrid.assert_called_once()
    mock_redis.delete.assert_called_once()  # best-effort cleanup of the malformed key


def test_redis_get_raising_is_treated_as_miss(mock_store, mock_redis):
    """Redis unreachable on lookup must degrade to no-cache, never a raised
    exception (SPOF & Replication Policy: Redis Degradation invariant)."""
    mock_redis.get.side_effect = ConnectionError("redis down")
    mock_store.search_hybrid.return_value = []

    pipeline = FirstPersonPipeline(store=mock_store, redis_client=mock_redis)
    res = pipeline.execute(query="What is suffering?", query_dense_vector=[0.1, 0.2])

    assert res.status == "abstained"
    mock_store.search_hybrid.assert_called_once()


def test_successful_answer_populates_exact_cache(mock_store, mock_redis):
    """A confident answer is written to the exact cache with the documented TTL."""
    from services.first_person_pipeline import EXACT_CACHE_TTL

    clip = _clip(passage_dense=[1.0, 0.0])
    mock_store.search_hybrid.return_value = [clip]

    pipeline = FirstPersonPipeline(
        store=mock_store, redis_client=mock_redis, calibration_profile=VALID_PROFILE
    )
    pipeline.execute(query="What causes suffering?", query_dense_vector=[1.0, 0.0])

    mock_redis.set.assert_called_once()
    args, kwargs = mock_redis.set.call_args
    assert kwargs.get("ex") == EXACT_CACHE_TTL


def test_redis_set_raising_does_not_propagate(mock_store, mock_redis):
    """A write-side Redis failure must not fail the request that already has a
    verified answer to serve."""
    mock_redis.set.side_effect = ConnectionError("redis down")
    clip = _clip(passage_dense=[1.0, 0.0])
    mock_store.search_hybrid.return_value = [clip]

    pipeline = FirstPersonPipeline(
        store=mock_store, redis_client=mock_redis, calibration_profile=VALID_PROFILE
    )
    res = pipeline.execute(query="What causes suffering?", query_dense_vector=[1.0, 0.0])

    assert res.status == "success"


def test_source_url_always_deep_links_to_the_clip_second(mock_store, mock_redis):
    """The index stores the plain video URL as source_url; the citation link must
    still jump to the clip's start second, or playback opens at 0:00."""
    clip = _clip_with("Suffering is resistance.", "vidT", [1.0, 0.0])
    clip.update(start_ms=94_500, source_url="https://www.youtube.com/watch?v=vidT")
    mock_store.search_hybrid.return_value = [clip]
    res = FirstPersonPipeline(store=mock_store, redis_client=mock_redis).execute(
        query="q", query_dense_vector=[1.0, 0.0]
    )
    cit = res.citations[0]
    assert cit["source_url"] == "https://www.youtube.com/watch?v=vidT&t=94s"
    assert cit["video_url"] == "https://www.youtube.com/watch?v=vidT"


def _first_citation(mock_store, mock_redis, **clip_overrides):
    clip = _clip_with("Suffering is resistance.", "vidP", [1.0, 0.0])
    clip.update(clip_overrides)
    mock_store.search_hybrid.return_value = [clip]
    res = FirstPersonPipeline(store=mock_store, redis_client=mock_redis).execute(
        query="q", query_dense_vector=[1.0, 0.0]
    )
    return res.citations[0]


def test_playback_window_pads_by_spec_pad_not_seconds(mock_store, mock_redis):
    """Spec pad is 150-300 ms. A multi-second pre-roll would play the host's
    question or the other teacher before the quoted words."""
    from services.first_person_pipeline import CITATION_PLAYBACK_PAD_S

    assert 0.15 <= CITATION_PLAYBACK_PAD_S <= 0.30
    cit = _first_citation(mock_store, mock_redis, start_ms=94_500, end_ms=120_000)
    assert cit["playback_start_seconds"] == round(94.5 - CITATION_PLAYBACK_PAD_S, 2)
    assert cit["playback_end_seconds"] == round(120.0 + CITATION_PLAYBACK_PAD_S, 2)
    assert (
        cit["playback_url"]
        == f"https://www.youtube.com/watch?v=vidP&t={int(94.5 - CITATION_PLAYBACK_PAD_S)}s"
    )
    # Existing contract unchanged.
    assert cit["timestamp_seconds"] == 94
    assert cit["source_url"] == "https://www.youtube.com/watch?v=vidP&t=94s"


def test_playback_start_floors_at_zero(mock_store, mock_redis):
    cit = _first_citation(mock_store, mock_redis, start_ms=100, end_ms=9_000)
    assert cit["playback_start_seconds"] == 0.0
    assert cit["playback_url"].endswith("&t=0s")


def test_playback_end_never_passes_video_duration(mock_store, mock_redis):
    cit = _first_citation(
        mock_store, mock_redis, start_ms=50_000, end_ms=59_900, duration_ms=60_000
    )
    assert cit["playback_end_seconds"] == 60.0


def test_blocked_topic_gets_the_guardrail_redirect_not_a_teacher_clip(mock_store, mock_redis):
    """A teacher's clip served in reply to a political question reads as an
    endorsement. Same regex topic rail as chat (no LLM), before retrieval."""
    mock_store.search_hybrid.return_value = [_clip()]
    res = FirstPersonPipeline(store=mock_store, redis_client=mock_redis).execute(
        query="Which party should I vote for in the election?", query_dense_vector=[1.0, 0.0]
    )
    assert res.status == "abstained"
    assert res.citations == []
    assert res.answer_text
    mock_store.search_hybrid.assert_not_called()


def test_domestic_abuse_topic_gets_helplines_as_a_safety_redirect(mock_store, mock_redis):
    mock_store.search_hybrid.return_value = [_clip()]
    res = FirstPersonPipeline(store=mock_store, redis_client=mock_redis).execute(
        query="My husband hits me every night, what should I do?", query_dense_vector=[1.0, 0.0]
    )
    assert res.status == "crisis_redirect"
    assert res.citations == []
    mock_store.search_hybrid.assert_not_called()


def test_ordinary_doctrine_question_is_not_blocked(mock_store, mock_redis):
    mock_store.search_hybrid.return_value = [_clip()]
    res = FirstPersonPipeline(store=mock_store, redis_client=mock_redis).execute(
        query="What causes suffering?", query_dense_vector=[1.0, 0.0]
    )
    assert res.status in ("success", "weak_match")


def _cache_roundtrip(mock_store, mock_redis):
    """Serve once (fills the cache), then return the cached payload for a replay."""
    stored = {}
    mock_redis.set.side_effect = lambda key, value, ex=None: stored.__setitem__(key, value)
    mock_store.search_hybrid.return_value = [_clip(point_id="p-cached")]
    pipeline = FirstPersonPipeline(store=mock_store, redis_client=mock_redis)
    first = pipeline.execute(query="What causes suffering?", query_dense_vector=[1.0, 0.0])
    assert first.citations[0]["point_id"] == "p-cached"
    mock_redis.get.side_effect = lambda key: stored.get(key)
    mock_store.search_hybrid.reset_mock()
    return pipeline


def test_cache_hit_is_served_only_while_its_clips_are_still_servable(mock_store, mock_redis):
    pipeline = _cache_roundtrip(mock_store, mock_redis)
    mock_store.points_servable.return_value = True
    pipeline.execute(query="What causes suffering?", query_dense_vector=[1.0, 0.0])
    mock_store.points_servable.assert_called_once_with(["p-cached"])
    mock_store.search_hybrid.assert_not_called()  # served from cache


def test_cache_hit_for_a_removed_or_revoked_clip_is_a_miss(mock_store, mock_redis):
    """A clip deleted from the index or with rights revoked must stop serving now,
    not when the 24 h cache entry expires."""
    pipeline = _cache_roundtrip(mock_store, mock_redis)
    mock_store.points_servable.return_value = False
    mock_store.search_hybrid.return_value = []
    res = pipeline.execute(query="What causes suffering?", query_dense_vector=[1.0, 0.0])
    mock_store.search_hybrid.assert_called_once()  # fell through to a fresh search
    assert res.citations == []


# --- 2026-09-27: query translation + optional cross-encoder reorder -------------


def test_rerank_fn_reorders_verified_clips_but_confidence_stays_cosine(mock_store, mock_redis):
    mock_store.search_hybrid.return_value = [
        _clip_with("Suffering is resistance.", "v1", [1.0, 0.0]),
        _clip_with("Love is a state within.", "v2", [0.0, 1.0]),
    ]
    seen = {}

    def rerank(query, texts):
        seen["query"] = query
        return [0.1 if "Suffering" in t else 0.9 for t in texts]

    pipeline = FirstPersonPipeline(store=mock_store, redis_client=mock_redis, rerank_fn=rerank)
    res = pipeline.execute(
        query="प्रेम क्या है",
        query_dense_vector=[1.0, 0.0],
        retrieval_query="what is love",
        max_clips=1,
    )
    assert seen["query"] == "what is love"  # reranker scores the English question
    assert res.citations[0]["video_id"] == "v2"
    assert res.citations[0]["confidence"] == 0.0  # still dense cosine, not the rerank score


def test_rerank_failure_keeps_fusion_order(mock_store, mock_redis):
    mock_store.search_hybrid.return_value = [
        _clip_with("Suffering is resistance.", "v1", [1.0, 0.0]),
        _clip_with("Love is a state within.", "v2", [0.0, 1.0]),
    ]

    def broken(query, texts):
        raise RuntimeError("reranker down")

    pipeline = FirstPersonPipeline(store=mock_store, redis_client=mock_redis, rerank_fn=broken)
    res = pipeline.execute(query="what is suffering", query_dense_vector=[1.0, 0.0])
    assert res.status == "weak_match"
    assert res.citations[0]["video_id"] == "v1"


def test_crisis_in_translated_query_is_redirected(mock_store, mock_redis):
    """A phrasing the native-script patterns miss must still be caught via its English form."""
    pipeline = FirstPersonPipeline(store=mock_store, redis_client=mock_redis)
    res = pipeline.execute(
        query="zzq unrecognised phrasing",
        query_dense_vector=[0.1] * 4,
        retrieval_query="I want to kill myself",
    )
    assert res.status == "crisis_redirect"
    mock_store.search_hybrid.assert_not_called()


def test_topic_rail_sees_translated_query(mock_store, mock_redis):
    pipeline = FirstPersonPipeline(store=mock_store, redis_client=mock_redis)
    res = pipeline.execute(
        query="zzq unrecognised phrasing",
        query_dense_vector=[0.1] * 4,
        retrieval_query="I am suicidal",
    )
    assert res.status == "crisis_redirect"
    mock_store.search_hybrid.assert_not_called()


def test_cache_key_differs_when_reranking(mock_store, mock_redis):
    plain = FirstPersonPipeline(store=mock_store, redis_client=mock_redis)
    reranked = FirstPersonPipeline(
        store=mock_store, redis_client=mock_redis, rerank_fn=lambda q, t: [0.0] * len(t)
    )
    assert plain._get_exact_cache_key("what is love") != reranked._get_exact_cache_key(
        "what is love"
    )


def test_cache_key_differs_by_language(mock_store, mock_redis):
    """D2 audit fix: different languages produce isolated exact cache keys."""
    pipeline = FirstPersonPipeline(store=mock_store, redis_client=mock_redis)
    key_en = pipeline._get_exact_cache_key("what is love", language="en")
    key_hi = pipeline._get_exact_cache_key("what is love", language="hi")
    key_te = pipeline._get_exact_cache_key("what is love", language="te")

    assert key_en != key_hi
    assert key_hi != key_te
    assert ":en:" in key_en
    assert ":hi:" in key_hi
    assert ":te:" in key_te
    # Also verify _exact_cache_key alias works identically
    assert pipeline._exact_cache_key("what is love", language="hi") == key_hi


def test_exact_cache_isolates_by_language(mock_store, mock_redis):
    """D2 audit fix: a cached English response cannot be returned to a Hindi user."""
    pipeline = FirstPersonPipeline(store=mock_store, redis_client=mock_redis)
    storage: dict[str, bytes] = {}
    mock_redis.get.side_effect = lambda k: storage.get(k)
    mock_redis.set.side_effect = lambda k, v, **kw: storage.update(
        {k: v.encode("utf-8") if isinstance(v, str) else v}
    )

    # Populate cache for English query
    en_payload = {
        "answer_text": "Suffering is resistance to what is.",
        "citations": [],
        "status": "success",
        "is_direct_answer": True,
    }
    pipeline.set_exact_cache("what is suffering", en_payload, language="en")

    # Hindi lookup must be a cache miss
    hi_hit = pipeline.check_exact_cache("what is suffering", language="hi")
    assert hi_hit is None

    # English lookup must be a cache hit
    en_hit = pipeline.check_exact_cache("what is suffering", language="en")
    assert en_hit is not None
    assert en_hit["answer_text"] == "Suffering is resistance to what is."


def test_execute_populates_language_sensitive_cache(mock_store, mock_redis):
    """D2 audit fix: pipeline.execute with language writes to a language-scoped key."""
    clip = _clip(passage_dense=[1.0, 0.0])
    mock_store.search_hybrid.return_value = [clip]

    pipeline = FirstPersonPipeline(
        store=mock_store, redis_client=mock_redis, calibration_profile=VALID_PROFILE
    )
    pipeline.execute(query="What causes suffering?", query_dense_vector=[1.0, 0.0], language="hi")

    mock_redis.set.assert_called_once()
    key, val = mock_redis.set.call_args[0]
    assert ":hi:" in key


def test_no_rerank_fn_by_default(mock_store, mock_redis):
    assert FirstPersonPipeline(store=mock_store, redis_client=mock_redis)._rerank_fn is None


# --- 2026-09-28: Invariant 10: Sentence Boundary & Conjunction Integrity -------


@pytest.mark.parametrize(
    "trailing_conjunction",
    ["or", "and", "so", "but", "because", "or.", "and,", "so!", "but..."],
)
def test_integrity_gate_rejects_trailing_coordinating_conjunction(trailing_conjunction):
    """L-SENTENCE-SPLIT-CONJUNCTION-1: Clips ending on dangling conjunctions must never be served."""
    from services.first_person_pipeline import _passes_integrity_gate

    text = f"We suffer from stress and anxiety and fear {trailing_conjunction}"
    clip = {
        "verbatim_text": text,
        "transcript_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "speaker": "Sri Krishnaji",
    }
    assert _passes_integrity_gate(clip) is False


def test_integrity_gate_accepts_clean_sentence():
    from services.first_person_pipeline import _passes_integrity_gate

    text = "We suffer from stress and anxiety and fear."
    clip = {
        "verbatim_text": text,
        "transcript_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "speaker": "Sri Krishnaji",
    }
    assert _passes_integrity_gate(clip) is True


def test_pipeline_skips_clips_with_trailing_conjunctions(mock_store, mock_redis):
    bad_text = "We suffer from fear or"
    bad_clip = _clip_with(bad_text, "v_bad", [1.0, 0.0])
    good_text = "Suffering is not a fact."
    good_clip = _clip_with(good_text, "v_good", [0.9, 0.1])

    mock_store.search_hybrid.return_value = [bad_clip, good_clip]
    pipeline = FirstPersonPipeline(store=mock_store, redis_client=mock_redis)
    res = pipeline.execute(query="what is suffering", query_dense_vector=[1.0, 0.0])

    assert len(res.citations) == 1
    assert res.citations[0]["video_id"] == "v_good"
    assert res.citations[0]["verbatim_text"] == good_text


# --- 2026-09-28: B4 serve-time boundary guard (flag, default off) -----------------


def test_boundary_guard_off_by_default_serves_unterminated_clip(mock_store, mock_redis):
    mock_store.search_hybrid.return_value = [
        _clip_with("you move from suffering to calm", "v1", [1.0, 0.0])
    ]
    res = FirstPersonPipeline(store=mock_store, redis_client=mock_redis).execute(
        query="what is suffering", query_dense_vector=[1.0, 0.0]
    )
    assert res.status == "weak_match"


def test_boundary_guard_on_quarantines_unterminated_clip(mock_store, mock_redis, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "first_person_boundary_guard_enabled", True)
    mock_store.search_hybrid.return_value = [
        _clip_with("you move from suffering to calm", "v1", [1.0, 0.0]),
        _clip_with("Suffering is resistance to what is.", "v2", [1.0, 0.0]),
    ]
    res = FirstPersonPipeline(store=mock_store, redis_client=mock_redis).execute(
        query="what is suffering", query_dense_vector=[1.0, 0.0]
    )
    assert [c["video_id"] for c in res.citations] == ["v2"]


# ── Content Quality Gate ──────────────────────────────────────────────────────

from services.first_person_pipeline import _passes_content_quality_gate  # noqa: E402


def _cq_clip(text: str) -> dict:
    """Minimal clip dict for content quality gate tests."""
    return {"verbatim_text": text, "point_id": "test_pt", "video_id": "test_vid"}


class TestContentQualityGate:
    """_passes_content_quality_gate rejects thin, instructional, and acknowledgment clips."""

    def test_rich_teaching_passes(self):
        text = (
            "Suffering arises when we resist what is. The moment you stop resisting, "
            "something shifts within you — not an escape, but a recognition. "
            "That recognition is the beginning of freedom."
        )
        assert _passes_content_quality_gate(_cq_clip(text), gate_enabled=True) is True

    def test_too_few_words_rejected(self):
        # 10 words — below MIN_TEACHING_WORDS=15
        text = "I am sure you too have tried to pierce through."
        assert len(text.split()) == 10
        assert _passes_content_quality_gate(_cq_clip(text), gate_enabled=True) is False

    def test_close_eyes_instruction_rejected(self):
        text = (
            "Please close your eyes. I still see a few sneaking a peek. "
            "Now let us breathe deeply and enter the space of stillness."
        )
        assert _passes_content_quality_gate(_cq_clip(text), gate_enabled=True) is False

    def test_let_us_begin_rejected(self):
        text = (
            "Let us begin this meditation by sitting upright and placing your hands on your knees. "
            "Feel the ground beneath you and allow your breathing to slow down naturally."
        )
        assert _passes_content_quality_gate(_cq_clip(text), gate_enabled=True) is False

    def test_discourse_acknowledgment_opener_rejected(self):
        text = (
            "Yes, as you mentioned, Sri Krishnaji shares with the world about the two states "
            "and that you either live in a state of suffering or a state of no suffering."
        )
        assert _passes_content_quality_gate(_cq_clip(text), gate_enabled=True) is False

    def test_acknowledgment_variant_rejected(self):
        text = (
            "Yes as you mentioned the beautiful state is not an emotional high "
            "but a place of deep inner stillness from which all action flows."
        )
        assert _passes_content_quality_gate(_cq_clip(text), gate_enabled=True) is False

    def test_genuine_long_teaching_with_eyes_mention_passes(self):
        # Contains "eyes" but not the exact instruction pattern
        text = (
            "When you look at life through the eyes of suffering, every small obstacle "
            "becomes a wall. But when you look through the eyes of love, every wall "
            "becomes a door. That shift is not in the world — it is in you. "
            "That is the beautiful state Sri Krishnaji speaks of."
        )
        assert _passes_content_quality_gate(_cq_clip(text), gate_enabled=True) is True

    def test_boundary_at_minimum_words(self):
        # Exactly 25 words should pass (min 25 words)
        words = ["word"] * 25
        text = " ".join(words) + "."
        assert _passes_content_quality_gate(_cq_clip(text), gate_enabled=True) is True

    def test_below_minimum_words_fails(self):
        # 24 words — below MIN_TEACHING_WORDS=25
        words = ["word"] * 24
        text = " ".join(words) + "."
        assert _passes_content_quality_gate(_cq_clip(text), gate_enabled=True) is False

    def test_parable_character_narrative_fails(self):
        # Pure parable narrative without core wisdom keywords should fail
        text = (
            "Yasme volunteers to help her. He carries her across the river and drops her on the other side "
            "while the other monk watched in total silence and wondered why he broke the sacred vow."
        )
        assert _passes_content_quality_gate(_cq_clip(text), gate_enabled=True) is False

    def test_parable_character_with_core_wisdom_passes(self):
        # Parable reference containing core wisdom definitions must pass
        text = (
            "Yasme carries her, but a beautiful state is a state where you are being present. "
            "A state in which there is no inner conflict and you are feeling connected to life."
        )
        assert _passes_content_quality_gate(_cq_clip(text), gate_enabled=True) is True

    def test_rhetorical_opener_fails(self):
        text = (
            "I am sure you too have tried to pierce through this mystery to make greater sense of life "
            "and discover what lies behind the curtains of everyday reality and suffering."
        )
        assert _passes_content_quality_gate(_cq_clip(text), gate_enabled=True) is False


def test_teacher_diversity_preserves_top_rank():
    """When teacher diversity balancing runs, the #1 top-ranked match is never demoted,
    and an other-teacher clip only displaces a same-teacher clip within cosine gap δ."""
    import hashlib

    from services.first_person_pipeline import FirstPersonPipeline

    def _make_clip(pid, spk, tid, text, vec):
        return {
            "point_id": pid,
            "video_id": f"vid_{pid}",
            "speaker": spk,
            "teacher_id": tid,
            "verbatim_text": text,
            "transcript_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "start_ms": 10000,
            "end_ms": 30000,
            "passage_dense": vec,
            "provenance_kind": "speech_turn_clip",
        }

    # Top match is Sri Preethaji with high similarity (vec = [1.0, 0.0])
    # Next match is Sri Preethaji (vec = [0.9, 0.1])
    # Third match is Sri Krishnaji (vec = [0.7, 0.3])
    q_vec = [1.0, 0.0]
    c1 = _make_clip(
        "p1",
        "Sri Preethaji",
        "preethaji",
        "A beautiful state is a state where you are being present with no inner conflict and full connection.",
        [1.0, 0.0],
    )
    c2 = _make_clip(
        "p2",
        "Sri Preethaji",
        "preethaji",
        "Suffering is an obsessive self-preoccupation that disconnects you completely from life and love.",
        [0.9, 0.1],
    )
    c3 = _make_clip(
        "k1",
        "Sri Krishnaji",
        "krishnaji",
        "When you connect with another person from deep presence, that connection is true sacred love.",
        [0.7, 0.3],
    )

    from unittest.mock import MagicMock

    mock_store = MagicMock()
    mock_store.search_hybrid.return_value = [c1, c2, c3]
    mock_redis = MagicMock()
    mock_redis.get.return_value = None

    profile = {
        "threshold": 0.5,
        "score_kind": "dense_cosine",
        "n": 10,
        "ucb_risk": 0.01,
        "target_risk": 0.01,
        "collection": "test_col",
        "fitted_at": "2026-09-29",
    }

    pipeline = FirstPersonPipeline(
        store=mock_store, redis_client=mock_redis, calibration_profile=profile
    )
    res = pipeline.execute(
        query="What is the beautiful state?",
        query_dense_vector=q_vec,
        teacher_id="both",
        max_clips=3,
    )

    assert res.status == "success"
    assert len(res.citations) == 3
    # Invariant: Preethaji's top-scoring match MUST remain in slot 0!
    assert res.citations[0]["point_id"] == "p1"
    assert res.citations[0]["speaker"] == "Sri Preethaji"
    # Rewritten 2026-09-29 (see trace_1A.md): this test previously encoded the Step 4c
    # defect — it asserted k1 (cos 0.919) forced into slot 1 over p2 (cos 0.994), a
    # gap of 0.075 > δ=0.05. Under the calibrated parity gate the same-teacher clip
    # holds slot 1; the Krishnaji clip still reaches slot 2, so teacher diversity is
    # preserved and nothing is dropped.
    assert res.citations[1]["point_id"] == "p2"
    assert res.citations[1]["speaker"] == "Sri Preethaji"
    assert res.citations[2]["point_id"] == "k1"
    assert res.citations[2]["speaker"] == "Sri Krishnaji"


def _fp_clip(text, video_id, cos, speaker="Sri Preethaji", teacher_id="preethaji"):
    """Clip at exact cosine `cos` vs the q=[1.0, 0.0] test query (2-D unit vector)."""
    clip = _clip_with(text, video_id, [cos, (1.0 - cos * cos) ** 0.5])
    clip.update({"speaker": speaker, "teacher_id": teacher_id})
    return clip


def test_other_teacher_clip_below_threshold_is_never_promoted(mock_store, mock_redis):
    """Step 4c parity gate, threshold leg: an other-teacher clip under the fitted
    profile threshold never takes a slot from a same-teacher clip — even when the
    cosine gap sits inside δ (0.51 - 0.47 = 0.04 <= 0.05)."""
    top = _fp_clip(
        "A beautiful state is a state where you are being present with no inner conflict.",
        "p_top",
        0.99,
    )
    same = _fp_clip(
        "Suffering is obsessive self-preoccupation that disconnects you from life and love.",
        "p_same",
        0.51,
    )
    other = _fp_clip(
        "When you connect with another person from deep presence, love becomes sacred.",
        "k_low",
        0.47,
        "Sri Krishnaji",
        "krishnaji",
    )
    mock_store.search_hybrid.return_value = [top, same, other]

    pipeline = FirstPersonPipeline(
        store=mock_store, redis_client=mock_redis, calibration_profile=VALID_PROFILE
    )
    res = pipeline.execute(
        query="What is the beautiful state?",
        query_dense_vector=[1.0, 0.0],
        teacher_id="both",
        max_clips=2,
    )

    assert res.status == "success"
    # max_clips=2 makes the promotion observable: had the below-threshold clip been
    # promoted into slot 1 it would then be dropped by the per-clip threshold filter,
    # leaving ONE citation. The refused promotion serves top + same-teacher → two.
    assert [c["point_id"] for c in res.citations] == ["p_top", "p_same"]
    # invariant (e): slot 0 untouched
    assert res.citations[0]["point_id"] == "p_top"


def test_america_un_clip_does_not_displace_higher_cosine_peace_clip(mock_store, mock_redis):
    """trace_1A regression (2026-09-29): for "how do I find inner peace?" the America/UN
    clip (-pBQ6Sy444o, cos 0.5791) displaced the same-teacher peace clip (0Fa4Wyv0GOk,
    cos 0.6837) — gap 0.1046 > δ=0.05. The same-teacher clip must hold slot 1."""
    profile = {**VALID_PROFILE, "threshold": 0.45}  # fitted production value (trace_1A.md)
    top = _fp_clip(
        "Peace begins when you stop fighting the moment and meet it with awareness.",
        "UlOt31lBhLY",
        0.6475,
        "Sri Krishnaji",
        "krishnaji",
    )
    peace = _fp_clip(
        "Inner peace is the natural state when the mind stops chasing and simply rests.",
        "0Fa4Wyv0GOk",
        0.6837,
        "Sri Krishnaji",
        "krishnaji",
    )
    america = _fp_clip(
        "Whether the world is at war or at play, come back to this moment and breathe.",
        "-pBQ6Sy444o",
        0.5791,
    )
    mock_store.search_hybrid.return_value = [top, peace, america]

    pipeline = FirstPersonPipeline(
        store=mock_store, redis_client=mock_redis, calibration_profile=profile
    )
    res = pipeline.execute(
        query="How do I find inner peace?",
        query_dense_vector=[1.0, 0.0],
        teacher_id="both",
        max_clips=3,
    )

    assert res.status == "success"
    assert [c["point_id"] for c in res.citations] == ["UlOt31lBhLY", "0Fa4Wyv0GOk", "-pBQ6Sy444o"]
    # invariant (e): slot 0 untouched
    assert res.citations[0]["point_id"] == "UlOt31lBhLY"
    # the served peace clip really is the higher-cosine one (0.6837 > 0.5791)
    assert res.citations[1]["confidence"] == pytest.approx(0.6837, abs=1e-6)
    assert res.citations[2]["confidence"] == pytest.approx(0.5791, abs=1e-6)


def test_other_teacher_clip_within_gap_is_promoted_for_diversity(mock_store, mock_redis):
    """Diversity preserved: an other-teacher clip that clears the profile threshold
    AND stays within δ (0.90 - 0.88 = 0.02 <= 0.05) still gets promoted to slot 1."""
    top = _fp_clip(
        "A beautiful state is presence without conflict, open and connected to life.", "p1", 0.99
    )
    same = _fp_clip(
        "Suffering is self-preoccupation that pulls you out of connection with life.", "p2", 0.90
    )
    other = _fp_clip(
        "From deep presence, another person becomes a doorway into sacred love.",
        "k1",
        0.88,
        "Sri Krishnaji",
        "krishnaji",
    )
    mock_store.search_hybrid.return_value = [top, same, other]

    pipeline = FirstPersonPipeline(
        store=mock_store, redis_client=mock_redis, calibration_profile=VALID_PROFILE
    )
    res = pipeline.execute(
        query="What is the beautiful state?",
        query_dense_vector=[1.0, 0.0],
        teacher_id="both",
        max_clips=3,
    )

    assert res.status == "success"
    assert [c["point_id"] for c in res.citations] == ["p1", "k1", "p2"]
    assert res.citations[1]["teacher_id"] == "krishnaji"
    # invariant (e): slot 0 untouched
    assert res.citations[0]["point_id"] == "p1"


def test_no_calibration_profile_never_promotes_other_teacher_clip(
    mock_store, mock_redis, monkeypatch
):
    """(d) No fitted profile → no quality parity → Step 4c never even evaluates a
    cross-teacher promotion (zero candidate/displaced cosine calls), and serving
    collapses to weak_match with only the slot-0 top clip."""
    import services.first_person_pipeline as fpp

    top = _fp_clip(
        "A beautiful state is presence without conflict, open and connected to life.", "p1", 0.99
    )
    same = _fp_clip(
        "Suffering is self-preoccupation that pulls you out of connection with life.", "p2", 0.88
    )
    # gap to same-teacher clip is 0.01, well inside δ — a gap-only bug would promote it
    other = _fp_clip(
        "From deep presence, another person becomes a doorway into sacred love.",
        "k1",
        0.87,
        "Sri Krishnaji",
        "krishnaji",
    )
    mock_store.search_hybrid.return_value = [top, same, other]

    cos_calls: list[int] = []
    _orig_cos = fpp._cosine_similarity

    def _spy(a, b):
        cos_calls.append(1)
        return _orig_cos(a, b)

    monkeypatch.setattr(fpp, "_cosine_similarity", _spy)

    pipeline = FirstPersonPipeline(
        store=mock_store, redis_client=mock_redis, calibration_profile=None
    )
    res = pipeline.execute(
        query="What is the beautiful state?",
        query_dense_vector=[1.0, 0.0],
        teacher_id="both",
        max_clips=3,
    )

    assert res.status == "weak_match"
    assert not res.is_direct_answer
    # Step 6 scores all 3 verified clips; the 4c promotion gate (candidate + displaced)
    # would add 2 more. With profile=None the gate must never run.
    assert len(cos_calls) == 3
    # invariant (e): only the slot-0 top clip is served, never displaced
    assert [c["point_id"] for c in res.citations] == ["p1"]


def test_pipeline_returns_audio_playback_clip_and_detected_concepts(mock_store, mock_redis):
    """Pipeline correctly constructs audio_playback_clip, detected_concepts, and inquiry."""
    clip = _clip(
        video_id="vid_hero",
        passage_dense=[1.0, 0.0],
        start_ms=60000,
        end_ms=90000,
        speaker="Sri Preethaji",
    )
    mock_store.search_hybrid.return_value = [clip]

    pipeline = FirstPersonPipeline(
        store=mock_store, redis_client=mock_redis, calibration_profile=VALID_PROFILE
    )
    res = pipeline.execute(query="What is the beautiful state?", query_dense_vector=[1.0, 0.0])

    assert res.status == "success"
    assert res.audio_playback_clip is not None
    assert res.audio_playback_clip["video_id"] == "vid_hero"
    assert res.audio_playback_clip["start_sec"] == 60.0
    assert res.audio_playback_clip["end_sec"] == 90
    assert "Beautiful State" in res.detected_concepts
    assert res.atma_vichara_inquiry is not None

    d = res.to_dict()
    assert "audio_playback_clip" in d
    assert "detected_concepts" in d
    assert "atma_vichara_inquiry" in d
    assert "practice_recommendation" in d


def test_pipeline_cache_hit_preserves_new_fields(mock_store, mock_redis):
    """Cache hit unpacks audio_playback_clip, detected_concepts, atma_vichara_inquiry, and practice_recommendation."""
    pipeline = FirstPersonPipeline(store=mock_store, redis_client=mock_redis)

    cached_json = (
        b'{"answer_text": "Cached teaching", "citations": [], "status": "success", '
        b'"is_direct_answer": true, "audio_playback_clip": {"video_id": "vid_cached", "start_sec": 10}, '
        b'"detected_concepts": ["Suffering"], "atma_vichara_inquiry": "*Who is observing?*", '
        b'"practice_recommendation": {"title": "Breath Practice"}}'
    )
    mock_redis.get.return_value = cached_json

    res = pipeline.execute(
        query="What is suffering?",
        query_dense_vector=[0.1] * 1024,
    )

    assert res.cached is True
    assert res.audio_playback_clip == {"video_id": "vid_cached", "start_sec": 10}
    assert res.detected_concepts == ["Suffering"]
    assert res.atma_vichara_inquiry == "*Who is observing?*"
    assert res.practice_recommendation == {"title": "Breath Practice"}
