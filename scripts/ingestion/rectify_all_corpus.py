#!/usr/bin/env python3
"""
Mukthi Guru — Full Corpus Rectification & Integrity Synchronization Engine
==========================================================================
Scans all packages in scripts/ingestion/corpus/, applies canonical doctrine term
corrections from raw sources, reconstructs clean transcript.md, updates reversible
correction_ledger.json, quality_report.json, artifact_manifest.json, and manifest.json
with 100% cryptographic SHA-256 integrity and zero discrepancies.

The per-package worker is imported from rectify_target_packages.py (the canonical
shared workflow) so both CLI entry points share one implementation.
"""

import argparse
import functools
import multiprocessing as mp
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.doctrine_terms import reload as reload_doctrine_terms
from rectify_target_packages import rectify_package

CORPUS_ROOT = REPO_ROOT / "scripts" / "ingestion" / "corpus"


def main():
    parser = argparse.ArgumentParser(description="Rectify all corpus packages")
    parser.add_argument("--workers", type=int, default=max(2, min(12, mp.cpu_count())))
    parser.add_argument("--packages", nargs="*", help="Specific package IDs (optional)")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing any files")
    args = parser.parse_args()

    reload_doctrine_terms()

    if args.packages:
        package_dirs = [str(CORPUS_ROOT / vid) for vid in args.packages if (CORPUS_ROOT / vid).is_dir()]
    else:
        package_dirs = [str(p) for p in sorted(CORPUS_ROOT.iterdir()) if p.is_dir()]

    print(f"Rectifying {len(package_dirs)} packages with {args.workers} workers{' (dry-run, no files written)' if args.dry_run else ''}...")

    worker = functools.partial(rectify_package, dry_run=args.dry_run)
    with mp.Pool(args.workers, initializer=reload_doctrine_terms) as pool:
        results = list(pool.imap_unordered(worker, package_dirs, chunksize=max(1, len(package_dirs) // (args.workers * 4))))

    rectified_count = sum(1 for r in results if r["status"] == "rectified")
    total_corrections = sum(r.get("corrections", 0) for r in results)

    print(f"Finished: {rectified_count}/{len(package_dirs)} packages rectified.")
    print(f"Total doctrine ledger corrections recorded: {total_corrections}")


if __name__ == "__main__":
    main()