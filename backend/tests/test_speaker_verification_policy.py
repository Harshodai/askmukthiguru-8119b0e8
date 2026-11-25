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
