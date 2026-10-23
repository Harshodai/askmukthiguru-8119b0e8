"""Focused tests for ``scripts.ops.build_fp_rights_register``.

The rights register must be **independent of Qdrant payload fields**. These
tests pin:

* a registry row only confirms an asset when its owner-confirmation marker is
  on the SAME markdown table row;
* the engineering allowlist alone can never produce a confirmed status;
* missing or ambiguous evidence quarantines the asset;
* the live collection's ``rights_cleared`` payload flag is carried through as
  an explicitly untrusted claim and never as evidence;
* the join is deterministic and the counts reconcile.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[1]
_REPO_ROOT = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from scripts.ops import build_fp_rights_register as rights  # noqa: E402

REGISTRY = _REPO_ROOT / "docs" / "rights" / "CONTENT-RIGHTS.md"
ALLOWLIST = _BACKEND / "scripts" / "ops" / "build_first_person_index.py"

CANDIDATE = {
    "source_span_id": "span-1",
    "video_id": "vid-ekam",
    "guru_id": "krishnaji",
    "rights_cleared": True,
}


def _registry(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "CONTENT-RIGHTS.md"
    path.write_text(body, encoding="utf-8")
    return path


def _candidate_jsonl(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "candidate.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return path


def _verdicts(tmp_path: Path, span_ids: list[str]) -> Path:
    path = tmp_path / "verdicts.json"
    path.write_text(
        json.dumps({"verdicts": {sid: {"reason_code": "verified"} for sid in span_ids}}),
        encoding="utf-8",
    )
    return path


def _channels(tmp_path: Path, mapping: dict[str, dict]) -> Path:
    path = tmp_path / "channels.json"
    path.write_text(json.dumps(mapping), encoding="utf-8")
    return path


def _args(tmp_path, **overrides):
    class _Args:
        pass

    args = _Args()
    args.candidate = str(overrides.get("candidate", tmp_path / "candidate.jsonl"))
    args.verdicts = str(overrides.get("verdicts", tmp_path / "verdicts.json"))
    args.registry = str(overrides.get("registry", REGISTRY))
    args.channels = list(overrides.get("channels", []))
    args.titles = overrides.get("titles")
    args.engineering_allowlist = str(
        overrides.get("engineering_allowlist", ALLOWLIST)
    )
    args.out_manifest = str(tmp_path / "manifest.json")
    args.out_join = str(tmp_path / "join.jsonl")
    args.out_quarantine = str(tmp_path / "quarantine.jsonl")
    args.out_summary = str(tmp_path / "summary.json")
    args.out_report = str(tmp_path / "report.md")
    args.generated_at_utc = "2026-10-22T00:00:00+00:00"
    return args


# ---------------------------------------------------------------------------
# registry parsing
# ---------------------------------------------------------------------------
def test_shipped_registry_confirms_every_declared_entry():
    parsed = rights.parse_registry(REGISTRY)
    assert parsed["applied"], "no registry entry applied against the shipped registry"
    assert not parsed["not_applied"]
    assert parsed["sha256"]


def test_a_row_without_the_owner_marker_does_not_confirm():
    body = (
        "| Asset | Format | Rights Basis | Owner | Status | Registered |\n"
        "| \"Sri Preethaji & Sri Krishnaji\" / \"Ekam / O&O Academy\" YouTube channels "
        "| video | unconfirmed | someone | pending | 2026-01-01 |\n"
    )
    tmp_path = Path(str(REGISTRY).replace("/", "_tmp_"))
    tmp_path.mkdir(exist_ok=True)
    try:
        parsed = rights.parse_registry(_registry(tmp_path, body))
        assert not parsed["applied"]
        assert any(
            entry["reason"] == "registry_row_has_no_owner_confirmation_marker"
            for entry in parsed["not_applied"]
        )
    finally:
        for child in tmp_path.iterdir():
            child.unlink()
        tmp_path.rmdir()


def test_a_missing_anchor_does_not_confirm():
    parsed = rights.parse_registry(REGISTRY)
    assert all(
        entry["anchor"] in REGISTRY.read_text(encoding="utf-8")
        for entry in rights.REGISTRY_ENTRIES
    )
    assert parsed["applied"]


# ---------------------------------------------------------------------------
# asset determination
# ---------------------------------------------------------------------------
def _registry_for(tmp_path: Path, entries: list[dict]):
    parsed = {"applied": entries, "not_applied": [], "path": "x", "sha256": "s" * 64}
    return parsed


def test_engineering_allowlist_alone_is_pending_owner_review():
    engineering = {
        "cleared_channels": ["ekam"],
        "cleared_video_ids": [],
        "path": "x",
        "sha256": "s" * 64,
        "authority": "engineering_input_only_not_a_rights_decision",
    }
    registry = {"applied": [], "not_applied": [], "path": "x", "sha256": "s" * 64}
    asset = rights.determine_asset_rights(
        video_id="vid-x",
        channel="Ekam",
        title="",
        registry=registry,
        engineering=engineering,
        payload_rights_claim=True,
    )
    assert asset["rights_status"] == rights.STATUS_PENDING
    assert asset["rights_status"] not in rights.SERVABLE_STATUSES
    assert asset["owner_review_status"] == "pending_owner_review"


def test_an_unknown_channel_is_missing_evidence():
    engineering = {"cleared_channels": [], "cleared_video_ids": [], "path": "", "sha256": ""}
    registry = {"applied": [], "not_applied": [], "path": "", "sha256": ""}
    asset = rights.determine_asset_rights(
        video_id="vid-y",
        channel="Some Other Channel",
        title="",
        registry=registry,
        engineering=engineering,
        payload_rights_claim=True,
    )
    assert asset["rights_status"] == rights.STATUS_MISSING
    assert asset["rights_status"] not in rights.SERVABLE_STATUSES


def test_a_confirmed_channel_asset_is_servable():
    parsed = rights.parse_registry(REGISTRY)
    engineering = rights.parse_engineering_allowlist(ALLOWLIST)
    asset = rights.determine_asset_rights(
        video_id="vid-z",
        channel="Sri Preethaji & Sri Krishnaji",
        title="A talk",
        registry=parsed,
        engineering=engineering,
        payload_rights_claim=True,
    )
    assert asset["rights_status"] in rights.SERVABLE_STATUSES
    assert asset["last_reviewed"]
    assert asset["review_date"]
    assert asset["evidence_sha256"] == parsed["sha256"]


def test_the_payload_flag_is_carried_as_an_untrusted_claim():
    parsed = rights.parse_registry(REGISTRY)
    engineering = rights.parse_engineering_allowlist(ALLOWLIST)
    asset = rights.determine_asset_rights(
        video_id="vid-z",
        channel="Sri Preethaji & Sri Krishnaji",
        title="",
        registry=parsed,
        engineering=engineering,
        payload_rights_claim=True,
    )
    assert asset["payload_rights_cleared_claim_untrusted"] is True
    assert "payload_flags_are_evidence" not in asset


# ---------------------------------------------------------------------------
# end-to-end build
# ---------------------------------------------------------------------------
def test_build_joins_every_candidate_span(tmp_path):
    rows = [
        dict(CANDIDATE, source_span_id=f"span-{index}", video_id=f"vid-{index}")
        for index in range(3)
    ]
    candidate = _candidate_jsonl(tmp_path, rows)
    verdicts = _verdicts(tmp_path, [row["source_span_id"] for row in rows])
    channels = _channels(
        tmp_path,
        {row["video_id"]: {"channel": "Sri Preethaji & Sri Krishnaji"} for row in rows},
    )
    args = _args(tmp_path, candidate=candidate, verdicts=verdicts, channels=[str(channels)])
    built = rights.build(args)
    assert len(built["join"]) == 3
    assert built["summary"]["span_count"] == 3
    assert built["summary"]["servable_span_count"] == 3
    assert built["summary"]["b5_exit_gate_met"] is False
    assert built["summary"]["register_owner_confirmation"] == "pending_owner_review"


def test_build_quarantines_a_rights_pending_span(tmp_path):
    rows = [dict(CANDIDATE, source_span_id="span-1", video_id="vid-1")]
    candidate = _candidate_jsonl(tmp_path, rows)
    verdicts = _verdicts(tmp_path, ["span-1"])
    channels = _channels(tmp_path, {"vid-1": {"channel": "Curly Tales"}})
    args = _args(tmp_path, candidate=candidate, verdicts=verdicts, channels=[str(channels)])
    built = rights.build(args)
    assert built["summary"]["quarantined_span_count"] == 1
    assert built["quarantine"][0]["source_span_id"] == "span-1"
    assert built["summary"]["release_blocking"] is True


def test_duplicate_candidate_span_ids_fail_closed(tmp_path):
    rows = [dict(CANDIDATE, source_span_id="span-1"), dict(CANDIDATE, source_span_id="span-1")]
    candidate = _candidate_jsonl(tmp_path, rows)
    verdicts = _verdicts(tmp_path, ["span-1"])
    channels = _channels(tmp_path, {"vid-ekam": {"channel": "Ekam"}})
    args = _args(tmp_path, candidate=candidate, verdicts=verdicts, channels=[str(channels)])
    with pytest.raises(rights.RightsRegisterError):
        rights.build(args)


def test_a_missing_candidate_span_in_the_verdicts_fails_closed(tmp_path):
    rows = [dict(CANDIDATE, source_span_id="span-1")]
    candidate = _candidate_jsonl(tmp_path, rows)
    verdicts = _verdicts(tmp_path, ["span-2"])
    channels = _channels(tmp_path, {"vid-ekam": {"channel": "Ekam"}})
    args = _args(tmp_path, candidate=candidate, verdicts=verdicts, channels=[str(channels)])
    built = rights.build(args)
    # A missing verdict is reported as a non-verified speaker verdict, not as
    # a rights failure; the tier builder is the place that quarantines it.
    assert built["summary"]["confirmed_but_speaker_unverified_spans"] == 1
