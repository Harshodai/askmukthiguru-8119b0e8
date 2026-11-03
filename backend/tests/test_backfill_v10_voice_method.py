"""The v10 voice-method backfill write path (B3).

The write is the dangerous half of the speaker fix, so these tests pin the
policy, not the plumbing:

* the written keys are a subset of the allowlist, whatever the branch;
* ``pass`` and ``fail`` map from evidence exactly as the plan states;
* absence of evidence (no verdict row, an unusable slice, an unverified
  calibration, a missing window check) is ``no_evidence`` and writes nothing;
* ``--apply`` without a snapshot exits 2 before it reads the collection;
* a dry run issues zero writes;
* the shared write rule refuses a payload before ``set_payload`` is issued;
* the post-checks (ids, immutable keys, allowlisted keys, vectors, violators) fail loudly.

No Qdrant and no network: the scroll and the payload patch are injected fakes.
"""

from __future__ import annotations

import datetime as dt
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
        "cosine_floor": 0.2828,
        "margin_threshold": 0.05,
        "speaker_model_revision": "ecapa-rev-1",
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
NOW = "2026-10-31T12:00:00+00:00"


def test_pass_sets_the_method_and_the_provenance_and_leaves_the_flag_alone():
    outcome, updates = backfill.decide(_payload(), _verdict(), _window(), now=NOW)
    assert outcome == "pass"
    # "speaker_verified stays true" is a no-op, not a write: this branch never
    # flips the flag, so a span that was already false is never promoted.
    assert "speaker_verified" not in updates
    assert updates == {
        "voice_verification_method": "ecapa_voxceleb_span_slice_v2",
        "voice_model_revision": "ecapa-rev-1",
        "voice_score": 0.71,
        "voice_margin": 0.4,
        "voice_threshold_applied": {"cosine_floor": 0.2828, "margin_threshold": 0.05},
        "voice_calibration_id": "rev-2026-10-30",
        "voice_window_check": "pass",
        "voice_verified_at": NOW,
        "speaker_verification_status": "verified",
    }


def test_a_pass_on_a_span_that_was_already_unverified_gets_no_verified_status():
    outcome, updates = backfill.decide(
        _payload(speaker_verified=False), _verdict(), _window(), now=NOW
    )
    assert outcome == "pass"
    assert "speaker_verification_status" not in updates
    assert "speaker_verified" not in updates


@pytest.mark.parametrize(
    "missing",
    ["speaker_model_revision", "cosine", "margin", "cosine_floor", "margin_threshold"],
)
def test_a_verified_row_that_cannot_back_the_full_record_is_no_evidence(missing):
    row = _verdict()
    row.pop(missing)
    assert backfill.decide(_payload(), row, _window(), now=NOW) == ("no_evidence", {})


@pytest.mark.parametrize(
    "verdict",
    ["refused_guru_mismatch", "refused_below_cosine_floor", "refused_below_margin"],
)
def test_a_refused_verdict_unverifies_the_span(verdict):
    outcome, updates = backfill.decide(_payload(), _verdict(verdict=verdict), _window(), now=NOW)
    assert outcome == "fail"
    assert updates["speaker_verified"] is False
    assert updates["speaker_verification_status"] == "ecapa_failed"
    # The listener gets the score and the threshold it missed, not just a flag.
    assert updates["voice_score"] == 0.71
    assert updates["voice_threshold_applied"] == {"cosine_floor": 0.2828, "margin_threshold": 0.05}
    assert updates["voice_window_check"] == "pass"
    # A failed span never gains a method it did not earn.
    assert "voice_verification_method" not in updates


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


class FakeQdrant:
    """Stateful stand-in for the three Qdrant calls the script makes."""

    def __init__(self, points, vectors=None):
        self.points = {pid: dict(payload) for pid, payload in points}
        self.vectors = vectors or {pid: [0.1, 0.2, 0.3] for pid, _ in points}
        self.writes: list[tuple[str, dict]] = []

    def scroll(self, *_a, **_k):
        return iter([(pid, dict(payload)) for pid, payload in self.points.items()])

    def set_payload(self, _url, _coll, point_id, updates):
        self.writes.append((point_id, updates))
        self.points[point_id].update(updates)

    def fetch_vectors(self, _url, _coll, ids):
        return {pid: self.vectors[pid] for pid in ids}

    def install(self, monkeypatch):
        monkeypatch.setattr(backfill, "_scroll", self.scroll)
        monkeypatch.setattr(backfill, "_set_payload", self.set_payload)
        monkeypatch.setattr(backfill, "_fetch_vectors", self.fetch_vectors)
        monkeypatch.setattr(backfill, "_list_snapshots", self.list_snapshots)

    snapshots: list[dict] | None = None

    def list_snapshots(self, _url, _coll):
        if self.snapshots is not None:
            return self.snapshots
        # Default: the snapshot the test args name, taken just now.
        return [
            {
                "name": "first_person_v10-snap-1.snapshot",
                "creation_time": dt.datetime.now(dt.UTC).replace(tzinfo=None).isoformat(),
            }
        ]


def _bare(span_id="span-1", **over):
    base = _payload(source_span_id=span_id, voice_verification_method=None)
    base.update(over)
    return base


def _args(tmp_path, verdicts, windows=None, *extra):
    args = ["--verdicts-jsonl", str(verdicts), "--report", str(tmp_path / "report.json")]
    if windows is not None:
        args += ["--windows-jsonl", str(windows)]
    return args + list(extra)


def _apply_args(tmp_path, verdicts, windows, *extra):
    return _args(
        tmp_path,
        verdicts,
        windows,
        "--apply",
        "--snapshot",
        "first_person_v10-snap-1.snapshot",
        "--rollback-out",
        str(tmp_path / "rollback.json"),
        "--before-out",
        str(tmp_path / "before.jsonl"),
        "--verified-at",
        NOW,
        *extra,
    )


def test_apply_writes_allowlisted_keys_and_saves_the_old_values(tmp_path, monkeypatch):
    fake = FakeQdrant(
        [
            ("p1", _payload()),
            ("p2", _payload(source_span_id="span-2", video_id="vid2")),
        ]
    )
    fake.install(monkeypatch)
    verdicts = _write_jsonl(
        tmp_path / "v.jsonl",
        [
            _verdict(),
            _verdict(source_span_id="span-2", point_id="p2", verdict="refused_guru_mismatch"),
        ],
    )
    windows = _write_jsonl(tmp_path / "w.jsonl", [_window(), _window(source_span_id="span-2")])

    code = backfill.main(_apply_args(tmp_path, verdicts, windows))

    assert code == 0
    assert [point_id for point_id, _updates in fake.writes] == ["p1", "p2"]
    for _point_id, updates in fake.writes:
        assert set(updates) <= set(backfill.ALLOWED_KEYS)

    rollback = json.loads((tmp_path / "rollback.json").read_text())
    assert rollback["schema"] == backfill.ROLLBACK_SCHEMA
    assert rollback["snapshot"] == "first_person_v10-snap-1.snapshot"
    by_id = {entry["id"]: entry for entry in rollback["points"]}
    assert by_id["p1"]["previous"]["voice_verification_method"] == "ecapa_voxceleb_centroid_v1"
    # A key that was absent is recorded as null AND flagged as previously absent.
    assert by_id["p1"]["previous"]["voice_score"] is None
    assert "voice_score" in by_id["p1"]["keys_previously_absent"]
    assert "voice_verification_method" not in by_id["p1"]["keys_previously_absent"]

    report = json.loads((tmp_path / "report.json").read_text())
    assert report["mode"] == "apply"
    assert report["written"] == 2
    assert report["outcomes"] == {"pass": 1, "fail": 1}
    assert report["listen_queue"] == {"vid2": ["span-2"]}
    assert report["post_checks"]["all_ok"] is True


# ---------------------------------------------------------------------------
# P1 x P5: what the backfill writes must be readable by the model that serves it
# ---------------------------------------------------------------------------
def test_every_key_the_backfill_writes_is_a_declared_span_field():
    """SourceSpan is extra='forbid': an undeclared key would make the parent unreadable."""
    from domain.first_person_context import SourceSpan

    for key in backfill.ALLOWED_KEYS:
        assert key in SourceSpan.model_fields, key


def test_the_allowlist_has_no_human_review_keys():
    from domain.speaker_provenance import HUMAN_REVIEW_KEYS

    for key in HUMAN_REVIEW_KEYS:
        assert key not in backfill.ALLOWED_KEYS


# ---------------------------------------------------------------------------
# P2: the write rule covers the set_payload path
# ---------------------------------------------------------------------------
def test_a_pass_that_contradicts_itself_is_refused_in_the_plan_and_never_written(
    tmp_path, monkeypatch
):
    # "verified" but the cosine sits below the floor recorded next to it.
    fake = FakeQdrant([("p1", _bare())])
    fake.install(monkeypatch)
    verdicts = _write_jsonl(tmp_path / "v.jsonl", [_verdict(cosine=0.1)])
    windows = _write_jsonl(tmp_path / "w.jsonl", [_window()])

    code = backfill.main(_apply_args(tmp_path, verdicts, windows))

    report = json.loads((tmp_path / "report.json").read_text())
    assert report["outcomes"] == {"guard_refused": 1}
    assert "ecapa_score_below_floor" in report["rows"][0]["reason"]
    assert fake.writes == []  # nothing issued
    # The span still violates the rule, so the post-check says so and the run is not clean.
    assert report["post_checks"]["checks"]["violators_zero"]["ok"] is False
    assert code == 1


def test_apply_row_refuses_before_issuing_the_write():
    calls: list[tuple] = []
    row = {
        "point_id": "p1",
        "updates": {
            "voice_verification_method": "ecapa_voxceleb_span_slice_v2",
            "voice_score": 0.9,
        },
    }
    with pytest.raises(backfill.SpeakerWriteRefused):
        backfill.apply_row(lambda *a: calls.append(a), "u", "c", row, _bare())
    assert calls == []


def test_apply_row_refuses_a_non_allowlisted_key_before_issuing_the_write():
    calls: list[tuple] = []
    row = {"point_id": "p1", "updates": {"verbatim_text": "edited"}}
    with pytest.raises(ValueError, match="verbatim_text"):
        backfill.apply_row(lambda *a: calls.append(a), "u", "c", row, _payload())
    assert calls == []


def test_apply_row_issues_the_write_when_the_record_is_complete():
    calls: list[tuple] = []
    _outcome, updates = backfill.decide(_bare(), _verdict(), _window(), now=NOW)
    backfill.apply_row(
        lambda *a: calls.append(a), "u", "c", {"point_id": "p1", "updates": updates}, _bare()
    )
    assert calls == [("u", "c", "p1", updates)]


# ---------------------------------------------------------------------------
# P5: dry run, expected count, sample diffs, before export
# ---------------------------------------------------------------------------
def test_dry_run_reports_the_bare_flag_count_and_ten_seeded_sample_diffs(tmp_path, monkeypatch):
    points = [(f"p{i}", _bare(f"span-{i}")) for i in range(25)]
    FakeQdrant(points).install(monkeypatch)
    verdicts = _write_jsonl(
        tmp_path / "v.jsonl",
        [_verdict(source_span_id=f"span-{i}", point_id=f"p{i}") for i in range(25)],
    )
    windows = _write_jsonl(
        tmp_path / "w.jsonl", [_window(source_span_id=f"span-{i}") for i in range(25)]
    )

    assert backfill.main(_args(tmp_path, verdicts, windows, "--verified-at", NOW)) == 0
    first = json.loads((tmp_path / "report.json").read_text())
    assert first["points_claiming_verified_without_method_before"] == 25
    assert len(first["sample_diffs"]) == 10
    sample = first["sample_diffs"][0]
    assert sample["before"]["voice_verification_method"] is None
    assert sample["after"]["voice_verification_method"] == "ecapa_voxceleb_span_slice_v2"

    assert backfill.main(_args(tmp_path, verdicts, windows, "--verified-at", NOW)) == 0
    second = json.loads((tmp_path / "report.json").read_text())
    assert [d["point_id"] for d in first["sample_diffs"]] == [
        d["point_id"] for d in second["sample_diffs"]
    ]


def test_expect_count_mismatch_refuses_in_dry_run_and_apply(tmp_path, monkeypatch, capsys):
    fake = FakeQdrant([("p1", _bare())])
    fake.install(monkeypatch)
    verdicts = _write_jsonl(tmp_path / "v.jsonl", [_verdict()])
    windows = _write_jsonl(tmp_path / "w.jsonl", [_window()])

    assert backfill.main(_args(tmp_path, verdicts, windows, "--expect-count", "732")) == 2
    assert "count_mismatch" in capsys.readouterr().err
    assert backfill.main(_apply_args(tmp_path, verdicts, windows, "--expect-count", "732")) == 2
    assert fake.writes == []
    assert not (tmp_path / "before.jsonl").exists()
    assert backfill.main(_args(tmp_path, verdicts, windows, "--expect-count", "1")) == 0


def test_apply_without_before_out_exits_two(tmp_path, monkeypatch, capsys):
    fake = FakeQdrant([("p1", _bare())])
    fake.install(monkeypatch)
    verdicts = _write_jsonl(tmp_path / "v.jsonl", [_verdict()])
    code = backfill.main(
        _args(
            tmp_path,
            verdicts,
            None,
            "--apply",
            "--snapshot",
            "snap-1",
            "--rollback-out",
            str(tmp_path / "rollback.json"),
        )
    )
    assert code == 2
    assert fake.writes == []
    assert "before-out" in capsys.readouterr().err


def test_the_before_export_is_complete_and_its_hash_is_in_the_report(tmp_path, monkeypatch):
    points = [("p1", _bare()), ("p2", _bare("span-2", video_id="vid2"))]
    FakeQdrant(points).install(monkeypatch)
    verdicts = _write_jsonl(
        tmp_path / "v.jsonl", [_verdict(), _verdict(source_span_id="span-2", point_id="p2")]
    )
    windows = _write_jsonl(tmp_path / "w.jsonl", [_window(), _window(source_span_id="span-2")])

    assert backfill.main(_apply_args(tmp_path, verdicts, windows)) == 0
    report = json.loads((tmp_path / "report.json").read_text())
    export = report["before_export"]
    data = (tmp_path / "before.jsonl").read_bytes()
    import hashlib

    assert export["sha256"] == hashlib.sha256(data).hexdigest()
    assert export["points"] == 2
    exported = [json.loads(line) for line in data.decode().splitlines()]
    assert [row["id"] for row in exported] == ["p1", "p2"]
    # The export is the state BEFORE any write.
    assert exported[0]["payload"].get("voice_verification_method") is None


# ---------------------------------------------------------------------------
# P5: post-checks (pure)
# ---------------------------------------------------------------------------
def _pts(**over):
    base = _payload(voice_verification_method="ecapa_voxceleb_centroid_v1")
    base.update(over)
    return [("p1", base)]


def test_post_checks_pass_on_an_allowlisted_change():
    before = _pts()
    after = _pts(voice_score=0.7, speaker_verification_status="verified")
    result = backfill.post_checks(before, after, {"p1": [1, 2]}, {"p1": [1, 2]})
    assert result["all_ok"] is True


def test_post_checks_catch_a_changed_point_count():
    result = backfill.post_checks(_pts(), [], {}, {})
    assert result["checks"]["points_unchanged"]["ok"] is False
    assert result["all_ok"] is False


def test_post_checks_catch_an_added_point():
    after = _pts() + [("p2", _payload(source_span_id="span-2"))]
    result = backfill.post_checks(_pts(), after, {}, {})
    assert result["checks"]["points_unchanged"]["added_after"] == ["p2"]
    assert result["all_ok"] is False


@pytest.mark.parametrize(
    "key", ["verbatim_text", "source_transcript_text", "transcript_hash", "source_text_hash"]
)
def test_post_checks_catch_a_changed_text_or_hash(key):
    before = _pts(**{key: "old"})
    after = _pts(**{key: "new"})
    result = backfill.post_checks(before, after, {}, {})
    assert result["checks"]["immutable_keys_unchanged"]["ok"] is False
    assert result["checks"]["only_allowlisted_keys_changed"]["ok"] is False
    assert result["all_ok"] is False


def test_post_checks_catch_a_change_to_a_key_outside_the_allowlist():
    result = backfill.post_checks(_pts(), _pts(video_id="other"), {}, {})
    assert result["checks"]["only_allowlisted_keys_changed"]["ok"] is False


def test_post_checks_catch_a_changed_vector():
    result = backfill.post_checks(_pts(), _pts(), {"p1": [1, 2]}, {"p1": [1, 3]})
    assert result["checks"]["vectors_identical_on_sample"]["ok"] is False
    assert result["checks"]["vectors_identical_on_sample"]["different"] == ["p1"]


def test_post_checks_catch_a_missing_vector_after():
    result = backfill.post_checks(_pts(), _pts(), {"p1": [1, 2]}, {})
    assert result["checks"]["vectors_identical_on_sample"]["ok"] is False


def test_post_checks_count_remaining_violators_by_reason():
    after = _pts(voice_verification_method=None)
    result = backfill.post_checks(_pts(), after, {}, {})
    check = result["checks"]["violators_zero"]
    assert check["ok"] is False
    assert check["violators"] == 1
    assert check["by_first_reason"] == {"speaker_verified_without_method": 1}
    assert result["all_ok"] is False


def test_post_checks_ignore_parent_records_when_counting_violators():
    parent = [("pp", {"record_type": "parent_unit", "speaker_verified": True})]
    assert backfill.post_checks(parent, parent, {}, {})["checks"]["violators_zero"]["ok"] is True


# ---------------------------------------------------------------------------
# End to end: the post-check fails the run when a span is left unresolved
# ---------------------------------------------------------------------------
def test_a_no_evidence_span_leaves_a_violator_and_the_run_exits_one(tmp_path, monkeypatch):
    fake = FakeQdrant([("p1", _bare()), ("p2", _bare("span-2", video_id="vid2"))])
    fake.install(monkeypatch)
    verdicts = _write_jsonl(tmp_path / "v.jsonl", [_verdict()])  # none for span-2
    windows = _write_jsonl(tmp_path / "w.jsonl", [_window()])

    code = backfill.main(_apply_args(tmp_path, verdicts, windows))

    assert code == 1
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["written"] == 1
    check = report["post_checks"]["checks"]["violators_zero"]
    assert check["violators"] == 1
    assert check["examples"] == ["span-2"]


def test_demote_no_evidence_resolves_them_and_the_run_is_clean(tmp_path, monkeypatch):
    fake = FakeQdrant([("p1", _bare()), ("p2", _bare("span-2", video_id="vid2"))])
    fake.install(monkeypatch)
    verdicts = _write_jsonl(tmp_path / "v.jsonl", [_verdict()])
    windows = _write_jsonl(tmp_path / "w.jsonl", [_window()])

    code = backfill.main(_apply_args(tmp_path, verdicts, windows, "--demote-no-evidence"))

    assert code == 0
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["outcomes"] == {"pass": 1, "demoted_no_evidence": 1}
    assert fake.points["p2"]["speaker_verified"] is False
    assert fake.points["p2"]["speaker_verification_status"] == "pending_voice_check"
    # Demotion never invents a method.
    assert not fake.points["p2"].get("voice_verification_method")


def test_a_vector_changed_by_the_writes_fails_the_run(tmp_path, monkeypatch):
    fake = FakeQdrant([("p1", _bare())])
    fake.install(monkeypatch)
    calls = {"n": 0}

    def drifting(_url, _coll, ids):
        calls["n"] += 1
        return {pid: [calls["n"]] for pid in ids}  # differs between the two reads

    monkeypatch.setattr(backfill, "_fetch_vectors", drifting)
    verdicts = _write_jsonl(tmp_path / "v.jsonl", [_verdict()])
    windows = _write_jsonl(tmp_path / "w.jsonl", [_window()])

    assert backfill.main(_apply_args(tmp_path, verdicts, windows)) == 1
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["post_checks"]["checks"]["vectors_identical_on_sample"]["ok"] is False


def test_the_backfilled_payload_still_loads_into_the_span_model():
    """Regression: the first version of this writer used a nested ``voice_verdict`` key that
    SourceSpan (extra='forbid') rejects, which would have made every touched parent unreadable.
    """
    from domain.first_person_context import (
        BoundaryStatus,
        CompletenessStatus,
        SourceSpan,
        SpeakerRole,
        clip_text_hash,
        make_source_span_id,
    )

    text = "hold the intention to live free from fear and walk with steady grace today"
    transcript_hash = "b" * 64
    span_id = make_source_span_id(
        guru_id="krishnaji",
        video_id="vid1",
        corpus_version="fp-context-v1",
        word_start=0,
        word_end=13,
        transcript_hash=transcript_hash,
    )
    payload = {
        "schema_version": "fp-context-v1",
        "corpus_version": "fp-context-v1",
        "guru_id": "krishnaji",
        "video_id": "vid1",
        "source_asset_id": "vid1",
        "source_span_id": span_id,
        "parent_unit_id": "parentA",
        "turn_id": "t0",
        "turn_index": 0,
        "source_span_index": 0,
        "start_ms": 0,
        "end_ms": 9000,
        "word_start": 0,
        "word_end": 13,
        "speaker_id": "krishnaji",
        "speaker_role": SpeakerRole.GURU.value,
        "speaker_verified": True,
        "voice_verification_method": None,
        "source_transcript_text": text,
        "verbatim_text": text,
        "transcript_hash": transcript_hash,
        "source_text_hash": clip_text_hash(text),
        "is_verbatim": True,
        "boundary_status": BoundaryStatus.VERIFIED.value,
        "completeness_status": CompletenessStatus.COMPLETE.value,
        "rights_cleared": True,
        "caption_status": "auto",
        "source_url": "https://www.youtube.com/watch?v=vid1",
    }
    for verdict, window in (
        (_verdict(source_span_id=span_id), _window(source_span_id=span_id)),
        (
            _verdict(source_span_id=span_id, verdict="refused_guru_mismatch"),
            _window(source_span_id=span_id),
        ),
    ):
        outcome, updates = backfill.decide(payload, verdict, window, now=NOW)
        assert outcome in ("pass", "fail")
        merged = {**payload, **updates}
        SourceSpan.model_validate(merged)


# ----------------------------------------------------------------- D4: snapshot check


def _listing(name, age_s):
    created = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=age_s)
    return [{"name": name, "creation_time": created.replace(tzinfo=None).isoformat()}]


def test_snapshot_problem_accepts_a_listed_fresh_snapshot():
    now = dt.datetime.now(dt.UTC)
    assert backfill.snapshot_problem("s1", _listing("s1", 60), now=now) is None


def test_snapshot_problem_refuses_unknown_stale_and_unreadable_snapshots():
    now = dt.datetime.now(dt.UTC)
    assert "not in the collection" in backfill.snapshot_problem("nope", _listing("s1", 60), now=now)
    assert "min old" in backfill.snapshot_problem("s1", _listing("s1", 3 * 3600), now=now)
    assert "creation_time" in backfill.snapshot_problem(
        "s1", [{"name": "s1", "creation_time": "not a date"}], now=now
    )
    assert "creation_time" in backfill.snapshot_problem("s1", [{"name": "s1"}], now=now)
    future = _listing("s1", -3600)
    assert "future" in backfill.snapshot_problem("s1", future, now=now)


def test_apply_with_an_unknown_snapshot_name_exits_two_and_writes_nothing(tmp_path, monkeypatch):
    fake = FakeQdrant([("p1", _payload())])
    fake.install(monkeypatch)
    fake.snapshots = []  # the server lists no such snapshot
    verdicts = _write_jsonl(tmp_path / "v.jsonl", [_verdict()])
    windows = _write_jsonl(tmp_path / "w.jsonl", [_window()])
    assert backfill.main(_apply_args(tmp_path, verdicts, windows)) == 2
    assert fake.writes == []


def test_apply_with_a_stale_snapshot_exits_two_and_writes_nothing(tmp_path, monkeypatch):
    fake = FakeQdrant([("p1", _payload())])
    fake.install(monkeypatch)
    fake.snapshots = _listing("first_person_v10-snap-1.snapshot", 3 * 3600)
    verdicts = _write_jsonl(tmp_path / "v.jsonl", [_verdict()])
    windows = _write_jsonl(tmp_path / "w.jsonl", [_window()])
    assert backfill.main(_apply_args(tmp_path, verdicts, windows)) == 2
    assert fake.writes == []


def test_apply_fails_closed_when_the_snapshot_list_cannot_be_read(tmp_path, monkeypatch):
    fake = FakeQdrant([("p1", _payload())])
    fake.install(monkeypatch)

    def boom(*_a, **_k):
        raise ConnectionError("qdrant down")

    monkeypatch.setattr(backfill, "_list_snapshots", boom)
    verdicts = _write_jsonl(tmp_path / "v.jsonl", [_verdict()])
    windows = _write_jsonl(tmp_path / "w.jsonl", [_window()])
    assert backfill.main(_apply_args(tmp_path, verdicts, windows)) == 2
    assert fake.writes == []
