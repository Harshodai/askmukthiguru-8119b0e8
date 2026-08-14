"""Build a deterministic, planning-only source re-ingestion manifest."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

ALLOWED_VERDICTS = {"MIGRATE", "MIGRATE_THEN_VERIFY", "REFETCH_FROM_ORIGIN"}
ACTIONS = {
    "MIGRATE": "copy_after_quality_and_rights_validation",
    "MIGRATE_THEN_VERIFY": "rebuild_then_hold_for_evaluation",
    "REFETCH_FROM_ORIGIN": "refetch_origin_then_rebuild",
}


def build_manifest(report: dict, *, generated_from: str) -> dict:
    rows = []
    for source in report.get("sources") or []:
        verdict = str(source.get("verdict") or "").strip().upper()
        url = str(source.get("source_url") or "").strip()
        if verdict not in ALLOWED_VERDICTS or not url:
            continue
        rows.append({
            "source_url": url,
            "verdict": verdict,
            "contamination_rate": source.get("contamination_rate"),
            "chunks": int(source.get("chunks") or 0),
            "source_identity": url,
            "candidate_action": ACTIONS[verdict],
            "publish_allowed": False,
        })
    rows.sort(key=lambda row: (row["verdict"], row["source_url"]))
    counts = {v: sum(row["verdict"] == v for row in rows) for v in sorted(ALLOWED_VERDICTS)}
    return {
        "schema_version": 1,
        "generated_from": generated_from,
        "planning_only": True,
        "publish_requires": [
            "source_origin_or_rights_verified",
            "domain_rights_status_stamped",
            "quality_gate_passed",
            "held_out_evaluation_passed",
            "candidate_release_approved",
        ],
        "source_count": len(rows),
        "verdict_counts": counts,
        "sources": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    manifest = build_manifest(json.loads(args.report.read_text()), generated_from=str(args.report))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(args.output), "source_count": manifest["source_count"], "verdict_counts": manifest["verdict_counts"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
