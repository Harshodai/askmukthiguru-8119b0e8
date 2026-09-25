"""Target-selection logic for scripts/ops/label_summary_points.py (P0, 2026-09-25).

Pure function, fake payloads only — no live Qdrant needed. The invariant this
guards: video-less summary points get BOTH labels, other video-less points get
only `first_person_eligible=false`, and any point that already has a
`video_id` is left alone entirely (never eligible for this script's writes).
"""

from __future__ import annotations

from scripts.ops.label_summary_points import _diff_point, classify_point, has_video_id


def test_has_video_id_true_for_non_empty_string():
    assert has_video_id({"video_id": "abc123"}) is True


def test_has_video_id_false_for_none_missing_or_blank():
    assert has_video_id({"video_id": None}) is False
    assert has_video_id({}) is False
    assert has_video_id({"video_id": "  "}) is False


def test_video_less_summary_point_gets_both_labels():
    delta = classify_point({"content_type": "summary", "video_id": None})
    assert delta == {"first_person_eligible": False, "provenance_kind": "machine_summary"}


def test_video_less_non_summary_point_gets_only_eligibility_label():
    for content_type in ("book", "contextual", None):
        delta = classify_point({"content_type": content_type, "video_id": None})
        assert delta == {"first_person_eligible": False}


def test_point_with_video_id_is_untouched_even_if_summary():
    assert classify_point({"content_type": "summary", "video_id": "xyz"}) is None


def test_diff_point_changed_is_false_when_labels_already_set():
    payload = {"content_type": "summary", "video_id": None, "first_person_eligible": False, "provenance_kind": "machine_summary"}
    diff = _diff_point("p1", payload)
    assert diff["changed"] is False
    assert diff["is_summary_group"] is True


def test_diff_point_changed_is_true_when_labels_missing():
    diff = _diff_point("p2", {"content_type": "summary", "video_id": None})
    assert diff["changed"] is True


def test_diff_point_none_for_points_with_video_id():
    assert _diff_point("p3", {"content_type": "summary", "video_id": "abc"}) is None


def test_diff_point_never_touches_existing_keys_outside_delta():
    """The delta only ever carries the two new keys — set_payload merges, so
    content_type/text/etc. are never part of what this script writes."""
    diff = _diff_point("p4", {"content_type": "summary", "video_id": None, "text": "hello"})
    assert set(diff["delta"].keys()) <= {"first_person_eligible", "provenance_kind"}


if __name__ == "__main__":  # ponytail: runnable self-check without pytest
    test_has_video_id_true_for_non_empty_string()
    test_has_video_id_false_for_none_missing_or_blank()
    test_video_less_summary_point_gets_both_labels()
    test_video_less_non_summary_point_gets_only_eligibility_label()
    test_point_with_video_id_is_untouched_even_if_summary()
    test_diff_point_changed_is_false_when_labels_already_set()
    test_diff_point_changed_is_true_when_labels_missing()
    test_diff_point_none_for_points_with_video_id()
    test_diff_point_never_touches_existing_keys_outside_delta()
    print("test_label_summary_points self-check OK")
