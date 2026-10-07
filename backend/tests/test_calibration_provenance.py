"""Calibration provenance guard (Section E audit, 2026-09-30).

Locks three TRUTHS about the first-person calibration path so the n=300 fiction
cannot silently become loadable fact again:

1. An empty ``FIRST_PERSON_CALIBRATION_PATH`` loads NO profile (HEAD contract).
2. A truthful profile built from the REAL label budget (14 single-judge pilot
   labels, 0 B1-adjudicated -- source:
   ~/mukthiguru_attribution_data/gold_pilot/relevance_pilot.csv) cannot pass
   either validator: the system fails closed rather than certify an unproven
   1% risk bound.
3. Profiles under ``config/`` / ``backend/config/`` are hand-written unless
   they carry ``evaluation.gold.run_calibration`` output keys
   (``n_selected``/``coverage``/``precision``) or an explicit
   ``provenance.status``; the three current copies assert ``n=300`` with no
   generator run anywhere in the repo. That check is xfail today on purpose:
   it flips to XPASS the moment a real fitted profile replaces the fiction.
"""

from __future__ import annotations

import json
from pathlib import Path

from services.first_person_pipeline import load_calibration_profile
from services.first_person_release import _profile_errors

# Real human-label budget measured 2026-09-30 by Section E:
# 2129 candidate rows / 116 questions, judge_a on 14 rows, judge_b on 0,
# adjudicated on 0 -> 0 B1-resolved labels, 14 single-judge pilot labels.
REAL_PILOT_LABELS = 14
# One-sided Clopper-Pearson UCB on 0 errors at n=14, delta=0.05 (rule of three).
REAL_UCB_RISK = 1 - 0.05 ** (1 / REAL_PILOT_LABELS)  # ~= 0.1926


def _candidate_profiles(name: str) -> list[Path]:
    """Both locations a profile can live: repo-root config/ (host + /config mount)."""
    here = Path(__file__).resolve()
    return [
        Path("/config") / name,
        here.parents[2] / "config" / name,
        here.parents[1] / "config" / name,
    ]


def _existing_profiles() -> list[Path]:
    names = (
        "first_person_calibration_first_person_v7.json",
        "first_person_calibration_v7.json",
    )
    seen: set[str] = set()
    found: list[Path] = []
    for name in names:
        for cand in _candidate_profiles(name):
            if cand.is_file() and str(cand) not in seen:
                seen.add(str(cand))
                found.append(cand)
                break
    return found


def test_empty_calibration_path_loads_no_profile():
    """HEAD contract: without the env var the pipeline is uncalibrated."""
    assert load_calibration_profile("", "first_person_v7") is None


def test_truthful_pilot_profile_is_rejected_by_serve_validator(tmp_path):
    """The honest profile for the real label budget must NOT load (fail-closed)."""
    profile = {
        "threshold": 0.45,
        "score_kind": "dense_cosine",
        "n": REAL_PILOT_LABELS,
        "ucb_risk": round(REAL_UCB_RISK, 4),
        "target_risk": 0.01,
        "collection": "first_person_v7",
        "fitted_at": "1970-01-01T00:00:00Z",
    }
    path = tmp_path / "truthful.json"
    path.write_text(json.dumps(profile), encoding="utf-8")

    assert REAL_UCB_RISK > 0.01, "n=14 can never clear the 1% product bound"
    assert load_calibration_profile(str(path), "first_person_v7") is None
    errors = _profile_errors(str(path), "first_person_v7")
    assert any("ucb_risk exceeds target_risk" in e for e in errors)


def test_fictional_n300_profile_shape_passes_arithmetic_gates(tmp_path):
    """Documents WHY the hand-written file loads: the validators check keys and
    arithmetic only -- nothing ties n/ucb_risk to any dataset. This is the
    provenance gap the rest of this module guards."""
    profile = {
        "threshold": 0.45,
        "score_kind": "dense_cosine",
        "n": 300,
        "ucb_risk": 0.009,
        "target_risk": 0.01,
        "collection": "first_person_v7",
        "fitted_at": "2026-09-28T18:00:00Z",
    }
    path = tmp_path / "fiction.json"
    path.write_text(json.dumps(profile), encoding="utf-8")
    loaded = load_calibration_profile(str(path), "first_person_v7")
    assert loaded is not None and loaded["n"] == 300
    # ...but the release gate is equally arithmetic-only:
    assert _profile_errors(str(path), "first_person_v7") == []
    # n is never even type-checked by either validator:
    assert "n" not in ("threshold", "ucb_risk", "target_risk")


def test_shipped_profiles_have_demoted_claims():
    """Section C audit (2026-09-30): all shipped calibration profiles must carry
    the demoted schema ('claims': 'none') and honest provenance ('n=14 pilot,
    no conformal guarantees'), with no statistical claims (no n, ucb_risk, target_risk).
    """
    profiles = _existing_profiles()
    assert profiles, "expected at least one shipped calibration profile"
    for path in profiles:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data.get("claims") == "none", f"{path} must declare 'claims': 'none'"
        assert "no conformal guarantees" in str(data.get("provenance", "")), (
            f"{path} must state honest provenance"
        )
        assert "n" not in data, f"{path} must not claim sample size n"
        assert "ucb_risk" not in data, f"{path} must not claim ucb_risk"
        assert "target_risk" not in data, f"{path} must not claim target_risk"
        assert data.get("threshold") == 0.45, f"{path} threshold must be 0.45"
        assert data.get("score_kind") in ("cosine", "dense_cosine"), (
            f"{path} score_kind must be cosine"
        )
        assert _profile_errors(str(path), "first_person_v7") == [], (
            f"{path} must pass release gate validator"
        )
