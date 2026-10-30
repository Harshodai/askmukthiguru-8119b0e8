"""v10 is the first-person context collection: naming and reachability guards."""

from app.config import settings
from scripts.ops.fp_v10_reachability import reachability


def test_context_collection_defaults_to_v10_without_enabling_anything():
    assert settings.model_fields["first_person_context_collection"].default == "first_person_v10"
    # naming the collection is not permission: the owner flags stay off by default
    assert settings.model_fields["first_person_context_harness_enabled"].default is False
    assert settings.model_fields["first_person_context_shadow_enabled"].default is False


def test_reachability_flags_a_video_with_no_rights_cleared_child():
    rows = [
        {"video_id": "a", "record_type": "retrieval_child", "rights_cleared": True},
        {"video_id": "b", "record_type": "retrieval_child", "rights_cleared": False},
        {"video_id": "c", "record_type": "parent_unit"},
        {
            "video_id": "a",
            "record_type": "retrieval_child",
            "rights_cleared": True,
            "speaker_verified": True,
        },
    ]
    rep = reachability(rows)
    assert rep["videos"] == 3 and rep["reachable_videos"] == 1
    assert rep["unreachable_videos"] == ["b", "c"]
    assert rep["speaker_verified_without_method"] == 1
