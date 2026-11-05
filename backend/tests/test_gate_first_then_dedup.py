"""Regression tests for T4-01 / RET-01: Gate first, then dedup.

Ensures that:
1. FirstPersonStore.search_hybrid supports returning the raw candidate pool
   without per-video deduplication when deduplicate=False.
2. FirstPersonPipeline evaluates integrity, content and length quality gates
   on all retrieved candidates BEFORE deduplicating per video, so that if the
   top-ranked clip of a video fails a gate, a valid lower-ranked clip of the same
   video survives and is served instead of being lost to premature deduplication.
"""

import hashlib
from unittest.mock import MagicMock

from app.config import settings
from services.first_person_pipeline import FirstPersonPipeline
from services.first_person_store import FirstPersonStore


def _make_clip(
    text: str,
    vid: str,
    dense: list[float],
    *,
    start_ms: int = 1000,
    end_ms: int = 15000,
    speaker: str = "Sri Preethaji",
    teacher_id: str = "preethaji",
    domain_rights_status: str = "licensed",
    point_id: str = "p1",
) -> dict:
    t_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {
        "point_id": point_id,
        "clip_id": point_id,
        "video_id": vid,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "speaker": speaker,
        "teacher_id": teacher_id,
        "transcript_hash": t_hash,
        "span_text_sha256": t_hash,
        "verbatim_text": text,
        "passage_dense": dense,
        "source_url": f"https://www.youtube.com/watch?v={vid}",
        "caption_status": "auto_transcript",
        "is_verbatim": True,
        "first_person_eligible": True,
        "rights_cleared": True,
        "domain_rights_status": domain_rights_status,
        "score": 0.95 if dense == [1.0, 0.0] else 0.85,
    }


def _mock_point(pid: str, score: float, vid: str, verbatim_text: str, vector: dict):
    p = MagicMock()
    p.id = pid
    p.score = score
    t_hash = hashlib.sha256(verbatim_text.encode("utf-8")).hexdigest()
    p.payload = {
        "video_id": vid,
        "speaker": "Sri Preethaji",
        "teacher_id": "preethaji",
        "verbatim_text": verbatim_text,
        "transcript_hash": t_hash,
        "start_ms": 1000,
        "end_ms": 10000,
        "is_verbatim": True,
        "first_person_eligible": True,
        "rights_cleared": True,
        "domain_rights_status": "licensed",
        "source_url": f"https://www.youtube.com/watch?v={vid}",
    }
    p.vector = vector
    return p


def test_search_hybrid_supports_deduplicate_flag(monkeypatch):
    """search_hybrid(..., deduplicate=False) returns raw pool; deduplicate=True dedups."""
    monkeypatch.setattr(
        "services.first_person_store.source_is_authoritatively_licensed",
        lambda **kw: True,
    )
    monkeypatch.setattr("services.first_person_store.video_is_blocked", lambda vid: False)

    client = MagicMock()
    store = FirstPersonStore(collection="first_person_v1", client=client)

    p1 = _mock_point("p1", 0.95, "vidA", "Suffering is a choice.", {"passage_dense": [1.0, 0.0]})
    p2 = _mock_point("p2", 0.90, "vidA", "Joy is your nature.", {"passage_dense": [0.9, 0.1]})
    p3 = _mock_point("p3", 0.85, "vidB", "Meditation is silence.", {"passage_dense": [0.8, 0.2]})
    client.query_points.return_value = MagicMock(points=[p1, p2, p3])

    # deduplicate=False: returns all 3 points
    raw = store.search_hybrid(query_dense_vector=[1.0, 0.0], limit=10, deduplicate=False)
    assert len(raw) == 3
    assert [c["point_id"] for c in raw] == ["p1", "p2", "p3"]

    # deduplicate=True: dedups by video, returns 2 points (vidA and vidB)
    deduped = store.search_hybrid(query_dense_vector=[1.0, 0.0], limit=10, deduplicate=True)
    assert len(deduped) == 2
    assert [c["point_id"] for c in deduped] == ["p1", "p3"]


def test_pipeline_serves_valid_lower_span_when_top_span_fails_gate(monkeypatch):
    """RET-01: When top-ranked span of video A fails an integrity/quality gate,

    the surviving lower-ranked span of the same video reaches the relevance stage
    and is served instead of being discarded before gating.
    """
    monkeypatch.setattr(settings, "first_person_relevance_gate_enabled", False)
    monkeypatch.setattr(settings, "first_person_speculative_parallelism_enabled", False)
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", False)
    monkeypatch.setattr(
        "services.first_person_pipeline.source_is_authoritatively_licensed",
        lambda **kw: True,
    )
    monkeypatch.setattr("services.first_person_pipeline.video_is_blocked", lambda vid: False)
    monkeypatch.setattr(
        "services.first_person_pipeline.is_youtube_video_available", lambda vid: True
    )

    # Rank 1 clip for vidA has an outcome promise (fails H4 integrity gate)
    rank1_bad_text = (
        "I promise you a miracle and your problems will melt like ice in the heat of the sun."
    )
    rank1_clip = _make_clip(
        rank1_bad_text,
        "vidA",
        [1.0, 0.0],
        point_id="p1_bad",
    )

    # Rank 2 clip for vidA is completely valid and clean
    rank2_good_text = "When you are in a beautiful state, you connect with others from a place of love and wisdom."
    rank2_clip = _make_clip(
        rank2_good_text,
        "vidA",
        [0.9, 0.1],
        point_id="p2_good",
    )

    store = MagicMock()
    store.collection = "first_person_v1"
    # The store returns both candidate clips for vidA
    store.search_hybrid.return_value = [rank1_clip, rank2_clip]

    redis = MagicMock()
    redis.get.return_value = None

    pipeline = FirstPersonPipeline(
        store=store,
        redis_client=redis,
        calibration_profile=None,
        llm_service=None,
    )

    result = pipeline.execute(
        query="How do I connect with others in love?",
        query_dense_vector=[1.0, 0.0],
    )

    # The pipeline must NOT abstain. It must serve the valid second clip from vidA!
    assert result.status == "weak_match" or result.status == "success"
    assert len(result.citations) >= 1
    assert result.citations[0]["point_id"] == "p2_good"
    assert result.citations[0]["video_id"] == "vidA"


def test_pipeline_with_store_gates_before_dedup(monkeypatch):
    """End-to-end RET-01 check:

    Store returns multiple spans for vidA where rank 1 fails H4 gate.
    Pipeline retrieves with deduplicate=False, gates all spans, then dedups per video.
    Result: p2_good is served, rather than premature deduplication discarding p2_good
    and quarantining p1_bad to end in abstention.
    """
    monkeypatch.setattr(settings, "first_person_relevance_gate_enabled", False)
    monkeypatch.setattr(settings, "first_person_speculative_parallelism_enabled", False)
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", False)
    monkeypatch.setattr(
        "services.first_person_pipeline.source_is_authoritatively_licensed",
        lambda **kw: True,
    )
    monkeypatch.setattr("services.first_person_pipeline.video_is_blocked", lambda vid: False)
    monkeypatch.setattr(
        "services.first_person_pipeline.is_youtube_video_available", lambda vid: True
    )
    monkeypatch.setattr(
        "services.first_person_store.source_is_authoritatively_licensed",
        lambda **kw: True,
    )
    monkeypatch.setattr("services.first_person_store.video_is_blocked", lambda vid: False)

    rank1_bad_text = (
        "I promise you a miracle and your problems will melt like ice in the heat of the sun."
    )
    rank2_good_text = "When you are in a beautiful state, you connect with others from a place of love and wisdom."

    client = MagicMock()
    p1 = _mock_point("p1_bad", 0.95, "vidA", rank1_bad_text, {"passage_dense": [1.0, 0.0]})
    p2 = _mock_point("p2_good", 0.90, "vidA", rank2_good_text, {"passage_dense": [0.9, 0.1]})
    client.query_points.return_value = MagicMock(points=[p1, p2])

    store = FirstPersonStore(collection="first_person_v1", client=client)
    redis = MagicMock()
    redis.get.return_value = None

    pipeline = FirstPersonPipeline(
        store=store,
        redis_client=redis,
        calibration_profile=None,
        llm_service=None,
    )

    result = pipeline.execute(
        query="How do I connect with others in love?",
        query_dense_vector=[1.0, 0.0],
    )

    assert result.status in ("weak_match", "success")
    assert len(result.citations) >= 1
    assert result.citations[0]["point_id"] == "p2_good"
    assert result.citations[0]["video_id"] == "vidA"
