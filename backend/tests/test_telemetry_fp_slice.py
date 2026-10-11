"""W5: FP liking-signal slice in _quality_snapshot.

Pure-function tests (no DB, no models): feedback rows carrying
metadata_json.surface == 'first_person' (as sent by TeacherWords ClipCard
qualityMetadata) must aggregate into fp_* keys alongside the globals.
"""

from app.telemetry_db import _quality_snapshot


def test_fp_slice_filters_surface_first_person():
    feedback_rows = [
        {
            "rating": 1,
            "metadata_json": {"surface": "first_person", "feedback_tags": ["Clear answer"]},
        },
        {"rating": -1, "metadata_json": {"surface": "first_person", "feedback_tags": []}},
        {"rating": 1, "metadata_json": {"surface": "chat", "feedback_tags": ["Clear answer"]}},
        {
            "rating": 1,
            "metadata_json": '{"surface": "first_person", "feedback_tags": ["Insightful"]}',
        },
        {"rating": 1, "metadata_json": None},
    ]
    snap = _quality_snapshot([], feedback_rows)
    assert snap["feedback_count"] == 5
    assert snap["fp_feedback_count"] == 3
    assert snap["fp_thumbs_up_rate"] == round(2 / 3, 4)
    assert snap["fp_tag_counts"] == {"Clear answer": 1, "Insightful": 1}
    # Globals still cover every row.
    assert snap["feedback_tag_counts"] == {"Clear answer": 2, "Insightful": 1}
    assert snap["thumbs_down_rate"] == 1 / 5


def test_fp_slice_empty_when_no_fp_rows():
    snap = _quality_snapshot([], [{"rating": 1, "metadata_json": {"surface": "chat"}}])
    assert snap["fp_feedback_count"] == 0
    assert snap["fp_thumbs_up_rate"] == 0.0
    assert snap["fp_tag_counts"] == {}


def test_fp_slice_empty_feedback():
    snap = _quality_snapshot([], [])
    assert snap["fp_feedback_count"] == 0
    assert snap["fp_thumbs_up_rate"] == 0.0
    assert snap["fp_tag_counts"] == {}


if __name__ == "__main__":
    test_fp_slice_filters_surface_first_person()
    test_fp_slice_empty_when_no_fp_rows()
    test_fp_slice_empty_feedback()
    print("telemetry fp slice OK")
