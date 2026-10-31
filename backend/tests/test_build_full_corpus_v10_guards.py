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


def test_only_videos_restricts_additions_before_the_limit_and_never_widens():
    """--only-videos narrows the already-missing candidates; it cannot add a video
    that is already indexed (the run stays purely additive)."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "scripts/ops/build_full_corpus_v10.py").read_text()
    assert '"--only-videos"' in src
    filt = src.index("p.stem in only")
    limit = src.index("if args.limit > 0:")
    built_from = src.index(
        "missing_candidates = [\n        p for p in all_transcripts if p.stem not in existing_videos"
    )
    # the filter works on the list that already excludes indexed videos
    assert built_from < filt < limit


def test_words_from_timed_file_requires_a_time_on_every_word(tmp_path):
    """--text-from-words never synthesises timings: a word without start/end -> None."""
    import json

    good = [{"w": "Hello", "start": 0.0, "end": 0.4}, {"w": "world.", "start": 0.5, "end": 1.0}]
    (tmp_path / "vidA.json").write_text(json.dumps(good))
    words, times, sha = builder.words_from_timed_file("vidA", [tmp_path])
    assert words == ["Hello", "world."] and times == [(0.0, 0.4), (0.5, 1.0)] and len(sha) == 64

    (tmp_path / "vidB.json").write_text(json.dumps([{"w": "no", "start": 0.0}]))
    assert builder.words_from_timed_file("vidB", [tmp_path]) is None
    assert builder.words_from_timed_file("missing", [tmp_path]) is None


def test_zero_duration_spans_are_quarantined_not_crashed_on():
    from collections import Counter

    q: Counter[str] = Counter()
    specs = [
        {"start_ms": 191160, "end_ms": 191160, "text": "a"},
        {"start_ms": 1000, "end_ms": 2000, "text": "b"},
    ]
    kept = builder.drop_zero_duration_specs(specs, q)
    assert [s["text"] for s in kept] == ["b"]
    assert q["zero_duration_span"] == 1


def test_asr_provenance_reads_the_archived_run_and_never_guesses(tmp_path):
    import json

    root = tmp_path / "run"
    (root / "raw").mkdir(parents=True)
    (root / "transcripts_B").mkdir()
    tb = [root / "transcripts_B"]
    assert builder.asr_provenance("v1", tb) == (None, None)
    (root / "raw" / "v1_parakeet.json").write_text(
        json.dumps({"ok": True, "model": "parakeet-tdt-0.6b-v3"})
    )
    assert builder.asr_provenance("v1", tb) == ("parakeet_mlx", "parakeet-tdt-0.6b-v3")
    (root / "raw" / "v2_parakeet.json").write_text(json.dumps({"ok": False, "model": "m"}))
    assert builder.asr_provenance("v2", tb) == (None, None)
