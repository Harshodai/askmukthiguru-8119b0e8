#!/usr/bin/env python3
"""Validate human-review packet provenance without making human decisions.

The validator is intentionally read-only. It verifies source hashes recorded in
PROVENANCE.json and checks that every decision field is still blank. A missing
packet is unresolved evidence, never an implicit approval.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


PACKET_DECISION_COLUMNS: dict[str, tuple[str, ...]] = {
    "02-native-speaker.csv": ("decision", "reviewer", "date"),
    "03-helplines.csv": (
        "live_call_made_yyyy_mm_dd",
        "caller",
        "reached_a_person_yes_no",
        "free_yes_no",
        "staffed_24_7_yes_no",
        "notes",
    ),
    "04-rights-signoff.csv": (
        "decision_approve_exclude_hold",
        "reviewer",
        "date",
        "reason",
    ),
    "05-gold-labels.csv": (
        "human_relevance_0_3",
        "human_complete_yes_no",
        "human_speaker_verified_yes_no_unsure",
        "reviewer",
        "date",
        "notes",
    ),
    "06-answer-sample.csv": (
        "answers_the_question_yes_no",
        "quote_supports_answer_yes_no",
        "attribution_correct_yes_no",
        "clip_usable_yes_no",
        "reviewer",
        "date",
        "notes",
    ),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "AGENTS.md").is_file() and (parent / ".git").exists():
            return parent
    raise RuntimeError("repository root not found")


def _blank(value: object) -> bool:
    return str(value or "").strip() in {"", "(blank)"}


def validate_packets(packet_dir: Path) -> dict[str, Any]:
    """Return a deterministic validation report; never edit packet files."""
    provenance_path = packet_dir / "PROVENANCE.json"
    report: dict[str, Any] = {
        "packet_dir": str(packet_dir),
        "provenance_present": provenance_path.is_file(),
        "source_hashes_match": True,
        "missing_packets": [],
        "unsigned": True,
        "errors": [],
    }
    if not provenance_path.is_file():
        report["errors"].append("PROVENANCE.json is missing")
        return report

    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    for relative, expected in sorted((provenance.get("inputs") or {}).items()):
        source = packet_dir.parents[2] / relative
        if not source.is_file():
            report["source_hashes_match"] = False
            report["errors"].append(f"source missing: {relative}")
        elif _sha256(source) != expected:
            report["source_hashes_match"] = False
            report["errors"].append(f"source hash mismatch: {relative}")

    for filename, columns in PACKET_DECISION_COLUMNS.items():
        path = packet_dir / filename
        if not path.is_file():
            report["missing_packets"].append(filename)
            continue
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        missing_columns = [column for column in columns if column not in (rows[0].keys() if rows else [])]
        if missing_columns:
            report["errors"].append(f"{filename}: missing decision columns {missing_columns}")
            continue
        for index, row in enumerate(rows, start=2):
            filled = [column for column in columns if not _blank(row.get(column))]
            if filled:
                report["unsigned"] = False
                report["errors"].append(f"{filename}:{index}: filled decision fields {filled}")

    clinician = packet_dir / "01-clinician-crisis-copy.md"
    if not clinician.is_file():
        report["missing_packets"].append(clinician.name)
    else:
        text = clinician.read_text(encoding="utf-8")
        if "| block | served when | decision | reviewer | date | notes |" not in text:
            report["errors"].append("01-clinician-crisis-copy.md: decision table missing")
        if "| (blank) | (blank) | (blank) |" not in text:
            report["unsigned"] = False
            report["errors"].append("01-clinician-crisis-copy.md: decision row is not blank")

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-dir", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    packet_dir = args.packet_dir or (_repo_root() / "docs" / "reviews" / "2026-11-14-human-gates")
    report = validate_packets(packet_dir)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"provenance_present: {report['provenance_present']}")
        print(f"source_hashes_match: {report['source_hashes_match']}")
        print(f"unsigned: {report['unsigned']}")
        for packet in report["missing_packets"]:
            print(f"missing_packet: {packet}")
        for error in report["errors"]:
            print(f"ERROR: {error}")
    return 0 if report["provenance_present"] and report["source_hashes_match"] and report["unsigned"] and not report["errors"] and not report["missing_packets"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
