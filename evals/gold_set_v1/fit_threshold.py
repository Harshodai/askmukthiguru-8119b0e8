"""Fit a 1%-risk serving threshold on HUMAN labels with backend's SelectiveRiskCalibrator.

    python3 evals/gold_set_v1/fit_threshold.py --labels labels_human.jsonl \
        --scores pairs_scores.csv --score-col dense_cosine --unit top1 [--min-annotators 2] [--profile-out p.json]

Correct (label 1) = relevance >= 2 AND complete AND NOT risk AND speaker_is_teacher == "yes".
"unsure" speaker counts as NOT correct (fail closed).
--unit top1 keeps only the rank-0 clip per question: the served unit, and the one the profile's
threshold is applied to at request time. --unit pair uses every labelled pair; never ship a
pair-fitted threshold against a top-1 serving rule.
Learn-then-Test fixed-sequence walk + Clopper-Pearson is backend/evaluation/gold/calibrator.py,
reused unchanged. Prints 'insufficient labels' (exit 2) when n < the zero-error minimum (299 at 1%/0.05).
Never run this on AI labels (.work/autoresearch_fp/labels.jsonl): CLAUDE.md invariant 3.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from evaluation.gold.calibrator import SelectiveRiskCalibrator  # noqa: E402
from evaluation.gold.metrics import clopper_pearson_upper  # noqa: E402


def is_correct(lab: dict) -> int:
    return int(
        lab["relevance"] >= 2
        and lab["complete"]
        and not lab["risk"]
        and lab.get("speaker_is_teacher") == "yes"
    )


def min_items(target_risk: float, delta: float) -> int:
    n = 1
    while clopper_pearson_upper(k_errors=0, n_total=n, delta=delta) > target_risk:
        n += 1
    return n


def load(
    labels_path: Path, scores_path: Path, score_col: str, unit: str, min_ann: int
) -> tuple[list, list]:
    labels = {}
    for line in labels_path.read_text().splitlines():
        if line.strip():
            lab = json.loads(line)
            if lab.get("source") != "human":
                raise ValueError(
                    f"{lab.get('id')}: not a human label (source={lab.get('source')!r}); refusing"
                )
            labels[lab["id"]] = lab
    scores, ys = [], []
    with scores_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            lab = labels.get(row["pair_id"])
            if lab is None or lab.get("n_annotators", 1) < min_ann:
                continue
            if unit == "top1" and row["cand_rank"] != "0":
                continue
            scores.append(float(row[score_col]))
            ys.append(is_correct(lab))
    return scores, ys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--labels", type=Path, required=True)
    ap.add_argument("--scores", type=Path, default=Path(__file__).with_name("pairs_scores.csv"))
    ap.add_argument("--score-col", default="dense_cosine")
    ap.add_argument("--unit", choices=("top1", "pair"), required=True)
    ap.add_argument("--min-annotators", type=int, default=1, choices=(1, 2))
    ap.add_argument("--target-risk", type=float, default=0.01)
    ap.add_argument("--delta", type=float, default=0.05)
    ap.add_argument("--collection", default="first_person_v8")
    ap.add_argument("--profile-out", type=Path)
    args = ap.parse_args(argv)

    scores, ys = load(args.labels, args.scores, args.score_col, args.unit, args.min_annotators)
    need = min_items(args.target_risk, args.delta)
    print(
        f"unit={args.unit} n={len(ys)} correct={sum(ys)} need>={need} confident items with 0 errors"
    )
    if len(ys) < need or sum(ys) < need:
        print(
            f"insufficient labels: n={len(ys)}, correct={sum(ys)}; need >= {need} correct items in the "
            f"selected set (zero errors) for risk {args.target_risk} at delta {args.delta}"
        )
        return 2
    cal = SelectiveRiskCalibrator(scores, ys)
    point = cal.find_operating_threshold(target_risk=args.target_risk, delta=args.delta)
    if point is None:
        print(
            "no operating point: no threshold passes the Clopper-Pearson bound (abstain everywhere)"
        )
        return 3
    print(json.dumps(point, indent=1))
    if args.profile_out:
        prof = cal.to_profile(
            point,
            collection=args.collection,
            target_risk=args.target_risk,
            score_kind=args.score_col,
        ) | {"unit": args.unit, "min_annotators": args.min_annotators}
        args.profile_out.write_text(json.dumps(prof, indent=1))
        print("wrote", args.profile_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
