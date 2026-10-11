"""Agreement + adjudicated export for two annotators' filled sheets.

    python3 evals/gold_set_v1/score_gold.py annotator_A_filled.csv annotator_B_filled.csv \
        [--adjudicated disagreements_filled.csv] [--out labels_human.jsonl]

Reports, on the overlap (pairs both annotators labelled): per-dimension raw agreement,
Cohen's kappa (quadratic-weighted for relevance 0-3, unweighted for the yes/no/unsure columns)
and a confusion matrix. Writes disagreements.csv (blank adj_* columns for the adjudicator),
then exports every resolved pair to `--out` in the .work/autoresearch_fp/labels.jsonl format
{id, relevance, complete, risk} plus speaker_is_teacher, n_annotators, source="human".
Overlap pairs with an unresolved disagreement are NOT exported (counted as pending).
Exit code 1 on any invalid / blank label cell: fix the sheet, never guess.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from evaluation.gold.agreement import adjudicate, cohens_kappa, confusion_matrix  # noqa: E402

DIMS = {  # sheet column -> allowed values (normalised lower-case strings)
    "relevance_0_3": ("0", "1", "2", "3"),
    "complete_yes_no": ("yes", "no"),
    "speaker_is_teacher_yes_no_unsure": ("yes", "no", "unsure"),
    "risk_yes_no": ("yes", "no"),
}


def read_sheet(path: Path) -> tuple[dict[str, dict], list[str]]:
    """{pair_id: {dim: value}} plus a list of human-readable errors for bad cells."""
    rows, errors = {}, []
    with path.open(newline="", encoding="utf-8-sig") as fh:  # Excel adds a BOM
        for row in csv.DictReader(fh):
            pid = row["pair_id"]
            if "SKIPPED" in (row.get("notes") or "").upper() and not any((row.get(d) or "").strip() for d in DIMS):
                print(f"skipped by annotator (needs another labeller): {path.name}:{pid}")
                continue
            vals = {}
            for dim, allowed in DIMS.items():
                v = (row.get(dim) or "").strip().lower()
                if v not in allowed:
                    errors.append(f"{path.name}:{pid}:{dim}={v!r} (allowed {'/'.join(allowed)})")
                vals[dim] = v
            rows[pid] = vals
    return rows, errors


def weighted_kappa(a: list[int], b: list[int], k: int = 4) -> float:
    """Quadratic-weighted Cohen's kappa for ordinal labels 0..k-1."""
    n = len(a)
    if n == 0:
        raise ValueError("need at least one labelled pair")
    obs = [[0.0] * k for _ in range(k)]
    for x, y in zip(a, b):
        obs[x][y] += 1
    ra = [sum(obs[i]) for i in range(k)]
    cb = [sum(obs[i][j] for i in range(k)) for j in range(k)]
    w = [[(i - j) ** 2 / (k - 1) ** 2 for j in range(k)] for i in range(k)]
    num = sum(w[i][j] * obs[i][j] for i in range(k) for j in range(k))
    den = sum(w[i][j] * ra[i] * cb[j] / n for i in range(k) for j in range(k))
    return 1.0 if den == 0 else 1.0 - num / den


def agreement_report(a: dict, b: dict, overlap: list[str]) -> dict:
    report = {}
    for dim in DIMS:
        la, lb = [a[p][dim] for p in overlap], [b[p][dim] for p in overlap]
        if not overlap:
            report[dim] = {"n": 0}
            continue
        kappa = (weighted_kappa([int(x) for x in la], [int(x) for x in lb]) if dim == "relevance_0_3"
                 else cohens_kappa(la, lb))
        report[dim] = {"n": len(overlap), "raw_agreement": round(sum(x == y for x, y in zip(la, lb)) / len(la), 4),
                       "kappa": round(kappa, 4), "kappa_kind": "quadratic" if dim == "relevance_0_3" else "cohen",
                       "confusion_a_rows_b_cols": confusion_matrix(la, lb)}
    return report


def read_adjudications(path: Path | None) -> dict[str, dict]:
    if path is None:
        return {}
    with path.open(newline="", encoding="utf-8-sig") as fh:  # Excel adds a BOM
        return {r["pair_id"]: {d: (r.get(f"adj_{d}") or "").strip().lower() for d in DIMS} for r in csv.DictReader(fh)}


def resolve(pid: str, a: dict, b: dict, adj: dict) -> dict | None:
    """Final labels for one pair, or None if an overlap disagreement is still unadjudicated."""
    if pid in a and pid in b:
        try:
            return {d: adjudicate(a[pid][d], b[pid][d], adj.get(pid, {}).get(d)) for d in DIMS} | {"n": 2}
        except ValueError:
            return None
    return (a.get(pid) or b[pid]) | {"n": 1}


def to_label(pid: str, v: dict) -> dict:
    return {"id": pid, "relevance": int(v["relevance_0_3"]), "complete": v["complete_yes_no"] == "yes",
            "risk": v["risk_yes_no"] == "yes", "speaker_is_teacher": v["speaker_is_teacher_yes_no_unsure"],
            "n_annotators": v["n"], "source": "human"}


def write_disagreements(path: Path, a: dict, b: dict, overlap: list[str]) -> int:
    rows = [p for p in overlap if any(a[p][d] != b[p][d] for d in DIMS)]
    cols = ["pair_id"] + [f"{s}_{d}" for d in DIMS for s in ("a", "b", "adj")]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for p in rows:
            w.writerow({"pair_id": p, **{f"a_{d}": a[p][d] for d in DIMS}, **{f"b_{d}": b[p][d] for d in DIMS},
                        **{f"adj_{d}": "" for d in DIMS}})
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("sheet_a", type=Path)
    ap.add_argument("sheet_b", type=Path)
    ap.add_argument("--adjudicated", type=Path, help="disagreements.csv with adj_* columns filled")
    ap.add_argument("--out", type=Path, default=Path(__file__).with_name("labels_human.jsonl"))
    ap.add_argument("--disagreements", type=Path, default=Path(__file__).with_name("disagreements.csv"))
    args = ap.parse_args(argv)

    a, err_a = read_sheet(args.sheet_a)
    b, err_b = read_sheet(args.sheet_b)
    if err_a or err_b:
        print("INVALID OR BLANK LABEL CELLS (fix the sheet, do not guess):", *(err_a + err_b)[:50], sep="\n  ")
        return 1
    overlap = sorted(set(a) & set(b))
    print(json.dumps({"overlap_pairs": len(overlap), "agreement": agreement_report(a, b, overlap)}, indent=1))
    n_dis = write_disagreements(args.disagreements, a, b, overlap)
    adj = read_adjudications(args.adjudicated)
    labels, pending = [], []
    for pid in sorted(set(a) | set(b)):
        v = resolve(pid, a, b, adj)
        (pending.append(pid) if v is None else labels.append(to_label(pid, v)))
    args.out.write_text("".join(json.dumps(x) + "\n" for x in labels))
    print(f"disagreeing overlap pairs: {n_dis} -> {args.disagreements}")
    print(f"exported {len(labels)} labels -> {args.out}; pending adjudication: {len(pending)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
