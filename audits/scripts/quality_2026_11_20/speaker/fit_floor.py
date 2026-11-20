"""Fit an AS-norm floor from the HUMAN-labelled sheet, bounding false-accept rate with Clopper-Pearson.

LABEL column: y = teacher correct (genuine), n = teacher incorrect (impostor). Other values/empty are ignored.
Floor = lowest AS-norm score f such that CP-upper(false accepts among n-labels with asnorm >= f) <= target at delta.
Refuses to run with fewer n-labels than the bound can ever satisfy (0 errors needs ceil(ln(delta)/ln(1-target)); 299 at 1%/0.05).
The sheet is a non-random sample, so the bound is conditional on the labelled population; it is not a global guarantee.

  python fit_floor.py label_sheet.csv [--target 0.01] [--delta 0.05]      |      python fit_floor.py   (self-check)
"""
from __future__ import annotations
import argparse, csv, math, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "backend"))
from evaluation.gold.metrics import clopper_pearson_upper  # existing repo implementation


def fit(rows: list[tuple[float, bool]], target: float, delta: float) -> dict:
    """rows = (asnorm, teacher_correct). Raises ValueError when labels are insufficient."""
    imp = sorted(s for s, ok in rows if not ok)
    gen = sorted(s for s, ok in rows if ok)
    need = math.ceil(math.log(delta) / math.log(1 - target))
    if len(imp) < need:
        raise ValueError(f"need >= {need} impostor (n) labels for FAR<={target} at delta={delta}; have {len(imp)}")
    cands = sorted({s for s, _ in rows})
    for f in cands:
        k = sum(1 for s in imp if s >= f)
        ub = clopper_pearson_upper(k_errors=k, n_total=len(imp), delta=delta)
        if ub <= target:
            acc = sum(1 for s in gen if s >= f)
            return {"floor": f, "false_accepts": k, "n_impostor": len(imp), "far_upper_bound": ub,
                    "genuine_accepted": acc, "n_genuine": len(gen), "target": target, "delta": delta}
    raise ValueError("no finite floor meets the target")


def load(path: str) -> list[tuple[float, bool]]:
    out = []
    with open(path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            return out
        label_col = next((c for c in reader.fieldnames if c and c.strip().upper().startswith("LABEL")), None)
        if not label_col:
            return out
        for r in reader:
            lab = str(r.get(label_col) or "").strip().lower()
            val = r.get("asnorm")
            if lab in ("y", "n") and val is not None and str(val).strip() != "":
                try:
                    out.append((float(val), lab == "y"))
                except ValueError:
                    continue
    return out


def _selfcheck():
    import random
    rnd = random.Random(1)
    rows = [(rnd.gauss(0, 1), False) for _ in range(400)] + [(rnd.gauss(3, 1), True) for _ in range(300)]
    res = fit(rows, 0.01, 0.05)
    assert res["far_upper_bound"] <= 0.01 and res["n_impostor"] == 400, res
    try:
        fit(rows[:100] + rows[400:], 0.01, 0.05); raise AssertionError("should refuse")
    except ValueError as e:
        assert "need >= 299" in str(e), e
    assert math.ceil(math.log(0.05) / math.log(0.99)) == 299
    print("self-check OK:", res)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("sheet", nargs="?"); ap.add_argument("--target", type=float, default=0.01)
    ap.add_argument("--delta", type=float, default=0.05); a = ap.parse_args()
    if not a.sheet:
        _selfcheck()
    else:
        try:
            print(fit(load(a.sheet), a.target, a.delta))
        except ValueError as e:
            sys.exit(f"REFUSED: {e}")
