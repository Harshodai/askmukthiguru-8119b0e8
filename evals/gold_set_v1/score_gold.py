"""Agreement + adjudicated export for two annotators' filled sheets.

    python3 evals/gold_set_v1/score_gold.py annotator_A_filled.csv annotator_B_filled.csv \
        [--adjudicated disagreements_filled.csv] [--out labels_human.jsonl]
    python3 evals/gold_set_v1/score_gold.py A_filled.csv B_filled.csv C_filled.csv \
        [--adjudicated disagreements_filled.csv] [--out labels_human.jsonl]

Reports, on the overlap (pairs both annotators labelled): per-dimension raw agreement,
Cohen's kappa (quadratic-weighted for relevance 0-3, unweighted for the yes/no/unsure columns)
and a confusion matrix. With a third sheet: per-dimension pairwise agreement for the 3
pairs (a_b, a_c, b_c) over the triple overlap, Krippendorff's alpha over the union of
the three sheets (ordinal weighting for relevance 0-3, nominal for the yes/no/unsure
columns; pairs labelled by only 2 of 3 raters still contribute), and majority-rule
resolution (unanimous or 2/3 resolves with n_annotators=3; a three-way split stays
pending for the adjudicator).
Writes disagreements.csv (blank adj_* columns for the adjudicator),
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
sys.path.insert(0, str(Path(__file__).resolve().parent))
from three_rater import krippendorff_alpha, usable_items  # noqa: E402

from evaluation.gold.agreement import (  # noqa: E402
    adjudicate,
    cohens_kappa,
    confusion_matrix,
    majority_vote,
)

DIMS = {  # sheet column -> allowed values (normalised lower-case strings)
    "relevance_0_3": ("0", "1", "2", "3"),
    "complete_yes_no": ("yes", "no"),
    "speaker_is_teacher_yes_no_unsure": ("yes", "no", "unsure"),
    "risk_yes_no": ("yes", "no"),
}
ALIASES = {
    "complete_yes_no": {"f": "yes", "i": "no", "yes": "yes", "no": "no"},
    "risk_yes_no": {"n": "no", "y": "yes", "yes": "yes", "no": "no"},
    "speaker_is_teacher_yes_no_unsure": {"y": "yes", "n": "no", "yes": "yes", "no": "no"},
}


def read_sheet(path: Path) -> tuple[dict[str, dict], list[str]]:
    """{pair_id: {dim: value}} plus a list of human-readable errors for bad cells."""
    rows, errors = {}, []
    with path.open(newline="", encoding="utf-8-sig") as fh:  # Excel adds a BOM
        for row in csv.DictReader(fh):
            pid = row["pair_id"]
            if "SKIPPED" in (row.get("notes") or "").upper() and not any(
                (row.get(d) or "").strip() for d in DIMS
            ):
                print(f"skipped by annotator (needs another labeller): {path.name}:{pid}")
                continue
            vals = {}
            for dim, allowed in DIMS.items():
                raw_v = (row.get(dim) or "").strip().lower()
                v = ALIASES.get(dim, {}).get(raw_v, raw_v)
                if v not in allowed:
                    errors.append(f"{path.name}:{pid}:{dim}={raw_v!r} (allowed {'/'.join(allowed)})")
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
        kappa = (
            weighted_kappa([int(x) for x in la], [int(x) for x in lb])
            if dim == "relevance_0_3"
            else cohens_kappa(la, lb)
        )
        report[dim] = {
            "n": len(overlap),
            "raw_agreement": round(sum(x == y for x, y in zip(la, lb)) / len(la), 4),
            "kappa": round(kappa, 4),
            "kappa_kind": "quadratic" if dim == "relevance_0_3" else "cohen",
            "confusion_a_rows_b_cols": confusion_matrix(la, lb),
        }
    return report


def read_adjudications(path: Path | None) -> dict[str, dict]:
    if path is None:
        return {}
    with path.open(newline="", encoding="utf-8-sig") as fh:  # Excel adds a BOM
        return {
            r["pair_id"]: {d: (r.get(f"adj_{d}") or "").strip().lower() for d in DIMS}
            for r in csv.DictReader(fh)
        }


def resolve(pid: str, a: dict, b: dict, adj: dict) -> dict | None:
    """Final labels for one pair, or None if an overlap disagreement is still unadjudicated."""
    if pid in a and pid in b:
        try:
            return {d: adjudicate(a[pid][d], b[pid][d], adj.get(pid, {}).get(d)) for d in DIMS} | {
                "n": 2
            }
        except ValueError:
            return None
    return (a.get(pid) or b[pid]) | {"n": 1}


def to_label(pid: str, v: dict) -> dict:
    return {
        "id": pid,
        "relevance": int(v["relevance_0_3"]),
        "complete": v["complete_yes_no"] == "yes",
        "risk": v["risk_yes_no"] == "yes",
        "speaker_is_teacher": v["speaker_is_teacher_yes_no_unsure"],
        "n_annotators": v["n"],
        "source": "human",
    }


def write_disagreements(path: Path, a: dict, b: dict, overlap: list[str]) -> int:
    rows = [p for p in overlap if any(a[p][d] != b[p][d] for d in DIMS)]
    cols = ["pair_id"] + [f"{s}_{d}" for d in DIMS for s in ("a", "b", "adj")]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for p in rows:
            w.writerow(
                {
                    "pair_id": p,
                    **{f"a_{d}": a[p][d] for d in DIMS},
                    **{f"b_{d}": b[p][d] for d in DIMS},
                    **{f"adj_{d}": "" for d in DIMS},
                }
            )
    return len(rows)


def pair_numbers(la: list[str], lb: list[str], dim: str) -> dict:
    """Raw agreement + kappa for one rater pair on one dimension, reusing the
    same kappa functions as the two-rater path (quadratic-weighted for
    relevance_0_3, unweighted Cohen otherwise)."""
    kappa = (
        weighted_kappa([int(x) for x in la], [int(x) for x in lb])
        if dim == "relevance_0_3"
        else cohens_kappa(la, lb)
    )
    return {
        "n": len(la),
        "raw_agreement": round(sum(x == y for x, y in zip(la, lb)) / len(la), 4),
        "kappa": round(kappa, 4),
        "kappa_kind": "quadratic" if dim == "relevance_0_3" else "cohen",
    }


def alpha_items(a: dict, b: dict, c: dict, dim: str) -> list[list]:
    """Per-union-pair rater values for Krippendorff's alpha (None = not labelled).

    Relevance is numeric for the ordinal (squared-distance) metric; the
    yes/no/unsure columns stay strings for the nominal metric."""
    items = []
    for p in sorted(set(a) | set(b) | set(c)):
        vals = []
        for s in (a, b, c):
            v = s.get(p, {}).get(dim)
            vals.append(None if v is None else (int(v) if dim == "relevance_0_3" else v))
        items.append(vals)
    return items


def agreement_report_3(a: dict, b: dict, c: dict, overlap: list[str]) -> dict:
    """Per-dimension pairwise agreement for the 3 rater pairs over the triple
    overlap (pairs all three annotators labelled). Each pair entry has the same
    numbers as the two-rater report; confusion keys name the pair's row/col side.
    Krippendorff's alpha runs over the union instead, so partial-overlap pairs
    (2 of 3 present) still contribute; alpha_n_items counts the pairs with 2+
    labels that entered it."""
    sheets = {"a": a, "b": b, "c": c}
    report = {}
    for dim in DIMS:
        pairs = {}
        for x, y in (("a", "b"), ("a", "c"), ("b", "c")):
            if not overlap:
                pairs[f"{x}_{y}"] = {"n": 0}
                continue
            la = [sheets[x][p][dim] for p in overlap]
            lb = [sheets[y][p][dim] for p in overlap]
            pairs[f"{x}_{y}"] = pair_numbers(la, lb, dim) | {
                f"confusion_{x}_rows_{y}_cols": confusion_matrix(la, lb)
            }
        items = alpha_items(a, b, c, dim)
        level = "ordinal" if dim == "relevance_0_3" else "nominal"
        n_items = usable_items(items)
        report[dim] = {
            "n": len(overlap),
            "pairs": pairs,
            "krippendorff_alpha": round(krippendorff_alpha(items, level), 4) if n_items else None,
            "alpha_level": level,
            "alpha_n_items": n_items,
        }
    return report


def resolve3(pid: str, a: dict, b: dict, c: dict, adj: dict) -> dict | None:
    """Majority-rule final labels for one pair, or None if still pending.

    Triple overlap: per dimension, unanimous or 2/3 majority resolves
    (n=3); a three-way split needs adj_<dim> filled (validated), else pending.
    Two of three present: falls back to the two-rater adjudicate rule (n=2).
    One of three present: exported as-is (n=1), as in the two-rater path."""
    present = [s for s in (a, b, c) if pid in s]
    if len(present) == 3:
        out = {}
        for d in DIMS:
            maj = majority_vote([s[pid][d] for s in present])
            if maj is not None:
                out[d] = maj
                continue
            v = adj.get(pid, {}).get(d) or ""
            if v not in DIMS[d]:  # blank or invalid adjudication: still pending
                return None
            out[d] = v
        return out | {"n": 3}
    if len(present) == 2:
        x, y = present
        try:
            return {d: adjudicate(x[pid][d], y[pid][d], adj.get(pid, {}).get(d)) for d in DIMS} | {
                "n": 2
            }
        except ValueError:
            return None
    if len(present) == 1:
        return dict(present[0][pid]) | {"n": 1}
    return None


def write_disagreements3(path: Path, a: dict, b: dict, c: dict, adj: dict | None = None) -> int:
    """Pending pairs under majority rule: triple-overlap three-way splits
    plus two-rater disagreements on partial overlap. Pairs carrying an
    existing adjudication are RETAINED (with their adj_* values copied
    through) even when resolve3 now resolves them — the sheet must round-trip
    as the next --adjudicated input without erasing prior decisions
    (review 2026-10-15). Columns extend the two-rater sheet with c_*
    (existing a_*/b_*/adj_* names unchanged)."""
    adj = adj or {}
    pids = sorted(set(a) | set(b) | set(c))
    rows = [p for p in pids if resolve3(p, a, b, c, adj) is None or p in adj]
    cols = ["pair_id"] + [f"{s}_{d}" for d in DIMS for s in ("a", "b", "c", "adj")]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for p in rows:
            w.writerow(
                {
                    "pair_id": p,
                    **{f"a_{d}": a.get(p, {}).get(d, "") for d in DIMS},
                    **{f"b_{d}": b.get(p, {}).get(d, "") for d in DIMS},
                    **{f"c_{d}": c.get(p, {}).get(d, "") for d in DIMS},
                    **{f"adj_{d}": adj.get(p, {}).get(d, "") for d in DIMS},
                }
            )
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("sheet_a", type=Path)
    ap.add_argument("sheet_b", type=Path)
    ap.add_argument(
        "sheet_c",
        type=Path,
        nargs="?",
        default=None,
        help="third annotator sheet: enables the three-rater majority path",
    )
    ap.add_argument("--adjudicated", type=Path, help="disagreements.csv with adj_* columns filled")
    ap.add_argument("--out", type=Path, default=Path(__file__).with_name("labels_human.jsonl"))
    ap.add_argument(
        "--disagreements", type=Path, default=Path(__file__).with_name("disagreements.csv")
    )
    args = ap.parse_args(argv)

    a, err_a = read_sheet(args.sheet_a)
    b, err_b = read_sheet(args.sheet_b)
    # --disagreements must never equal --adjudicated in EITHER rater flow: the
    # "w" open would truncate the adjudications unread. Check once, before any
    # disagreements write. (Review: the guard existed only in the three-rater
    # branch; the two-rater flow could still truncate its own adjudications.)
    if args.disagreements is not None and args.adjudicated is not None:
        try:
            same = args.disagreements.resolve() == args.adjudicated.resolve()
        except OSError:
            same = False
        if same:
            print(
                "REFUSING: --disagreements and --adjudicated are the same file; "
                "writing would truncate the adjudications. Use distinct paths."
            )
            return 1
    # Read adjudications before any disagreements write in both flows.
    adj = read_adjudications(args.adjudicated)
    if args.sheet_c is None:
        if err_a or err_b:
            print(
                "INVALID OR BLANK LABEL CELLS (fix the sheet, do not guess):",
                *(err_a + err_b)[:50],
                sep="\n  ",
            )
            return 1
        overlap = sorted(set(a) & set(b))
        print(
            json.dumps(
                {"overlap_pairs": len(overlap), "agreement": agreement_report(a, b, overlap)},
                indent=1,
            )
        )
        n_dis = write_disagreements(args.disagreements, a, b, overlap)
        labels, pending = [], []
        for pid in sorted(set(a) | set(b)):
            v = resolve(pid, a, b, adj)
            (pending.append(pid) if v is None else labels.append(to_label(pid, v)))
        args.out.write_text("".join(json.dumps(x) + "\n" for x in labels))
        print(f"disagreeing overlap pairs: {n_dis} -> {args.disagreements}")
        print(f"exported {len(labels)} labels -> {args.out}; pending adjudication: {len(pending)}")
        return 0
    c, err_c = read_sheet(args.sheet_c)
    if err_a or err_b or err_c:
        print(
            "INVALID OR BLANK LABEL CELLS (fix the sheet, do not guess):",
            *(err_a + err_b + err_c)[:50],
            sep="\n  ",
        )
        return 1
    # adjudications + same-file guard were already read/checked above (both flows).
    overlap = sorted(set(a) & set(b) & set(c))
    print(
        json.dumps(
            {
                "overlap_pairs": len(overlap),
                "n_raters": 3,
                "agreement": agreement_report_3(a, b, c, overlap),
            },
            indent=1,
        )
    )
    n_dis = write_disagreements3(args.disagreements, a, b, c, adj)
    labels, pending = [], []
    for pid in sorted(set(a) | set(b) | set(c)):
        v = resolve3(pid, a, b, c, adj)
        (pending.append(pid) if v is None else labels.append(to_label(pid, v)))
    args.out.write_text("".join(json.dumps(x) + "\n" for x in labels))
    print(f"disagreeing overlap pairs: {n_dis} -> {args.disagreements}")
    print(f"exported {len(labels)} labels -> {args.out}; pending adjudication: {len(pending)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
