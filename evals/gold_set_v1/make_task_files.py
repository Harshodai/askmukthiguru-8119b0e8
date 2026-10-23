"""Split pairs.csv into per-annotator task files with a shared overlap batch.

    backend/.venv/bin/python3 evals/gold_set_v1/make_task_files.py \
        evals/gold_set_v1/pairs.csv --raters A B C [--overlap 101] [--seed 20261011]

Reads ONLY pairs.csv (never pairs_scores.csv: seeing ranks biases labels, and
no clip text beyond the columns already in the sheets is ever added). Every
sheet keeps the pairs.csv columns minus `assignment`, in pairs.csv row order.

Two modes:
  A/B (default): honours the `assignment` column, reproducing annotator_A.csv
    (assignment A or A+B) and annotator_B.csv (B or A+B) byte-identically.
  3+ raters (e.g. --raters A B C): the 101 A+B rows become the triple-shared
    overlap; the 404 remainder rows are seed-shuffled and dealt round-robin,
    so each sheet holds 101 shared + ~135 disjoint rows (~236 rows each).
    Without an `assignment` column, the first --overlap shuffled rows are
    shared instead (same seed rule).

Refuses when any label cell is already filled (never redistribute filled
labels) and refuses to overwrite existing sheets without --force.
Exit 1 with a message on any refusal.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

LABEL_COLS = [
    "relevance_0_3",
    "complete_yes_no",
    "speaker_is_teacher_yes_no_unsure",
    "risk_yes_no",
    "notes",
]
DEFAULT_SEED = 20261011
DEFAULT_OVERLAP = 101


def read_pairs(path: Path) -> tuple[list[dict], list[str]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    if not rows or "pair_id" not in (rows[0] or {}):
        raise ValueError(f"{path} has no pair_id column")
    return rows, list(rows[0])


def check_blank(rows: list[dict]) -> list[str]:
    bad = [
        f"{r['pair_id']}:{c}={r[c]!r}"
        for r in rows
        for c in LABEL_COLS
        if c in r and (r[c] or "").strip()
    ]
    return bad


def split(
    rows: list[dict], raters: list[str], overlap: int, seed: int
) -> tuple[list[dict], dict[str, list[dict]]]:
    """(shared, {rater: own rows}). Honours `assignment` for the A/B case;
    otherwise the A+B rows are shared and the remainder is seed-dealt."""
    by_id = {r["pair_id"]: r for r in rows}
    if len(by_id) != len(rows):
        raise ValueError("duplicate pair_id in pairs.csv")
    if (
        "assignment" in rows[0]
        and set(raters) != {"A", "B"}
        and {r["assignment"] for r in rows} <= {"A", "B", "A+B"}
    ):
        shared = [r for r in rows if r["assignment"] == "A+B"]
        rest = [r for r in rows if r["assignment"] != "A+B"]
        if len(shared) != overlap:
            raise ValueError(f"A+B rows are {len(shared)}, not --overlap {overlap}")
        rng = random.Random(seed)
        order = rest[:]
        rng.shuffle(order)
        own = {r: [] for r in raters}
        for i, row in enumerate(order):
            own[raters[i % len(raters)]].append(row)
        # Stable sheet order: back to pairs.csv order within each sheet.
        pos = {r["pair_id"]: i for i, r in enumerate(rows)}
        for r in raters:
            own[r].sort(key=lambda row: pos[row["pair_id"]])
        return shared, own
    if "assignment" in rows[0] and set(raters) == {"A", "B"}:
        got = {r["assignment"] for r in rows}
        if got <= {"A", "B", "A+B"}:
            shared = [r for r in rows if r["assignment"] == "A+B"]
            if len(shared) != overlap:
                raise ValueError(f"A+B rows are {len(shared)}, not --overlap {overlap}")
            return shared, {
                "A": [r for r in rows if r["assignment"] in ("A", "A+B")],
                "B": [r for r in rows if r["assignment"] in ("B", "A+B")],
            }
    rng = random.Random(seed)
    order = rows[:]
    rng.shuffle(order)
    shared = order[:overlap]
    rest = order[overlap:]
    own = {r: [] for r in raters}
    for i, row in enumerate(rest):
        own[raters[i % len(raters)]].append(row)
    pos = {r["pair_id"]: i for i, r in enumerate(rows)}
    shared.sort(key=lambda row: pos[row["pair_id"]])
    for r in raters:
        own[r].sort(key=lambda row: pos[row["pair_id"]])
    return shared, own


def write_sheet(path: Path, rows: list[dict], cols: list[str], force: bool) -> None:
    if path.exists() and not force:
        raise ValueError(f"{path} exists; re-run with --force to overwrite")
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pairs", type=Path)
    ap.add_argument("--raters", nargs="+", default=["A", "B"])
    ap.add_argument("--overlap", type=int, default=DEFAULT_OVERLAP)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    if len(set(args.raters)) != len(args.raters) or not args.raters:
        print("REFUSING: --raters must list distinct names")
        return 1
    try:
        rows, cols = read_pairs(args.pairs)
    except (ValueError, OSError) as e:
        print(f"REFUSING: {e}")
        return 1
    bad = check_blank(rows)
    if bad:
        print(
            "REFUSING: label cells already filled (never redistribute filled labels):",
            *bad[:10],
            sep="\n  ",
        )
        return 1
    try:
        shared, own = split(rows, list(args.raters), args.overlap, args.seed)
    except ValueError as e:
        print(f"REFUSING: {e}")
        return 1
    cols = [c for c in cols if c != "assignment"]  # annotators must not see the split
    out_dir = args.out_dir or args.pairs.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    if not args.force:  # preflight EVERY sheet: never half-write when one exists
        for r in args.raters:
            target = out_dir / f"annotator_{r}.csv"
            if target.exists():
                print(f"REFUSING: {target} exists; re-run with --force to overwrite")
                return 1
    counts = {}
    try:
        for r in args.raters:
            sheet = shared + [x for x in own[r] if x not in shared]
            pos = {x["pair_id"]: i for i, x in enumerate(rows)}
            sheet = sorted(sheet, key=lambda x: pos[x["pair_id"]])
            sheet = [{k: v for k, v in x.items() if k != "assignment"} for x in sheet]
            write_sheet(out_dir / f"annotator_{r}.csv", sheet, cols, args.force)
            counts[r] = len(sheet)
    except ValueError as e:
        print(f"REFUSING: {e}")
        return 1
    print(
        json.dumps(
            {
                "pairs": len(rows),
                "shared": len(shared),
                "sheets": counts,
                "seed": args.seed,
                "raters": list(args.raters),
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
