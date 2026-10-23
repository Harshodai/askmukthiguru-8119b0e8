#!/usr/bin/env python3
"""Build an INDEPENDENT rights/provenance register for first-person candidate spans.

**Read-only.** This script never writes to Qdrant, never touches an alias, never
mutates an input manifest and never reads a rights field out of a Qdrant
payload. It only reads files on disk and writes new evidence files.

Why this exists
---------------
``docs/FIRST_PERSON_PUBLIC_RELEASE_STATUS_2026-10-21.md`` blocker **B5**: the
rights manifest that shipped with the live first-person collection was derived
from the corpus builder's own engineering allowlist and from the collection's
``rights_cleared`` payload flag. ``docs/rights/source-register.md`` records the
same problem for the sibling corpus: ``domain_rights_status="licensed"`` is an
ingestion-time *default* written to every chunk unconditionally, so it is not
evidence of anything. A payload flag is a **derived** claim; a rights basis is a
**human** decision. This script produces the human side.

Evidence sources, and what each one is allowed to prove
--------------------------------------------------------
``registry`` (``docs/rights/CONTENT-RIGHTS.md``)
    The human-authored registry. Rows are matched by an anchor substring and
    every match must carry an owner-confirmation marker on the *same* table
    row, so an edited or removed row silently stops confirming anything. This
    is the only source that can produce ``confirmed_*``.
``channels`` (corpus ``channels.json`` files)
    Channel identity + video title metadata captured at ingest time. Metadata
    only: it can say *which channel uploaded this video*, never *whether the
    use is permitted*.
``engineering_allowlist`` (``build_first_person_index.py``)
    The corpus builder's ``CLEARED_CHANNELS`` / ``CLEARED_VIDEO_IDS`` sets. This
    is an **engineering input**, not a rights decision. It is used for exactly
    one purpose: to detect assets the builder treats as cleared but the
    registry does not confirm. Those become ``pending_owner_review`` — never
    ``confirmed``.

Rules (fail closed)
-------------------
* Missing rights evidence  -> ``missing_evidence``  -> quarantine.
* Ambiguous rights evidence-> ``ambiguous``          -> quarantine.
* Engineering-allowlist-only -> ``pending_owner_review`` -> quarantine.
* Only a registry row carrying an owner-confirmation marker may produce
  ``confirmed_channel_owner`` / ``confirmed_video_owner``.
* The live collection's ``rights_cleared`` flag is **never** read. When a
  candidate span carries one in its Phase-3 row it is copied through under
  ``payload_rights_cleared_claim`` and explicitly labelled untrusted/derived.

Exit codes
----------
=====  ===================================================================
0      Report produced and no asset was quarantined.
1      Report produced; quarantined assets exist (the ordinary outcome while
       B5 owner confirmation is outstanding). Release-blocking status.
2      No trustworthy report could be produced: an input is unreadable or
       unparseable, the registry document is missing, or the candidate/verdict
       sets disagree structurally. Fail closed.
=====  ===================================================================

Usage
-----
    python -m scripts.ops.build_fp_rights_register \\
        --candidate audits/evidence/public_release_phase3_candidate_2026-10-21.jsonl \\
        --verdicts audits/evidence/public_release_phase2_verdicts_2026-10-22.json \\
        --registry docs/rights/CONTENT-RIGHTS.md \\
        --channels ~/mukthiguru_attribution_data/v9_full_apply_20261018/channels.json \\
        --engineering-allowlist scripts/ops/build_first_person_index.py \\
        --out-manifest audits/evidence/public_release_phase4_rights_manifest_2026-10-22.json \\
        --out-join audits/evidence/public_release_phase4_rights_join_2026-10-22.jsonl \\
        --out-quarantine audits/evidence/public_release_phase4_rights_quarantine_2026-10-22.jsonl \\
        --out-summary audits/evidence/public_release_phase4_rights_summary_2026-10-22.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

SCHEMA = "first-person-rights-register-v1"
JOIN_SCHEMA = "first-person-rights-join-v1"
SCRIPT_VERSION = "build-fp-rights-register-v1"

# Rights statuses. Only the two ``confirmed_*`` values may serve; everything
# else quarantines.
STATUS_CONFIRMED_CHANNEL = "confirmed_channel_owner"
STATUS_CONFIRMED_VIDEO = "confirmed_video_owner"
STATUS_PENDING = "pending_owner_review"
STATUS_MISSING = "missing_evidence"
STATUS_AMBIGUOUS = "ambiguous"

SERVABLE_STATUSES = frozenset({STATUS_CONFIRMED_CHANNEL, STATUS_CONFIRMED_VIDEO})

# Registry entries. Each entry names the substring that must appear on the
# table row in ``docs/rights/CONTENT-RIGHTS.md`` and the owner-confirmation
# marker that must appear on that same row. If the row moves, the marker
# moves with it, or the document changes shape, the entry stops confirming and
# the affected assets quarantine.
REGISTRY_ENTRIES: tuple[dict[str, Any], ...] = (
    {
        "entry_id": "channel:sri-preethaji-krishnaji-ekam",
        "scope": "channel",
        "channels": (
            "sri preethaji & sri krishnaji",
            "ekam",
            "o&o academy",
        ),
        "anchor": '"Sri Preethaji & Sri Krishnaji" / "Ekam / O&O Academy" YouTube channels',
        "confirmation_marker": "stated 2026-09-23",
        "rightsholder": "Sri Preethaji & Sri Krishnaji / Ekam (Oneness)",
        "permission_basis": "owner_confirmed_channel_approval",
        "confirmed_on": "2026-09-23",
    },
    {
        "entry_id": "channel:times-now",
        "scope": "channel",
        "channels": ("times now",),
        "anchor": '"Times Now" (broadcaster news coverage)',
        "confirmation_marker": "stated 2026-09-23",
        "rightsholder": "Times Now",
        "permission_basis": "owner_confirmed_channel_approval",
        "confirmed_on": "2026-09-23",
        "restriction_note": (
            "Third-party broadcaster content re-broadcasting the gurus. The owner's "
            "confirmation covers the channel; the rightsholder of the segment is the "
            "broadcaster, not the gurus' organisation."
        ),
    },
    {
        "entry_id": "video:TqxxCYnAxo8",
        "scope": "video",
        "video_ids": ("TqxxCYnAxo8",),
        "anchor": "TqxxCYnAxo8",
        "confirmation_marker": "stated 2026-09-26",
        "rightsholder": "TEDx / Sri Preethaji",
        "permission_basis": "owner_confirmed_video_approval",
        "confirmed_on": "2026-09-26",
    },
    {
        "entry_id": "video:UlOt31lBhLY",
        "scope": "video",
        "video_ids": ("UlOt31lBhLY",),
        "anchor": "UlOt31lBhLY",
        "confirmation_marker": "stated 2026-09-26",
        "rightsholder": "MarieTV / Sri Preethaji & Sri Krishnaji",
        "permission_basis": "owner_confirmed_video_approval",
        "confirmed_on": "2026-09-26",
    },
)

# Attribution the owner must see when a clip is served. Derived from the
# registry's rightsholder column, not from a payload display label.
PERMITTED_USE = (
    "verbatim transcript excerpt quoted with attribution, plus a source link and "
    "the archived audio window for playback"
)
ATTRIBUTION_REQUIREMENT = (
    "name the rightsholder and the teacher the excerpt is attributed to, and "
    "link the canonical source URL"
)

# Review cadence from docs/rights/CONTENT-RIGHTS.md ("Review rights basis
# annually or when ingestion corpus changes significantly").
REVIEW_INTERVAL_DAYS = 365


class RightsRegisterError(RuntimeError):
    """Raised when no trustworthy register can be produced."""


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RightsRegisterError(f"{path}:{lineno} is not valid JSON: {exc}") from exc
            if not isinstance(row, dict):
                raise RightsRegisterError(f"{path}:{lineno} is not a JSON object")
            rows.append(row)
    return rows


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RightsRegisterError(f"cannot read JSON from {path}: {exc}") from exc


def _add_one_year(iso_date: str) -> str:
    import datetime

    try:
        base = datetime.date.fromisoformat(iso_date)
    except ValueError:
        return ""
    try:
        nxt = base.replace(year=base.year + REVIEW_INTERVAL_DAYS // 365)
    except ValueError:  # 29 Feb
        nxt = base.replace(year=base.year + 1, day=28)
    return nxt.isoformat()


# ---------------------------------------------------------------------------
# registry parsing
# ---------------------------------------------------------------------------
def parse_registry(path: Path) -> dict[str, Any]:
    """Match the human registry rows and return the applied entries.

    An entry applies only when its anchor and its owner-confirmation marker
    are on the SAME markdown table row. Anything else means the registry no
    longer says what this script believes it says, so the entry does not
    apply and the assets it would have covered quarantine instead.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RightsRegisterError(f"cannot read rights registry {path}: {exc}") from exc

    lines = text.splitlines()
    applied: list[dict[str, Any]] = []
    not_applied: list[dict[str, Any]] = []
    for entry in REGISTRY_ENTRIES:
        anchor = str(entry["anchor"])
        marker = str(entry["confirmation_marker"])
        matched_row: str | None = None
        for line in lines:
            if not line.lstrip().startswith("|"):
                continue
            if anchor in line:
                matched_row = line
                break
        if matched_row is None:
            not_applied.append({**entry, "reason": "registry_row_anchor_not_found"})
            continue
        if marker not in matched_row:
            not_applied.append(
                {
                    **entry,
                    "reason": "registry_row_has_no_owner_confirmation_marker",
                    "row_excerpt": matched_row[:240],
                }
            )
            continue
        applied.append({**entry, "row_excerpt": matched_row[:240]})
    return {
        "path": str(path),
        "sha256": _sha256_file(path),
        "byte_length": path.stat().st_size,
        "applied": applied,
        "not_applied": not_applied,
        "review_interval_days": REVIEW_INTERVAL_DAYS,
    }


def parse_engineering_allowlist(path: Path) -> dict[str, Any]:
    """Read the builder's CLEARED_CHANNELS / CLEARED_VIDEO_IDS.

    These are engineering inputs. They can prove that the *builder* treated a
    channel as cleared; they can never prove a rights basis.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RightsRegisterError(f"cannot read engineering allowlist {path}: {exc}") from exc

    def _extract(name: str) -> list[str]:
        match = re.search(name + r"\s*=\s*\{(.*?)\}", text, re.DOTALL)
        if not match:
            return []
        return re.findall(r'"([^"]+)"', match.group(1))

    channels = [c.strip().casefold() for c in _extract("CLEARED_CHANNELS")]
    videos = [v.strip() for v in _extract("CLEARED_VIDEO_IDS")]
    return {
        "path": str(path),
        "sha256": _sha256_file(path),
        "cleared_channels": channels,
        "cleared_video_ids": videos,
        "authority": "engineering_input_only_not_a_rights_decision",
    }


def load_channels(paths: list[Path]) -> dict[str, dict[str, Any]]:
    """Merge channel metadata files (later files do not override earlier ones)."""
    merged: dict[str, dict[str, Any]] = {}
    for path in paths:
        data = _read_json(path)
        if not isinstance(data, dict):
            raise RightsRegisterError(f"channel metadata {path} must be a JSON object")
        for video_id, meta in data.items():
            if not isinstance(meta, dict):
                continue
            merged.setdefault(str(video_id), dict(meta))
    return merged


def load_titles(path: Path | None) -> dict[str, str]:
    """Optional inventory with video titles (metadata only)."""
    if path is None or not path.is_file():
        return {}
    data = _read_json(path)
    titles: dict[str, str] = {}
    records = data if isinstance(data, list) else list(data.values())
    for record in records:
        if not isinstance(record, dict):
            continue
        video_id = str(record.get("video_id") or "").strip()
        title = str(record.get("title") or "").strip()
        if video_id and title:
            titles[video_id] = title
    return titles


# ---------------------------------------------------------------------------
# per-asset determination
# ---------------------------------------------------------------------------
def _entry_for_video(
    video_id: str,
    channel: str,
    registry: dict[str, Any],
) -> tuple[dict[str, Any] | None, str]:
    """Return the applied registry entry for a video, plus the reason code."""
    for entry in registry["applied"]:
        if entry["scope"] == "video" and video_id in entry.get("video_ids", ()):
            return entry, "registry_video_entry"
    channel_key = (channel or "").strip().casefold()
    for entry in registry["applied"]:
        if entry["scope"] != "channel":
            continue
        if channel_key in tuple(entry.get("channels", ())):
            return entry, "registry_channel_entry"
    return None, "no_registry_entry"


def determine_asset_rights(
    *,
    video_id: str,
    channel: str,
    title: str,
    registry: dict[str, Any],
    engineering: dict[str, Any],
    payload_rights_claim: bool | None,
) -> dict[str, Any]:
    """Determine the rights status of ONE source asset."""
    entry, reason = _entry_for_video(video_id, channel, registry)
    engineering_only = False
    if entry is None:
        # Engineering allowlist can only move an asset to "pending", never to
        # "confirmed".
        channel_key = (channel or "").strip().casefold()
        engineering_only = (
            channel_key in set(engineering["cleared_channels"])
            or video_id in set(engineering["cleared_video_ids"])
        )

    asset: dict[str, Any] = {
        "source_asset_id": video_id,
        "video_id": video_id,
        "canonical_source_url": f"https://www.youtube.com/watch?v={video_id}",
        "title": title or "",
        "channel": channel or "",
        "rightsholder": "",
        "permission_basis": "",
        "permitted_use": PERMITTED_USE,
        "attribution_requirements": ATTRIBUTION_REQUIREMENT,
        "review_date": "",
        "last_reviewed": "",
        "evidence_document": registry["path"],
        "evidence_url": registry["path"],
        "evidence_sha256": registry["sha256"],
        "owner_review_status": "",
        "ambiguity_reason": "",
        "restriction_reason": "",
        "engineering_allowlist_only": engineering_only,
        # The live collection's own flag. Carried through for comparison only,
        # explicitly untrusted: it is a derived claim, never evidence.
        "payload_rights_cleared_claim_untrusted": payload_rights_claim,
        "registry_entry_id": "",
    }

    if entry is not None:
        asset["rights_status"] = (
            STATUS_CONFIRMED_VIDEO if entry["scope"] == "video" else STATUS_CONFIRMED_CHANNEL
        )
        asset["registry_entry_id"] = entry["entry_id"]
        asset["rightsholder"] = entry["rightsholder"]
        asset["permission_basis"] = entry["permission_basis"]
        asset["last_reviewed"] = entry["confirmed_on"]
        asset["review_date"] = _add_one_year(entry["confirmed_on"])
        asset["owner_review_status"] = f"owner_confirmed_{entry['confirmed_on']}"
        asset["restriction_reason"] = entry.get("restriction_note", "")
        asset["determination_reason"] = reason
        return asset

    asset["determination_reason"] = reason
    if not channel:
        asset["rights_status"] = STATUS_MISSING
        asset["owner_review_status"] = "unknown"
        asset["ambiguity_reason"] = "no_channel_identity_recorded_for_asset"
        return asset
    if engineering_only:
        asset["rights_status"] = STATUS_PENDING
        asset["owner_review_status"] = "pending_owner_review"
        asset["ambiguity_reason"] = (
            "engineering_allowlist_clears_this_asset_but_the_rights_registry_does_not_"
            "confirm_it"
        )
        return asset
    asset["rights_status"] = STATUS_MISSING
    asset["owner_review_status"] = "unknown"
    asset["ambiguity_reason"] = "channel_not_present_in_the_rights_registry"
    return asset


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def build(args: argparse.Namespace) -> dict[str, Any]:
    candidate_path = Path(args.candidate)
    verdicts_path = Path(args.verdicts)
    registry_path = Path(args.registry)
    if not candidate_path.is_file():
        raise RightsRegisterError(f"candidate manifest not found: {candidate_path}")
    if not verdicts_path.is_file():
        raise RightsRegisterError(f"verdict manifest not found: {verdicts_path}")
    if not registry_path.is_file():
        raise RightsRegisterError(f"rights registry not found: {registry_path}")

    candidates = _read_jsonl(candidate_path)
    if not candidates:
        raise RightsRegisterError("candidate manifest is empty")

    verdict_index = _read_json(verdicts_path)
    if not isinstance(verdict_index, dict) or not isinstance(
        verdict_index.get("verdicts"), dict
    ):
        raise RightsRegisterError("verdict manifest has no 'verdicts' object")

    registry = parse_registry(registry_path)
    engineering = parse_engineering_allowlist(Path(args.engineering_allowlist))
    channels = load_channels([Path(p) for p in args.channels])
    titles = load_titles(Path(args.titles) if args.titles else None)

    # ---- per-asset ---------------------------------------------------------
    candidate_videos = {str(row.get("video_id") or "").strip() for row in candidates}
    assets: dict[str, dict[str, Any]] = {}
    # The universe is every video the corpus metadata knows about, so the
    # register also covers assets that are NOT in the candidate (those are
    # listed with in_candidate=false). This is what makes an
    # engineering-allowlist-only asset visible instead of invisible.
    for video_id in sorted(set(channels) | candidate_videos):
        meta = channels.get(video_id, {})
        channel = str(meta.get("channel") or "").strip()
        payload_claim = None
        for row in candidates:
            if str(row.get("video_id") or "").strip() == video_id:
                claim = row.get("rights_cleared")
                if isinstance(claim, bool):
                    payload_claim = claim
                break
        assets[video_id] = determine_asset_rights(
            video_id=video_id,
            channel=channel,
            title=titles.get(video_id, ""),
            registry=registry,
            engineering=engineering,
            payload_rights_claim=payload_claim,
        )
        assets[video_id]["in_candidate"] = video_id in candidate_videos

    # ---- join --------------------------------------------------------------
    join_rows: list[dict[str, Any]] = []
    quarantine_rows: list[dict[str, Any]] = []
    seen_span_ids: set[str] = set()
    for row in candidates:
        span_id = str(row.get("source_span_id") or "").strip()
        video_id = str(row.get("video_id") or "").strip()
        if not span_id:
            raise RightsRegisterError("candidate row without source_span_id")
        if span_id in seen_span_ids:
            raise RightsRegisterError(f"duplicate source_span_id in candidate: {span_id}")
        seen_span_ids.add(span_id)
        asset = assets[video_id]
        verdict = verdict_index["verdicts"].get(span_id)
        join = {
            "schema": JOIN_SCHEMA,
            "source_span_id": span_id,
            "video_id": video_id,
            "guru_id": str(row.get("guru_id") or ""),
            "rights_status": asset["rights_status"],
            "owner_review_status": asset["owner_review_status"],
            "servable": asset["rights_status"] in SERVABLE_STATUSES,
            "quarantine_reason": (
                "" if asset["rights_status"] in SERVABLE_STATUSES else asset["ambiguity_reason"]
            ),
            "rights_evidence_document": asset["evidence_document"],
            "rights_evidence_sha256": asset["evidence_sha256"],
            "rights_review_date": asset["review_date"],
            "payload_rights_cleared_claim_untrusted": asset[
                "payload_rights_cleared_claim_untrusted"
            ],
            "speaker_verdict": str((verdict or {}).get("reason_code") or "missing_verdict"),
        }
        join_rows.append(join)
        if not join["servable"]:
            quarantine_rows.append(
                {
                    **join,
                    "canonical_source_url": asset["canonical_source_url"],
                    "title": asset["title"],
                    "channel": asset["channel"],
                    "rightsholder": asset["rightsholder"],
                    "ambiguity_reason": asset["ambiguity_reason"],
                    "restriction_reason": asset["restriction_reason"],
                }
            )

    # ---- summaries ---------------------------------------------------------
    status_counts = Counter(a["rights_status"] for a in assets.values())
    candidate_status_counts = Counter(
        a["rights_status"] for a in assets.values() if a["in_candidate"]
    )
    asset_span_counts = Counter()
    for row in join_rows:
        asset_span_counts[row["rights_status"]] += 1

    span_status_counts = Counter(row["rights_status"] for row in join_rows)
    confirmed_but_unverified = sum(
        1
        for row in join_rows
        if row["rights_status"] in SERVABLE_STATUSES
        and row["speaker_verdict"] != "verified"
    )

    manifest = {
        "schema": SCHEMA,
        "script_version": SCRIPT_VERSION,
        "generated_at_utc": args.generated_at_utc,
        "independent_sources": {
            "rights_registry": {
                "path": registry["path"],
                "sha256": registry["sha256"],
                "byte_length": registry["byte_length"],
                "applied_entries": [e["entry_id"] for e in registry["applied"]],
                "not_applied_entries": [
                    {"entry_id": e["entry_id"], "reason": e["reason"]}
                    for e in registry["not_applied"]
                ],
                "authority": "human_authored_owner_decision",
            },
            "channel_metadata": {
                "paths": [str(p) for p in args.channels],
                "authority": "ingest_time_metadata_only",
            },
            "engineering_allowlist": {
                "path": engineering["path"],
                "sha256": engineering["sha256"],
                "authority": engineering["authority"],
            },
        },
        "policy": {
            "servable_statuses": sorted(SERVABLE_STATUSES),
            "quarantine_rule": (
                "missing rights evidence, ambiguous rights, or engineering-allowlist-only "
                "coverage quarantines every associated span"
            ),
            "payload_flags_are_evidence": False,
            "permitted_use": PERMITTED_USE,
            "attribution_requirements": ATTRIBUTION_REQUIREMENT,
            "review_interval_days": REVIEW_INTERVAL_DAYS,
        },
        "asset_count": len(assets),
        "candidate_asset_count": len(candidate_videos),
        "span_count": len(join_rows),
        "assets": [assets[key] for key in sorted(assets)],
    }

    summary = {
        "schema": "first-person-rights-summary-v1",
        "script_version": SCRIPT_VERSION,
        "generated_at_utc": args.generated_at_utc,
        "asset_count": len(assets),
        "candidate_asset_count": len(candidate_videos),
        "span_count": len(join_rows),
        "rights_status_counts_by_asset": dict(sorted(status_counts.items())),
        "rights_status_counts_by_candidate_asset": dict(sorted(candidate_status_counts.items())),
        "rights_status_counts_by_span": dict(sorted(span_status_counts.items())),
        "servable_asset_count": sum(
            1 for a in assets.values() if a["rights_status"] in SERVABLE_STATUSES
        ),
        "servable_candidate_asset_count": sum(
            1
            for a in assets.values()
            if a["rights_status"] in SERVABLE_STATUSES and a["in_candidate"]
        ),
        "servable_span_count": sum(1 for r in join_rows if r["servable"]),
        "quarantined_span_count": len(quarantine_rows),
        "quarantined_asset_count": len(
            {r["video_id"] for r in quarantine_rows}
        ),
        "quarantined_universe_asset_count": sum(
            1 for a in assets.values() if a["rights_status"] not in SERVABLE_STATUSES
        ),
        "confirmed_but_speaker_unverified_spans": confirmed_but_unverified,
        "registry_entries_applied": [e["entry_id"] for e in registry["applied"]],
        "registry_entries_not_applied": [
            {"entry_id": e["entry_id"], "reason": e["reason"]} for e in registry["not_applied"]
        ],
        "b5_exit_gate_met": False,
        "release_blocking": True,
        "register_owner_confirmation": "pending_owner_review",
        "notes": [
            "The live collection's rights_cleared flag is never read as evidence.",
            "A registry row confirms an asset only when its owner-confirmation marker "
            "is on the same markdown table row.",
            "This register has not yet been signed off by the owner for the "
            "fp-context-transcript-v2 corpus: B5 stays open.",
        ],
    }

    return {
        "manifest": manifest,
        "join": join_rows,
        "quarantine": quarantine_rows,
        "summary": summary,
        "assets": assets,
    }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def render_report(result: dict[str, Any], args: argparse.Namespace) -> str:
    manifest = result["manifest"]
    summary = result["summary"]
    assets = result["assets"]
    by_status: dict[str, list[dict[str, Any]]] = {}
    for asset in assets.values():
        by_status.setdefault(asset["rights_status"], []).append(asset)

    lines: list[str] = []
    lines.append("# B5 — independent rights register (human-readable)")
    lines.append("")
    lines.append(f"**Generated:** {args.generated_at_utc}")
    lines.append(
        f"**Register owner confirmation:** {summary['register_owner_confirmation']} — "
        "**B5 remains open.**"
    )
    lines.append("")
    lines.append("This register is built from `docs/rights/CONTENT-RIGHTS.md` (human-authored, ")
    lines.append("owner-confirmed) and ingest-time channel metadata. It does **not** read any ")
    lines.append("rights field from a Qdrant payload; the payload flag is carried through only ")
    lines.append("as `payload_rights_cleared_claim_untrusted`, for comparison.")
    lines.append("")
    lines.append("## Counts by rights status")
    lines.append("")
    lines.append("| Rights status | Assets (universe) | Assets (in candidate) | Candidate spans | Servable |")
    lines.append("|---|---:|---:|---:|---|")
    for status in sorted(by_status):
        asset_n = len(by_status[status])
        cand_n = sum(1 for a in by_status[status] if a.get("in_candidate"))
        span_n = summary["rights_status_counts_by_span"].get(status, 0)
        servable = "yes" if status in SERVABLE_STATUSES else "**no**"
        lines.append(f"| `{status}` | {asset_n} | {cand_n} | {span_n} | {servable} |")
    lines.append(
        f"| **total** | **{manifest['asset_count']}** | "
        f"**{manifest['candidate_asset_count']}** | **{manifest['span_count']}** | |"
    )
    lines.append("")
    lines.append("## Evidence sources")
    lines.append("")
    sources = manifest["independent_sources"]
    lines.append(
        f"- Rights registry: `{sources['rights_registry']['path']}` "
        f"(sha256 `{sources['rights_registry']['sha256'][:16]}…`, "
        f"{sources['rights_registry']['byte_length']} bytes)"
    )
    lines.append(f"- Registry entries applied: {sources['rights_registry']['applied_entries']}")
    if sources["rights_registry"]["not_applied_entries"]:
        lines.append(
            f"- Registry entries **not** applied: {sources['rights_registry']['not_applied_entries']}"
        )
    lines.append(
        f"- Engineering allowlist (not a rights decision): "
        f"`{sources['engineering_allowlist']['path']}` "
        f"(sha256 `{sources['engineering_allowlist']['sha256'][:16]}…`)"
    )
    lines.append(f"- Channel metadata: {sources['channel_metadata']['paths']}")
    lines.append("")
    lines.append("## Quarantined assets")
    lines.append("")
    quarantined = [a for a in assets.values() if a["rights_status"] not in SERVABLE_STATUSES]
    if not quarantined:
        lines.append(
            "No asset is quarantined on rights grounds: every asset's channel (or the "
            "video itself) carries an owner confirmation in the registry."
        )
    else:
        lines.append(
            f"{len(quarantined)} asset(s) quarantined "
            f"({sum(1 for a in quarantined if a.get('in_candidate'))} of them inside the "
            "candidate corpus)."
        )
        lines.append("")
        lines.append("| Video | Channel | Status | In candidate | Reason |")
        lines.append("|---|---|---|---|---|")
        for asset in sorted(quarantined, key=lambda a: a["video_id"]):
            lines.append(
                f"| `{asset['video_id']}` | {asset['channel']} | `{asset['rights_status']}` | "
                f"{'yes' if asset.get('in_candidate') else 'no'} | "
                f"{asset['ambiguity_reason']} |"
            )
    lines.append("")
    lines.append("## What still blocks B5")
    lines.append("")
    lines.append("1. The owner has not signed off **this register** for the "
                 "`fp-context-transcript-v2` candidate corpus.")
    lines.append("2. Every confirmation is the owner's statement recorded in the registry; "
                 "no agent can verify it independently (repo rule N9).")
    lines.append("3. The registry's review cadence is annual; the candidate corpus was "
                 "ingested after the last confirmation.")
    lines.append("")
    lines.append("## Safe use")
    lines.append("")
    lines.append("Only `confirmed_*` assets may enter a serving candidate. Everything else "
                 "is quarantined and excluded from the owner-only test mode and from any "
                 "future public candidate.")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--candidate", required=True, help="Phase-3 candidate JSONL")
    parser.add_argument("--verdicts", required=True, help="Phase-2 verdict index JSON")
    parser.add_argument("--registry", required=True, help="rights registry markdown")
    parser.add_argument(
        "--channels",
        action="append",
        default=[],
        help="channel metadata JSON (repeatable)",
    )
    parser.add_argument("--titles", default=None, help="optional inventory JSON with titles")
    parser.add_argument(
        "--engineering-allowlist",
        default="scripts/ops/build_first_person_index.py",
        help="corpus builder module holding CLEARED_CHANNELS/CLEARED_VIDEO_IDS",
    )
    parser.add_argument("--out-manifest", required=True)
    parser.add_argument("--out-join", required=True)
    parser.add_argument("--out-quarantine", required=True)
    parser.add_argument("--out-summary", required=True)
    parser.add_argument("--out-report", default=None)
    parser.add_argument(
        "--generated-at-utc",
        default=os.environ.get("FP_RIGHTS_GENERATED_AT_UTC", ""),
        help="pinned timestamp for byte-identical repeats",
    )
    args = parser.parse_args(argv)

    try:
        result = build(args)
    except RightsRegisterError as exc:
        print(f"[fp-rights] ERROR: {exc}", file=sys.stderr)
        return 2

    _write_json(Path(args.out_manifest), result["manifest"])
    _write_jsonl(Path(args.out_join), result["join"])
    _write_jsonl(Path(args.out_quarantine), result["quarantine"])
    _write_json(Path(args.out_summary), result["summary"])
    if args.out_report:
        Path(args.out_report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_report).write_text(render_report(result, args), encoding="utf-8")

    summary = result["summary"]
    print(
        "[fp-rights] assets={assets} spans={spans} servable_spans={servable} "
        "quarantined_spans={quarantined}".format(
            assets=summary["asset_count"],
            spans=summary["span_count"],
            servable=summary["servable_span_count"],
            quarantined=summary["quarantined_span_count"],
        )
    )
    print(f"[fp-rights] rights status counts: {summary['rights_status_counts_by_span']}")
    return 1 if summary["release_blocking"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
