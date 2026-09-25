"""Cohen's kappa, confusion matrix, and the two-annotator adjudication merge.

Rule (see docs/agent/B1_gold_set_protocol.md): judge_a == judge_b -> that
label stands. They disagree -> `adjudicated` must be filled in by a third
reviewer; raw judge_a/judge_b are kept, never overwritten.
"""

from __future__ import annotations

from collections import Counter


def confusion_matrix(labels_a: list, labels_b: list) -> dict:
    """Nested {label_a: {label_b: count}} over every class seen in either list."""
    if len(labels_a) != len(labels_b):
        raise ValueError("labels_a and labels_b must be the same length")
    classes = sorted(set(labels_a) | set(labels_b), key=str)
    matrix = {a: {b: 0 for b in classes} for a in classes}
    for a, b in zip(labels_a, labels_b):
        matrix[a][b] += 1
    return matrix


def cohens_kappa(labels_a: list, labels_b: list) -> float:
    """Standard (unweighted) Cohen's kappa over paired categorical labels."""
    n = len(labels_a)
    if n == 0:
        raise ValueError("need at least one labeled pair")
    matrix = confusion_matrix(labels_a, labels_b)
    classes = list(matrix)
    po = sum(matrix[c][c] for c in classes) / n
    count_a, count_b = Counter(labels_a), Counter(labels_b)
    pe = sum((count_a[c] / n) * (count_b[c] / n) for c in classes)
    if pe == 1.0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)


def adjudicate(judge_a, judge_b, adjudicated=None):
    """Final label for one row. Raises if the judges disagree and no
    adjudicated value was supplied — that is an incomplete row, not a 'no'."""
    if judge_a == judge_b:
        return judge_a
    if adjudicated is None or adjudicated == "":
        raise ValueError(f"disagreement (a={judge_a!r}, b={judge_b!r}) with no adjudicated value")
    return adjudicated


def merge_adjudicated(
    rows: list[dict],
    col_a: str = "judge_a",
    col_b: str = "judge_b",
    col_adj: str = "adjudicated",
) -> tuple[list[dict], dict]:
    """Adds 'final_label' to each row (copy). Returns (rows, summary) where
    summary reports agreement counts and Cohen's kappa over the raw judgments."""
    merged = []
    n_agree = 0
    for row in rows:
        row = dict(row)
        row["final_label"] = adjudicate(row.get(col_a), row.get(col_b), row.get(col_adj))
        n_agree += int(row.get(col_a) == row.get(col_b))
        merged.append(row)
    kappa = cohens_kappa([r[col_a] for r in rows], [r[col_b] for r in rows]) if rows else None
    summary = {
        "n": len(rows),
        "n_agree": n_agree,
        "n_disagree": len(rows) - n_agree,
        "cohens_kappa": round(kappa, 4) if kappa is not None else None,
    }
    return merged, summary


if __name__ == "__main__":
    a = ["yes", "no", "yes", "yes", "no", "no"]
    b = ["yes", "no", "yes", "no", "no", "yes"]
    k = cohens_kappa(a, b)
    assert -1.0 <= k <= 1.0
    assert cohens_kappa(["yes"] * 5, ["yes"] * 5) == 1.0
    rows = [
        {"judge_a": "yes", "judge_b": "yes"},
        {"judge_a": "yes", "judge_b": "no", "adjudicated": "no"},
    ]
    merged, summary = merge_adjudicated(rows)
    assert merged[0]["final_label"] == "yes"
    assert merged[1]["final_label"] == "no"
    assert summary["n_disagree"] == 1
    try:
        adjudicate("yes", "no")
        raise AssertionError("should have raised on missing adjudication")
    except ValueError:
        pass
    print("ok", round(k, 4), summary)
