#!/usr/bin/env python3
"""Compare two CorpusHealthSnapshot files and detect regressions.

Usage:
    python scripts/ops/corpus_diff.py <old_snapshot.json> <new_snapshot.json> \\
        [--allow-shrink] [--allow-model-change]

Exit codes:
    0  All checks PASS
    1  One or more REGRESSIONS detected
    2  Usage / file error

X22: read-only. No Qdrant access.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load(path: str) -> dict:
    try:
        return json.loads(Path(path).read_text())
    except Exception as exc:
        print(f"ERROR: cannot read {path}: {exc}", file=sys.stderr)
        sys.exit(2)


def pct_licensed(snap: dict) -> float:
    dist = snap.get("rights_distribution", {})
    total = sum(dist.values())
    if total == 0:
        return 0.0
    return 100.0 * dist.get("licensed", 0) / total


def diff(old_path: str, new_path: str, allow_shrink: bool, allow_model_change: bool) -> int:
    old = load(old_path)
    new = load(new_path)

    regressions: list[str] = []
    warnings: list[str] = []

    print(f"\n=== Corpus Diff: {Path(old_path).name} → {Path(new_path).name} ===\n")

    # Total points
    old_total = old.get("total_points", 0)
    new_total = new.get("total_points", 0)
    delta = new_total - old_total
    print(f"Total points  : {delta:+d}  ({old_total} → {new_total})")
    if not allow_shrink and new_total < old_total * 0.95:
        regressions.append(
            f"total_points dropped by >{(1 - new_total/max(old_total,1))*100:.1f}% "
            f"({old_total} → {new_total}). Use --allow-shrink to override."
        )

    # Parent / child
    for key, label in [("parent_count", "Parent count"), ("child_count", "Child count")]:
        ov, nv = old.get(key, 0), new.get(key, 0)
        d = nv - ov
        print(f"{label:<14}: {d:+d}  ({ov} → {nv})")

    # Completeness
    print("\nCompleteness changes:")
    old_comp = old.get("completeness_distribution", {})
    new_comp = new.get("completeness_distribution", {})
    all_keys = sorted(set(old_comp) | set(new_comp))
    for k in all_keys:
        ov, nv = old_comp.get(k, 0), new_comp.get(k, 0)
        d = nv - ov
        note = ""
        if k == "fragment" and d > 0:
            note = "  ← REGRESSION"
            regressions.append(f"FRAGMENT count INCREASED by {d} ({ov} → {nv}).")
        print(f"  {k:<12}: {d:+d}  ({ov} → {nv}){note}")

    # Rights coverage
    old_pct = pct_licensed(old)
    new_pct = pct_licensed(new)
    note = ""
    if new_pct < 100.0:
        if new_pct < old_pct:
            note = "  ← REGRESSION"
            regressions.append(
                f"Licensed coverage dropped: {old_pct:.1f}% → {new_pct:.1f}%. All spans must be licensed."
            )
        else:
            note = "  ← WARNING: not 100%"
            warnings.append(f"Licensed coverage is {new_pct:.1f}% — not 100%.")
    print(f"\nRights coverage: {old_pct:.1f}% → {new_pct:.1f}%{note}")

    # Embedding model
    old_em = old.get("embedding_model_family_distribution", {})
    new_em = new.get("embedding_model_family_distribution", {})
    if old_em != new_em:
        note = " ← CHANGED"
        if not allow_model_change:
            warnings.append(
                f"Embedding model distribution changed: {old_em} → {new_em}. "
                "Use --allow-model-change to suppress. Re-embedding may be needed."
            )
    else:
        note = ""
    print(f"Embedding model: {old_em} → {new_em}{note}")

    # Summary
    print()
    if regressions:
        print("REGRESSIONS DETECTED:")
        for r in regressions:
            print(f"  ✗ {r}")
        print(f"\nResult: FAIL ({len(regressions)} regression(s))")
        return 1
    if warnings:
        print("WARNINGS:")
        for w in warnings:
            print(f"  ⚠ {w}")
    print("\nResult: PASS")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("old", help="Old snapshot JSON path")
    parser.add_argument("new", help="New snapshot JSON path")
    parser.add_argument(
        "--allow-shrink",
        action="store_true",
        help="Allow total_points to decrease by >5%%",
    )
    parser.add_argument(
        "--allow-model-change",
        action="store_true",
        help="Suppress warning on embedding model family change",
    )
    args = parser.parse_args()
    sys.exit(diff(args.old, args.new, args.allow_shrink, args.allow_model_change))


if __name__ == "__main__":
    main()
