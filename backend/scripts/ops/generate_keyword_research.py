#!/usr/bin/env python3
"""Standalone operator CLI for generating locked-in Keyword Research deliverables.

Usage:
    python -m scripts.ops.generate_keyword_research --seed "meditation" [options]

Options:
    --country COUNTRY   Target country (default: 'United States'; or 'worldwide').
    --source SOURCE     Data source (default: 'public_data'; or 'ahrefs', 'semrush').
    --out PATH          Output path for .xlsx workbook (default: 'outputs/keyword_research.xlsx').
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure backend root is on sys.path
_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[2] if _HERE.parents[1].name == "scripts" else _HERE.parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.keyword_research.engine import generate_keyword_research
from services.keyword_research.validator import validate_keyword_research_payload
from services.keyword_research.workbook import create_keyword_research_workbook


def main() -> int:
    parser = argparse.ArgumentParser(description="Standalone Keyword Research Workbook Generator")
    parser.add_argument("--seed", required=True, help="Seed keyword or topic")
    parser.add_argument(
        "--country",
        default="United States",
        help="Target country or 'worldwide' (default: United States)",
    )
    parser.add_argument(
        "--source",
        default="public_data",
        help="Data source: public_data, ahrefs, semrush, dataforseo (default: public_data)",
    )
    parser.add_argument(
        "--out", default="outputs/keyword_research.xlsx", help="Output path for .xlsx workbook"
    )
    parser.add_argument(
        "--require-external",
        action="store_true",
        default=False,
        help="Require real external provider data; fail closed if unavailable",
    )
    args = parser.parse_args()

    provider = None

    print(
        f"\n[Step 0 Intake] Seed: '{args.seed}' | Target Country: '{args.country}' | Data Source: '{args.source}'"
    )
    if args.source == "public_data" and not args.require_external and not provider:
        print(
            "  Notice: Using public search baseline with explicit uncertified provenance disclosure."
        )

    print("\n[Step 1 Data Gathering & Analysis] Generating 300 keywords across 5 clusters...")
    try:
        payload = generate_keyword_research(
            seed_keyword=args.seed,
            target_country=args.country,
            data_source=args.source,
            provider=provider,
            require_external_provenance=args.require_external,
        )
    except Exception as exc:
        print(f"ERROR: Keyword research data generation failed: {exc}", file=sys.stderr)
        return 2

    print("  Validating contract constraints...")
    try:
        validate_keyword_research_payload(
            payload, require_external_certification=args.require_external
        )
        print(
            "  All schema invariants passed (300 keywords, 5 clusters, 20 competitors, 20 gaps, 5 findings, 5 recommendations)."
        )
    except Exception as e:
        print(f"ERROR: Validation failed: {e}", file=sys.stderr)
        return 1

    out_path = Path(args.out)
    print(f"\n[Step 2 Excel Generation] Writing three-tab workbook to: {out_path}...")
    create_keyword_research_workbook(payload, out_path)

    print("\n[Step 3 Deliverable Review]")
    print("  Tab 1: Topic Cluster Summary (5 clusters + TOTAL row)")
    print(f"  Tab 2: Priority Keyword Targets (300 rows, {payload.volume_scope_label})")
    print("  Tab 3: Competitor & Gap Analysis (20 competitors, 20 gaps, 10 insights)")
    if payload.provenance:
        prov = payload.provenance
        print(f"  Provenance Provider: {prov.get('provider')}")
        print(f"  Certified External: {prov.get('production_certified', False)}")
        if prov.get("request_sha256"):
            print(f"  Request SHA256: {prov.get('request_sha256')[:16]}...")
        if prov.get("response_sha256"):
            print(f"  Response SHA256: {prov.get('response_sha256')[:16]}...")
    print(f"  Workbook size: {out_path.stat().st_size:,} bytes")
    print(f"\n Deliverable complete: {out_path.resolve()}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
