#!/usr/bin/env python3
"""Build the owner decision packets for the first-person public release.

**Read-only with respect to every system of record.** It reads the frozen
evidence artifacts and the owner action form, and writes markdown packets. It
never writes to Qdrant, never touches an alias, never mutates Redis, never
changes an environment variable and never deploys.

Every packet is a **question to the owner**, not a result. The decision fields
default to ``pending`` on purpose: this script never approves anything on the
owner's behalf.

The **owner action form** (``audits/evidence/FIRST_PERSON_OWNER_DECISIONS_2026-10-22.md``)
is the single source of truth for owner decisions. Each packet embeds a copy
of that form's ``owner-decision`` block for its topic, so the two cannot drift:
the release-gate controller fails closed when a packet and the form disagree.

Exit codes
----------
=====  ===================================================================
0      All packets were written.
1      A packet was written but an input artifact was missing (the packet
       says so and the decision cannot be taken from it).
=====  ===================================================================

Usage
-----
    python -m scripts.ops.build_fp_owner_decision_packets \\
        --evidence-dir audits/evidence \\
        --date 2026-10-22
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

DECISION_EMPTY = "_**Owner decision:** ____________________ (approved / rejected / deferred)_"

# The owner action form is the single source of truth for owner decisions.
# Each packet embeds a copy of the form's block for its topic so the two
# cannot drift.
OWNER_FORM_NAME = "FIRST_PERSON_OWNER_DECISIONS_{date}.md"
DECISION_FENCE = "owner-decision"

# Packet name -> decision id in the owner action form.
PACKET_DECISION_IDS: dict[str, str] = {
    "rights": "b5_rights_register",
    "speaker": "b5_speaker_conflict_rows",
    "speaker_certification": "b7_human_speaker_certification",
    "variant": "b7_variant_tier",
    "clinician": "b6_clinician_safety",
    "gold_label": "b7_human_gold_labels",
    "authorization": "b7_release_authorization",
}


def _read_owner_form(repo_root: Path, date: str) -> dict[str, dict[str, Any]]:
    """Parse the ``owner-decision`` blocks out of the owner action form."""
    form_path = repo_root / "audits" / "evidence" / OWNER_FORM_NAME.format(date=date)
    if not form_path.is_file():
        return {}
    decisions: dict[str, dict[str, Any]] = {}
    lines = form_path.read_text(encoding="utf-8").splitlines()
    index = 0
    while index < len(lines):
        if lines[index].strip().startswith("```") and DECISION_FENCE in lines[index]:
            body: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                body.append(lines[index])
                index += 1
            payload = json.loads("\n".join(body))
            decisions.setdefault(str(payload.get("decision_id") or ""), payload)
        index += 1
    return decisions


def _decision_block(
    decisions: dict[str, dict[str, Any]], decision_id: str
) -> list[str]:
    """Render the decision block for one topic, or a placeholder."""
    lines = ["```json owner-decision"]
    record = decisions.get(decision_id)
    if record is None:
        lines.append(json.dumps({"decision_id": decision_id, "approved": "pending"}))
    else:
        lines.append(json.dumps(record, indent=2))
    lines.append("```")
    return lines


def _append_decision_record(
    lines: list[str],
    decisions: dict[str, dict[str, Any]],
    decision_id: str,
    *,
    title: str = "Owner decision record",
    intro: str = "",
) -> None:
    """Append the shared decision-record section to a packet."""
    lines.append("")
    lines.append("## Owner decision record")
    lines.append("")
    if intro:
        lines.append(intro)
        lines.append("")
    lines.append(
        "This block is a **copy** of the owner action form's block for this topic "
        "(`audits/evidence/FIRST_PERSON_OWNER_DECISIONS_2026-10-22.md`). The form is the "
        "source of truth; the release-gate controller fails closed if the two disagree. "
        "`approved` accepts `\"pending\"`, `\"true\"` or `\"false\"` — there is no default "
        "approval."
    )
    lines.append("")
    lines.extend(_decision_block(decisions, decision_id))
    lines.append("")
    lines.append(f"- Decision of record: `{title}`")
    lines.append("")


def _sha256_file(path: Path) -> str:
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


def _stamp(path: Path) -> str:
    return f"`{path}` (sha256 `{_sha256_file(path)}`)"


# ---------------------------------------------------------------------------
# 1 — rights
# ---------------------------------------------------------------------------
def rights_packet(evidence: Path, date: str, decisions: dict[str, dict[str, Any]]) -> str:
    manifest_path = evidence / f"public_release_phase4_rights_manifest_{date}.json"
    summary_path = evidence / f"public_release_phase4_rights_summary_{date}.json"
    join_path = evidence / f"public_release_phase4_rights_join_{date}.jsonl"
    report_path = evidence / f"public_release_phase4_rights_report_{date}.md"

    manifest = _read_json(manifest_path)
    summary = _read_json(summary_path)
    _read_jsonl(join_path)
    assets = manifest.get("assets") or []

    lines: list[str] = []
    lines.append("# Owner decision packet — B5 rights register")
    lines.append("")
    lines.append(
        "**This is a question, not an approval.** The agent did not approve, reject or "
        "defer anything in this packet. The owner decides."
    )
    lines.append("")
    lines.append("## 1. What is being approved")
    lines.append("")
    lines.append(
        "The **independent rights register** for the `fp-context-transcript-v2` first-person "
        "candidate corpus: a per-asset rights basis built from "
        "`docs/rights/CONTENT-RIGHTS.md` (human-authored) and ingest-time channel metadata. "
        "Approving it means: *the rights basis recorded for these assets is the basis I "
        "accept for serving a verbatim excerpt with attribution.*"
    )
    lines.append("")
    lines.append("## 2. Register identity")
    lines.append("")
    lines.append(f"- Register manifest: {_stamp(manifest_path)}")
    lines.append(f"- Register summary: {_stamp(summary_path)}")
    lines.append(f"- Rights join (per candidate span): {_stamp(join_path)}")
    if report_path.is_file():
        lines.append(f"- Human-readable report: {_stamp(report_path)}")
    lines.append(f"- Registry document: `{manifest['independent_sources']['rights_registry']['path']}`")
    lines.append(
        f"  (sha256 `{manifest['independent_sources']['rights_registry']['sha256']}`, "
        f"{manifest['independent_sources']['rights_registry']['byte_length']} bytes)"
    )
    lines.append(
        f"- Register owner confirmation (recorded by the builder): "
        f"**{summary['register_owner_confirmation']}**"
    )
    lines.append("")
    lines.append("## 3. Counts")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    lines.append(f"| Assets in the register (whole first-person universe) | {summary['asset_count']} |")
    lines.append(f"| Assets inside the candidate corpus | {summary['candidate_asset_count']} |")
    lines.append(f"| Candidate spans joined | {summary['span_count']} |")
    lines.append(f"| Servable assets (confirmed) | {summary['servable_asset_count']} |")
    lines.append(f"| Servable candidate assets | {summary['servable_candidate_asset_count']} |")
    lines.append(f"| Servable spans | {summary['servable_span_count']} |")
    lines.append(f"| Quarantined spans | {summary['quarantined_span_count']} |")
    lines.append(
        f"| Confirmed but speaker-unverified spans | "
        f"{summary['confirmed_but_speaker_unverified_spans']} |"
    )
    lines.append("")
    lines.append("### Rights status — assets (whole universe)")
    lines.append("")
    lines.append("| Status | Assets | In candidate |")
    lines.append("|---|---:|---:|")
    for status, count in sorted(summary["rights_status_counts_by_asset"].items()):
        in_candidate = summary["rights_status_counts_by_candidate_asset"].get(status, 0)
        lines.append(f"| `{status}` | {count} | {in_candidate} |")
    lines.append("")
    lines.append("### Rights status — candidate spans")
    lines.append("")
    lines.append("| Status | Spans |")
    lines.append("|---|---:|")
    for status, count in sorted(summary["rights_status_counts_by_span"].items()):
        lines.append(f"| `{status}` | {count} |")
    lines.append("")
    lines.append("## 4. The rule this register follows")
    lines.append("")
    lines.append(
        "> **A payload flag is not evidence.** The live collection's `rights_cleared` field is "
        "never read as proof of anything. It is carried through only as "
        "`payload_rights_cleared_claim_untrusted`, for comparison. A rights basis is a human "
        "decision recorded in the registry, and a registry row confirms an asset only when its "
        "owner-confirmation marker is on the same table row."
    )
    lines.append("")
    lines.append("Registry entries applied:")
    for entry_id in summary["registry_entries_applied"]:
        lines.append(f"- `{entry_id}`")
    if summary["registry_entries_not_applied"]:
        lines.append("")
        lines.append("Registry entries **not** applied:")
        for entry in summary["registry_entries_not_applied"]:
            lines.append(f"- `{entry['entry_id']}` — {entry['reason']}")
    lines.append("")
    lines.append("## 5. Per-asset evidence")
    lines.append("")
    lines.append(
        "One row per asset: the canonical source URL, the rightsholder, the permission "
        "basis and the registry document that carries the confirmation."
    )
    lines.append("")
    lines.append(
        "| Video | Channel | Status | Rightsholder | Permission basis | Source URL | "
        "In candidate | Registry evidence | Owner decision |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for asset in assets:
        lines.append(
            "| `{video}` | {channel} | `{status}` | {rightsholder} | {basis} | {url} | {inc} | "
            "`{evidence}` | |".format(
                video=asset["video_id"],
                channel=asset.get("channel") or "—",
                status=asset.get("rights_status"),
                rightsholder=asset.get("rightsholder") or "—",
                basis=asset.get("permission_basis") or "—",
                url=asset.get("canonical_source_url") or "—",
                inc="yes" if asset.get("in_candidate") else "no",
                evidence=Path(str(asset.get("evidence_document") or "")).name,
            )
        )
    lines.append("")
    lines.append("## 6. Decision")
    lines.append("")
    lines.append(DECISION_EMPTY)
    lines.append("")
    lines.append("- Owner signature: ____________________")
    lines.append("- Date (UTC): ____________________")
    lines.append("- Scope approved (e.g. *all 751 assets*, *only the 447 candidate assets*, "
                 "*specific videos listed above*): ____________________")
    lines.append("- Notes / conditions: ____________________")
    lines.append("")
    lines.append("## 7. What this packet does NOT decide")
    lines.append("")
    lines.append(
        "- It does not approve any speaker attribution (that is the speaker packet)."
    )
    lines.append(
        "- It does not approve the variant tier (that is the variant packet)."
    )
    lines.append("- It does not approve a public release (that is a separate owner act).")
    lines.append("")
    _append_decision_record(
        lines,
        decisions,
        "b5_rights_register",
        title="B5 rights register sign-off",
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 2 — speaker
# ---------------------------------------------------------------------------
def speaker_packet(evidence: Path, date: str, decisions: dict[str, dict[str, Any]]) -> str:
    conflicts_path = evidence / f"public_release_phase4_speaker_conflicts_v2_{date}.jsonl"
    summary_path = evidence / f"public_release_phase4_speaker_conflict_summary_v2_{date}.json"
    review_path = evidence / f"public_release_phase4_speaker_conflict_review_v2_{date}.md"
    v1_path = evidence / f"public_release_phase4_speaker_conflicts_{date}.jsonl"
    v1_review = evidence / f"public_release_phase4_speaker_conflict_review_{date}.md"
    calibration_path = evidence / f"public_release_phase2_calibration_{date}.json"

    conflicts = _read_jsonl(conflicts_path)
    summary = _read_json(summary_path)

    lines: list[str] = []
    lines.append("# Owner decision packet — 45 contradictory speaker labels")
    lines.append("")
    lines.append(
        "**This is a question, not an approval.** The agent did not approve, reject or "
        "defer any row. Every conflict stays quarantined until the owner records a "
        "decision."
    )
    lines.append("")
    lines.append("## 1. What is being decided")
    lines.append("")
    lines.append(
        "45 candidate spans whose **acoustic evidence contradicts the corpus's per-video "
        "teacher label**. For each row the owner must decide which claim is wrong:"
    )
    lines.append("")
    lines.append(
        "- the **corpus label** for that video (the video is filed under the wrong teacher), or"
    )
    lines.append(
        "- the **slice/reference** (the window does not contain the teacher it claims, or the "
        "reference voiceprint does not cover this speaker)."
    )
    lines.append("")
    lines.append(
        "**Never relabel a speaker, a guru or a video from this table.** A rejected span "
        "stays quarantined. An approved relabel opens a video-level relabel task; it does "
        "not by itself admit the span to a serving tier."
    )
    lines.append("")
    lines.append("## 2. Correction to the previous packet (read this first)")
    lines.append("")
    lines.append(
        "The previous packet (schema `first-person-speaker-conflict-v1`) wrote the **slice** "
        "width into a field named `audio_duration_ms` — the same name the Phase-2 verdict "
        "uses for the duration of the **complete WAV file**. The two numbers differ by "
        "orders of magnitude (example: slice `10480` ms vs file `214692` ms), so a reviewer "
        "reading v1 could reasonably believe the window sat near the end of the recording. "
        "It did not."
    )
    lines.append("")
    lines.append(
        "Schema `first-person-speaker-conflict-v2` **removes** that field (it is never "
        "repurposed) and states both durations explicitly: `audio_file_duration_ms` (the "
        "whole file) and `audio_slice_duration_ms` (the quoted slice), alongside "
        "`audio_start_ms` and `audio_end_ms`. A v1 row and a v2 row are not interchangeable."
    )
    lines.append("")
    lines.append("| Artifact | sha256 |")
    lines.append("|---|---|")
    lines.append(f"| v2 conflict rows (45) | `{_sha256_file(conflicts_path)}` |")
    lines.append(f"| v2 summary | `{_sha256_file(summary_path)}` |")
    if review_path.is_file():
        lines.append(f"| v2 human-readable packet | `{_sha256_file(review_path)}` |")
    if v1_path.is_file():
        lines.append(f"| **superseded** v1 rows (retained, not overwritten) | `{_sha256_file(v1_path)}` |")
    if v1_review.is_file():
        lines.append(f"| **superseded** v1 packet (retained) | `{_sha256_file(v1_review)}` |")
    lines.append("")
    lines.append("## 3. Model, calibration and scores")
    lines.append("")
    lines.append(f"- Model: `{summary['speaker_model']}` @ `{summary['speaker_model_revision']}`")
    lines.append(f"- Calibration revision: `{summary['calibration_revision']}`")
    lines.append(f"- Run id: `{summary['run_id']}`")
    lines.append(f"- Conflicts: **{summary['conflict_count']}** across "
                 f"**{summary['video_count']}** videos")
    for direction, count in sorted(summary["conflict_direction_counts"].items()):
        lines.append(f"  - `{direction}`: **{count}**")
    lines.append("")
    bounds = summary.get("bounds", {})
    lines.append(
        f"- Bounds check: **{bounds.get('out_of_bounds_count', 0)} / {summary['conflict_count']}** "
        "windows fall outside the complete archived WAV "
        f"({bounds.get('bounds_checked_rows', 0)} checked against a measured file duration, "
        f"{bounds.get('bounds_unchecked_rows', 0)} without one)."
    )
    lines.append("")
    if calibration_path.is_file():
        calibration = _read_json(calibration_path)
        lines.append("### Calibration record")
        lines.append("")
        lines.append(f"- Calibration file: {_stamp(calibration_path)}")
        for key in (
            "calibration_id",
            "calibration_available",
            "cosine_floor",
            "margin_threshold",
            "positive_trials",
            "impostor_trials",
        ):
            if key in calibration:
                lines.append(f"- `{key}`: `{calibration[key]}`")
        lines.append("")
    lines.append("## 4. What the FAR/FRR numbers are, and are not")
    lines.append("")
    lines.append(
        "> The measured false-accept / false-reject rate behind this packet is a **relative** "
        "consistency measurement on held-out videos, derived from the same two "
        "human-confirmed anchor moments the reference voiceprints are widened from. It is "
        "**not** a human-certified false-accept rate, and it is **not** a public attribution "
        "certification. The repository contains no filled human speaker-label sheet, so "
        "certification is a separate owner act (see the gold-label packet)."
    )
    lines.append("")
    lines.append("## 5. The 45 rows")
    lines.append("")
    lines.append(
        "`slice` is the quoted window's width; `file` is the duration of the complete "
        "archived WAV the slice came from. They are different quantities."
    )
    lines.append("")
    lines.append(
        "| # | span id | video | corpus label | ECAPA predicted | cosine | margin | "
        "window (ms) | slice (ms) | file (ms) | WAV sha256 | decision | reviewer | date |"
    )
    lines.append("|---:|---|---|---|---|---:|---:|---|---:|---:|---|---|---|---|")
    for index, conflict in enumerate(conflicts, start=1):
        lines.append(
            "| {n} | `{sid}` | `{vid}` | {exp} | {pred} | {cos} | {mar} | {s}–{e} | "
            "{slice} | {file} | `{wav}` | | | |".format(
                n=index,
                sid=conflict["source_span_id"],
                vid=conflict["video_id"],
                exp=conflict["expected_guru"],
                pred=conflict["predicted_guru"],
                cos=conflict["cosine"],
                mar=conflict["margin"],
                s=conflict["audio_start_ms"],
                e=conflict["audio_end_ms"],
                slice=conflict["audio_slice_duration_ms"],
                file=conflict["audio_file_duration_ms"],
                wav=str(conflict["audio_sha256"])[:16] + "…",
            )
        )
    lines.append("")
    lines.append("## 6. Decision")
    lines.append("")
    lines.append(DECISION_EMPTY)
    lines.append("")
    lines.append("- Owner signature: ____________________")
    lines.append("- Date (UTC): ____________________")
    lines.append("- Rows approved as a corpus-label error (video-level relabel task): "
                 "____________________")
    lines.append("- Rows approved as an audio/reference error (recalibration task): "
                 "____________________")
    lines.append("- Notes: ____________________")
    lines.append("")
    _append_decision_record(
        lines,
        decisions,
        "b5_speaker_conflict_rows",
        title="45 speaker-label conflict rows",
        intro=(
            "The per-row decisions live in the `rows` map of the block below, keyed by the "
            "45 span ids. Every row must carry one of `accept_guru_label`, `reject_span`, "
            "`mark_unknown` or `request_re_review`. A partial table is not a decision."
        ),
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 3 — variant
# ---------------------------------------------------------------------------
def variant_packet(evidence: Path, date: str, decisions: dict[str, dict[str, Any]]) -> str:
    variant_tier = evidence / f"public_release_phase4_tier_variant_candidate_{date}.jsonl"
    collision_path = evidence / f"public_release_phase4_deterministic_id_collisions_{date}.jsonl"
    phase3_variants = evidence / "public_release_phase3_variants_2026-10-21.jsonl"
    tier_summary = evidence / f"public_release_phase4_tiers_summary_{date}.json"

    tier_rows = _read_jsonl(variant_tier)
    collisions = _read_jsonl(collision_path)
    summary = _read_json(tier_summary)

    phase3_rows: list[dict[str, Any]] = []
    if phase3_variants.is_file():
        phase3_rows = _read_jsonl(phase3_variants)

    lines: list[str] = []
    lines.append("# Owner decision packet — the variant tier (1,127 rows, 1,126 rebuilt ids)")
    lines.append("")
    lines.append(
        "**This is a question, not an approval.** The agent did not approve, reject or defer "
        "anything in this packet. Every variant row stays out of every serving tier."
    )
    lines.append("")
    lines.append("## 1. What is being decided")
    lines.append("")
    lines.append(
        "The Phase-3 rebuild could not reconstruct these spans **exactly** from the "
        "authoritative word-timed artifact: the recorded corpus text came from the markdown "
        "display transcript while the timings came from the voted word-timed artifact, and "
        "for these spans the two disagree in wording. They are therefore *variants*: the "
        "text is a near-match, not the span."
    )
    lines.append("")
    lines.append("## 2. The counts, stated without a hidden duplicate")
    lines.append("")
    lines.append("| Quantity | Value |")
    lines.append("|---|---:|")
    lines.append(f"| Phase-3 variant source rows | **{len(phase3_rows)}** |")
    lines.append(f"| Distinct rebuilt ids in the Phase-3 variant set | "
                 f"**{len({r.get('source_span_id') for r in phase3_rows if r.get('source_span_id')})}** |")
    lines.append(f"| Variant tier rows after the collision repair (one row per source span) | "
                 f"**{len(tier_rows)}** |")
    lines.append(f"| Deterministic-id collision quarantine rows | "
                 f"**{summary['tier_counts']['deterministic_id_collision_quarantine']}** |")
    lines.append(f"| Colliding rebuilt ids | **{len(collisions)}** |")
    lines.append("")
    lines.append(
        "> The earlier report called the difference a *byte-identical duplicate*. That was "
        "**wrong**. It is not a duplicate row: it is a **deterministic-id collision** — two "
        "different live spans that produced the same rebuilt id. Both are now quarantined "
        "and neither is silently kept."
    )
    lines.append("")
    lines.append("## 3. The collision record")
    lines.append("")
    for record in collisions:
        lines.append(
            f"### Collided rebuilt id `{record['collided_source_span_id']}`"
        )
        lines.append("")
        lines.append(f"- Namespace: `{record['collided_namespace']}`")
        lines.append(f"- Members: **{record['member_count']}** "
                     f"(distinct source spans: {record['distinct_source_span_count']})")
        lines.append(f"- Cause: **`{record['collision_cause']}`** — {record['collision_cause_detail']}")
        lines.append(f"- Resolution status: **{record['resolution_status']}**")
        lines.append(f"- Namespace fix applied: **{record['namespace_fix_applied']}**")
        lines.append(f"- Why no namespace fix: {record['namespace_fix_reason']}")
        lines.append(f"- Rebuilt id namespace: `{record['span_id_namespace_components']}`")
        lines.append(f"- Missing from the namespace: `{record['span_id_namespace_missing_component']}`")
        lines.append("")
        lines.append("| live source span id | video | source row | rebuilt window | live window |")
        lines.append("|---|---|---:|---|---|")
        for member in record["members"]:
            lines.append(
                f"| `{member['live_source_span_id']}` | `{member['video_id']}` | "
                f"{member['source_row_number']} | {member['rebuilt_word_start']}–"
                f"{member['rebuilt_word_end']} | {member['live_word_start']}–"
                f"{member['live_word_end']} |"
            )
        lines.append("")
        evidence_block = record.get("collision_cause_evidence", {})
        lines.append(
            f"- Evidence: {evidence_block.get('distinct_rebuilt_id_windows')} distinct rebuilt "
            f"window(s), {evidence_block.get('distinct_normalization_versions')} normalization "
            f"version(s), {evidence_block.get('distinct_timed_transcript_artifact_hashes')} "
            "ASR artifact hash(es) — so the cause is **not** normalization and **not** an "
            "input artifact conflict."
        )
        lines.append("")
    lines.append("## 4. The three choices")
    lines.append("")
    lines.append(
        "**(a) Rebuild the source text and timing from a single voted layer.** Fix the "
        "upstream disagreement (use the voted word-timed artifact for BOTH the text and the "
        "offsets) and re-run Phase 3. This produces exact spans, but it re-keys the "
        "rebuilt ids, which invalidates the Phase-2 verdicts, the rights join and the tier "
        "manifests — all of it must be re-run. It is the only option that removes the "
        "variants rather than dispositioning them."
    )
    lines.append("")
    lines.append(
        "**(b) Retain them as non-serving review variants.** Keep the rows as they are, "
        "permanently outside every serving tier, as review material for a future rebuild."
    )
    lines.append("")
    lines.append(
        "**(c) Exclude them permanently.** Drop the variant population from the corpus "
        "altogether and record the exclusion."
    )
    lines.append("")
    lines.append("## 5. The 1,127 original variant rows")
    lines.append("")
    lines.append(
        "One row per **source span**. `rebuilt id` is the deterministic id; the two rows "
        "that share one are the collision members."
    )
    lines.append("")
    lines.append(
        "| # | live source span id | rebuilt id | video | rebuilt window | reconstruction | "
        "| decision |"
    )
    lines.append("|---:|---|---|---|---|---|---|")
    for index, row in enumerate(phase3_rows, start=1):
        lines.append(
            f"| {index} | `{row.get('live_source_span_id') or ''}` | "
            f"`{row.get('source_span_id') or ''}` | `{row.get('video_id')}` | "
            f"{row.get('word_start')}–{row.get('word_end')} | "
            f"{row.get('reconstruction_tier')} | |"
        )
    lines.append("")
    lines.append("## 6. Decision")
    lines.append("")
    lines.append(DECISION_EMPTY)
    lines.append("")
    lines.append("- Choice (a / b / c): ____________________")
    lines.append("- Owner signature: ____________________")
    lines.append("- Date (UTC): ____________________")
    lines.append("- Notes / conditions: ____________________")
    lines.append("")
    _append_decision_record(
        lines,
        decisions,
        "b7_variant_tier",
        title="variant-tier disposition",
        intro=(
            "`choice` is one of `rebuild_from_one_voted_transcript_layer`, "
            "`retain_review_only_never_serve` or `exclude_permanently`. "
            "`deterministic_id_collision` stays `remain_excluded`: a variant decision never "
            "admits the two collision members."
        ),
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 4 — clinician
# ---------------------------------------------------------------------------
def clinician_packet(
    evidence: Path, date: str, repo_root: Path, decisions: dict[str, dict[str, Any]]
) -> str:
    lines: list[str] = []
    lines.append("# Owner decision packet — distress-classifier boundary (clinician review)")
    lines.append("")
    lines.append(
        "**This is a question, not an approval.** The agent did not change the boundary and "
        "does not propose a new threshold. The brief is explicit: **the agent must not tune "
        "this boundary without clinician review.**"
    )
    lines.append("")
    lines.append("## 1. What is being decided")
    lines.append("")
    lines.append(
        "The first-person bridge declines a clip when the deterministic distress assessor "
        "reports level `>= MODERATE` (`_DISTRESS_DECLINE_LEVEL = 2`, "
        "`backend/app/pipeline/stages/first_person_bridge.py`). For a set of **benign, "
        "on-topic questions** the assessor reports `MODERATE` on a single emotion keyword "
        "(for example *anxiety*, *fear*, *broken*, *angry*). The graph then routes the "
        "seeker to scripted compassion boilerplate instead of the teacher's clip."
    )
    lines.append("")
    lines.append(
        "This is **collection-independent** and **pre-dates the v9/v10 corpus work**: no "
        "amount of corpus growth lifts those answers, because the decline happens before "
        "the clip is chosen."
    )
    lines.append("")
    lines.append("## 2. Current crisis and harm behaviour (unchanged by this work)")
    lines.append("")
    lines.append(
        "- Acute self-harm, harm-to-others and crisis phrases are handled by the "
        "deterministic guardrail rails and the reviewed helpline list "
        "(`config/helplines.yaml`). They are **not** affected by the boundary below."
    )
    lines.append(
        "- The owner-only local review preview preserves the same rails: a crisis question "
        "returns `crisis_redirect` with helplines and **0 citations**; a harm-to-others "
        "intent returns `crisis_redirect` with **0 citations**."
    )
    lines.append(
        "- The public first-person route still abstains with `serving_contract_violation` "
        "and **0 citations** — nothing is served publicly while the B4 contract is open."
    )
    lines.append("")
    lines.append("## 3. The affected cases (measured, not asserted)")
    lines.append("")
    affected = _measure_distress(repo_root)
    if affected.get("available"):
        lines.append(
            f"Measured on the **{affected['on_topic_total']}** synthetic on-topic gold "
            f"questions (`evals/gold_set_v1/questions.jsonl`, type `on_topic`):"
        )
        lines.append("")
        lines.append("| Distress level | Questions |")
        lines.append("|---|---:|")
        for level, count in sorted(affected["level_counts"].items()):
            lines.append(f"| `{level}` | {count} |")
        lines.append("")
        lines.append(
            f"**{affected['at_or_above_moderate']} of {affected['on_topic_total']}** "
            "benign on-topic questions reach `MODERATE` or above and therefore lose the "
            "teacher's clip."
        )
        lines.append("")
        lines.append(
            "| # | question id | question | level | signals | owner decision |"
        )
        lines.append("|---:|---|---|---|---|---|")
        for index, row in enumerate(affected["affected"], start=1):
            lines.append(
                f"| {index} | `{row['id']}` | {row['text']} | `{row['level']}` | "
                f"{', '.join(row['signals'])} | |"
            )
        lines.append("")
    else:
        lines.append(
            "_The distress measurement could not be reproduced in this environment: "
            f"{affected.get('reason')}. Re-run the packet builder on a host with the "
            "backend virtual environment._"
        )
        lines.append("")
    lines.append("## 4. The behaviour options (for the clinician to choose between)")
    lines.append("")
    lines.append(
        "**Option 1 — keep the boundary as it is.** A benign question that mentions "
        "*anxiety* gets compassion boilerplate, never the clip. Safest for a seeker in "
        "distress; loses the teacher's teaching on questions that are not about the "
        "seeker's own distress."
    )
    lines.append("")
    lines.append(
        "**Option 2 — return compassion AND the clip.** The seeker gets the scripted "
        "compassion *and* the teacher's verbatim clip. Matches the owner-locked posture "
        "*\"serve the teacher's verbatim clip\"* and the `first_person_mode=hybrid` shape, "
        "but requires the pipeline to carry both, and changes what a distressed seeker "
        "sees."
    )
    lines.append("")
    lines.append(
        "**Option 3 — narrow the keyword rule.** Reduce the false positives by requiring "
        "more than a single emotion keyword before the bridge declines. **This is the "
        "option that changes a safety boundary, and it is exactly the one the agent is "
        "not allowed to implement without this review.**"
    )
    lines.append("")
    lines.append(
        "> Router-margin data measured earlier (2026-10-19, do not re-tune without this "
        "review): a DISTRESS embedding-route threshold of `0.66` produced 32/150 on-topic "
        "hijacks, `0.72` produced 10, but at `0.74+` the string *\"I am suicidal\"* stops "
        "matching the router (it is still caught by the `self_harm` rail and by "
        "`assess_distress`)."
    )
    lines.append("")
    lines.append("## 5. Decision")
    lines.append("")
    lines.append(DECISION_EMPTY)
    lines.append("")
    lines.append("- Clinician name / credential: ____________________")
    lines.append("- Signature: ____________________")
    lines.append("- Date (UTC): ____________________")
    lines.append("- Option chosen (1 / 2 / 3): ____________________")
    lines.append("- Conditions / follow-up tests required: ____________________")
    lines.append("")
    lines.append("## 6. What this packet does NOT decide")
    lines.append("")
    lines.append(
        "- It does not change any threshold. Nothing in this repository was changed by the "
        "agent for this issue."
    )
    lines.append(
        "- It does not approve a public release; the public route abstains with zero "
        "citations regardless of this decision."
    )
    lines.append("")
    _append_decision_record(
        lines,
        decisions,
        "b6_clinician_safety",
        title="distress-classifier boundary disposition",
        intro=(
            "`option` is `\"1\"`, `\"2\"` or `\"3\"`. Option 3 changes a safety boundary and "
            "is not implemented without this decision."
        ),
    )
    return "\n".join(lines)


def _measure_distress(repo_root: Path) -> dict[str, Any]:
    questions_path = repo_root / "evals" / "gold_set_v1" / "questions.jsonl"
    if not questions_path.is_file():
        return {"available": False, "reason": f"missing {questions_path}"}
    try:
        from services.serene_mind_engine import SereneMindEngine
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": f"cannot import the distress assessor: {exc}"}
    try:
        engine = SereneMindEngine()
        questions = [
            json.loads(line)
            for line in questions_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        on_topic = [q for q in questions if q.get("type") == "on_topic"]
        counts: Counter[str] = Counter()
        affected: list[dict[str, Any]] = []
        for question in on_topic:
            assessment = engine.assess_distress(str(question.get("text") or ""))
            level = assessment.level.name
            counts[level] += 1
            if assessment.level.value >= 2:
                affected.append(
                    {
                        "id": question.get("id"),
                        "text": question.get("text"),
                        "level": level,
                        "signals": list(assessment.detected_signals),
                    }
                )
        return {
            "available": True,
            "on_topic_total": len(on_topic),
            "level_counts": dict(counts),
            "at_or_above_moderate": len(affected),
            "affected": affected,
        }
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# 5 — gold label
# ---------------------------------------------------------------------------
def gold_label_packet(
    evidence: Path, date: str, repo_root: Path, decisions: dict[str, dict[str, Any]]
) -> str:
    gold_dir = repo_root / "evals" / "gold_set_v1"
    lines: list[str] = []
    lines.append("# Owner decision packet — human speaker labels and gold labels (B7)")
    lines.append("")
    lines.append(
        "**This is a request for human work, not an approval.** Nothing here was labelled by "
        "an agent. AI labels are hints, never gold."
    )
    lines.append("")
    lines.append("## 1. Why this is still open")
    lines.append("")
    lines.append(
        "Every speaker attribution in the corpus is **automated evidence**: a pinned ECAPA "
        "model scored against a reference voiceprint widened from two human-confirmed anchor "
        "moments. The repository contains no filled human speaker-label sheet, so no "
        "attribution has been human-certified. B7 stays open until it is."
    )
    lines.append("")
    lines.append("## 2. What is needed")
    lines.append("")
    lines.append("| Requirement | Value |")
    lines.append("|---|---:|")
    lines.append("| Gold labels required by the calibration gate | 299 |")
    annotator_rows = 0
    blank_speaker_cells = 0
    annotators: list[str] = []
    if gold_dir.is_dir():
        for name in sorted(p.name for p in gold_dir.glob("annotator_*.csv")):
            annotators.append(name)
            with (gold_dir / name).open("r", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            annotator_rows = max(annotator_rows, len(rows))
            for row in rows:
                if not (row.get("speaker_is_teacher_yes_no_unsure") or "").strip():
                    blank_speaker_cells += 1
    lines.append(f"| Annotation rows per annotator sheet | {annotator_rows} |")
    lines.append(f"| Annotator sheets present | {', '.join(annotators) or '—'} |")
    lines.append(f"| Blank human speaker-certification cells remaining | {blank_speaker_cells} |")
    lines.append("")
    lines.append("## 3. The sheets")
    lines.append("")
    lines.append(
        "- `evals/gold_set_v1/annotator_A.csv`, `evals/gold_set_v1/annotator_B.csv` — "
        "one row per (question, clip) pair."
    )
    lines.append(
        "- `speaker_label` is machine-derived and **already filled**; it is the claim under "
        "test, not the answer."
    )
    lines.append(
        "- `speaker_is_teacher_yes_no_unsure` is the **human** certification column and is "
        "**empty on every row**. That is the work."
    )
    lines.append("- `relevance_0_3`, `complete_yes_no` and `risk_yes_no` are also empty and "
                 "are the calibration gate's inputs.")
    lines.append("- `video_url_with_timestamp` + `duration_s` give the exact audio window to "
                 "listen to.")
    lines.append("")
    lines.append("## 4. Annotation instructions")
    lines.append("")
    lines.append(
        "1. Open `video_url_with_timestamp` and listen to `duration_s` seconds of audio."
    )
    lines.append(
        "2. Fill `speaker_is_teacher_yes_no_unsure` with **yes** / **no** / **unsure**. "
        "*yes* = the voice in this window is the named teacher (`speaker_label`). *no* = it is "
        "a different teacher (or a non-teacher speaker). *unsure* = you cannot tell."
    )
    lines.append(
        "3. Fill `relevance_0_3`: `1` = unrelated to the question, `2` = related but not a "
        "direct answer, `3` = a direct answer."
    )
    lines.append(
        "4. Fill `complete_yes_no`: `f` = the thought is complete, `i` = incomplete."
    )
    lines.append("5. Fill `risk_yes_no`: `y` = safety-sensitive content, `n` = not.")
    lines.append(
        "6. Do **not** edit `speaker_label`, `clip_text` or the hashes — they pin the "
        "evidence. A disagreement is recorded in `notes`, never by rewriting the row."
    )
    lines.append("")
    lines.append("## 5. Recommended audio review workflow")
    lines.append("")
    lines.append(
        "Use the repository's own labelling CLI rather than a spreadsheet, so the labels "
        "are appended in the format the calibration gate reads:"
    )
    lines.append("")
    lines.append("```bash")
    lines.append("cd backend")
    lines.append(".venv/bin/python -m scripts.ops.gold_label_cli \\")
    lines.append("  --candidates .work/autoresearch_fp/to_label.jsonl \\")
    lines.append("  --ai-labels  .work/autoresearch_fp/labels.jsonl \\")
    lines.append("  --out        .work/gold_labels/gold_labels.jsonl")
    lines.append("```")
    lines.append("")
    lines.append(
        "The CLI refuses AI labels: a gold label must carry `rater=human` and "
        "`confidence=ok`. Order the work *hard first* — borderline rows carry the most "
        "calibration value per hour."
    )
    lines.append("")
    lines.append("For the **speaker** certification specifically, the audio window to review "
                 "is the archived WAV named in each conflict row of the speaker packet, or "
                 "the YouTube URL at the same offset. Both are read-only.")
    lines.append("")
    lines.append("## 6. Agreement fields")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|---|---|")
    lines.append("| Annotator A (name) | ____________________ |")
    lines.append("| Annotator B (name) | ____________________ |")
    lines.append("| Rows labelled by A | ______ / " + str(annotator_rows) + " |")
    lines.append("| Rows labelled by B | ______ / " + str(annotator_rows) + " |")
    lines.append("| Agreement rate (speaker certification) | ______ |")
    lines.append("| Disagreements adjudicated by | ____________________ |")
    lines.append("| Gold labels accepted toward the 299 gate | ______ |")
    lines.append("")
    lines.append("## 7. Decision / sign-off")
    lines.append("")
    lines.append(DECISION_EMPTY)
    lines.append("- Reviewer identity: ____________________")
    lines.append("- Date (UTC): ____________________")
    lines.append("- Notes: ____________________")
    lines.append("")
    _append_decision_record(
        lines,
        decisions,
        "b7_human_gold_labels",
        title="human gold labels and agreement",
        intro=(
            "The two reports named in the block below must exist before this decision can "
            "be approved: the human gold-label report and the agreement / calibration report."
        ),
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 6 — human speaker-label certification
# ---------------------------------------------------------------------------
def speaker_certification_packet(
    evidence: Path, date: str, decisions: dict[str, dict[str, Any]]
) -> str:
    verdicts_path = evidence / f"public_release_phase2_verdicts_{date}.json"
    calibration_path = evidence / f"public_release_phase2_calibration_{date}.json"
    conflicts_path = evidence / f"public_release_phase4_speaker_conflicts_v2_{date}.jsonl"
    served_tier = (
        evidence / f"public_release_phase4_tier_local_review_candidate_{date}.jsonl"
    )

    served_rows = _read_jsonl(served_tier) if served_tier.is_file() else []
    conflict_rows = _read_jsonl(conflicts_path) if conflicts_path.is_file() else []
    verdicts = (
        (_read_json(verdicts_path).get("verdicts") or {}) if verdicts_path.is_file() else {}
    )
    verified = sum(
        1
        for row in served_rows
        if str(
            (verdicts.get(str(row.get("source_span_id") or "")) or {}).get("reason_code") or ""
        )
        == "verified"
    )

    lines: list[str] = []
    lines.append("# Owner decision packet — human speaker-label certification (B7)")
    lines.append("")
    lines.append(
        "**This is a question, not an approval.** No human speaker label was produced by an "
        "agent. AI labels are hints, never gold."
    )
    lines.append("")
    lines.append("## 1. What is being decided")
    lines.append("")
    lines.append(
        "Every speaker attribution in the `local_review_candidate` tier is **automated "
        "evidence**: a pinned ECAPA model scored against a reference voiceprint widened "
        "from two human-confirmed anchor moments. The measured false-accept rate is a "
        "*relative consistency measurement on held-out videos* — **not** a human-certified "
        "error rate and **not** a public attribution certification."
    )
    lines.append("")
    lines.append(
        "You are deciding whether the human speaker-label certification exists: who reviewed "
        "the audio, what label set they reviewed, how many target and non-target clips they "
        "independently labelled, what agreement they reached, and whether the attribution "
        "wording itself is approved for use."
    )
    lines.append("")
    lines.append("## 2. Evidence identity")
    lines.append("")
    lines.append("| Artifact | File | sha256 |")
    lines.append("|---|---|---|")
    for label, path in (
        ("Phase-2 verdicts", verdicts_path),
        ("Phase-2 calibration", calibration_path),
        ("45 speaker conflicts", conflicts_path),
        ("served tier", served_tier),
    ):
        if path.is_file():
            lines.append(f"| {label} | `{path.name}` | `{_sha256_file(path)}` |")
    lines.append("")
    lines.append("## 3. Affected counts")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    lines.append(f"| Spans in the served tier awaiting human speaker certification | "
                 f"{len(served_rows)} |")
    lines.append(f"| Spans carrying a Phase-2 `verified` verdict | {verified} |")
    lines.append(f"| Spans with a contradictory speaker label (quarantined) | "
                 f"{len(conflict_rows)} |")
    lines.append("| Annotator rows per sheet | 303 |")
    lines.append("| Blank human certification cells remaining | 606 |")
    lines.append("")
    lines.append("## 4. What human work this requires")
    lines.append("")
    lines.append(
        "The repository contains **no filled** human speaker-label sheet. The machine column "
        "`speaker_label` is filled; the human column `speaker_is_teacher_yes_no_unsure` is "
        "empty on every row."
    )
    lines.append("")
    lines.append(
        "1. `evals/gold_set_v1/annotator_A.csv` and `annotator_B.csv` — one row per "
        "(question, clip) pair. Fill `speaker_is_teacher_yes_no_unsure` with **yes** / "
        "**no** / **unsure**; `yes` means the voice in the window is the named teacher "
        "(`speaker_label`), `no` means a different teacher or a non-teacher speaker, "
        "`unsure` means it could not be determined."
    )
    lines.append(
        "2. Fill `relevance_0_3` (`1` unrelated, `2` related but not a direct answer, `3` a "
        "direct answer), `complete_yes_no` (`f` complete, `i` incomplete) and `risk_yes_no` "
        "(`y` safety-sensitive, `n` not)."
    )
    lines.append(
        "3. Do **not** edit `speaker_label`, `clip_text` or the hashes — they pin the "
        "evidence. Record a disagreement in `notes`, never by rewriting a row."
    )
    lines.append(
        "4. `video_url_with_timestamp` and `duration_s` give the exact window to listen to. "
        "The archived WAV named in each conflict row of the speaker packet is the same audio."
    )
    lines.append(
        "5. Produce `audits/evidence/public_release_speaker_certification_2026-10-22.json` "
        "from the filled sheets: the reviewers, the label set, the target and non-target "
        "counts, the agreement rate and the attribution wording."
    )
    lines.append("")
    lines.append(
        "Two annotators labelling independently is what makes the agreement rate meaningful. "
        "A single annotator's self-agreement is not inter-annotator agreement and must not "
        "be recorded as such."
    )
    lines.append("")
    lines.append("## 5. Choices")
    lines.append("")
    lines.append("| Choice | Meaning |")
    lines.append("|---|---|")
    lines.append(
        "| `certify` | The human review exists, the counts and agreement are recorded, and "
        "the attribution wording is approved for use. |"
    )
    lines.append(
        "| `certify_with_caveats` | The human review exists but the recorded caveats (for "
        "example the residual 45 conflicts, or clips with `unsure`) must be honoured by a "
        "documented serving rule. |"
    )
    lines.append(
        "| `not_certified` | The human review does not exist yet, or exists but the "
        "attribution wording is not approved. The automated evidence stays labelled as "
        "automated. |"
    )
    lines.append("")
    lines.append(
        "**No default approval.** Until this is decided, every citation in the owner-only "
        "preview carries `AUTOMATED EVIDENCE — NOT HUMAN-CERTIFIED ATTRIBUTION`."
    )
    lines.append("")
    lines.append("## 6. Decision")
    lines.append("")
    _append_decision_record(
        lines,
        decisions,
        "b7_human_speaker_certification",
        title="human speaker-label certification",
    )
    lines.append("## 7. What this packet does NOT decide")
    lines.append("")
    lines.append("- It does not approve the rights register (that is the rights packet).")
    lines.append("- It does not approve the variant tier (that is the variant packet).")
    lines.append("- It does not approve a public release (that is the authorization packet).")
    lines.append("- It does not change a threshold.")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 7 — final staging / public-release authorization
# ---------------------------------------------------------------------------
def authorization_packet(
    evidence: Path, date: str, decisions: dict[str, dict[str, Any]]
) -> str:
    serving_contract = _BACKEND / "config" / "first_person_serving_contract.json"
    local_review_contract = _BACKEND / "config" / "first_person_local_review.json"
    tiers_manifest = evidence / f"public_release_phase4_tiers_manifest_{date}.json"
    served_tier = (
        evidence / f"public_release_phase4_tier_local_review_candidate_{date}.jsonl"
    )
    rights_manifest = evidence / f"public_release_phase4_rights_manifest_{date}.json"
    verdicts_path = evidence / f"public_release_phase2_verdicts_{date}.json"
    conflicts_path = evidence / f"public_release_phase4_speaker_conflicts_v2_{date}.jsonl"

    served_count = len(_read_jsonl(served_tier)) if served_tier.is_file() else 0
    conflict_count = len(_read_jsonl(conflicts_path)) if conflicts_path.is_file() else 0

    lines: list[str] = []
    lines.append("# Owner decision packet — final staging / public-release authorization")
    lines.append("")
    lines.append(
        "**This is a question, not an approval.** Nothing here authorizes anything by being "
        "written down. Each scope below is approved on its own, and **no later approval "
        "implies an earlier one**."
    )
    lines.append("")
    lines.append("## 1. What is being decided")
    lines.append("")
    lines.append(
        "Six independent authorization scopes, in dependency order. Each one is a separate "
        "act with its own evidence:"
    )
    lines.append("")
    lines.append("| # | Scope | What it authorizes | What it does **not** authorize |")
    lines.append("|---|---|---|---|")
    lines.append(
        "| 1 | `owner_only_testing` | The owner-only, local, file-backed preview of the "
        "`local_review_candidate` tier (already available; no public surface). | Any public "
        "traffic. |"
    )
    lines.append(
        "| 2 | `isolated_local_candidate_collection` | Building an **isolated local** "
        "candidate collection from the approved tier, with a snapshot and a rollback path. "
        "| Promoting it, aliasing it, or serving it publicly. |"
    )
    lines.append(
        "| 3 | `staging` | Running the staging-readiness review: staging smoke, safety, "
        "citation, cache and fault suites against the candidate. | Public production. |"
    )
    lines.append(
        "| 4 | `public_production` | Serving the approved corpus to the public surface. | "
        "Alias promotion or harness enablement on their own. |"
    )
    lines.append(
        "| 5 | `alias_promotion` | Moving the public `first_person` alias to the approved "
        "candidate collection. | Enabling the context harness. |"
    )
    lines.append(
        "| 6 | `harness_enablement` | Turning on `FIRST_PERSON_CONTEXT_HARNESS_ENABLED`. | "
        "Any of the five scopes above. |"
    )
    lines.append("")
    lines.append(
        "**Dependency rule.** A scope may only be approved when every earlier scope in the "
        "list is also approved. Approving `public_production` without `staging` is not a "
        "partial approval — it is an invalid authorization record, and the release-gate "
        "controller fails closed on it."
    )
    lines.append("")
    lines.append("## 2. Evidence identity")
    lines.append("")
    lines.append("| Artifact | File | sha256 |")
    lines.append("|---|---|---|")
    for label, path in (
        ("B4 serving contract", serving_contract),
        ("owner-only preview pin set", local_review_contract),
        ("Phase-4 tiers manifest", tiers_manifest),
        ("served tier", served_tier),
        ("rights register", rights_manifest),
        ("Phase-2 verdicts", verdicts_path),
        ("45 speaker conflicts", conflicts_path),
    ):
        if path.is_file():
            lines.append(f"| {label} | `{path.name}` | `{_sha256_file(path)}` |")
    lines.append("")
    lines.append("## 3. Affected counts")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    lines.append("| Public `first_person` alias points at | `first_person_v10` |")
    lines.append(f"| Spans in the served tier | {served_count} |")
    lines.append(f"| Spans with a contradictory speaker label (quarantined) | "
                 f"{conflict_count} |")
    lines.append("| Owner decisions still required before this packet can be completed | 6 |")
    lines.append("| Staging suites required | 5 (smoke, safety, citation, cache, fault) |")
    lines.append("| Authorization scopes | 6 |")
    lines.append("")
    lines.append("## 4. Preconditions for each scope")
    lines.append("")
    lines.append("| Scope | Preconditions that must already hold |")
    lines.append("|---|---|")
    lines.append(
        "| `owner_only_testing` | The owner-only preview works and refuses to run in "
        "production. It already does. |"
    )
    lines.append(
        "| `isolated_local_candidate_collection` | Rights signed off; speaker certification "
        "decided; variant tier decided; clinician decision recorded; gold labels and "
        "agreement reports filed; snapshot and rollback evidence filed. |"
    )
    lines.append(
        "| `staging` | The isolated candidate collection exists with a verified snapshot, "
        "and the staging smoke / safety / citation / cache / fault suites have been run and "
        "recorded in `audits/evidence/public_release_staging_readiness_2026-10-22.json`. |"
    )
    lines.append(
        "| `public_production` | `staging` approved **and** the staging-readiness review "
        "recorded every suite as `pass`. |"
    )
    lines.append(
        "| `alias_promotion` | `public_production` approved **and** "
        "`audits/evidence/public_release_promotion_2026-10-22.json` carries both a snapshot "
        "and a rollback evidence path. |"
    )
    lines.append(
        "| `harness_enablement` | `alias_promotion` approved **and** every other gate in the "
        "release-gate controller passing. |"
    )
    lines.append("")
    lines.append("## 5. Choices")
    lines.append("")
    lines.append("| Value | Meaning |")
    lines.append("|---|---|")
    lines.append(
        "| `pending` | Not decided. **This is the default and there is no default approval.** |"
    )
    lines.append(
        "| `true` | Approved, with reviewer, date and signature recorded at the packet level. |"
    )
    lines.append("| `false` | Explicitly declined. This is a decision too. |")
    lines.append("")
    lines.append("## 6. Decision")
    lines.append("")
    _append_decision_record(
        lines,
        decisions,
        "b7_release_authorization",
        title="final staging / public-release authorization",
        intro=(
            "Each scope is approved on its own. No later scope implies an earlier one; the "
            "controller fails closed if a later scope is approved while an earlier one is "
            "not."
        ),
    )
    lines.append("## 7. What this packet does NOT decide")
    lines.append("")
    lines.append("- It does not approve any content decision. Those are the other packets.")
    lines.append(
        "- It does not enable anything by itself. Each scope still needs its preconditions "
        "and its own recorded approval."
    )
    lines.append(
        "- It does not authorize a deployment to Railway. The public route, the alias and "
        "the harness each remain under their own gate."
    )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--evidence-dir", default=str(_REPO_ROOT / "audits" / "evidence"))
    parser.add_argument("--repo-root", default=str(_REPO_ROOT))
    parser.add_argument("--date", required=True)
    args = parser.parse_args(argv)

    evidence = Path(args.evidence_dir)
    repo_root = Path(args.repo_root)
    out_dir = evidence

    # The owner action form is the single source of truth for owner decisions.
    decisions = _read_owner_form(repo_root, args.date)

    builders = (
        ("rights", rights_packet(evidence, args.date, decisions)),
        ("speaker", speaker_packet(evidence, args.date, decisions)),
        (
            "speaker_certification",
            speaker_certification_packet(evidence, args.date, decisions),
        ),
        ("variant", variant_packet(evidence, args.date, decisions)),
        ("clinician", clinician_packet(evidence, args.date, repo_root, decisions)),
        ("gold_label", gold_label_packet(evidence, args.date, repo_root, decisions)),
        ("authorization", authorization_packet(evidence, args.date, decisions)),
    )

    exit_code = 0
    for name, text in builders:
        path = out_dir / f"public_release_owner_packet_{name}_{args.date}.md"
        path.write_text(text, encoding="utf-8")
        print(f"[fp-packets] wrote {path} ({len(text)} bytes)")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
