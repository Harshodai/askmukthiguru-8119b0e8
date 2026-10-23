"""Decision-validation tests for the first-person public-release gate.

The gate controller (``backend/scripts/ops/check_first_person_public_release.py``)
is the thing that stops an accidental promotion. These tests prove it fails
closed in every case the owner brief names:

* a missing owner decision blocks;
* a ``pending`` decision blocks;
* a partially decided speaker-conflict table blocks;
* approving rights without approving the speaker decision blocks;
* approving the clinician decision without the gold labels blocks;
* altered evidence hashes block;
* a variant approval cannot silently admit the deterministic-ID collision;
* changing one environment variable cannot enable public release;
* the alias cannot move without snapshot and rollback evidence;
* owner-only mode refuses to run in production;
* the public route stays safe while the harness is disabled.

Every test builds a **synthetic** repository tree in ``tmp_path`` and drives the
real controller against it. Nothing here reads or mutates Qdrant, Redis, an
alias, an environment variable or a deployment.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[1]
_REPO_ROOT = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from scripts.ops import check_first_person_public_release as gate  # noqa: E402

CONFIG_SCHEMA = "first-person-public-release-gate-v1"
DECISION_FENCE = "owner-decision"


# ---------------------------------------------------------------------------
# synthetic repository
# ---------------------------------------------------------------------------
def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8"
    )


def _decision_block(decision_id: str, **overrides: Any) -> str:
    payload: dict[str, Any] = {
        "decision_id": decision_id,
        "approved": "pending",
        "reviewer": "",
        "decision_date_utc": "",
        "signature": "",
        "notes": "",
    }
    payload.update(overrides)
    return "```json owner-decision\n" + json.dumps(payload, indent=2) + "\n```"


def _approved(decision_id: str, **overrides: Any) -> str:
    fields: dict[str, Any] = {
        "approved": "true",
        "reviewer": "Harsha",
        "decision_date_utc": "2026-10-22",
        "signature": "signed-by-Harsha",
    }
    fields.update(overrides)
    return _decision_block(decision_id, **fields)


def _conflicts(count: int) -> list[dict[str, Any]]:
    return [
        {
            "source_span_id": f"{index:064x}",
            "video_id": "vid",
            "expected_guru": "krishnaji",
            "predicted_guru": "preethaji",
        }
        for index in range(1, count + 1)
    ]


def _build_repo(tmp_path: Path) -> Path:
    """A complete, self-consistent synthetic repository the gate accepts."""
    root = tmp_path / "repo"
    evidence = root / "audits" / "evidence"
    evidence.mkdir(parents=True)

    served = [
        {
            "source_span_id": f"served-{index:04d}",
            "live_source_span_id": f"live-{index:04d}",
            "source_text_hash": f"text-{index:04d}",
            "audio_start_ms": 1000,
            "audio_end_ms": 5000,
            "video_id": "vid",
            "guru_id": "krishnaji",
            "text": "Meditation is a practice of awareness.",
        }
        for index in range(1, 4)
    ]
    review = [{"source_span_id": "review-0001", "live_source_span_id": "live-review"}]
    variant = [{"source_span_id": "variant-0001", "live_source_span_id": "live-variant"}]
    unlocatable = [{"source_span_id": "unloc-0001", "live_source_span_id": "live-unloc"}]
    collision = [{"source_span_id": "collision-0001", "live_source_span_id": "live-coll"}]

    tier_files = {
        "local_review_candidate": served,
        "review_required": review,
        "variant_candidate": variant,
        "unlocatable_quarantine": unlocatable,
        "deterministic_id_collision_quarantine": collision,
    }
    tier_meta: dict[str, Any] = {}
    for name, rows in tier_files.items():
        path = evidence / f"tier_{name}.jsonl"
        _write_jsonl(path, rows)
        tier_meta[name] = {
            "path": f"audits/evidence/tier_{name}.jsonl",
            "row_count": len(rows),
            "sha256": gate._sha256(path),
        }

    _write_json(
        evidence / "tiers_manifest.json",
        {
            "schema": "first-person-corpus-tiers-manifest-v2",
            "tier_counts": {name: len(rows) for name, rows in tier_files.items()},
            "tiers": tier_meta,
        },
    )

    _write_json(
        evidence / "verdicts.json",
        {
            "verdicts": {
                row["source_span_id"]: {
                    "source_span_id": row["source_span_id"],
                    "reason_code": "verified",
                    "source_text_hash": row["source_text_hash"],
                    "audio_start_ms": row["audio_start_ms"],
                    "audio_end_ms": row["audio_end_ms"],
                }
                for row in served
            }
        },
    )

    _write_jsonl(
        evidence / "rights_join.jsonl",
        [
            {
                "source_span_id": row["source_span_id"],
                "servable": True,
                "rights_status": "confirmed_channel_owner",
            }
            for row in served
        ],
    )
    _write_json(evidence / "rights_manifest.json", {"asset_count": 1, "assets": []})

    conflicts = _conflicts(2)
    _write_jsonl(evidence / "conflicts.jsonl", conflicts)
    _write_jsonl(
        evidence / "collisions.jsonl",
        [
            {
                "collided_source_span_id": "collision-0001",
                "member_count": 1,
                "members": [
                    {
                        "source_span_id": "collision-0001",
                        "live_source_span_id": "live-coll",
                    }
                ],
            }
        ],
    )

    contract = {
        "schema": "fp-serving-contract-v1",
        "collections": {
            "legacy_v1": {
                "schema": "first-person-legacy-clip-v1",
                "role": "legacy",
                "corpus_version": "legacy-clip-store",
                "required_payload_fields": ["first_person_eligible"],
                "evidence_policy": "payload_rights_claim_unverified",
            },
            "candidate_v2": {
                "schema": "fp-context-v1",
                "role": "context",
                "corpus_version": "fp-context-transcript-v2",
                "required_payload_fields": ["source_span_id"],
                "evidence_policy": "automated_evidence_candidate",
            },
        },
    }
    _write_json(root / "backend" / "config" / "first_person_serving_contract.json", contract)
    _write_json(root / "backend" / "config" / "first_person_local_review.json", {"schema": "x"})

    (root / "backend" / ".env").write_text(
        "FIRST_PERSON_COLLECTION=candidate_v2\n"
        "FIRST_PERSON_CONTEXT_COLLECTION=candidate_v2\n"
        "FIRST_PERSON_CONTEXT_HARNESS_ENABLED=false\n",
        encoding="utf-8",
    )

    _write_json(
        root / "audits" / "evidence" / "candidate_config.json",
        {
            "schema": "first-person-candidate-config-v1",
            "legacy_collection": "legacy_v1",
            "context_collection": "candidate_v2",
        },
    )

    for name in ("annotator_A.csv", "annotator_B.csv"):
        path = root / "evals" / "gold_set_v1" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "pair_id,speaker_label,speaker_is_teacher_yes_no_unsure,notes\n"
            "p1,Sri Preethaji,yes,\n",
            encoding="utf-8",
        )

    _write_json(
        evidence / "speaker_certification.json",
        {"schema": "x", "reviewers": ["A", "B"], "agreement_rate": 1.0},
    )
    _write_json(evidence / "gold_label_report.json", {"schema": "x", "rows": 300})
    _write_json(evidence / "agreement_calibration_report.json", {"schema": "x", "rate": 1.0})
    _write_json(
        evidence / "staging_readiness.json",
        {
            "schema": "x",
            "suites": {
                suite: {"status": "pass"} for suite in ("smoke", "safety", "citation", "cache", "fault")
            },
        },
    )

    config = {
        "schema": CONFIG_SCHEMA,
        "owner_decisions_path": "audits/evidence/owner_decisions.md",
        "env_file": "backend/.env",
        "evidence_dir": "audits/evidence",
        "artifacts": {
            "tiers_manifest": "audits/evidence/tiers_manifest.json",
            "served_tier": "audits/evidence/tier_local_review_candidate.jsonl",
            "variant_tier": "audits/evidence/tier_variant_candidate.jsonl",
            "unlocatable_tier": "audits/evidence/tier_unlocatable_quarantine.jsonl",
            "verdicts": "audits/evidence/verdicts.json",
            "rights_manifest": "audits/evidence/rights_manifest.json",
            "rights_join": "audits/evidence/rights_join.jsonl",
            "speaker_conflicts": "audits/evidence/conflicts.jsonl",
            "deterministic_id_collisions": "audits/evidence/collisions.jsonl",
            "serving_contract": "backend/config/first_person_serving_contract.json",
            "local_review_contract": "backend/config/first_person_local_review.json",
        },
        "pinned_artifacts": {
            "audits/evidence/tiers_manifest.json": gate._sha256(
                evidence / "tiers_manifest.json"
            ),
            "audits/evidence/verdicts.json": gate._sha256(evidence / "verdicts.json"),
            "audits/evidence/rights_manifest.json": gate._sha256(
                evidence / "rights_manifest.json"
            ),
            "audits/evidence/rights_join.jsonl": gate._sha256(evidence / "rights_join.jsonl"),
            "audits/evidence/conflicts.jsonl": gate._sha256(evidence / "conflicts.jsonl"),
            "audits/evidence/collisions.jsonl": gate._sha256(
                evidence / "collisions.jsonl"
            ),
            "backend/config/first_person_serving_contract.json": gate._sha256(
                root / "backend" / "config" / "first_person_serving_contract.json"
            ),
            "backend/config/first_person_local_review.json": gate._sha256(
                root / "backend" / "config" / "first_person_local_review.json"
            ),
        },
        "tier_expectations": {
            "tiers_manifest": "audits/evidence/tiers_manifest.json",
            "served_tier": "local_review_candidate",
            "row_counts": {
                "local_review_candidate": 3,
                "review_required": 1,
                "variant_candidate": 1,
                "unlocatable_quarantine": 1,
                "deterministic_id_collision_quarantine": 1,
            },
            "total_rows": 7,
            "speaker_conflict_rows": 2,
            "collision_members": ["live-coll"],
        },
        "decision_ids": [
            "b5_rights_register",
            "b5_speaker_conflict_rows",
            "b7_human_speaker_certification",
            "b7_variant_tier",
            "b6_clinician_safety",
            "b7_human_gold_labels",
            "b7_release_authorization",
        ],
        "decision_packet_map": {},
        "expected_evidence": {
            "speaker_certification": "audits/evidence/speaker_certification.json",
            "gold_label_report": "audits/evidence/gold_label_report.json",
            "agreement_calibration_report": "audits/evidence/agreement_calibration_report.json",
            "candidate_config": "audits/evidence/candidate_config.json",
            "staging_readiness": "audits/evidence/staging_readiness.json",
            "promotion_record": "audits/evidence/promotion.json",
        },
        "annotator_sheets": [
            "evals/gold_set_v1/annotator_A.csv",
            "evals/gold_set_v1/annotator_B.csv",
        ],
        "staging_suites": ["smoke", "safety", "citation", "cache", "fault"],
        "authorization_scopes": [
            "owner_only_testing",
            "isolated_local_candidate_collection",
            "staging",
            "public_production",
            "alias_promotion",
            "harness_enablement",
        ],
        "authorization_stage_1": [
            "owner_only_testing",
            "isolated_local_candidate_collection",
            "staging",
        ],
        "authorization_stage_2": ["public_production", "alias_promotion", "harness_enablement"],
        "variant_choices": [
            "rebuild_from_one_voted_transcript_layer",
            "retain_review_only_never_serve",
            "exclude_permanently",
        ],
        "conflict_row_choices": [
            "accept_guru_label",
            "reject_span",
            "mark_unknown",
            "request_re_review",
        ],
        "clinician_options": ["1", "2", "3"],
    }
    _write_json(root / "backend" / "config" / "gate.json", config)
    return root


def _write_form(root: Path, sections: dict[str, str]) -> None:
    path = root / "audits" / "evidence" / "owner_decisions.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Owner decisions\n\n" + "\n\n".join(sections.values()) + "\n", encoding="utf-8"
    )


def _all_pending() -> dict[str, str]:
    return {
        decision_id: _decision_block(decision_id)
        for decision_id in (
            "b5_rights_register",
            "b5_speaker_conflict_rows",
            "b7_human_speaker_certification",
            "b7_variant_tier",
            "b6_clinician_safety",
            "b7_human_gold_labels",
            "b7_release_authorization",
        )
    }


def _all_approved() -> dict[str, str]:
    """Every decision approved, every scope approved, every conflict row decided."""
    sections = {
        decision_id: _approved(decision_id)
        for decision_id in (
            "b5_rights_register",
            "b7_human_speaker_certification",
            "b7_variant_tier",
            "b6_clinician_safety",
            "b7_human_gold_labels",
            "b7_release_authorization",
        )
    }
    sections["b5_speaker_conflict_rows"] = _approved(
        "b5_speaker_conflict_rows",
        rows={
            f"{index:064x}": "reject_span" for index in range(1, 3)
        },
    )
    sections["b7_variant_tier"] = _approved(
        "b7_variant_tier",
        choice="retain_review_only_never_serve",
        deterministic_id_collision="remain_excluded",
    )
    sections["b6_clinician_safety"] = _approved(
        "b6_clinician_safety",
        option="1",
        clinician_name="Dr Example",
    )
    sections["b7_release_authorization"] = _approved(
        "b7_release_authorization",
        scopes={
            scope: "true"
            for scope in (
                "owner_only_testing",
                "isolated_local_candidate_collection",
                "staging",
                "public_production",
                "alias_promotion",
                "harness_enablement",
            )
        },
    )
    return sections


def _evaluate(root: Path) -> dict[str, Any]:
    config = gate._load_config(root, root / "backend" / "config" / "gate.json")
    return gate.evaluate(root, config)


def _gate(report: dict[str, Any], gate_id: str) -> dict[str, Any]:
    for entry in report["gates"]:
        if entry["gate_id"] == gate_id:
            return entry
    raise AssertionError(f"gate {gate_id} not found in report")


# ---------------------------------------------------------------------------
# 1 — missing owner decisions block
# ---------------------------------------------------------------------------
def test_missing_owner_decisions_block_the_release(tmp_path: Path) -> None:
    root = _build_repo(tmp_path)
    _write_form(root, {"b5_rights_register": _approved("b5_rights_register")})

    report = _evaluate(root)

    assert report["status"] == gate.STATUS_OWNER
    assert report["exit_code"] == gate.EXIT_OWNER_ACTION_REQUIRED
    assert report["public_release_authorized"] is False
    missing = _gate(report, "decision:b7_variant_tier")
    assert missing["passed"] is False
    assert "missing from the owner action form" in missing["detail"]


# ---------------------------------------------------------------------------
# 2 — pending decisions block
# ---------------------------------------------------------------------------
def test_pending_decisions_block_the_release(tmp_path: Path) -> None:
    root = _build_repo(tmp_path)
    _write_form(root, _all_pending())

    report = _evaluate(root)

    assert report["status"] == gate.STATUS_OWNER
    assert report["public_release_authorized"] is False
    pending = _gate(report, "decision:b5_rights_register")
    assert pending["passed"] is False
    assert "no default approval" in pending["detail"]


def test_a_claim_of_approval_without_a_reviewer_is_not_an_approval(tmp_path: Path) -> None:
    root = _build_repo(tmp_path)
    sections = _all_approved()
    sections["b5_rights_register"] = _decision_block(
        "b5_rights_register", approved="true"
    )
    _write_form(root, sections)

    report = _evaluate(root)

    assert report["status"] == gate.STATUS_OWNER
    decision = _gate(report, "decision:b5_rights_register")
    assert decision["passed"] is False
    assert "missing reviewer" in decision["detail"]


# ---------------------------------------------------------------------------
# 3 — partial speaker-conflict decisions block
# ---------------------------------------------------------------------------
def test_partial_speaker_conflict_decisions_block_the_release(tmp_path: Path) -> None:
    root = _build_repo(tmp_path)
    sections = _all_approved()
    sections["b5_speaker_conflict_rows"] = _approved(
        "b5_speaker_conflict_rows",
        rows={"0000000000000000000000000000000000000000000000000000000000000001": "reject_span"},
    )
    _write_form(root, sections)

    report = _evaluate(root)

    assert report["status"] == gate.STATUS_OWNER
    rows = _gate(report, "conflict_rows_decided")
    assert rows["passed"] is False
    assert "1 conflict rows have no decision" in rows["detail"]


# ---------------------------------------------------------------------------
# 4 — rights approval without speaker approval blocks
# ---------------------------------------------------------------------------
def test_rights_approval_without_speaker_approval_blocks(tmp_path: Path) -> None:
    root = _build_repo(tmp_path)
    sections = _all_approved()
    sections["b5_speaker_conflict_rows"] = _decision_block("b5_speaker_conflict_rows")
    _write_form(root, sections)

    report = _evaluate(root)

    assert report["status"] == gate.STATUS_OWNER
    assert report["public_release_authorized"] is False
    assert _gate(report, "decision:b5_speaker_conflict_rows")["passed"] is False
    assert _gate(report, "conflict_rows_decided")["passed"] is False


# ---------------------------------------------------------------------------
# 5 — clinician approval without gold labels blocks
# ---------------------------------------------------------------------------
def test_clinician_approval_without_gold_labels_blocks(tmp_path: Path) -> None:
    root = _build_repo(tmp_path)
    sections = _all_approved()
    sections["b7_human_gold_labels"] = _decision_block("b7_human_gold_labels")
    _write_form(root, sections)

    report = _evaluate(root)

    assert report["status"] == gate.STATUS_OWNER
    assert report["public_release_authorized"] is False
    assert _gate(report, "decision:b7_human_gold_labels")["passed"] is False


def test_missing_gold_label_reports_block_the_release(tmp_path: Path) -> None:
    root = _build_repo(tmp_path)
    _write_form(root, _all_approved())
    (root / "audits" / "evidence" / "gold_label_report.json").unlink()

    report = _evaluate(root)

    assert report["status"] == gate.STATUS_OWNER
    evidence = _gate(report, "gold_label_evidence")
    assert evidence["passed"] is False
    assert "missing evidence" in evidence["detail"]


# ---------------------------------------------------------------------------
# 6 — altered evidence hashes block
# ---------------------------------------------------------------------------
def test_altered_evidence_hashes_block_the_release(tmp_path: Path) -> None:
    root = _build_repo(tmp_path)
    _write_form(root, _all_approved())
    verdict_path = root / "audits" / "evidence" / "verdicts.json"
    document = json.loads(verdict_path.read_text(encoding="utf-8"))
    document["verdicts"]["served-0001"]["reason_code"] = "refused_guru_mismatch"
    verdict_path.write_text(json.dumps(document, indent=2, sort_keys=True), encoding="utf-8")

    report = _evaluate(root)

    assert report["status"] == gate.STATUS_NO_GO
    assert report["exit_code"] == gate.EXIT_NO_GO
    assert report["public_release_authorized"] is False
    artifacts = _gate(report, "pinned_artifacts")
    assert artifacts["passed"] is False
    assert "stale or altered" in artifacts["detail"]


def test_a_contaminated_served_tier_blocks_the_release(tmp_path: Path) -> None:
    root = _build_repo(tmp_path)
    _write_form(root, _all_approved())
    # Re-point the served tier at a conflict row and re-pin the manifest so the
    # integrity gate is what fails, not the hash gate.
    conflict_id = f"{1:064x}"
    tier_path = root / "audits" / "evidence" / "tier_local_review_candidate.jsonl"
    rows = [json.loads(line) for line in tier_path.read_text().splitlines() if line.strip()]
    rows[0]["source_span_id"] = conflict_id
    _write_jsonl(tier_path, rows)
    manifest_path = root / "audits" / "evidence" / "tiers_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["tiers"]["local_review_candidate"]["sha256"] = gate._sha256(tier_path)
    _write_json(manifest_path, manifest)
    config_path = root / "backend" / "config" / "gate.json"
    config = json.loads(config_path.read_text())
    config["pinned_artifacts"]["audits/evidence/tiers_manifest.json"] = gate._sha256(
        manifest_path
    )
    _write_json(config_path, config)

    report = _evaluate(root)

    assert report["status"] == gate.STATUS_NO_GO
    assert _gate(report, "served_tier_integrity")["passed"] is False


# ---------------------------------------------------------------------------
# 7 — a variant approval cannot admit the collision
# ---------------------------------------------------------------------------
def test_variant_approval_cannot_silently_admit_the_collision(tmp_path: Path) -> None:
    root = _build_repo(tmp_path)
    sections = _all_approved()
    sections["b7_variant_tier"] = _approved(
        "b7_variant_tier",
        choice="rebuild_from_one_voted_transcript_layer",
        deterministic_id_collision="include_in_variant_tier",
    )
    _write_form(root, sections)

    report = _evaluate(root)

    assert report["status"] == gate.STATUS_OWNER
    variant = _gate(report, "variant_decision")
    assert variant["passed"] is False
    assert "must remain excluded" in variant["detail"]


def test_a_collision_member_in_the_served_tier_is_an_integrity_violation(
    tmp_path: Path,
) -> None:
    root = _build_repo(tmp_path)
    _write_form(root, _all_approved())
    tier_path = root / "audits" / "evidence" / "tier_local_review_candidate.jsonl"
    rows = [json.loads(line) for line in tier_path.read_text().splitlines() if line.strip()]
    rows[0]["live_source_span_id"] = "live-coll"
    _write_jsonl(tier_path, rows)
    manifest_path = root / "audits" / "evidence" / "tiers_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["tiers"]["local_review_candidate"]["sha256"] = gate._sha256(tier_path)
    _write_json(manifest_path, manifest)
    config_path = root / "backend" / "config" / "gate.json"
    config = json.loads(config_path.read_text())
    config["pinned_artifacts"]["audits/evidence/tiers_manifest.json"] = gate._sha256(
        manifest_path
    )
    _write_json(config_path, config)

    report = _evaluate(root)

    assert report["status"] == gate.STATUS_NO_GO
    assert _gate(report, "served_tier_integrity")["passed"] is False


# ---------------------------------------------------------------------------
# 8 — one environment variable cannot enable public release
# ---------------------------------------------------------------------------
def test_flipping_the_harness_flag_alone_cannot_enable_public_release(
    tmp_path: Path,
) -> None:
    root = _build_repo(tmp_path)
    _write_form(root, _all_approved())
    env_path = root / "backend" / ".env"
    env_path.write_text(
        env_path.read_text().replace(
            "FIRST_PERSON_CONTEXT_HARNESS_ENABLED=false",
            "FIRST_PERSON_CONTEXT_HARNESS_ENABLED=true",
        ),
        encoding="utf-8",
    )

    report = _evaluate(root)

    assert report["public_release_authorized"] is False
    assert report["status"] in {gate.STATUS_NO_GO, gate.STATUS_OWNER, gate.STATUS_ENGINEERING}
    # The owner-approved ``harness_enablement`` scope is what makes the flipped
    # flag legitimate, so this gate passes on that basis. The release must still
    # be refused by every other gate that is not satisfied.
    harness = _gate(report, "harness_flag_disabled")
    assert harness["passed"] is True
    assert "harness_enablement scope approves it" in harness["detail"]
    assert report["gate_counts"]["failed"] >= 1


def test_an_unauthorized_harness_flag_is_an_integrity_violation(tmp_path: Path) -> None:
    root = _build_repo(tmp_path)
    _write_form(root, _all_pending())
    env_path = root / "backend" / ".env"
    env_path.write_text(
        env_path.read_text().replace(
            "FIRST_PERSON_CONTEXT_HARNESS_ENABLED=false",
            "FIRST_PERSON_CONTEXT_HARNESS_ENABLED=true",
        ),
        encoding="utf-8",
    )

    report = _evaluate(root)

    assert report["status"] == gate.STATUS_NO_GO
    assert _gate(report, "harness_flag_disabled")["blocker"] == gate.BLOCKER_INTEGRITY


def test_public_production_cannot_be_implied_by_a_later_scope(tmp_path: Path) -> None:
    root = _build_repo(tmp_path)
    sections = _all_approved()
    sections["b7_release_authorization"] = _approved(
        "b7_release_authorization",
        scopes={
            "owner_only_testing": "true",
            "isolated_local_candidate_collection": "true",
            "staging": "false",
            "public_production": "true",
            "alias_promotion": "true",
            "harness_enablement": "true",
        },
    )
    _write_form(root, sections)

    report = _evaluate(root)

    assert report["public_release_authorized"] is False
    scopes = _gate(report, "authorization_scopes_public")
    assert scopes["passed"] is False
    assert "approved without" in scopes["detail"]


# ---------------------------------------------------------------------------
# 9 — the alias cannot move without snapshot and rollback evidence
# ---------------------------------------------------------------------------
def test_an_alias_promotion_without_snapshot_and_rollback_evidence_blocks(
    tmp_path: Path,
) -> None:
    root = _build_repo(tmp_path)
    sections = _all_approved()
    _write_form(root, sections)
    # The alias-promotion scope is approved, but no promotion record exists.
    report = _evaluate(root)

    assert report["public_release_authorized"] is False
    promotion = _gate(report, "promotion_evidence")
    assert promotion["passed"] is False
    assert "no promotion record with snapshot and rollback evidence" in promotion["detail"]


def test_a_promotion_record_without_rollback_evidence_blocks(tmp_path: Path) -> None:
    root = _build_repo(tmp_path)
    _write_form(root, _all_approved())
    _write_json(
        root / "audits" / "evidence" / "promotion.json",
        {"schema": "x", "snapshot": {"evidence_path": "snap.json"}},
    )

    report = _evaluate(root)

    assert report["public_release_authorized"] is False
    promotion = _gate(report, "promotion_evidence")
    assert promotion["passed"] is False
    assert "no rollback evidence" in promotion["detail"]


def test_a_promotion_record_with_snapshot_and_rollback_evidence_passes(
    tmp_path: Path,
) -> None:
    root = _build_repo(tmp_path)
    _write_form(root, _all_approved())
    _write_json(
        root / "audits" / "evidence" / "promotion.json",
        {
            "schema": "x",
            "snapshot": {"evidence_path": "snap.json"},
            "rollback": {"evidence_path": "rollback.json"},
        },
    )

    report = _evaluate(root)

    assert report["public_release_authorized"] is True
    assert report["status"] == gate.STATUS_READY
    assert _gate(report, "promotion_evidence")["passed"] is True


# ---------------------------------------------------------------------------
# 10 — owner-only mode refuses to run in production
# ---------------------------------------------------------------------------
def test_owner_only_mode_refuses_to_run_in_production() -> None:
    from app.api import first_person_local_review as route
    from app.config import settings

    original_enabled = settings.first_person_local_review_enabled
    original_production = settings.is_production
    try:
        settings.first_person_local_review_enabled = True
        settings.is_production = True
        allowed, reason = route._local_review_allowed()
        assert allowed is False
        assert reason == "local_review_mode_refuses_production"

        settings.is_production = False
        allowed, reason = route._local_review_allowed()
        assert allowed is True
        assert reason == ""

        settings.first_person_local_review_enabled = False
        allowed, reason = route._local_review_allowed()
        assert allowed is False
        assert reason == "local_review_mode_disabled"
    finally:
        settings.first_person_local_review_enabled = original_enabled
        settings.is_production = original_production


def test_owner_only_mode_cannot_run_in_production_even_with_the_flag_on() -> None:
    """A production deployment must refuse the local-review route outright."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import first_person_local_review as route
    from app.config import settings

    original_enabled = settings.first_person_local_review_enabled
    original_production = settings.is_production
    try:
        settings.first_person_local_review_enabled = True
        settings.is_production = True
        app = FastAPI()
        app.include_router(route.router, prefix="/api")
        client = TestClient(app)
        response = client.post(
            "/api/first-person/local-review/query",
            json={"query": "What is meditation?", "max_clips": 1},
        )
        assert response.status_code == 404
        body = response.json()
        assert "review_label" in body.get("detail", {})
    finally:
        settings.first_person_local_review_enabled = original_enabled
        settings.is_production = original_production


# ---------------------------------------------------------------------------
# 11 — the public route stays safe while the harness is disabled
# ---------------------------------------------------------------------------
def test_the_public_route_stays_safe_while_the_harness_is_disabled() -> None:
    """The legacy public route must refuse to serve context records.

    The public route reads a legacy-schema collection. Pointing it at an
    fp-context collection is exactly the conflation the B4 gate refuses, so
    the route serves nothing rather than serving the wrong schema.
    """
    from services.first_person_serving_contract import (
        load_contract,
        validate_serving_contract,
    )

    contract_path = _REPO_ROOT / "backend" / "config" / "first_person_serving_contract.json"
    contract = load_contract(contract_path)

    report = validate_serving_contract(
        contract=contract,
        legacy_collection="first_person_v10",
        context_collection="first_person_v10",
    )
    assert report.ok is False
    assert any("fp-context collection" in error for error in report.errors)


def test_the_harness_is_disabled_by_default() -> None:
    from app.config import Settings

    assert Settings().first_person_context_harness_enabled is False


def test_the_release_gate_never_writes_or_mutates() -> None:
    """The controller is read-only: it must not import a Qdrant client."""
    source = (
        _REPO_ROOT / "backend" / "scripts" / "ops" / "check_first_person_public_release.py"
    ).read_text(encoding="utf-8")
    for forbidden in ("qdrant_client", "import redis", "subprocess", "os.environ["):
        assert forbidden not in source, f"the gate controller must not contain {forbidden!r}"


# ---------------------------------------------------------------------------
# The decision parser itself
# ---------------------------------------------------------------------------
def test_the_decision_parser_rejects_a_malformed_block() -> None:
    with pytest.raises(gate.GateError):
        gate._parse_decision_blocks("```json owner-decision\n{not json}\n```")


def test_the_decision_parser_keeps_the_first_block_for_a_duplicate_id() -> None:
    markdown = (
        _decision_block("dup", approved="true")
        + "\n"
        + _decision_block("dup", approved="false")
    )
    decisions = gate._parse_decision_blocks(markdown)
    assert decisions["dup"]["approved"] == "true"


def test_approval_state_never_treats_a_truthy_string_as_approval() -> None:
    assert gate._approval_state(True) == "approved"
    assert gate._approval_state("true") == "approved"
    assert gate._approval_state("TRUE") == "approved"
    assert gate._approval_state(False) == "declined"
    assert gate._approval_state("false") == "declined"
    assert gate._approval_state("pending") == "pending"
    assert gate._approval_state(None) == "pending"
    assert gate._approval_state("yes") == "invalid"


def test_the_repository_packets_mirror_the_owner_action_form() -> None:
    """The shipped packets and the shipped form must agree today."""
    form = (
        _REPO_ROOT / "audits" / "evidence" / "FIRST_PERSON_OWNER_DECISIONS_2026-10-22.md"
    )
    assert form.is_file()
    decisions = gate._parse_decision_blocks(form.read_text(encoding="utf-8"))
    assert set(decisions) == {
        "b5_rights_register",
        "b5_speaker_conflict_rows",
        "b7_human_speaker_certification",
        "b7_variant_tier",
        "b6_clinician_safety",
        "b7_human_gold_labels",
        "b7_release_authorization",
    }
    for decision_id, record in decisions.items():
        if decision_id in {"b5_speaker_conflict_rows", "b7_human_speaker_certification"}:
            assert gate._approval_state(record.get("approved")) == "approved"
        else:
            assert gate._approval_state(record.get("approved")) == "pending", (
                f"{decision_id} must not carry a default approval"
            )


def test_the_repository_gate_reports_owner_action_required() -> None:
    """The shipped repository state is OWNER_ACTION_REQUIRED, never ready."""
    config_path = _REPO_ROOT / "backend" / "config" / "first_person_public_release_gate.json"
    config = gate._load_config(_REPO_ROOT, config_path)
    report = gate.evaluate(_REPO_ROOT, config)
    assert report["status"] == gate.STATUS_OWNER
    assert report["public_release_authorized"] is False
    assert report["mutations"]["qdrant_writes"] == 0
    assert report["mutations"]["alias_changes"] == 0
    assert report["mutations"]["deployments"] == 0


def test_the_shipped_conflict_table_covers_every_artifact_row() -> None:
    """The form's per-row decisions must cover exactly the 45 conflict rows."""
    conflicts = [
        json.loads(line)
        for line in (
            _REPO_ROOT
            / "audits/evidence/public_release_phase4_speaker_conflicts_v2_2026-10-22.jsonl"
        )
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    form = (
        _REPO_ROOT / "audits" / "evidence" / "FIRST_PERSON_OWNER_DECISIONS_2026-10-22.md"
    ).read_text(encoding="utf-8")
    decisions = gate._parse_decision_blocks(form)
    rows = decisions["b5_speaker_conflict_rows"].get("rows") or {}
    config_path = _REPO_ROOT / "backend" / "config" / "first_person_public_release_gate.json"
    config = gate._load_config(_REPO_ROOT, config_path)
    choices = set(config.get("conflict_row_choices") or [])
    assert len(conflicts) == 45
    assert set(rows) == {row["source_span_id"] for row in conflicts}
    assert all(value in choices and value != "pending" for value in rows.values())


def test_the_repository_copy_of_the_controller_is_the_canonical_one() -> None:
    """A copy of the controller must not drift from the canonical script."""
    canonical = _REPO_ROOT / "backend" / "scripts" / "ops" / "check_first_person_public_release.py"
    root_copy = _REPO_ROOT / "scripts" / "ops" / "check_first_person_public_release.py"
    if root_copy.exists():
        assert shutil.samefile(canonical, canonical)
        assert root_copy.read_bytes() == canonical.read_bytes()
