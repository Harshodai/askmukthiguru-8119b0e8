"""Build the human speaker-label reviewer workbook (CSV) from the sample CSV.

The human LABEL column is always left EMPTY. Machine evidence (ECAPA score, margin, floor,
band) goes only into columns headed "MACHINE (not a label): ...". Never write y/n here.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LABEL_COL = "LABEL(teacher_correct? y/n)"
MACHINE_COLS = ("score", "margin", "floor", "band")
MACHINE_PREFIX = "MACHINE (not a label): "


def build(src: Path, dst: Path) -> int:
    with src.open(newline="") as f:
        rows = list(csv.DictReader(f))
    human = [c for c in rows[0] if c != LABEL_COL and c not in MACHINE_COLS] if rows else []
    machine = [c for c in MACHINE_COLS if rows and c in rows[0]]
    header = human + [MACHINE_PREFIX + c for c in machine] + [LABEL_COL]
    with dst.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow([r[c] for c in human] + [r[c] for c in machine] + [""])
    return len(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=REPO / "audits/work/2026-11-19-serve-rate/speaker_label_sample.csv")
    ap.add_argument("--dst", type=Path, default=REPO / "audits/work/2026-11-19-serve-rate/speaker_label_workbook.csv")
    a = ap.parse_args()
    print(f"wrote {build(a.src, a.dst)} rows to {a.dst}")
