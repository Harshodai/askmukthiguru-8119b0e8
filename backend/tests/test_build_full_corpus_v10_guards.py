"""Guards on ``scripts.ops.build_full_corpus_v10`` (2026-10-25 data audit D3/D9).

The builder imports the acoustic stack (soundfile, torch, speechbrain). Where those
are not installed (CI) the module cannot be imported, so these tests skip there and
run on the Mac, where the builder is actually used.
"""

from __future__ import annotations

import pytest

pytest.importorskip("soundfile")
pytest.importorskip("torch")

from scripts.ops import build_full_corpus_v10 as builder  # noqa: E402


def test_label_derived_centroids_are_refused_by_default(tmp_path):
    with pytest.raises(RuntimeError, match="circular"):
        builder.compute_centroids(tmp_path / "points.json", tmp_path)


def test_label_derived_centroids_need_the_explicit_flag(tmp_path):
    # With the flag the old behaviour (and its missing-file error) is reachable.
    with pytest.raises(RuntimeError, match="Missing"):
        builder.compute_centroids(tmp_path / "points.json", tmp_path, allow_label_derived=True)


def test_blocking_release_grade_codes_exclude_the_duration_band():
    assert "speaker_verified_without_method" in builder.RELEASE_GRADE_BLOCKING
    assert "boundary_status_verified_with_defects" in builder.RELEASE_GRADE_BLOCKING
    assert not any(code.startswith("duration") for code in builder.RELEASE_GRADE_BLOCKING)
