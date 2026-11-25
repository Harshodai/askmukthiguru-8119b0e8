"""Component 4 (SOTA plan): cross-video MMR diversity for first-person candidate pools.

Pure unit tests — no Qdrant, no LLM, no settings. The contract under test:

* every candidate survives exactly once (diversity reorders, it never drops);
* one video cannot exceed ``max_per_video`` in the head;
* deferred candidates keep their original relative order in the tail;
* a bad input degrades to the input order instead of raising.
"""

from __future__ import annotations

from types import SimpleNamespace

from services.cross_video_diversity import (
    apply_cross_video_diversity,
    jaccard_similarity,
)

VID_A = "aaaaaaaaaaa"
VID_B = "bbbbbbbbbbb"
VID_C = "ccccccccccc"


def _candidate(video_id: str, score: float, text: str) -> dict:
    return {"video_id": video_id, "score": score, "text": text}


def test_single_candidate_is_passthrough():
    pool = [_candidate(VID_A, 0.9, "one teaching")]
    ordered, deferred = apply_cross_video_diversity(pool)
    assert ordered == pool
    assert deferred == 0


def test_per_video_cap_promotes_second_video():
    pool = [
        _candidate(VID_A, 0.95, "the mind is a warring state"),
        _candidate(VID_A, 0.94, "the mind is a warring state today"),
        _candidate(VID_A, 0.93, "the mind is a warring state now"),
        _candidate(VID_B, 0.60, "observe the breath gently"),
    ]
    ordered, deferred = apply_cross_video_diversity(pool, max_per_video=2)

    assert len(ordered) == len(pool), "diversity must never lose a candidate"
    assert {id(c) for c in ordered} == {id(c) for c in pool}
    head_videos = [c["video_id"] for c in ordered[:3]]
    assert head_videos.count(VID_A) == 2
    assert VID_B in head_videos
    assert ordered[0] is pool[0], "best relevance stays first"
    assert deferred == 1
    assert ordered[-1] is pool[2], "deferred candidate keeps its tail slot"


def test_mmr_prefers_a_new_video_over_a_redundant_sibling():
    """With lambda 0.7 the second video's 0.70 beats a near-duplicate 0.89 sibling."""
    pool = [
        _candidate(VID_A, 0.90, "the mind is a warring state and it suffers"),
        _candidate(VID_A, 0.89, "the mind is a warring state and it suffers"),
        _candidate(VID_B, 0.70, "observe the breath gently without forcing"),
    ]
    ordered, _ = apply_cross_video_diversity(pool, max_per_video=2, mmr_lambda=0.7)
    assert ordered[1]["video_id"] == VID_B, ordered


def test_relevance_only_lambda_keeps_score_order_within_cap():
    pool = [
        _candidate(VID_A, 0.90, "alpha"),
        _candidate(VID_B, 0.80, "beta"),
        _candidate(VID_C, 0.70, "gamma"),
    ]
    ordered, deferred = apply_cross_video_diversity(pool, max_per_video=2, mmr_lambda=1.0)
    assert [c["score"] for c in ordered] == [0.90, 0.80, 0.70]
    assert deferred == 0


def test_attribute_access_matches_dict_access():
    records = [
        SimpleNamespace(video_id=VID_A, score=0.9, text="alpha teaching"),
        SimpleNamespace(video_id=VID_A, score=0.8, text="alpha teaching again"),
        SimpleNamespace(video_id=VID_B, score=0.5, text="beta teaching"),
    ]
    ordered, _ = apply_cross_video_diversity(records, max_per_video=1)
    assert isinstance(ordered[0], SimpleNamespace)
    assert ordered[0].video_id == VID_A
    assert ordered[1].video_id == VID_B
    assert len(ordered) == 3


def test_bad_scores_do_not_raise():
    pool = [
        {"video_id": VID_A, "score": "not-a-number", "text": "a"},
        {"video_id": VID_A, "score": None, "text": "b"},
        {"video_id": VID_B, "score": float("nan"), "text": "c"},
    ]
    ordered, deferred = apply_cross_video_diversity(pool, max_per_video=1)
    assert len(ordered) == 3
    assert deferred >= 0


def test_jaccard_similarity_bounds():
    assert jaccard_similarity("", "anything") == 0.0
    assert jaccard_similarity("the same words here", "the same words here") == 1.0
    assert 0.0 < jaccard_similarity("love and fear", "love and anger") < 1.0


def test_mmr_does_not_demote_topical_teaching_over_small_domain_overlap():
    """Modest topic overlap (~0.14 Jaccard) must not let an off-topic low-score clip win."""
    pool = [
        _candidate(VID_A, 0.74, "anger aggression state hurting people words actions"),
        _candidate(VID_B, 0.71, "anger stressful state beautiful state workplace decision"),
        _candidate(VID_C, 0.68, "flowers silent moon ocean breeze mountains"),
    ]
    ordered, _ = apply_cross_video_diversity(pool, max_per_video=2, mmr_lambda=0.7)
    assert ordered[1]["video_id"] == VID_B, ordered
