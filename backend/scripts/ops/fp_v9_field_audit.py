"""Read-only scroll of first_person_v9 — Phase 3 field audit.

Fetches exactly the 17 required fp-context fields + minimum provenance per
point. No verbatim_text, no vectors.  Produces two output files:

  audits/evidence/fp_v9_field_audit_<ISO>.json   — full per-point records
  audits/evidence/fp_v9_field_audit_<ISO>.csv    — flat summary rows

Usage (from repo root, against running local stack):
  python backend/scripts/ops/fp_v9_field_audit.py

Outputs SHA-256 checksums to stdout.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
COLLECTION = os.environ.get("FIRST_PERSON_COLLECTION", "first_person_v9")
BATCH_SIZE = 100

# Required fp-context fields (17) that the auditor expects missing on all points
REQUIRED_FP_FIELDS = [
    "asr_engine",
    "asr_model_version",
    "audio_start_ms",
    "audio_end_ms",
    "boundary_status",
    "caption_status",
    "completeness_status",
    "corpus_version",
    "guru_id",
    "parent_unit_id",
    "source_asset_id",
    "source_span_id",
    "source_text_hash",
    "speaker_id",
    "speaker_role",
    "turn_id",
    "turn_index",
]

# Provenance fields to fetch (no verbatim_text, no vectors)
FETCH_FIELDS = [
    "video_id",
    "teacher_id",
    "speaker",
    "speaker_verified",
    "start_ms",
    "end_ms",
    "transcript_hash",
] + REQUIRED_FP_FIELDS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def scroll_all(client, collection: str) -> list[dict]:
    """Scroll all points with payload projection; no vectors."""
    records: list[dict] = []
    offset = None
    while True:
        result = client.scroll(
            collection_name=collection,
            limit=BATCH_SIZE,
            offset=offset,
            with_payload=FETCH_FIELDS,
            with_vectors=False,
        )
        points, next_offset = result
        for pt in points:
            payload = pt.payload or {}
            rec: dict = {"point_id": str(pt.id)}
            for field in FETCH_FIELDS:
                rec[field] = payload.get(field)  # None if absent
            # Analyse speaker_verified specifically
            rec["speaker_verified_present"] = "speaker_verified" in payload
            rec["speaker_verified_value"] = payload.get("speaker_verified")
            # Per-point missing required field set
            missing = [f for f in REQUIRED_FP_FIELDS if payload.get(f) is None]
            rec["missing_required_fields"] = missing
            rec["missing_required_count"] = len(missing)
            records.append(rec)
        if next_offset is None:
            break
        offset = next_offset
        sys.stdout.write(f"\r  Scrolled {len(records)} points...")
        sys.stdout.flush()
    sys.stdout.write("\n")
    return records


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    try:
        from qdrant_client import QdrantClient
    except ImportError:
        print("ERROR: qdrant-client not installed in this environment.")
        return 1

    print(f"Connecting to Qdrant at {QDRANT_URL}, collection={COLLECTION}")
    client = QdrantClient(url=QDRANT_URL, timeout=60)

    # Verify collection exists
    try:
        info = client.get_collection(COLLECTION)
    except Exception as exc:
        print(f"ERROR: cannot reach collection {COLLECTION!r}: {exc}")
        return 1
    print(f"Collection {COLLECTION!r}: {info.points_count} points")

    print("Starting read-only payload scroll (no vectors, no verbatim_text)...")
    records = scroll_all(client, COLLECTION)

    # -----------------------------------------------------------------------
    # Validate totals
    # -----------------------------------------------------------------------
    total = len(records)
    ids_seen: set[str] = set()
    duplicate_ids: list[str] = []
    for r in records:
        pid = r["point_id"]
        if pid in ids_seen:
            duplicate_ids.append(pid)
        ids_seen.add(pid)

    speaker_key_absent = [r for r in records if not r["speaker_verified_present"]]
    speaker_true = [r for r in records if r["speaker_verified_value"] is True]
    speaker_false = [r for r in records if r["speaker_verified_value"] is False]
    speaker_null = [
        r for r in records if r["speaker_verified_value"] is None and r["speaker_verified_present"]
    ]

    # Per-field absence counts
    field_absence: dict[str, int] = {}
    for field in REQUIRED_FP_FIELDS:
        field_absence[field] = sum(1 for r in records if r[field] is None)

    # Aggregate by video_id + teacher_id for the 1202-absent group
    absent_by_video: dict[str, dict] = {}
    for r in speaker_key_absent:
        vid = r.get("video_id") or "UNKNOWN"
        tid = r.get("teacher_id") or "UNKNOWN"
        key = f"{tid}::{vid}"
        if key not in absent_by_video:
            absent_by_video[key] = {
                "video_id": vid,
                "teacher_id": tid,
                "point_ids": [],
                "missing_required_fields_union": set(),
                "start_ms_range": [],
            }
        absent_by_video[key]["point_ids"].append(r["point_id"])
        absent_by_video[key]["missing_required_fields_union"].update(r["missing_required_fields"])
        if r.get("start_ms") is not None:
            absent_by_video[key]["start_ms_range"].append(r["start_ms"])

    # Serialise sets
    for v in absent_by_video.values():
        v["missing_required_fields_union"] = sorted(v["missing_required_fields_union"])
        v["point_count"] = len(v["point_ids"])
        if v["start_ms_range"]:
            v["start_ms_min"] = min(v["start_ms_range"])
            v["start_ms_max"] = max(v["start_ms_range"])
        del v["start_ms_range"]

    # -----------------------------------------------------------------------
    # Build summary
    # -----------------------------------------------------------------------
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    summary = {
        "generated_at_utc": ts,
        "collection": COLLECTION,
        "qdrant_url": QDRANT_URL,
        "total_points_scanned": total,
        "duplicate_point_ids": duplicate_ids,
        "speaker_verified": {
            "key_absent": len(speaker_key_absent),
            "value_true": len(speaker_true),
            "value_false": len(speaker_false),
            "value_null_present": len(speaker_null),
        },
        "required_fp_field_absence_counts": field_absence,
        "absent_speaker_by_video_teacher": list(absent_by_video.values()),
        "all_points": records,
    }

    # -----------------------------------------------------------------------
    # Write outputs
    # -----------------------------------------------------------------------
    # Repo root is 3 levels up from backend/scripts/ops
    repo_root = Path(__file__).resolve().parents[3]
    out_dir = repo_root / "audits" / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / f"fp_v9_field_audit_{ts}.json"
    csv_path = out_dir / f"fp_v9_field_audit_{ts}.csv"

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # CSV: one row per point
    csv_cols = [
        "point_id",
        "video_id",
        "teacher_id",
        "speaker_verified_present",
        "speaker_verified_value",
        "start_ms",
        "end_ms",
        "missing_required_count",
        "missing_required_fields",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_cols)
        writer.writeheader()
        for r in records:
            writer.writerow(
                {
                    "point_id": r["point_id"],
                    "video_id": r.get("video_id"),
                    "teacher_id": r.get("teacher_id"),
                    "speaker_verified_present": r["speaker_verified_present"],
                    "speaker_verified_value": r["speaker_verified_value"],
                    "start_ms": r.get("start_ms"),
                    "end_ms": r.get("end_ms"),
                    "missing_required_count": r["missing_required_count"],
                    "missing_required_fields": "|".join(r["missing_required_fields"]),
                }
            )

    json_sha = sha256_file(json_path)
    csv_sha = sha256_file(csv_path)

    # -----------------------------------------------------------------------
    # Print validation report
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("PHASE 3 FIELD AUDIT — VALIDATION REPORT")
    print("=" * 60)
    print(f"Total scanned:              {total}")
    print(
        f"Duplicate point IDs:        {len(duplicate_ids)}  {'FAIL' if duplicate_ids else 'PASS'}"
    )
    print(f"speaker_verified key absent:{len(speaker_key_absent)}  (expected ~1202)")
    print(f"speaker_verified = true:    {len(speaker_true)}  (expected ~779)")
    print(f"speaker_verified = false:   {len(speaker_false)}  (expected 0)")
    print(f"speaker_verified = null:    {len(speaker_null)}  (expected 0)")
    print()
    print("Required fp-context field absence counts (all expected 1981):")
    for field, count in field_absence.items():
        status = "MATCH" if count == total else f"DIFF (expected {total})"
        print(f"  {field:<30} {count}  {status}")
    print()
    print(f"Speaker-absent records × distinct videos: {len(absent_by_video)}")
    print()
    print(f"JSON output:  {json_path}")
    print(f"JSON SHA-256: {json_sha}")
    print(f"CSV output:   {csv_path}")
    print(f"CSV SHA-256:  {csv_sha}")
    print("=" * 60)

    if duplicate_ids:
        print(f"FAIL: {len(duplicate_ids)} duplicate point IDs found: {duplicate_ids[:5]}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
