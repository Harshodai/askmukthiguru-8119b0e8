"""The v10 voice-method backfill write path (B3).

The write is the dangerous half of the speaker fix, so these tests pin the
policy, not the plumbing:

* the written keys are a subset of the four allowed keys, whatever the branch;
* ``pass`` and ``fail`` map from evidence exactly as the plan states;
* absence of evidence (no verdict row, an unusable slice, an unverified
  calibration, a missing window check) is ``no_evidence`` and writes nothing;
* ``--apply`` without a snapshot exits 2 before it reads the collection;
* a dry run issues zero writes.

No Qdrant and no network: the scroll and the payload patch are injected fakes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND.parent
for _entry in (str(_REPO_ROOT), str(_BACKEND)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from scripts.ops import backfill_v10_voice_method as backfill  # noqa: E402


def _payload(**over):
    base = {
        "source_span_id": "span-1",
        "video_id": "vid1",
        "speaker_verified": True,
        "voice_verification_method": "ecapa_voxceleb_centroid_v1",
        "verbatim_text": "Hold the intention to live free.",
        "transcript_hash": "hash-1",
    }
    base.update(over)
    return base


def _verdict(**over):
    base = {
        "source_span_id": "span-1",
        "point_id": "p1",
        "video_id": "vid1",
        "verdict": "verified",
        "cosine": 0.71,
        "margin": 0.4,
        "calibration_revision": "rev-2026-10-30",
    }
    base.update(over)
    return base


def _window(verdict="window_pass", **over):
    base = {"source_span_id": "span-1", "video_id": "vid1", "verdict": verdict}
    base.update(over)
    return base


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Allowlist
# ---------------------------------------------------------------------------
def test_every_branch_writes_only_allowlisted_keys():
    branches = [
        backfill.decide(_payload(), _verdict(), _window()),
        backfill.decide(_payload(), _verdict(verdict="refused_guru_mismatch"), _window()),
        backfill.decide(_payload(), None, None),
    ]
    for outcome, updates in branches:
        assert set(updates) <= set(backfill.ALLOWED_KEYS)
        assert backfill.allowed_key_violation(updates) is None
        if outcome == "no_evidence":
            assert updates == {}


def test_a_forbidden_key_is_named():
    assert backfill.allowed_key_violation({"verbatim_text": "x"}) == "verbatim_text"
    assert backfill.allowed_key_violation({"transcript_hash": "x"}) == "transcript_hash"
    assert backfill.allowed_key_violation({"speaker_verified": True}) is None


def test_the_allowlist_never_includes_text_or_hash_keys():
    for key in ("verbatim_text", "source_transcript_text", "transcript_hash", "source_text_hash"):
        assert key not in backfill.ALLOWED_KEYS


# ---------------------------------------------------------------------------
# Pass / fail mapping
# ---------------------------------------------------------------------------
def test_pass_sets_the_method_and_the_verdict_and_leaves_the_flag_alone():
    outcome, updates = backfill.decide(_payload(), _verdict(), _window())
    assert outcome == "pass"
    assert updates["voice_verification_method"] == "ecapa_voxceleb_span_slice_v2"
    # "speaker_verified stays true" is a no-op, not a write: this branch never
    # flips the flag, so a span that was already false is never promoted.
    assert "speaker_verified" not in updates
    assert updates["voice_verdict"] == {
        "cosine": 0.71,
        "margin": 0.4,
        "calibration_revision": "rev-2026-10-30",
        "window_check": "window_pass",
    }


@pytest.mark.parametrize(
    "verdict",
    ["refused_guru_mismatch", "refused_below_cosine_floor", "refused_below_margin"],
)
def test_a_refused_verdict_unverifies_the_span(verdict):
    outcome, updates = backfill.decide(_payload(), _verdict(verdict=verdict), _window())
    assert outcome == "fail"
    assert updates == {
        "speaker_verified": False,
        "speaker_verification_status": "ecapa_failed",
    }


def test_a_host_window_fails_even_when_the_acoustics_passed():
    outcome, updates = backfill.decide(_payload(), _verdict(), _window(verdict="window_fail"))
    assert outcome == "fail"
    assert updates["speaker_verified"] is False
    assert updates["speaker_verification_status"] == "ecapa_failed"


# ---------------------------------------------------------------------------
# Absence of evidence is never evidence
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "verdict_row",
    [
        None,
        _verdict(verdict="missing_audio"),
        _verdict(verdict="invalid_audio"),
        _verdict(verdict="out_of_bounds"),
        _verdict(verdict="too_short"),
        _verdict(verdict="not_run"),
        _verdict(verdict="calibration_unavailable"),
        _verdict(source_span_id="span-other"),
        _verdict(calibration_revision=""),
    ],
)
def test_missing_or_unusable_evidence_is_no_evidence(verdict_row):
    outcome, updates = backfill.decide(_payload(), verdict_row, _window())
    assert outcome == "no_evidence"
    assert updates == {}


def test_a_missing_or_undecided_window_check_never_becomes_a_pass():
    assert backfill.decide(_payload(), _verdict(), None) == ("no_evidence", {})
    assert backfill.decide(_payload(), _verdict(), _window(verdict="no_diarization")) == (
        "no_evidence",
        {},
    )
    # A window row that belongs to another span is not this span's evidence.
    assert backfill.decide(_payload(), _verdict(), _window(source_span_id="span-other")) == (
        "no_evidence",
        {},
    )


# ---------------------------------------------------------------------------
# Plan (pure)
# ---------------------------------------------------------------------------
def test_a_span_without_a_verdict_row_is_untouched_and_counted():
    planned = backfill.plan(
        [("p1", _payload()), ("p2", _payload(source_span_id="span-2"))],
        {"span-1": _verdict()},
        {"span-1": _window()},
    )
    assert planned["counts"] == {"pass": 1}
    assert planned["points_without_verdict"] == 1
    assert [row["span_id"] for row in planned["rows"]] == ["span-1"]


def test_a_declared_point_id_mismatch_blocks_the_write():
    planned = backfill.plan(
        [("p9", _payload())], {"span-1": _verdict(point_id="p1")}, {"span-1": _window()}
    )
    assert planned["point_id_mismatch"] == 1
    assert planned["rows"][0]["outcome"] == "no_evidence"
    assert planned["rows"][0]["updates"] == {}


def test_listen_queue_lists_the_videos_of_failed_spans():
    rows = [
        {"outcome": "fail", "video_id": "vid2", "span_id": "span-2"},
        {"outcome": "fail", "video_id": "vid1", "span_id": "span-1"},
        {"outcome": "pass", "video_id": "vid1", "span_id": "span-3"},
    ]
    assert backfill._listen_queue(rows) == {"vid1": ["span-1"], "vid2": ["span-2"]}


# ---------------------------------------------------------------------------
# CLI gates
# ---------------------------------------------------------------------------
def _no_network(monkeypatch, calls):
    def _scroll(*_args, **_kwargs):
        calls.append("scroll")
        return iter(())

    def _set_payload(*_args, **_kwargs):
        calls.append("set_payload")

    monkeypatch.setattr(backfill, "_scroll", _scroll)
    monkeypatch.setattr(backfill, "_set_payload", _set_payload)


def test_apply_without_a_snapshot_exits_two_before_touching_the_collection(
    tmp_path, monkeypatch, capsys
):
    calls: list[str] = []
    _no_network(monkeypatch, calls)
    verdicts = _write_jsonl(tmp_path / "v.jsonl", [_verdict()])
    code = backfill.main(["--verdicts-jsonl", str(verdicts), "--apply"])
    assert code == 2
    assert calls == []
    assert "snapshot" in capsys.readouterr().err


def test_apply_without_a_rollback_file_exits_two(tmp_path, monkeypatch, capsys):
    calls: list[str] = []
    _no_network(monkeypatch, calls)
    verdicts = _write_jsonl(tmp_path / "v.jsonl", [_verdict()])
    code = backfill.main(
        [
            "--verdicts-jsonl",
            str(verdicts),
            "--apply",
            "--snapshot",
            "snap-1",
            "--report",
            str(tmp_path / "r.json"),
        ]
    )
    assert code == 2
    assert "set_payload" not in calls
    assert "rollback" in capsys.readouterr().err


def test_a_dry_run_issues_zero_writes(tmp_path, monkeypatch):
    calls: list[str] = []
    points = [("p1", _payload())]
    monkeypatch.setattr(backfill, "_scroll", lambda *a, **k: iter(points))
    monkeypatch.setattr(backfill, "_set_payload", lambda *a, **k: calls.append("set_payload"))
    verdicts = _write_jsonl(tmp_path / "v.jsonl", [_verdict()])
    windows = _write_jsonl(tmp_path / "w.jsonl", [_window()])
    report_path = tmp_path / "report.json"
    rollback_path = tmp_path / "rollback.json"

    code = backfill.main(
        [
            "--verdicts-jsonl",
            str(verdicts),
            "--windows-jsonl",
            str(windows),
            "--report",
            str(report_path),
            "--rollback-out",
            str(rollback_path),
        ]
    )

    assert code == 0
    assert calls == []
    assert not rollback_path.exists()
    report = json.loads(report_path.read_text())
    assert report["mode"] == "dry_run"
    assert report["written"] == 0
    assert report["outcomes"] == {"pass": 1}
    assert report["mutations"] == {"qdrant_writes": 0}
    assert report["listen_queue"] == {}


def test_apply_writes_allowlisted_keys_and_saves_the_old_values(tmp_path, monkeypatch):
    written: list[tuple[str, dict]] = []
    points = [
        ("p1", _payload()),
        ("p2", _payload(source_span_id="span-2", video_id="vid2")),
    ]
    monkeypatch.setattr(backfill, "_scroll", lambda *a, **k: iter(points))
    monkeypatch.setattr(
        backfill,
        "_set_payload",
        lambda _url, _coll, point_id, updates: written.append((point_id, updates)),
    )
    verdicts = _write_jsonl(
        tmp_path / "v.jsonl",
        [
            _verdict(),
            _verdict(source_span_id="span-2", point_id="p2", verdict="refused_guru_mismatch"),
        ],
    )
    windows = _write_jsonl(
        tmp_path / "w.jsonl", [_window(), _window(span_id=None, source_span_id="span-2")]
    )
    rollback_path = tmp_path / "rollback.json"
    report_path = tmp_path / "report.json"

    code = backfill.main(
        [
            "--verdicts-jsonl",
            str(verdicts),
            "--windows-jsonl",
            str(windows),
            "--apply",
            "--snapshot",
            "first_person_v10-snap-1.snapshot",
            "--rollback-out",
            str(rollback_path),
            "--report",
            str(report_path),
        ]
    )

    assert code == 0
    assert [point_id for point_id, _updates in written] == ["p1", "p2"]
    for _point_id, updates in written:
        assert set(updates) <= set(backfill.ALLOWED_KEYS)

    rollback = json.loads(rollback_path.read_text())
    assert rollback["schema"] == backfill.ROLLBACK_SCHEMA
    assert rollback["snapshot"] == "first_person_v10-snap-1.snapshot"
    by_id = {entry["id"]: entry for entry in rollback["points"]}
    assert by_id["p1"]["previous"]["voice_verification_method"] == "ecapa_voxceleb_centroid_v1"
    # A key that was absent is recorded as null AND flagged as previously absent.
    assert by_id["p1"]["previous"]["voice_verdict"] is None
    assert by_id["p1"]["keys_previously_absent"] == ["voice_verdict"]

    report = json.loads(report_path.read_text())
    assert report["mode"] == "apply"
    assert report["written"] == 2
    assert report["outcomes"] == {"pass": 1, "fail": 1}
    assert report["listen_queue"] == {"vid2": ["span-2"]}
