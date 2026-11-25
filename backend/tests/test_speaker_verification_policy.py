from __future__ import annotations

import pytest

from scripts.ops.windowed_ecapa_v1_scorer import (
    VERDICT_VERIFIED,
    is_verified_windowed_verdict,
)


@pytest.mark.parametrize("verdict", [VERDICT_VERIFIED, " VERIFIED "])
def test_only_exact_positive_window_verdict_is_verified(verdict: str) -> None:
    assert is_verified_windowed_verdict(verdict) is True


@pytest.mark.parametrize(
    "verdict",
    [
        "refused_host_window",
        "refused_below_cosine_floor",
        "refused_below_margin",
        "indeterminate_no_windows",
        "",
        None,
        True,
        0.99,
    ],
)
def test_failed_or_non_string_window_verdict_never_verifies(verdict: object) -> None:
    assert is_verified_windowed_verdict(verdict) is False



def test_pending_audio_patch_revokes_stale_positive_and_records_reason() -> None:
    from scripts.ops.windowed_ecapa_v1_scorer import pending_voice_check_patch

    patch = pending_voice_check_patch(
        cosine_floor=0.72,
        margin_threshold=0.10,
        reason="audio_file_missing",
    )

    assert patch["speaker_verified"] is False
    assert patch["speaker_verification_status"] == "pending_voice_check"
    assert patch["voice_window_check"] == "indeterminate"
    assert patch["voice_pending_reason"] == "audio_file_missing"
    assert patch["voice_score"] is None
    assert patch["voice_margin"] is None
    assert patch["voice_threshold_applied"] == {
        "cosine_floor": 0.72,
        "margin_threshold": 0.10,
    }
