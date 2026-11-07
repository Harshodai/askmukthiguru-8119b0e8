#!/usr/bin/env python3
"""dream_okf_wikis.py — Autonomous OKF Knowledge Wiki Dreamer & Staging Triage.

Triages memory/okf/staging/, deduplicates against production and within staging,
runs quality & CoT filters, resolves teacher attribution, applies bidirectional
[[wikilinks]], graduates valid concepts into canonical subdirectories
(sri-preethaji/, sri-krishnaji/, shared/), cleans up staging, generates an audit
report, and recompiles memory/okf/compiled.json.

Usage:
    python -m scripts.ops.dream_okf_wikis
    python -m scripts.ops.dream_okf_wikis --dry-run
    python -m scripts.ops.dream_okf_wikis --no-compile
    python -m scripts.ops.dream_okf_wikis --report-path audits/okf/dreaming_report_2026-11-08.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Offline embedding resolution for compilation
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

_HERE = Path(__file__).resolve()
_BACKEND = (
    _HERE.parents[2]
    if (_HERE.parents[2] / "app").is_dir()
    else _HERE.parents[2] / "backend"
)
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.okf.wiki_dreamer import OKFWikiDreamer  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Autonomous OKF Wiki Dreamer and Staging Triage."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate triage and graduation without modifying disk.",
    )
    parser.add_argument(
        "--no-compile",
        action="store_true",
        help="Skip compilation of memory/okf/compiled.json.",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=None,
        help="Destination path for audit report JSON.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Output summary results as JSON.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose DEBUG logging.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    dreamer = OKFWikiDreamer(audit_path=args.report_path)
    report = dreamer.triage_and_graduate(
        dry_run=args.dry_run, auto_compile=not args.no_compile
    )

    if args.output_json:
        summary = {
            "total_staged": report.total_staged,
            "duplicates_production": report.duplicates_production,
            "duplicates_staging": report.duplicates_staging,
            "quality_rejected": report.quality_rejected,
            "junk_templates": report.junk_templates,
            "graduated": report.graduated,
            "graduated_by_teacher": report.graduated_by_teacher,
            "remaining_staged": report.remaining_staged,
            "compiled_entries": report.compiled_entries,
        }
        print(json.dumps(summary, indent=2))
        return 0

    print("\n" + "=" * 60)
    print("OKF WIKI DREAMER & STAGING TRIAGE REPORT")
    print("=" * 60)
    print(f"Total Staging Files Evaluated:  {report.total_staged}")
    print(f"Duplicates of Production:       {report.duplicates_production}")
    print(f"Duplicates within Staging:      {report.duplicates_staging}")
    print(f"Quality Rejected:               {report.quality_rejected}")
    print(f"Junk / Placeholder Files:       {report.junk_templates}")
    print(f"Graduated to Canonical OKF:     {report.graduated}")
    print(f"  - Sri Preethaji:              {report.graduated_by_teacher.get('sri-preethaji', 0)}")
    print(f"  - Sri Krishnaji:              {report.graduated_by_teacher.get('sri-krishnaji', 0)}")
    print(f"  - Shared / Both:              {report.graduated_by_teacher.get('both', 0)}")
    print(f"Remaining in Staging (Review):  {report.remaining_staged}")
    if report.compiled_entries:
        print(f"Compiled Production Index:      {report.compiled_entries} entries")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
