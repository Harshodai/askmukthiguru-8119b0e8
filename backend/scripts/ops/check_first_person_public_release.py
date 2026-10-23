#!/usr/bin/env python3
"""Release-gate controller for the first-person public release.

**Read-only.** It reads the pinned evidence artifacts, the owner action form
and the serving contract, verifies every required gate, and prints a release
decision. It never writes a file, never contacts Qdrant, never moves an alias,
never changes an environment variable, never rebuilds a container and never
deploys.

Exit codes carry the decision:

=====  ====================================================================
0     READY_FOR_PUBLIC_RELEASE_REVIEW — every gate passed.
1     OWNER_ACTION_REQUIRED — an owner decision is missing, pending,
      declined or only partially recorded.
2     ENGINEERING_BLOCKED — a required engineering artifact is missing,
      stale or internally inconsistent.
3     READY_FOR_STAGING_REVIEW — the prerequisites passed; the next agent
      can execute the final staging-readiness review.
4     NO_GO — an invariant is violated (evidence tampered, the served tier
      contaminated, the harness enabled without authorization, an implicit
      deployment). Fail closed.
5     USAGE / unreadable inputs — the controller could not evaluate.
=====  ====================================================================

The controller fails closed. Missing, stale or contradictory evidence is a
blocker, never a pass. It never reports public readiness because automated
tests passed: public readiness additionally requires the explicit
``b7_release_authorization`` decision with every scope individually approved.

Two stages
----------
A gate is either a **prerequisite** (needed before the staging-readiness
review can run) or a **public** gate (needed before the public release can be
reviewed). Prerequisites are evaluated first: while a prerequisite fails, the
release cannot advance at all.

Usage
-----
    python backend/scripts/ops/check_first_person_public_release.py
    python backend/scripts/ops/check_first_person_public_release.py --json
    python backend/scripts/ops/check_first_person_public_release.py \\
        --root /path/to/repo --config backend/config/first_person_public_release_gate.json
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

EXIT_READY = 0
EXIT_OWNER_ACTION_REQUIRED = 1
EXIT_ENGINEERING_BLOCKED = 2
EXIT_READY_FOR_STAGING_REVIEW = 3
EXIT_NO_GO = 4
EXIT_USAGE = 5

STATUS_READY = "READY_FOR_PUBLIC_RELEASE_REVIEW"
STATUS_OWNER = "OWNER_ACTION_REQUIRED"
STATUS_ENGINEERING = "ENGINEERING_BLOCKED"
STATUS_STAGING = "READY_FOR_STAGING_REVIEW"
STATUS_NO_GO = "NO_GO"
STATUS_USAGE = "USAGE"

CONFIG_SCHEMA = "first-person-public-release-gate-v1"
DECISION_FENCE = "owner-decision"

STAGE_PREREQUISITE = "prerequisite"
STAGE_PUBLIC = "public"

BLOCKER_OWNER = "owner"
BLOCKER_ENGINEERING = "engineering"
BLOCKER_INTEGRITY = "integrity"


class GateError(RuntimeError):
    """Raised when the controller cannot evaluate its inputs at all."""


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _parse_decision_blocks(markdown: str) -> dict[str, dict[str, Any]]:
    """Extract the ``owner-decision`` JSON blocks from a Markdown document.

    Each block is a fenced code block tagged ``owner-decision`` whose body is
    one JSON object carrying a ``decision_id``. The first occurrence of a
    decision id wins, so a duplicated block cannot silently flip a decision.
    """
    decisions: dict[str, dict[str, Any]] = {}
    lines = markdown.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if line.startswith("```") and DECISION_FENCE in line:
            body: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                body.append(lines[index])
                index += 1
            try:
                payload = json.loads("\n".join(body))
            except json.JSONDecodeError:
                raise GateError(
                    f"decision block ending at line {index + 1} is not valid JSON"
                ) from None
            decision_id = str(payload.get("decision_id") or "").strip()
            if not decision_id:
                raise GateError(f"decision block ending at line {index + 1} has no decision_id")
            decisions.setdefault(decision_id, payload)
        index += 1
    return decisions


def _approval_state(value: Any) -> str:
    """Classify a decision's ``approved`` field.

    ``"true"`` / ``true`` is an approval, ``"false"`` / ``false`` is an
    explicit decline, ``"pending"`` / empty / missing is undecided and
    anything else is invalid. A truthy string is never an approval by
    accident: only the literal ``true`` counts.
    """
    if value is True:
        return "approved"
    if value is False:
        return "declined"
    if value is None:
        return "pending"
    text = str(value).strip().lower()
    if text == "true":
        return "approved"
    if text == "false":
        return "declined"
    if text in {"", "pending"}:
        return "pending"
    return "invalid"


def _pending(value: Any) -> bool:
    return _approval_state(value) == "pending"


# ---------------------------------------------------------------------------
# gate collection
# ---------------------------------------------------------------------------
class GateReport:
    """Collects gate outcomes and derives the release decision."""

    def __init__(self) -> None:
        self.gates: list[dict[str, Any]] = []

    def add(
        self,
        gate_id: str,
        requirement: str,
        *,
        passed: bool,
        status: str,
        detail: str,
        blocker: str = "",
        stage: str = STAGE_PREREQUISITE,
    ) -> None:
        self.gates.append(
            {
                "gate_id": gate_id,
                "requirement": requirement,
                "status": status,
                "passed": passed,
                "detail": detail,
                "blocker": blocker,
                "stage": stage,
            }
        )

    def _failed(self, stage: str) -> list[dict[str, Any]]:
        return [
            gate
            for gate in self.gates
            if not gate["passed"] and gate["stage"] == stage
        ]

    def _blocking(self, failed: list[dict[str, Any]]) -> str:
        for blocker in (BLOCKER_INTEGRITY, BLOCKER_ENGINEERING, BLOCKER_OWNER):
            if any(gate["blocker"] == blocker for gate in failed):
                return blocker
        return ""


# ---------------------------------------------------------------------------
# gates
# ---------------------------------------------------------------------------
def _artifact(root: Path, config: dict[str, Any], name: str) -> Path:
    """Resolve one artifact path from the gate config."""
    artifacts: dict[str, Any] = config.get("artifacts") or {}
    return root / str(artifacts.get(name) or "")


def _check_pinned_artifacts(root: Path, config: dict[str, Any], report: GateReport) -> None:
    """Every pinned artifact must exist with the pinned sha256.

    A **missing** artifact is outstanding engineering work. An artifact whose
    hash **changed** is tampering or drift: that is an invariant violation and
    fails the gate as ``NO_GO``.
    """
    pinned: dict[str, str] = config.get("pinned_artifacts") or {}
    missing: list[str] = []
    stale: list[str] = []
    for relative, expected in sorted(pinned.items()):
        path = root / relative
        if not path.is_file():
            missing.append(relative)
            continue
        if _sha256(path) != expected:
            stale.append(relative)

    if stale:
        report.add(
            "pinned_artifacts",
            "every pinned evidence artifact exists and its sha256 matches",
            passed=False,
            status="fail",
            detail=(
                "stale or altered (sha256 does not match the pinned value): "
                + ", ".join(stale)
            ),
            blocker=BLOCKER_INTEGRITY,
        )
        return
    report.add(
        "pinned_artifacts",
        "every pinned evidence artifact exists and its sha256 matches",
        passed=not missing,
        status="pass" if not missing else "fail",
        detail=(
            "all pinned artifacts present with matching sha256"
            if not missing
            else f"missing: {', '.join(missing)}"
        ),
        blocker="" if not missing else BLOCKER_ENGINEERING,
    )


def _check_tier_arithmetic(
    root: Path, config: dict[str, Any], report: GateReport
) -> None:
    """The tier manifests must reconcile to the expected row counts."""
    expectations: dict[str, Any] = config.get("tier_expectations") or {}
    manifest_path = root / str(expectations.get("tiers_manifest") or "")
    if not manifest_path.is_file():
        report.add(
            "tier_arithmetic",
            "tier row counts reconcile to the expected totals",
            passed=False,
            status="fail",
            detail=f"tiers manifest missing: {manifest_path}",
            blocker=BLOCKER_ENGINEERING,
        )
        return

    manifest = _read_json(manifest_path)
    expected_counts: dict[str, int] = expectations.get("row_counts") or {}
    observed_counts: dict[str, int] = dict(manifest.get("tier_counts") or {})

    mismatches: list[str] = []
    for tier, expected in expected_counts.items():
        actual = observed_counts.get(tier)
        if actual != expected:
            mismatches.append(f"{tier}: expected {expected}, got {actual}")

    total_rows = 0
    for tier_entry in (manifest.get("tiers") or {}).values():
        tier_path = root / str(tier_entry.get("path") or "")
        if not tier_path.is_file():
            mismatches.append(f"tier file missing: {tier_entry.get('path')}")
            continue
        rows = _read_jsonl(tier_path)
        if len(rows) != tier_entry.get("row_count"):
            mismatches.append(
                f"{tier}: manifest says {tier_entry.get('row_count')} rows, "
                f"file has {len(rows)}"
            )
        total_rows += len(rows)

    expected_total = int(expectations.get("total_rows") or 0)
    if total_rows != expected_total:
        mismatches.append(f"total rows: expected {expected_total}, got {total_rows}")

    passed = not mismatches
    report.add(
        "tier_arithmetic",
        "tier row counts reconcile to the expected totals with no drops or duplicates",
        passed=passed,
        status="pass" if passed else "fail",
        detail="; ".join(mismatches) if mismatches else (
            f"{total_rows} rows across {len(expected_counts)} tiers, all counts as expected"
        ),
        blocker="" if passed else BLOCKER_ENGINEERING,
    )


def _check_served_tier_integrity(
    root: Path, config: dict[str, Any], report: GateReport
) -> None:
    """The served tier must be exactly reconstructible, verified and uncontaminated."""
    expectations: dict[str, Any] = config.get("tier_expectations") or {}
    served_tier = str(expectations.get("served_tier") or "local_review_candidate")
    manifest = _read_json(root / str(expectations.get("tiers_manifest") or ""))
    tier_entry = (manifest.get("tiers") or {}).get(served_tier) or {}
    tier_path = root / str(tier_entry.get("path") or "")
    if not tier_path.is_file():
        report.add(
            "served_tier_integrity",
            "every served-tier span is verified, uncontaminated and rights-cleared",
            passed=False,
            status="fail",
            detail=f"served tier file missing: {tier_path}",
            blocker=BLOCKER_ENGINEERING,
        )
        return

    served_rows = _read_jsonl(tier_path)
    verdicts_doc = _read_json(_artifact(root, config, "verdicts"))
    verdicts: dict[str, Any] = verdicts_doc.get("verdicts") or {}
    rights_rows = {
        str(row.get("source_span_id") or ""): row
        for row in _read_jsonl(_artifact(root, config, "rights_join"))
    }

    missing_verdict: list[str] = []
    unverified: list[str] = []
    rights_gap: list[str] = []
    for row in served_rows:
        span_id = str(row.get("source_span_id") or "")
        verdict = verdicts.get(span_id)
        if not isinstance(verdict, dict):
            missing_verdict.append(span_id)
            continue
        if (
            verdict.get("reason_code") != "verified"
            or verdict.get("source_text_hash") != row.get("source_text_hash")
            or verdict.get("audio_start_ms") != row.get("audio_start_ms")
            or verdict.get("audio_end_ms") != row.get("audio_end_ms")
        ):
            unverified.append(span_id)
            continue
        rights = rights_rows.get(span_id)
        if not isinstance(rights, dict) or not rights.get("servable"):
            rights_gap.append(span_id)

    conflict_rows = _read_jsonl(_artifact(root, config, "speaker_conflicts"))
    conflict_ids = {str(row.get("source_span_id") or "") for row in conflict_rows}
    collision_members = set(expectations.get("collision_members") or [])
    served_ids = {str(row.get("source_span_id") or "") for row in served_rows}
    served_live = {str(row.get("live_source_span_id") or "") for row in served_rows}

    contaminated = sorted(
        (served_ids & conflict_ids)
        | (served_live & conflict_ids)
        | (served_ids & collision_members)
        | (served_live & collision_members)
    )

    variant_ids = {
        str(row.get("source_span_id") or "")
        for row in _read_jsonl(_artifact(root, config, "variant_tier"))
    }
    unlocatable_ids = {
        str(row.get("source_span_id") or "")
        for row in _read_jsonl(_artifact(root, config, "unlocatable_tier"))
    }
    quarantined = sorted(
        (served_ids & variant_ids) | (served_live & variant_ids)
        | (served_ids & unlocatable_ids) | (served_live & unlocatable_ids)
    )

    problems: list[str] = []
    if missing_verdict:
        problems.append(f"{len(missing_verdict)} served spans have no Phase-2 verdict")
    if unverified:
        problems.append(
            f"{len(unverified)} served spans lack a verified, hash-matched verdict"
        )
    if rights_gap:
        problems.append(f"{len(rights_gap)} served spans lack servable rights")
    if contaminated:
        problems.append(
            f"{len(contaminated)} served spans are speaker conflicts or collision members"
        )
    if quarantined:
        problems.append(f"{len(quarantined)} served spans are variant or unlocatable rows")

    passed = not problems
    report.add(
        "served_tier_integrity",
        "every served-tier span is verified, uncontaminated and rights-cleared",
        passed=passed,
        status="pass" if passed else "fail",
        detail="; ".join(problems) if problems else (
            f"{len(served_rows)} served spans each carry a source-span-keyed verified "
            "verdict, servable rights, and no conflict, collision, variant or "
            "unlocatable row"
        ),
        blocker="" if passed else BLOCKER_INTEGRITY,
    )


def _check_b4_contract(root: Path, config: dict[str, Any], report: GateReport) -> None:
    """The declared serving contract must separate the legacy and context roles."""
    contract_path = _artifact(root, config, "serving_contract")
    if not contract_path.is_file():
        report.add(
            "b4_contract_declared",
            "the serving contract declares distinct legacy and context roles",
            passed=False,
            status="fail",
            detail=f"serving contract missing: {contract_path}",
            blocker=BLOCKER_ENGINEERING,
        )
        return

    contract = _read_json(contract_path)
    collections: dict[str, Any] = contract.get("collections") or {}
    legacy = sorted(name for name, entry in collections.items() if entry.get("role") == "legacy")
    context = sorted(
        name for name, entry in collections.items() if entry.get("role") == "context"
    )
    shared = sorted(set(legacy) & set(context))
    incomplete = sorted(
        name
        for name, entry in collections.items()
        if not entry.get("schema")
        or not entry.get("corpus_version")
        or not entry.get("evidence_policy")
        or not entry.get("required_payload_fields")
    )

    problems: list[str] = []
    if not legacy:
        problems.append("no legacy-role collection is declared")
    if not context:
        problems.append("no context-role collection is declared")
    if shared:
        problems.append(f"collections declared with both roles: {', '.join(shared)}")
    if incomplete:
        problems.append(
            f"collections missing schema/corpus version/evidence policy: {', '.join(incomplete)}"
        )

    passed = not problems
    report.add(
        "b4_contract_declared",
        "the serving contract declares distinct legacy and context roles",
        passed=passed,
        status="pass" if passed else "fail",
        detail="; ".join(problems) if problems else (
            f"{len(legacy)} legacy-role and {len(context)} context-role collections "
            "declared with distinct schemas, corpus versions and evidence policies"
        ),
        blocker="" if passed else BLOCKER_ENGINEERING,
    )


def _check_b4_release_configuration(
    root: Path, config: dict[str, Any], report: GateReport
) -> None:
    """The candidate release configuration must name two separate collections.

    The candidate configuration artifact is produced when the
    ``isolated_local_candidate_collection`` scope is exercised. Until it
    exists, this gate is outstanding owner work — not a defect.
    """
    expected = config.get("expected_evidence") or {}
    path = root / str(expected.get("candidate_config") or "")
    if not path.is_file():
        report.add(
            "b4_release_configuration",
            "the candidate release configuration names a legacy and a context "
            "collection that are not the same collection",
            passed=False,
            status="fail",
            detail=(
                "no candidate configuration artifact yet: "
                f"{expected.get('candidate_config')} (produced by the "
                "isolated_local_candidate_collection scope)"
            ),
            blocker=BLOCKER_OWNER,
        )
        return

    document = _read_json(path)
    legacy = str(document.get("legacy_collection") or "")
    context = str(document.get("context_collection") or "")
    contract_path = _artifact(root, config, "serving_contract")
    collections = (_read_json(contract_path).get("collections") or {}) if (
        contract_path.is_file()
    ) else {}

    problems: list[str] = []
    if not legacy or not context:
        problems.append("the candidate configuration names no legacy/context collection")
    elif legacy == context:
        problems.append(
            f"the candidate configuration points both roles at {legacy!r}"
        )
    else:
        legacy_entry = collections.get(legacy) or {}
        context_entry = collections.get(context) or {}
        if legacy_entry.get("role") != "legacy":
            problems.append(f"{legacy!r} is not declared with the legacy role")
        if context_entry.get("role") != "context":
            problems.append(f"{context!r} is not declared with the context role")
        if legacy_entry.get("schema") == context_entry.get("schema"):
            problems.append("the legacy and context collections share a payload schema")

    passed = not problems
    report.add(
        "b4_release_configuration",
        "the candidate release configuration names a legacy and a context collection "
        "that are not the same collection",
        passed=passed,
        status="pass" if passed else "fail",
        detail="; ".join(problems) if problems else (
            f"legacy={legacy!r} context={context!r} — separated and schema-compatible"
        ),
        blocker="" if passed else BLOCKER_ENGINEERING,
    )


def _check_harness_flag(
    root: Path,
    config: dict[str, Any],
    decisions: dict[str, dict[str, Any]],
    report: GateReport,
) -> None:
    """The public harness stays disabled unless explicitly authorized."""
    env_file = root / str(config.get("env_file") or "backend/.env")
    if not env_file.is_file():
        report.add(
            "harness_flag_disabled",
            "the public context harness stays disabled until explicitly authorized",
            passed=False,
            status="fail",
            detail=f"env file missing: {env_file}",
            blocker=BLOCKER_ENGINEERING,
        )
        return

    value = ""
    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("FIRST_PERSON_CONTEXT_HARNESS_ENABLED="):
            value = stripped.partition("=")[2].strip().strip('"').strip("'").lower()
    enabled = value == "true"

    scopes = (decisions.get("b7_release_authorization") or {}).get("scopes") or {}
    authorized = _approval_state(scopes.get("harness_enablement")) == "approved"

    if not enabled:
        report.add(
            "harness_flag_disabled",
            "the public context harness stays disabled until explicitly authorized",
            passed=True,
            status="pass",
            detail="FIRST_PERSON_CONTEXT_HARNESS_ENABLED=false in the repository env file",
        )
        return

    report.add(
        "harness_flag_disabled",
        "the public context harness stays disabled until explicitly authorized",
        passed=authorized,
        status="pass" if authorized else "fail",
        detail=(
            "the harness flag is on and the explicit harness_enablement scope approves it"
            if authorized
            else "FIRST_PERSON_CONTEXT_HARNESS_ENABLED=true without an explicit "
            "harness_enablement scope — an unauthorized promotion attempt"
        ),
        blocker="" if authorized else BLOCKER_INTEGRITY,
    )


def _check_owner_decisions(
    config: dict[str, Any], decisions: dict[str, dict[str, Any]], report: GateReport
) -> None:
    """Every required owner decision must be recorded and explicitly approved."""
    for decision_id in config.get("decision_ids") or []:
        record = decisions.get(decision_id)
        if record is None:
            report.add(
                f"decision:{decision_id}",
                f"owner decision {decision_id} is recorded and explicitly approved",
                passed=False,
                status="fail",
                detail="decision block missing from the owner action form",
                blocker=BLOCKER_OWNER,
            )
            continue

        state = _approval_state(record.get("approved"))
        reviewer = str(record.get("reviewer") or "").strip()
        decided_at = str(record.get("decision_date_utc") or "").strip()
        signature = str(record.get("signature") or "").strip()
        incomplete = [
            name
            for name, value in (
                ("reviewer", reviewer),
                ("decision_date_utc", decided_at),
                ("signature", signature),
            )
            if not value
        ]
        passed = state == "approved" and not incomplete
        if state == "pending":
            detail = "approved=pending — there is no default approval"
        elif state == "declined":
            detail = "the owner declined this decision"
        elif state == "invalid":
            detail = f"approved={record.get('approved')!r} is not a valid decision value"
        elif incomplete:
            detail = f"approved but incomplete: missing {', '.join(incomplete)}"
        else:
            detail = f"approved by {reviewer} on {decided_at}"
        report.add(
            f"decision:{decision_id}",
            f"owner decision {decision_id} is recorded and explicitly approved",
            passed=passed,
            status="pass" if passed else "fail",
            detail=detail,
            blocker="" if passed else BLOCKER_OWNER,
        )


def _check_conflict_rows(
    root: Path,
    config: dict[str, Any],
    decisions: dict[str, dict[str, Any]],
    report: GateReport,
) -> None:
    """All 45 speaker-conflict rows need an explicit per-row decision."""
    record = decisions.get("b5_speaker_conflict_rows") or {}
    rows: dict[str, Any] = record.get("rows") or {}
    expected = int((config.get("tier_expectations") or {}).get("speaker_conflict_rows") or 0)
    choices = set(config.get("conflict_row_choices") or [])
    # ``mark_unknown`` is a legacy spelling.  It is accepted only as an input
    # compatibility alias and is evaluated as the canonical quarantine state.
    choices.add("unknown_keep_quarantined")

    def _canonical_choice(value: Any) -> str:
        text = str(value or "").strip()
        return "unknown_keep_quarantined" if text == "mark_unknown" else text

    conflict_path = _artifact(root, config, "speaker_conflicts")
    if not conflict_path.is_file():
        report.add(
            "conflict_rows_decided",
            "every speaker-conflict row carries an explicit decision",
            passed=False,
            status="fail",
            detail=f"conflict artifact missing: {conflict_path}",
            blocker=BLOCKER_ENGINEERING,
        )
        return

    conflict_ids = [
        str(row.get("source_span_id") or "") for row in _read_jsonl(conflict_path)
    ]
    undecided: list[str] = []
    invalid: list[str] = []
    for span_id in conflict_ids:
        value = rows.get(span_id)
        if value is None or _pending(value):
            undecided.append(span_id)
            continue
        if _canonical_choice(value) not in choices:
            invalid.append(span_id)
    unknown = sorted(set(rows) - set(conflict_ids))

    problems: list[str] = []
    if len(conflict_ids) != expected:
        problems.append(
            f"expected {expected} conflict rows, artifact has {len(conflict_ids)}"
        )
    if undecided:
        problems.append(f"{len(undecided)} conflict rows have no decision")
    if invalid:
        problems.append(f"{len(invalid)} conflict rows use an unknown decision value")
    if unknown:
        problems.append(f"{len(unknown)} recorded conflict rows are not in the artifact")

    passed = not problems
    report.add(
        "conflict_rows_decided",
        "every speaker-conflict row carries an explicit decision",
        passed=passed,
        status="pass" if passed else "fail",
        detail="; ".join(problems) if problems else (
            f"all {len(conflict_ids)} conflict rows carry an explicit decision"
        ),
        blocker="" if passed else BLOCKER_OWNER,
    )


def _check_variant_decision(
    decisions: dict[str, dict[str, Any]], report: GateReport
) -> None:
    """The variant decision must not silently approve the collision."""
    record = decisions.get("b7_variant_tier") or {}
    choice = str(record.get("choice") or "").strip()
    collision = str(record.get("deterministic_id_collision") or "").strip()
    problems: list[str] = []
    if not choice:
        problems.append("no variant choice recorded")
    if not collision:
        problems.append("no deterministic-ID collision disposition recorded")
    if collision and collision != "remain_excluded":
        problems.append(
            f"the collision disposition is {collision!r}; the two collision members must "
            "remain excluded unless separately resolved"
        )
    passed = not problems
    report.add(
        "variant_decision",
        "the variant-tier decision is recorded and cannot approve the collision",
        passed=passed,
        status="pass" if passed else "fail",
        detail="; ".join(problems) if problems else (
            f"variant choice {choice!r}; collision members remain excluded"
        ),
        blocker="" if passed else BLOCKER_OWNER,
    )


def _check_clinician_decision(
    decisions: dict[str, dict[str, Any]], report: GateReport
) -> None:
    """The distress-boundary decision must name an option and a clinician."""
    record = decisions.get("b6_clinician_safety") or {}
    option = str(record.get("option") or "").strip()
    name = str(record.get("clinician_name") or "").strip()
    problems: list[str] = []
    if not option:
        problems.append("no clinician option recorded")
    if not name:
        problems.append("no clinician name recorded")
    passed = not problems
    report.add(
        "clinician_decision",
        "the distress-boundary decision names an option and a clinician",
        passed=passed,
        status="pass" if passed else "fail",
        detail="; ".join(problems) if problems else (
            f"option {option} recorded by {name}; no tuning without this decision"
        ),
        blocker="" if passed else BLOCKER_OWNER,
    )


def _check_speaker_certification(
    root: Path, config: dict[str, Any], report: GateReport
) -> None:
    """The human speaker-label certification must exist as an artifact."""
    expected = config.get("expected_evidence") or {}
    path = root / str(expected.get("speaker_certification") or "")
    if not path.is_file():
        report.add(
            "speaker_certification_evidence",
            "the human speaker-label certification artifact exists",
            passed=False,
            status="fail",
            detail=f"missing evidence: {expected.get('speaker_certification')}",
            blocker=BLOCKER_OWNER,
        )
        return
    report.add(
        "speaker_certification_evidence",
        "the human speaker-label certification artifact exists",
        passed=True,
        status="pass",
        detail=str(expected.get("speaker_certification")),
    )


def _check_gold_label_artifacts(
    root: Path, config: dict[str, Any], report: GateReport
) -> None:
    """The human gold labels and the agreement report must both exist."""
    expected = config.get("expected_evidence") or {}
    gold_path = root / str(expected.get("gold_label_report") or "")
    agreement_path = root / str(expected.get("agreement_calibration_report") or "")

    missing: list[str] = []
    if not gold_path.is_file():
        missing.append(str(expected.get("gold_label_report") or ""))
    if not agreement_path.is_file():
        missing.append(str(expected.get("agreement_calibration_report") or ""))

    sheets = config.get("annotator_sheets") or []
    blank_sheets: list[str] = []
    for sheet in sheets:
        sheet_path = root / str(sheet)
        if not sheet_path.is_file():
            blank_sheets.append(f"{sheet} (missing)")
            continue
        with sheet_path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if not rows:
            blank_sheets.append(f"{sheet} (empty)")
            continue
        blanks = sum(
            1
            for row in rows
            if not str(row.get("speaker_is_teacher_yes_no_unsure") or "").strip()
        )
        if blanks:
            blank_sheets.append(f"{sheet} ({blanks} blank certification cells)")

    problems: list[str] = []
    if missing:
        problems.append(f"missing evidence: {', '.join(missing)}")
    if blank_sheets:
        problems.append(f"annotator sheets incomplete: {', '.join(blank_sheets)}")

    passed = not problems
    report.add(
        "gold_label_evidence",
        "the human gold-label report and the agreement report exist and are filled in",
        passed=passed,
        status="pass" if passed else "fail",
        detail="; ".join(problems) if problems else (
            "human gold labels, agreement report and annotator sheets are complete"
        ),
        blocker="" if passed else BLOCKER_OWNER,
    )


def _check_authorization_scopes(
    config: dict[str, Any],
    decisions: dict[str, dict[str, Any]],
    report: GateReport,
) -> None:
    """Every authorization scope is approved separately; none implies another."""
    record = decisions.get("b7_release_authorization") or {}
    scopes: dict[str, Any] = record.get("scopes") or {}
    ordered: list[str] = list(config.get("authorization_scopes") or [])
    prerequisite_scopes = set(config.get("authorization_stage_1") or [])
    public_scopes = set(config.get("authorization_stage_2") or [])

    def _scope_gate(
        gate_id: str,
        requirement: str,
        wanted: set[str],
        stage: str,
    ) -> None:
        missing = [scope for scope in ordered if scope in wanted and scope not in scopes]
        not_approved = [
            scope
            for scope in ordered
            if scope in wanted and _approval_state(scopes.get(scope)) != "approved"
        ]
        # "No later approval implies earlier approval": an approved scope may not
        # be used to infer an earlier scope that was never approved.
        implied: list[str] = []
        for index, scope in enumerate(ordered):
            if _approval_state(scopes.get(scope)) != "approved":
                continue
            for earlier in ordered[:index]:
                if _approval_state(scopes.get(earlier)) != "approved":
                    implied.append(f"{scope} approved without {earlier}")
        problems: list[str] = []
        if missing:
            problems.append(f"scopes not recorded: {', '.join(missing)}")
        if not_approved:
            problems.append(f"scopes not approved: {', '.join(not_approved)}")
        if implied:
            problems.append("; ".join(implied))
        passed = not problems
        report.add(
            gate_id,
            requirement,
            passed=passed,
            status="pass" if passed else "fail",
            detail="; ".join(problems) if problems else (
                "each scope in this group is approved independently"
            ),
            blocker="" if passed else BLOCKER_OWNER,
            stage=stage,
        )

    _scope_gate(
        "authorization_scopes_prerequisites",
        "the authorization scopes needed before the staging review are approved "
        "separately",
        prerequisite_scopes,
        STAGE_PREREQUISITE,
    )
    _scope_gate(
        "authorization_scopes_public",
        "the authorization scopes needed before the public release are approved "
        "separately",
        public_scopes,
        STAGE_PUBLIC,
    )


def _check_no_implicit_deployment(
    root: Path,
    config: dict[str, Any],
    decisions: dict[str, dict[str, Any]],
    report: GateReport,
) -> None:
    """Deployment is never implied by evidence or by an environment variable."""
    record = decisions.get("b7_release_authorization") or {}
    scopes: dict[str, Any] = record.get("scopes") or {}
    env_file = root / str(config.get("env_file") or "backend/.env")
    env_values: dict[str, str] = {}
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            env_values[key.strip()] = value.strip().strip('"').strip("'")

    public_approved = _approval_state(scopes.get("public_production")) == "approved"
    harness_approved = _approval_state(scopes.get("harness_enablement")) == "approved"

    problems: list[str] = []
    if public_approved and not _approval_state(scopes.get("staging")) == "approved":
        problems.append("public production approved without a staging approval")
    if harness_approved and not public_approved:
        problems.append("harness enablement approved without public production approval")
    if (
        env_values.get("FIRST_PERSON_CONTEXT_HARNESS_ENABLED", "").lower() == "true"
        and not harness_approved
    ):
        problems.append(
            "the harness flag is on in the environment without an explicit "
            "harness-enablement scope"
        )
    if public_approved and not _approval_state(scopes.get("alias_promotion")) == "approved":
        problems.append("public production approved without an alias-promotion approval")

    passed = not problems
    report.add(
        "no_implicit_deployment",
        "no deployment, promotion or harness enablement is implied by anything but "
        "an explicit scope approval",
        passed=passed,
        status="pass" if passed else "fail",
        detail="; ".join(problems) if problems else (
            "no deployment authorization is implied; every scope stands alone"
        ),
        blocker="" if passed else BLOCKER_INTEGRITY,
        stage=STAGE_PUBLIC,
    )


def _check_packet_mirrors(
    root: Path,
    config: dict[str, Any],
    decisions: dict[str, dict[str, Any]],
    report: GateReport,
) -> None:
    """Each decision packet must carry the same decision block as the form."""
    mapping: dict[str, str] = config.get("decision_packet_map") or {}
    drifted: list[str] = []
    missing: list[str] = []
    for decision_id, relative in sorted(mapping.items()):
        packet_path = root / relative
        if not packet_path.is_file():
            missing.append(relative)
            continue
        try:
            packet_blocks = _parse_decision_blocks(packet_path.read_text(encoding="utf-8"))
        except GateError as exc:
            drifted.append(f"{relative}: {exc}")
            continue
        packet_record = packet_blocks.get(decision_id)
        form_record = decisions.get(decision_id)
        if packet_record is None or form_record is None:
            drifted.append(f"{relative}: decision {decision_id} not present")
            continue
        if json.dumps(packet_record, sort_keys=True) != json.dumps(
            form_record, sort_keys=True
        ):
            drifted.append(f"{relative}: decision {decision_id} differs from the form")

    problems: list[str] = []
    if missing:
        problems.append(f"missing packets: {', '.join(missing)}")
    if drifted:
        problems.append("; ".join(drifted))
    passed = not problems
    report.add(
        "packet_decision_mirrors",
        "every decision packet mirrors the owner action form exactly",
        passed=passed,
        status="pass" if passed else "fail",
        detail="; ".join(problems) if problems else (
            f"all {len(mapping)} packets mirror the owner action form"
        ),
        blocker="" if passed else BLOCKER_ENGINEERING,
    )


def _check_per_span_ecapa_evidence(
    root: Path, config: dict[str, Any], report: GateReport
) -> None:
    """Require direct, release-grade per-span acoustic evidence."""
    expected = config.get("expected_evidence") or {}
    relative = str(expected.get("ecapa_reconciliation_summary") or "").strip()
    if not relative:
        return
    path = root / relative
    if not path.is_file():
        report.add(
            "per_span_ecapa_evidence",
            "the ECAPA reconciliation has direct release-grade per-span coverage",
            passed=False,
            status="fail",
            detail=f"missing evidence: {relative}",
            blocker=BLOCKER_ENGINEERING,
        )
        return
    document = _read_json(path)
    coverage = document.get("direct_span_id_coverage") or {}
    safe = document.get("safe_to_upgrade") or {}
    problems: list[str] = []
    if document.get("release_blocking") is True:
        problems.append("reconciliation artifact is release_blocking=true")
    if float(coverage.get("pct_of_v10_children") or 0) <= 0:
        problems.append("direct v10 source-span coverage is zero")
    if int(safe.get("count") or 0) <= 0:
        problems.append("no release-grade per-span verdicts are safe to upgrade")
    if (document.get("independent_per_span_evidence") or {}).get("available") is not True:
        problems.append("independent per-span acoustic evidence is unavailable")
    report.add(
        "per_span_ecapa_evidence",
        "the ECAPA reconciliation has direct release-grade per-span coverage",
        passed=not problems,
        status="pass" if not problems else "fail",
        detail="; ".join(problems) if problems else relative,
        blocker="" if not problems else BLOCKER_ENGINEERING,
    )


def _check_staging_readiness(
    root: Path, config: dict[str, Any], report: GateReport
) -> None:
    """The staging-readiness review must have been executed and passed."""
    expected = config.get("expected_evidence") or {}
    path = root / str(expected.get("staging_readiness") or "")
    suites = list(config.get("staging_suites") or [])
    if not path.is_file():
        report.add(
            "staging_readiness_review",
            "the staging-readiness review has been executed and every suite passed",
            passed=False,
            status="fail",
            detail=f"missing evidence: {expected.get('staging_readiness')}",
            blocker=BLOCKER_ENGINEERING,
            stage=STAGE_PUBLIC,
        )
        return

    document = _read_json(path)
    results = document.get("suites") or {}
    failed = sorted(
        suite
        for suite in suites
        if str((results.get(suite) or {}).get("status") or "") != "pass"
    )
    metadata_required = list(config.get("staging_metadata_required") or [])
    missing_metadata = [field for field in metadata_required if not document.get(field)]
    if missing_metadata:
        failed.append("metadata:" + ",".join(missing_metadata))
    passed = not failed
    report.add(
        "staging_readiness_review",
        "the staging-readiness review has been executed and every suite passed",
        passed=passed,
        status="pass" if passed else "fail",
        detail=(
            f"suites not passing: {', '.join(failed)}"
            if failed
            else f"all {len(suites)} staging suites passed"
        ),
        blocker="" if passed else BLOCKER_ENGINEERING,
        stage=STAGE_PUBLIC,
    )


def _check_promotion_evidence(
    root: Path,
    config: dict[str, Any],
    decisions: dict[str, dict[str, Any]],
    report: GateReport,
) -> None:
    """An alias promotion needs snapshot and rollback evidence."""
    expected = config.get("expected_evidence") or {}
    path = root / str(expected.get("promotion_record") or "")
    scopes = (decisions.get("b7_release_authorization") or {}).get("scopes") or {}
    promotion_approved = _approval_state(scopes.get("alias_promotion")) == "approved"

    if not path.is_file():
        report.add(
            "promotion_evidence",
            "any candidate-collection promotion carries snapshot and rollback evidence",
            passed=not promotion_approved,
            status="pass" if not promotion_approved else "fail",
            detail=(
                "no promotion record and no alias-promotion scope: nothing has been "
                "promoted, so there is nothing to prove"
                if not promotion_approved
                else "the alias-promotion scope is approved but no promotion record with "
                "snapshot and rollback evidence exists"
            ),
            blocker="" if not promotion_approved else BLOCKER_ENGINEERING,
            stage=STAGE_PUBLIC,
        )
        return

    document = _read_json(path)
    snapshot = document.get("snapshot") or {}
    rollback = document.get("rollback") or {}
    problems: list[str] = []
    if not snapshot.get("evidence_path"):
        problems.append("no snapshot evidence")
    if not rollback.get("evidence_path"):
        problems.append("no rollback evidence")
    passed = not problems
    report.add(
        "promotion_evidence",
        "any candidate-collection promotion carries snapshot and rollback evidence",
        passed=passed,
        status="pass" if passed else "fail",
        detail="; ".join(problems) if problems else (
            "promotion record carries snapshot and rollback evidence"
        ),
        blocker="" if passed else BLOCKER_ENGINEERING,
        stage=STAGE_PUBLIC,
    )


# ---------------------------------------------------------------------------
# evaluation
# ---------------------------------------------------------------------------
def evaluate(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    """Evaluate every gate and return the release decision."""
    report = GateReport()

    decisions_path = root / str(config.get("owner_decisions_path") or "")
    if not decisions_path.is_file():
        raise GateError(f"owner decision record missing: {decisions_path}")
    decisions = _parse_decision_blocks(decisions_path.read_text(encoding="utf-8"))

    _check_pinned_artifacts(root, config, report)
    _check_tier_arithmetic(root, config, report)
    _check_served_tier_integrity(root, config, report)
    _check_b4_contract(root, config, report)
    _check_b4_release_configuration(root, config, report)
    _check_harness_flag(root, config, decisions, report)
    _check_owner_decisions(config, decisions, report)
    _check_conflict_rows(root, config, decisions, report)
    _check_variant_decision(decisions, report)
    _check_clinician_decision(decisions, report)
    _check_speaker_certification(root, config, report)
    _check_gold_label_artifacts(root, config, report)
    _check_authorization_scopes(config, decisions, report)
    _check_packet_mirrors(root, config, decisions, report)
    _check_no_implicit_deployment(root, config, decisions, report)
    _check_staging_readiness(root, config, report)
    _check_promotion_evidence(root, config, decisions, report)

    prerequisite_failed = report._failed(STAGE_PREREQUISITE)
    public_failed = report._failed(STAGE_PUBLIC)

    if not prerequisite_failed and not public_failed:
        status = STATUS_READY
        exit_code = EXIT_READY
        summary = (
            "every gate passed and every release-authorization scope is individually "
            "approved: the public release is reviewable"
        )
    elif prerequisite_failed:
        blocker = report._blocking(prerequisite_failed)
        if blocker == BLOCKER_INTEGRITY:
            status = STATUS_NO_GO
            exit_code = EXIT_NO_GO
            summary = (
                f"{len(prerequisite_failed)} prerequisite gate(s) failed and violate an "
                "invariant: the release is NO-GO until the violation is fixed"
            )
        elif blocker == BLOCKER_ENGINEERING:
            status = STATUS_ENGINEERING
            exit_code = EXIT_ENGINEERING_BLOCKED
            summary = (
                f"{len(prerequisite_failed)} prerequisite gate(s) failed and need "
                "engineering work before the public release can be reviewed"
            )
        else:
            status = STATUS_OWNER
            exit_code = EXIT_OWNER_ACTION_REQUIRED
            summary = (
                f"{len(prerequisite_failed)} prerequisite gate(s) failed and need an "
                "owner decision before the public release can be reviewed"
            )
    elif public_failed:
        blocker = report._blocking(public_failed)
        if blocker == BLOCKER_INTEGRITY:
            status = STATUS_NO_GO
            exit_code = EXIT_NO_GO
            summary = (
                f"{len(public_failed)} public-stage gate(s) failed and violate an "
                "invariant: the release is NO-GO"
            )
        elif blocker == BLOCKER_ENGINEERING:
            status = STATUS_ENGINEERING
            exit_code = EXIT_ENGINEERING_BLOCKED
            summary = (
                f"{len(public_failed)} public-stage gate(s) failed and need "
                "engineering work before the public release can be reviewed"
            )
        else:
            status = STATUS_STAGING
            exit_code = EXIT_READY_FOR_STAGING_REVIEW
            summary = (
                "every prerequisite passed; the staging-readiness review is the "
                "remaining step before the public release can be reviewed"
            )
    else:  # pragma: no cover - defensive
        status = STATUS_OWNER
        exit_code = EXIT_OWNER_ACTION_REQUIRED
        summary = "the release is blocked"

    failed = prerequisite_failed + public_failed
    return {
        "schema": "first-person-public-release-gate-report-v1",
        "status": status,
        "exit_code": exit_code,
        "summary": summary,
        "gates": report.gates,
        "gate_counts": {
            "total": len(report.gates),
            "passed": len(report.gates) - len(failed),
            "failed": len(failed),
            "prerequisite_failed": len(prerequisite_failed),
            "public_failed": len(public_failed),
            "owner_blocked": sum(
                1 for gate in failed if gate["blocker"] == BLOCKER_OWNER
            ),
            "engineering_blocked": sum(
                1 for gate in failed if gate["blocker"] == BLOCKER_ENGINEERING
            ),
            "integrity_violations": sum(
                1 for gate in failed if gate["blocker"] == BLOCKER_INTEGRITY
            ),
        },
        "failed_gates": [gate["gate_id"] for gate in failed],
        "public_release_authorized": status == STATUS_READY,
        "mutations": {
            "qdrant_writes": 0,
            "alias_changes": 0,
            "redis_operations": 0,
            "environment_changes": 0,
            "container_rebuilds": 0,
            "deployments": 0,
            "git_operations": 0,
        },
    }


def render_summary(report: dict[str, Any]) -> str:
    """Human-readable summary of the gate report."""
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append("FIRST-PERSON PUBLIC RELEASE GATE")
    lines.append("=" * 78)
    lines.append(f"STATUS : {report['status']}")
    lines.append(f"SUMMARY: {report['summary']}")
    counts = report["gate_counts"]
    lines.append(
        f"GATES  : {counts['passed']}/{counts['total']} passed "
        f"({counts['prerequisite_failed']} prerequisite, {counts['public_failed']} public-stage failed)"
    )
    lines.append(
        f"BLOCKED: {counts['owner_blocked']} need an owner decision, "
        f"{counts['engineering_blocked']} need engineering work, "
        f"{counts['integrity_violations']} violate an invariant"
    )
    lines.append("MUTATIONS: qdrant=0 alias=0 redis=0 env=0 docker=0 deploy=0 git=0")
    lines.append("=" * 78)
    for gate in report["gates"]:
        mark = "PASS" if gate["passed"] else "FAIL"
        stage = "prereq" if gate["stage"] == STAGE_PREREQUISITE else "public"
        lines.append(f"[{mark}] ({stage}) {gate['gate_id']} — {gate['requirement']}")
        if not gate["passed"]:
            lines.append(f"        {gate['detail']}")
    lines.append("=" * 78)
    if report["public_release_authorized"]:
        lines.append("Public release is REVIEWABLE. It is not deployed and not enabled.")
    else:
        lines.append("Public release is NOT reviewable yet. Nothing was promoted.")
    return "\n".join(lines)


def _load_config(root: Path, config_path: Path) -> dict[str, Any]:
    if not config_path.is_file():
        raise GateError(f"gate config missing: {config_path}")
    config = _read_json(config_path)
    if config.get("schema") != CONFIG_SCHEMA:
        raise GateError(
            f"gate config schema must be {CONFIG_SCHEMA!r}; got {config.get('schema')!r}"
        )
    return config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--root",
        default=None,
        help="repository root (default: the repository containing this script)",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="gate config path (default: backend/config/first_person_public_release_gate.json)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the machine-readable JSON report instead of the human summary",
    )
    args = parser.parse_args(argv)

    script_root = Path(__file__).resolve().parents[3]
    root = Path(args.root).resolve() if args.root else script_root
    config_path = (
        Path(args.config).resolve()
        if args.config
        else root / "backend/config/first_person_public_release_gate.json"
    )

    try:
        config = _load_config(root, config_path)
        report = evaluate(root, config)
    except GateError as exc:
        if args.json:
            print(
                json.dumps(
                    {
                        "schema": "first-person-public-release-gate-report-v1",
                        "status": STATUS_USAGE,
                        "exit_code": EXIT_USAGE,
                        "summary": str(exc),
                        "gates": [],
                        "gate_counts": {
                            "total": 0,
                            "passed": 0,
                            "failed": 0,
                            "prerequisite_failed": 0,
                            "public_failed": 0,
                            "owner_blocked": 0,
                            "engineering_blocked": 0,
                            "integrity_violations": 0,
                        },
                        "failed_gates": [],
                        "public_release_authorized": False,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(f"[fp-release-gate] cannot evaluate: {exc}", file=sys.stderr)
        return EXIT_USAGE

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_summary(report))
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
