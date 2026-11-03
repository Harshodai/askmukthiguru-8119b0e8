"""P7: more impostor trials, and the false-accept bound the calibration record carries.

Torch-free: the ECAPA stack is never loaded. Vectors are small synthetic arrays.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

_BACKEND = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND.parent
for _entry in (str(_REPO_ROOT), str(_BACKEND)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from scripts.ops import build_impostor_slices as slices  # noqa: E402
from scripts.ops import regenerate_v10_span_ecapa_verdicts as regen  # noqa: E402

# ---------------------------------------------------------------------------------------------
# Bound arithmetic: the numbers in the merged plan, recomputed
# ---------------------------------------------------------------------------------------------


def test_262_clean_trials_bound_the_rate_near_one_point_one_percent():
    bound = regen.far_upper_bound(0, 262)
    assert bound == pytest.approx(0.01137, abs=1e-4)  # the plan's "about 1.1%"
    assert bound > 3 / 262 - 0.0005  # and consistent with the rule of three


def test_about_600_clean_trials_reach_half_a_percent():
    assert regen.trials_needed_for_far(0.005) == 598
    assert regen.far_upper_bound(0, 598) <= 0.005
    assert regen.far_upper_bound(0, 597) > 0.005


def test_about_3000_clean_trials_reach_a_tenth_of_a_percent():
    assert regen.trials_needed_for_far(0.001) == 2995
    assert regen.far_upper_bound(0, 2995) <= 0.001
    assert regen.far_upper_bound(0, 2994) > 0.001


def test_one_false_accept_costs_a_lot_of_evidence():
    assert regen.far_upper_bound(1, 600) > 0.005


@pytest.mark.parametrize("target", [0.0, 1.0, -0.1, 1.5])
def test_a_target_outside_the_open_unit_interval_is_refused(target):
    with pytest.raises(ValueError):
        regen.trials_needed_for_far(target)


@pytest.mark.parametrize("accepts,trials", [(0, 0), (-1, 10), (11, 10)])
def test_an_impossible_count_has_no_bound(accepts, trials):
    assert regen.far_upper_bound(accepts, trials) is None


def test_the_record_carries_counts_bound_target_and_trials_needed():
    record = regen.far_bound_record(0, 262, target=0.005)
    assert record["impostor_trials"] == 262 and record["false_accepts"] == 0
    assert record["meets_target"] is False
    assert record["upper_bound"] == pytest.approx(0.011369, abs=1e-5)
    assert record["clean_trials_needed_for_target"] == 598
    assert record["method"] == "clopper_pearson_one_sided_exact"
    assert regen.far_bound_record(0, 700, target=0.005)["meets_target"] is True


def test_a_missing_count_cannot_meet_any_target():
    record = regen.far_bound_record(None, None)
    assert record["upper_bound"] is None and record["meets_target"] is False


# ---------------------------------------------------------------------------------------------
# The gate: refuse a calibration whose bound exceeds the target
# ---------------------------------------------------------------------------------------------
def _artifact(trials=262, accepts=0, **over):
    data = {
        "calibration_available": True,
        "calibration_revision": "rev-1",
        "thresholds": {"cosine_floor": 0.2828, "margin_threshold": 0.05},
        "trial_counts": {"test_impostor_trials": trials},
        "false_accept": {"test": {"count": accepts}},
    }
    data.update(over)
    return data


def test_the_gate_refuses_the_pinned_262_trial_calibration_at_half_a_percent():
    ok, record = regen.far_gate(_artifact(262, 0), 0.005)
    assert ok is False
    assert record["upper_bound"] > 0.005


def test_the_gate_passes_when_enough_clean_trials_exist():
    ok, record = regen.far_gate(_artifact(700, 0), 0.005)
    assert ok is True and record["meets_target"] is True


def test_the_gate_refuses_one_false_accept_in_600():
    assert regen.far_gate(_artifact(600, 1), 0.005)[0] is False


def test_the_gate_refuses_an_artifact_without_the_counts():
    assert regen.far_gate({"calibration_available": True}, 0.005)[0] is False
    assert regen.far_gate(_artifact(accepts=None), 0.005)[0] is False


def _write(tmp_path, data):
    path = tmp_path / "cal.json"
    path.write_text(json.dumps(data))
    return path


def test_loading_a_pinned_calibration_without_max_far_still_records_the_bound(tmp_path):
    loaded = regen.load_pinned_calibration(_write(tmp_path, _artifact(262, 0)))
    assert loaded["far_bound"]["meets_target"] is False  # recorded...
    assert loaded["cosine_floor"] == 0.2828  # ...but not refused: the gate is opt-in


def test_loading_with_max_far_refuses_a_weak_calibration(tmp_path):
    with pytest.raises(regen.InputError, match="false-accept target"):
        regen.load_pinned_calibration(_write(tmp_path, _artifact(262, 0)), max_far=0.005)


def test_loading_with_max_far_accepts_a_strong_calibration(tmp_path):
    loaded = regen.load_pinned_calibration(_write(tmp_path, _artifact(700, 0)), max_far=0.005)
    assert loaded["far_bound"]["meets_target"] is True


# ---------------------------------------------------------------------------------------------
# Foreign (host / interviewer) trials
# ---------------------------------------------------------------------------------------------
def _unit(*xs):
    v = np.array(xs, dtype=np.float32)
    return v / np.linalg.norm(v)


REFS = {"krishnaji": _unit(1, 0, 0), "preethaji": _unit(0, 1, 0)}


def test_each_foreign_slice_yields_one_trial_per_teacher():
    vectors = {"foreign:a": _unit(0, 0, 1), "foreign:b": _unit(0.2, 0.2, 1)}
    splits = {"foreign:a": "test", "foreign:b": "calibration"}
    trials = regen.build_foreign_trials(vectors, splits, REFS, "test", {"foreign:a": "other"})
    assert [(t["source_span_id"], t["claimed"]) for t in trials] == [
        ("foreign:a", "krishnaji"),
        ("foreign:a", "preethaji"),
    ]
    assert {t["kind"] for t in trials} == {"foreign_voice"}
    assert trials[0]["true_label"] == "other"


def test_a_foreign_voice_far_from_both_teachers_scores_low():
    trials = regen.build_foreign_trials({"f": _unit(0, 0, 1)}, {"f": "test"}, REFS, "test")
    assert all(abs(t["cosine"]) < 1e-6 for t in trials)


def test_a_foreign_voice_close_to_a_teacher_is_a_high_scoring_impostor():
    trials = regen.build_foreign_trials({"f": _unit(1, 0.05, 0)}, {"f": "test"}, REFS, "test")
    claimed = {t["claimed"]: t for t in trials}
    assert claimed["krishnaji"]["cosine"] > 0.99
    assert claimed["krishnaji"]["margin"] > 0.9  # the dangerous case the floors must exceed
    assert claimed["preethaji"]["margin"] < 0


def test_foreign_trials_are_only_built_for_the_requested_split():
    vectors = {"a": _unit(0, 0, 1), "b": _unit(0, 0, 1)}
    trials = regen.build_foreign_trials(vectors, {"a": "train", "b": "test"}, REFS, "test")
    assert {t["source_span_id"] for t in trials} == {"b"}


def test_foreign_trials_raise_the_floor_above_every_foreign_score():
    base = {
        "positive_trials": [],
        "impostor_trials": [
            {"cosine": 0.1, "margin": -0.2} for _ in range(regen.MIN_IMPOSTOR_TRIALS)
        ],
    }
    low = regen.calibrate_from_trials(base)
    foreign = regen.build_foreign_trials(
        {"f": _unit(1, 0.3, 0)}, {"f": "calibration"}, REFS, "calibration"
    )
    with_foreign = {**base, "impostor_trials": base["impostor_trials"] + foreign}
    high = regen.calibrate_from_trials(with_foreign)
    assert high["cosine_floor"] > low["cosine_floor"]
    assert high["cosine_floor"] > max(t["cosine"] for t in foreign)
    assert high["calibration_false_accepts"] == 0


# ---------------------------------------------------------------------------------------------
# Foreign slice input file
# ---------------------------------------------------------------------------------------------
def _row(**over):
    base = {"slice_id": "s1", "video_id": "v1", "start_ms": 1000, "end_ms": 5000, "label": "other"}
    base.update(over)
    return base


def _jsonl(tmp_path, rows):
    path = tmp_path / "foreign.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def test_valid_foreign_slices_load(tmp_path):
    rows = regen.load_foreign_slices(_jsonl(tmp_path, [_row(), _row(slice_id="s2", label="host")]))
    assert [r["slice_id"] for r in rows] == ["s1", "s2"]


@pytest.mark.parametrize(
    "bad",
    [
        _row(label="krishnaji"),
        _row(label=""),
        _row(slice_id=""),
        _row(start_ms=5000, end_ms=1000),
        _row(start_ms="x"),
    ],
)
def test_malformed_foreign_slices_are_refused(tmp_path, bad):
    with pytest.raises(regen.InputError):
        regen.load_foreign_slices(_jsonl(tmp_path, [bad]))


def test_a_duplicate_slice_id_is_refused(tmp_path):
    with pytest.raises(regen.InputError, match="duplicate"):
        regen.load_foreign_slices(_jsonl(tmp_path, [_row(), _row()]))


def test_a_missing_file_is_an_input_error(tmp_path):
    with pytest.raises(regen.InputError):
        regen.load_foreign_slices(tmp_path / "nope.jsonl")


# ---------------------------------------------------------------------------------------------
# Building slices from diarization windows
# ---------------------------------------------------------------------------------------------
def _speaker(labels, start=1.0, hop=1.0, ok=True):
    return {
        "ok": ok,
        "t_centres": [start + i * hop for i in range(len(labels))],
        "win_lab": list(labels),
    }


def test_runs_are_found_centre_to_centre():
    runs = slices.other_runs([1, 2, 3, 4, 5, 6], ["K", "O", "O", "O", "O", "K"])
    assert runs == [(2, 5)]


def test_two_runs_split_by_a_teacher_window():
    runs = slices.other_runs(list(range(1, 11)), list("OOOOKOOOOO"))
    assert runs == [(1, 4), (6, 10)]


def test_a_gap_in_the_window_centres_splits_a_run():
    runs = slices.other_runs([1, 2, 3, 10, 11], list("OOOOO"))
    assert runs == [(1, 3), (10, 11)]


def test_a_slice_never_reaches_into_a_teacher_window():
    # Teacher windows at centres 1 and 8; O windows 2..7. A window centred at c covers
    # [c-1, c+1], so the teacher at 1 covers up to 2 and the teacher at 8 starts at 7.
    out = slices.slices_for_video("v", _speaker(list("KOOOOOOK")))
    assert [(r["start_ms"], r["end_ms"]) for r in out] == [(2000, 7000)]


def test_short_runs_are_dropped():
    assert slices.slices_for_video("v", _speaker(list("KOOOK"))) == []  # 2 s < 3 s


def test_long_runs_are_cut_into_pieces_no_longer_than_max():
    out = slices.slices_for_video("v", _speaker(["O"] * 30), max_s=12.0)
    assert all(r["end_ms"] - r["start_ms"] <= 12_000 for r in out)
    assert all(r["end_ms"] - r["start_ms"] >= 3_000 for r in out)
    ranges = [(r["start_ms"], r["end_ms"]) for r in out]
    assert all(a[1] <= b[0] for a, b in zip(ranges, ranges[1:], strict=False))  # no overlap


def test_the_per_video_cap_keeps_an_even_spread():
    labels = (["O"] * 5 + ["K"]) * 40
    out = slices.slices_for_video("v", _speaker(labels), max_per_video=10)
    assert len(out) == 10
    starts = [r["start_ms"] for r in out]
    assert starts == sorted(starts) and starts[-1] - starts[0] > 100_000


def test_a_failed_or_malformed_speaker_file_yields_nothing():
    assert slices.slices_for_video("v", _speaker(["O"] * 9, ok=False)) == []
    assert slices.slices_for_video("v", {"ok": True, "t_centres": [1], "win_lab": []}) == []
    assert slices.slices_for_video("v", None) == []


def test_slice_ids_are_unique_and_the_label_is_other():
    out = slices.slices_for_video("v", _speaker((["O"] * 6 + ["K"]) * 5))
    assert len({r["slice_id"] for r in out}) == len(out)
    assert {r["label"] for r in out} == {"other"}


def test_the_built_file_loads_with_the_calibrator_loader(tmp_path):
    speaker_dir = tmp_path / "speaker"
    speaker_dir.mkdir()
    (speaker_dir / "vidA_speaker.json").write_text(json.dumps(_speaker((["O"] * 6 + ["K"]) * 3)))
    (speaker_dir / "vidB_speaker.json").write_text("{broken")
    out = tmp_path / "slices.jsonl"
    summary = tmp_path / "summary.json"
    code = slices.main(
        ["--speaker-dir", str(speaker_dir), "--out", str(out), "--summary", str(summary)]
    )
    assert code == 0
    report = json.loads(summary.read_text())
    assert report["unreadable_files"] == ["vidB"]
    assert report["videos_with_slices"] == 1
    loaded = regen.load_foreign_slices(out)
    assert len(loaded) == report["candidate_slices"] > 0
    assert math.isfinite(loaded[0]["start_ms"])


def test_no_speaker_files_is_an_input_error(tmp_path, capsys):
    code = slices.main(["--speaker-dir", str(tmp_path), "--out", str(tmp_path / "o.jsonl")])
    assert code == 2
    assert "no *_speaker.json" in capsys.readouterr().err
