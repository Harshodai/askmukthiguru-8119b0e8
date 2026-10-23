"""Focused tests for ``scripts.ops.reconcile_v10_ecapa_verdicts``.

The script is the read-only Phase-1 gate for first-person blocker **B1**
(per-span ECAPA evidence). These tests pin:

* every match class in the documented taxonomy;
* the fail-closed behaviour for malformed / conflicting input;
* the guarantee that exactly one row is emitted per v10 child;
* byte-identical repeated output;
* that the script can never mutate Qdrant or a source manifest.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve()
if _HERE.parents[1].name == "app" or _HERE.parents[1] == Path("/app"):
    _BACKEND = Path("/app")
else:
    _BACKEND = _HERE.parents[1]
_REPO_ROOT = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from scripts.ops import reconcile_v10_ecapa_verdicts as recon  # noqa: E402

SCRIPT_PATH = _BACKEND / "scripts" / "ops" / "reconcile_v10_ecapa_verdicts.py"


# ---------------------------------------------------------------------------
# Fixtures / builders
# ---------------------------------------------------------------------------
def _span(
    *,
    span_id: str = "span-1",
    point_id: str = "point-1",
    video_id: str = "vid-1",
    text: str = "Today I want you to hold the intention to live free.",
    start_ms: int = 1000,
    end_ms: int = 4000,
    word_start: int = 0,
    word_end: int = 9,
    declared_hash: str | None = None,
    source_url: str = "https://www.youtube.com/watch?v=vid-1",
) -> dict:
    payload = {
        "record_type": "retrieval_child",
        "source_span_id": span_id,
        "video_id": video_id,
        "source_asset_id": video_id,
        "guru_id": "krishnaji",
        "verbatim_text": text,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "word_start": word_start,
        "word_end": word_end,
        "source_text_hash": declared_hash
        if declared_hash is not None
        else recon.clip_text_hash(text),
        "source_url": source_url,
    }
    return {"id": point_id, "payload": payload}


def _legacy(
    *,
    point_id: str = "legacy-1",
    video_id: str = "vid-1",
    text: str = "Today I want you to hold the intention to live free.",
    start_ms: int = 1000,
    end_ms: int = 4000,
    declared_hash: str | None = None,
    source_url: str = "https://www.youtube.com/watch?v=vid-1",
) -> dict:
    payload = {
        "video_id": video_id,
        "verbatim_text": text,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "transcript_hash": declared_hash
        if declared_hash is not None
        else recon.clip_text_hash(text),
        "teacher_id": "krishnaji",
        "source_url": source_url,
    }
    return {"id": point_id, "payload": payload}


def _verdict_record(
    *,
    verified: bool = True,
    method: str = "ecapa_voxceleb_centroid_v1",
    cosine: float = 0.91,
    margin: float = 0.72,
) -> dict:
    return {
        "verified": verified,
        "method": method,
        "cosine": cosine,
        "margin": margin,
        "predicted_guru": "krishnaji",
        "payload_guru": "krishnaji",
    }


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8"
    )
    return path


def _write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _run(
    tmp_path: Path,
    v10_rows: list[dict],
    legacy_rows: list[dict],
    verdicts: dict,
    *,
    asr_manifest: dict | None = None,
    policy: str = "release_grade",
    extra_args: list[str] | None = None,
    tag: str = "",
) -> tuple[int, list[dict], dict]:
    v10_file = _write_jsonl(tmp_path / "v10.jsonl", v10_rows)
    legacy_file = _write_json(tmp_path / "legacy.json", {"result": {"points": legacy_rows}})
    verdict_file = _write_json(tmp_path / "verdicts.json", verdicts)
    out = tmp_path / f"out{tag}.jsonl"
    summary_path = tmp_path / f"summary{tag}.json"
    argv = [
        "--v10-points",
        str(v10_file),
        "--legacy-points",
        str(legacy_file),
        "--verdicts",
        str(verdict_file),
        "--out",
        str(out),
        "--summary",
        str(summary_path),
        "--verdict-schema-policy",
        policy,
        "--generated-at-utc",
        "2026-10-21T00:00:00+00:00",
    ]
    if asr_manifest is not None:
        manifest_file = _write_json(tmp_path / "asr.json", asr_manifest)
        argv += ["--asr-manifest", str(manifest_file)]
    if extra_args:
        argv += extra_args
    code = recon.main(argv)
    rows = []
    if out.is_file():
        rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines() if line]
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else {}
    return code, rows, summary


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------
def test_normalization_is_versioned_and_matches_the_builder():
    """``fp-norm-v1`` must not drift from the corpus builder's normalizer."""
    builder = None
    for candidate in (
        _BACKEND / "scripts" / "ops" / "build_fp_context_from_v9.py",
        _REPO_ROOT / "scripts" / "ops" / "build_fp_context_from_v9.py",
    ):
        if candidate.is_file():
            builder = candidate
            break
    if builder is None:  # pragma: no cover - the builder is always present
        pytest.skip("build_fp_context_from_v9.py not found")
    import importlib.util

    spec = importlib.util.spec_from_file_location("_fp_builder", builder)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    samples = [
        "Today, I want you to hold the intention.",
        "40,000 people -- really!",
        "Shri Krishnaji and Preetha Ji",
        "Hello, world.",
        "",
    ]
    for sample in samples:
        assert recon.normalize_text(sample) == module._norm(sample)


def test_normalization_is_ascii_only_and_marks_unverifiable_text():
    assert recon.normalize_text("नमस्ते") == ""
    assert recon.normalize_text("Hello") == "hello"


# ---------------------------------------------------------------------------
# Match classes
# ---------------------------------------------------------------------------
def test_exact_span_id_match(tmp_path):
    span = _span(span_id="span-abc")
    code, rows, summary = _run(
        tmp_path,
        [span],
        [_legacy()],
        {"items": {"span-abc": _verdict_record()}},
    )
    assert code == recon.EXIT_RELEASE_BLOCKED
    assert len(rows) == 1
    assert rows[0]["match_class"] == recon.MATCH_EXACT_SPAN_ID
    assert rows[0]["verdict_key"] == "span-abc"
    assert summary["match_class_counts"][recon.MATCH_EXACT_SPAN_ID] == 1
    assert summary["direct_span_id_coverage"]["v10_source_span_ids_present_in_verdict_file"] == 1


def test_exact_point_id_match(tmp_path):
    span = _span(point_id="qdrant-uuid-1")
    code, rows, summary = _run(
        tmp_path,
        [span],
        [_legacy()],
        {"items": {"qdrant-uuid-1": _verdict_record()}},
    )
    assert code == recon.EXIT_RELEASE_BLOCKED
    assert rows[0]["match_class"] == recon.MATCH_EXACT_POINT_ID
    assert summary["direct_point_id_coverage"]["v10_qdrant_point_ids_present_in_verdict_file"] == 1


def test_unique_legacy_identity_match(tmp_path):
    code, rows, summary = _run(
        tmp_path,
        [_span()],
        [_legacy()],
        {"items": {"legacy-1": _verdict_record()}},
        policy="legacy_v1",
    )
    assert code == recon.EXIT_RELEASE_BLOCKED
    row = rows[0]
    assert row["match_class"] == recon.MATCH_UNIQUE_IDENTITY
    assert row["legacy_point_id"] == "legacy-1"
    assert row["candidate_count"] == 1
    assert row["identity_join_ok"] is True
    assert row["safe_to_upgrade"] is True
    assert row["safe_to_upgrade_blockers"] == []
    assert summary["safe_to_upgrade"]["count"] == 1
    assert summary["legacy_identity_coverage"]["unique_legacy_points_resolved"] == 1


def test_duplicate_identity_is_ambiguous_and_never_upgradable(tmp_path):
    code, rows, summary = _run(
        tmp_path,
        [_span()],
        [_legacy(point_id="legacy-a"), _legacy(point_id="legacy-b")],
        {"items": {"legacy-a": _verdict_record()}},
        policy="legacy_v1",
    )
    assert code == recon.EXIT_RELEASE_BLOCKED
    assert rows[0]["match_class"] == recon.MATCH_AMBIGUOUS_IDENTITY
    assert rows[0]["candidate_count"] == 2
    assert rows[0]["safe_to_upgrade"] is False
    assert "match_class:ambiguous_identity_match" in rows[0]["safe_to_upgrade_blockers"]
    assert summary["ambiguous_count"] == 1


def test_text_hash_mismatch_is_an_identity_conflict(tmp_path):
    code, rows, summary = _run(
        tmp_path,
        [_span(text="A completely different sentence from the archive.")],
        [_legacy()],
        {"items": {"legacy-1": _verdict_record()}},
        policy="legacy_v1",
    )
    assert code == recon.EXIT_RELEASE_BLOCKED
    assert rows[0]["match_class"] == recon.MATCH_IDENTITY_CONFLICT
    assert rows[0]["reason"] == "text_hash_mismatch"
    assert rows[0]["safe_to_upgrade"] is False
    assert summary["conflicting_count"] == 1


def test_time_bound_mismatch_is_an_identity_conflict(tmp_path):
    code, rows, summary = _run(
        tmp_path,
        [_span(start_ms=1000, end_ms=9000)],
        [_legacy(start_ms=1000, end_ms=4000)],
        {"items": {"legacy-1": _verdict_record()}},
        policy="legacy_v1",
    )
    assert code == recon.EXIT_RELEASE_BLOCKED
    assert rows[0]["match_class"] == recon.MATCH_IDENTITY_CONFLICT
    assert rows[0]["reason"] == "time_bound_mismatch"
    assert "end_ms" in rows[0]["conflict_fields"]
    assert summary["conflicting_count"] == 1


def test_missing_verdict_for_a_matched_legacy_point(tmp_path):
    code, rows, summary = _run(
        tmp_path,
        [_span()],
        [_legacy()],
        {"items": {}},
        policy="legacy_v1",
    )
    assert code == recon.EXIT_RELEASE_BLOCKED
    assert rows[0]["match_class"] == recon.MATCH_MISSING_VERDICT
    assert rows[0]["legacy_point_id"] == "legacy-1"
    assert rows[0]["verdict"] is None
    assert rows[0]["safe_to_upgrade"] is False
    assert summary["match_class_counts"][recon.MATCH_MISSING_VERDICT] == 1
    assert summary["verdict_coverage"]["spans_without_any_verdict"] == 1


def test_missing_legacy_point(tmp_path):
    code, rows, summary = _run(
        tmp_path,
        [_span(video_id="vid-unknown")],
        [_legacy()],
        {"items": {"legacy-1": _verdict_record()}},
        policy="legacy_v1",
    )
    assert code == recon.EXIT_RELEASE_BLOCKED
    assert rows[0]["match_class"] == recon.MATCH_MISSING_LEGACY_POINT
    assert rows[0]["legacy_point_id"] is None
    assert summary["match_class_counts"][recon.MATCH_MISSING_LEGACY_POINT] == 1


def test_malformed_verdict_is_quarantined_and_not_upgradable(tmp_path):
    code, rows, summary = _run(
        tmp_path,
        [_span()],
        [_legacy()],
        {"items": {"legacy-1": {"verified": "yes", "cosine": "not-a-number"}}},
        policy="legacy_v1",
    )
    assert code == recon.EXIT_RELEASE_BLOCKED
    assert rows[0]["match_class"] == recon.MATCH_INVALID_INPUT
    assert rows[0]["verdict_malformed"] is True
    assert rows[0]["safe_to_upgrade"] is False
    assert summary["totals"]["malformed_verdict_records"] == 1
    assert summary["verdict_coverage"]["spans_with_any_verdict"] == 0
    assert summary["invalid_count"] == 1


def test_malformed_verdict_record_survives_as_a_structured_entry(tmp_path):
    """A malformed record must be reported, not silently dropped."""
    verdicts_file = _write_json(
        tmp_path / "verdicts.json", {"items": {"legacy-1": "not-an-object"}}
    )
    v10_file = _write_jsonl(tmp_path / "v10.jsonl", [_span()])
    legacy_file = _write_json(tmp_path / "legacy.json", {"result": {"points": [_legacy()]}})
    out = tmp_path / "out.jsonl"
    summary_path = tmp_path / "summary.json"
    code = recon.main(
        [
            "--v10-points",
            str(v10_file),
            "--legacy-points",
            str(legacy_file),
            "--verdicts",
            str(verdicts_file),
            "--out",
            str(out),
            "--summary",
            str(summary_path),
        ]
    )
    assert code == recon.EXIT_RELEASE_BLOCKED
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines() if line]
    assert len(rows) == 1
    assert rows[0]["match_class"] == recon.MATCH_INVALID_INPUT


# ---------------------------------------------------------------------------
# Completeness / determinism
# ---------------------------------------------------------------------------
def test_every_v10_child_produces_exactly_one_row(tmp_path):
    spans = [
        _span(span_id=f"span-{index}", point_id=f"point-{index}", video_id=f"vid-{index}")
        for index in range(7)
    ]
    code, rows, summary = _run(tmp_path, spans, [_legacy()], {"items": {}})
    assert code == recon.EXIT_RELEASE_BLOCKED
    assert len(rows) == len(spans)
    assert summary["totals"]["rows_emitted"] == len(spans)
    assert summary["totals"]["v10_children"] == len(spans)
    span_ids = [row["source_span_id"] for row in rows]
    assert sorted(span_ids) == sorted(f"span-{index}" for index in range(7))
    assert len(set(span_ids)) == len(span_ids)


def test_repeated_runs_are_byte_identical(tmp_path):
    """Same inputs, same paths, two runs -> byte-identical artifacts."""
    spans = [_span(span_id="span-1"), _span(span_id="span-2", point_id="p2", video_id="v2")]
    _run(tmp_path, spans, [_legacy()], {"items": {"legacy-1": _verdict_record()}}, tag="_a")
    _run(tmp_path, spans, [_legacy()], {"items": {"legacy-1": _verdict_record()}}, tag="_b")
    assert (tmp_path / "out_a.jsonl").read_bytes() == (tmp_path / "out_b.jsonl").read_bytes()
    assert (tmp_path / "summary_a.json").read_bytes() == (tmp_path / "summary_b.json").read_bytes()


def test_summary_is_stable_apart_from_the_timestamp(tmp_path):
    spans = [_span()]
    _run(tmp_path, spans, [_legacy()], {"items": {}}, tag="_a")
    v10_file = _write_jsonl(tmp_path / "v10.jsonl", spans)
    legacy_file = _write_json(tmp_path / "legacy.json", {"result": {"points": [_legacy()]}})
    verdict_file = _write_json(tmp_path / "verdicts.json", {"items": {}})
    recon.main(
        [
            "--v10-points",
            str(v10_file),
            "--legacy-points",
            str(legacy_file),
            "--verdicts",
            str(verdict_file),
            "--out",
            str(tmp_path / "out_b.jsonl"),
            "--summary",
            str(tmp_path / "summary_b.json"),
        ]
    )
    one = json.loads((tmp_path / "summary_a.json").read_text(encoding="utf-8"))
    two = json.loads((tmp_path / "summary_b.json").read_text(encoding="utf-8"))
    assert one.pop("generated_at_utc") != two.pop("generated_at_utc")
    assert one == two


# ---------------------------------------------------------------------------
# Fail-closed behaviour
# ---------------------------------------------------------------------------
def test_unparseable_input_fails_closed(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    out = tmp_path / "out.jsonl"
    summary = tmp_path / "summary.json"
    code = recon.main(
        [
            "--v10-points",
            str(bad),
            "--legacy-points",
            str(bad),
            "--verdicts",
            str(bad),
            "--out",
            str(out),
            "--summary",
            str(summary),
        ]
    )
    assert code == recon.EXIT_INVALID_INPUT
    assert not out.exists()
    assert not summary.exists()


def test_duplicate_point_ids_in_an_export_fail_closed(tmp_path):
    v10_file = _write_jsonl(tmp_path / "v10.jsonl", [_span(), _span()])
    legacy_file = _write_json(tmp_path / "legacy.json", {"result": {"points": []}})
    verdict_file = _write_json(tmp_path / "verdicts.json", {"items": {}})
    code = recon.main(
        [
            "--v10-points",
            str(v10_file),
            "--legacy-points",
            str(legacy_file),
            "--verdicts",
            str(verdict_file),
            "--out",
            str(tmp_path / "out.jsonl"),
            "--summary",
            str(tmp_path / "summary.json"),
        ]
    )
    assert code == recon.EXIT_INVALID_INPUT


def test_write_mode_is_refused(tmp_path):
    for flag in ("--apply-upgrades", "--write-mode"):
        code = recon.main([flag, "--legacy-points", "x", "--verdicts", "y", "--out", "z", "--summary", "s"])
        assert code == recon.EXIT_INVALID_INPUT


def test_missing_v10_points_argument_is_refused(tmp_path):
    code = recon.main(
        [
            "--legacy-points",
            "x",
            "--verdicts",
            "y",
            "--out",
            str(tmp_path / "o.jsonl"),
            "--summary",
            str(tmp_path / "s.json"),
        ]
    )
    assert code == recon.EXIT_INVALID_INPUT


# ---------------------------------------------------------------------------
# Release-grade verdict schema
# ---------------------------------------------------------------------------
def test_release_grade_policy_rejects_a_legacy_archive(tmp_path):
    """The archived legacy verdict file must never pass the release gate."""
    code, rows, summary = _run(
        tmp_path,
        [_span()],
        [_legacy()],
        {"items": {"legacy-1": _verdict_record()}},
        policy="release_grade",
    )
    assert code == recon.EXIT_RELEASE_BLOCKED
    row = rows[0]
    assert row["identity_join_ok"] is True
    assert row["safe_to_upgrade"] is False
    problems = row["verdict_schema_problems"]
    assert "missing_provenance:model_revision" in problems
    assert "missing_provenance:calibration_revision" in problems
    assert "missing_provenance:audio_sha256" in problems
    assert "missing_archive_provenance:calibration_available" in problems
    assert summary["safe_to_upgrade"]["count"] == 0


def test_release_grade_policy_accepts_a_complete_verdict(tmp_path):
    record = dict(_verdict_record())
    record.update(
        {
            "model_revision": "ecapa-0f99f2d0",
            "calibration_revision": "cal-2026-10-21",
            "source_span_id": "span-1",
            "audio_sha256": "a" * 64,
            "start_ms": 1000,
            "end_ms": 4000,
            "cosine_floor": 0.41,
            "margin_threshold": 0.12,
            "timestamp": "2026-10-21T00:00:00+00:00",
        }
    )
    code, rows, summary = _run(
        tmp_path,
        [_span()],
        [_legacy()],
        {
            "items": {"legacy-1": record},
            "calibration_available": True,
            "cosine_floor": 0.41,
            "margin_threshold": 0.12,
        },
        policy="release_grade",
    )
    assert rows[0]["safe_to_upgrade"] is True
    assert summary["safe_to_upgrade"]["count"] == 1


# ---------------------------------------------------------------------------
# ASR manifest cross-check
# ---------------------------------------------------------------------------
def test_asr_manifest_window_mismatch_blocks_upgrade(tmp_path):
    manifest = {
        "span-1": {
            "audio_start_ms": 1000,
            "audio_end_ms": 4000,
            "alignment_ok": True,
        }
    }
    code, rows, summary = _run(
        tmp_path,
        [_span()],
        [_legacy()],
        {"items": {"legacy-1": _verdict_record()}},
        asr_manifest=manifest,
        policy="legacy_v1",
    )
    assert rows[0]["asr_manifest_check"] == "pass"
    assert rows[0]["safe_to_upgrade"] is True

    bad_manifest = {
        "span-1": {"audio_start_ms": 5, "audio_end_ms": 9, "alignment_ok": True}
    }
    code, rows, summary = _run(
        tmp_path,
        [_span()],
        [_legacy()],
        {"items": {"legacy-1": _verdict_record()}},
        asr_manifest=bad_manifest,
        policy="legacy_v1",
    )
    assert rows[0]["asr_manifest_check"] == "asr_manifest_window_mismatch"
    assert rows[0]["safe_to_upgrade"] is False


# ---------------------------------------------------------------------------
# Read-only guarantees
# ---------------------------------------------------------------------------
def test_script_source_contains_no_qdrant_mutation():
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "/points/upsert",
        "/points/delete",
        "/points/payload",
        "/aliases",
        "/snapshots",
        "method=\"PUT\"",
        "method=\"DELETE\"",
        "method=\"PATCH\"",
        "qdrant_client",
        "upsert(",
        "delete_collection",
        "update_collection",
    ):
        assert forbidden not in source, f"reconciliation script must not contain {forbidden!r}"


def test_qdrant_access_is_read_only_scroll_only(tmp_path, monkeypatch):
    """The only network call the script can make is a scroll."""
    calls: list[tuple[str, str]] = []

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"result": {"points": [], "next_page_offset": None}}).encode("utf-8")

    def _fake_urlopen(request, timeout=None):
        calls.append((request.get_method(), request.full_url))
        return _Response()

    monkeypatch.setattr(recon.urllib.request, "urlopen", _fake_urlopen)
    recon._qdrant_scroll("http://localhost:6333", "first_person_v10")
    assert calls
    for method, url in calls:
        assert method == "POST"
        assert url.endswith("/collections/first_person_v10/points/scroll")


def test_file_input_performs_no_network_access(tmp_path, monkeypatch):
    def _boom(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("the file-based path must not touch the network")

    monkeypatch.setattr(recon.urllib.request, "urlopen", _boom)
    code, rows, summary = _run(
        tmp_path,
        [_span()],
        [_legacy()],
        {"items": {"legacy-1": _verdict_record()}},
    )
    assert code == recon.EXIT_RELEASE_BLOCKED
    assert len(rows) == 1


def test_source_manifests_are_not_modified(tmp_path):
    v10_rows = [_span()]
    legacy_rows = [_legacy()]
    v10_file = _write_jsonl(tmp_path / "v10.jsonl", v10_rows)
    legacy_file = _write_json(tmp_path / "legacy.json", {"result": {"points": legacy_rows}})
    verdict_file = _write_json(tmp_path / "verdicts.json", {"items": {}})
    before = {
        path: path.read_bytes() for path in (v10_file, legacy_file, verdict_file)
    }
    recon.main(
        [
            "--v10-points",
            str(v10_file),
            "--legacy-points",
            str(legacy_file),
            "--verdicts",
            str(verdict_file),
            "--out",
            str(tmp_path / "out.jsonl"),
            "--summary",
            str(tmp_path / "summary.json"),
        ]
    )
    for path, payload in before.items():
        assert path.read_bytes() == payload


# ---------------------------------------------------------------------------
# CLI smoke test (real process, real exit code)
# ---------------------------------------------------------------------------
def test_cli_help_exits_zero():
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "reconcile" in result.stdout.lower()


def test_cli_missing_file_exits_non_zero(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--v10-points",
            str(tmp_path / "does-not-exist.jsonl"),
            "--legacy-points",
            str(tmp_path / "nope.json"),
            "--verdicts",
            str(tmp_path / "nope2.json"),
            "--out",
            str(tmp_path / "o.jsonl"),
            "--summary",
            str(tmp_path / "s.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == recon.EXIT_INVALID_INPUT
    assert "invalid_input" in result.stderr
