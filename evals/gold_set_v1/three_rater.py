"""Krippendorff's alpha for the three-rater gold-set path.

Agreement computation lives here, not in backend/evaluation/gold/agreement.py
(which is read-only for the gold-set work): pairwise kappa and majority_vote
are reused from there unchanged.

Method (Krippendorff 2004, "Content Analysis: An Introduction to Its
Methodology", ch. 11): for each item, count pairable value coincidences
o_ck over the raters that labelled it, weighting each item by 1/(m-1) so an
item labelled by 2 raters and one labelled by 3 contribute equally per
rater. Observed and expected disagreement are:

    D_o = sum_ck o_ck * d^2_ck / n
    D_e = sum_ck n_c * n_k * d^2_ck / (n * (n - 1))
    alpha = 1 - D_o / D_e

Difference metric d^2 (chosen per dimension by the caller):
  nominal (complete, speaker, risk): 0 when equal, 1 otherwise.
  ordinal (relevance 0-3): Krippendorff's ordinal metric, the squared
    difference of cumulative-frequency ranks:
      d^2_ck = (sum_{g between c and k} n_g - (n_c + n_k) / 2)^2,
    where n_g are the observed category totals over pairable values. A
    frequent category lying between c and k stretches their distance;
    the plain (c - k)^2 form is Krippendorff's *interval* metric and
    wrongly assumes equal spacing, which 0-3 does not promise. A scale
    factor cancels in the D_o / D_e ratio, so no normalisation is needed.

Missing labels (partial overlap: a pair labelled by only 2 of 3 raters, or
SKIPPED rows) are handled by construction: None entries never enter the
coincidence matrix, and items with fewer than 2 labels are skipped. Alpha
therefore runs over the union of the three sheets, while the pairwise
kappas in score_gold.py run over the triple overlap only.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from evaluation.gold.agreement import cohens_kappa, majority_vote  # noqa: E402

LEVELS = ("nominal", "ordinal")


def _delta(level: str, c, k, totals: dict | None = None, order: list | None = None) -> float:
    if level == "nominal":
        return 0.0 if c == k else 1.0
    if level == "ordinal":
        if c == k:
            return 0.0
        if totals is None or order is None:
            raise ValueError("ordinal delta needs category totals and order")
        lo, hi = (c, k) if order.index(c) <= order.index(k) else (k, c)
        between = order[order.index(lo) : order.index(hi) + 1]
        rank_gap = sum(totals[g] for g in between) - (totals[lo] + totals[hi]) / 2.0
        return float(rank_gap**2)
    raise ValueError(f"level must be one of {LEVELS}, got {level!r}")


def krippendorff_alpha(items: list[list], level: str = "nominal") -> float:
    """Alpha over items; each item is the list of its raters' values, None = missing.

    Raises ValueError when no item has 2+ labels, or on an unknown level.
    Returns 1.0 when every pairable label agrees (D_e == 0 and D_o == 0).
    """
    if level not in LEVELS:
        raise ValueError(f"level must be one of {LEVELS}, got {level!r}")
    coincidences: dict = defaultdict(float)
    totals: dict = defaultdict(float)
    n, n_items = 0.0, 0
    for item in items:
        vals = [v for v in item if v is not None]
        if len(vals) < 2:
            continue
        n_items += 1
        counts: dict = defaultdict(int)
        for v in vals:
            counts[v] += 1
        m = len(vals)
        for c, nc in counts.items():
            coincidences[(c, c)] += nc * (nc - 1) / (m - 1)
            for k, nk in counts.items():
                if k != c:
                    coincidences[(c, k)] += nc * nk / (m - 1)
        for v in vals:
            totals[v] += 1
            n += 1
    if n_items == 0:
        raise ValueError("need at least one item with 2+ labels")
    n_c = dict(totals)
    order = sorted(n_c) if level == "ordinal" else None
    do = sum(o * _delta(level, c, k, n_c, order) for (c, k), o in coincidences.items()) / n
    de = sum(n_c[c] * n_c[k] * _delta(level, c, k, n_c, order) for c in n_c for k in n_c) / (
        n * (n - 1)
    )
    if de == 0:
        return 1.0 if do == 0 else 0.0
    return 1.0 - do / de


def usable_items(items: list[list]) -> int:
    """Items contributing to alpha (2+ non-missing labels)."""
    return sum(1 for item in items if sum(v is not None for v in item) >= 2)


def pairwise_kappa(a_vals: list, b_vals: list) -> float:
    """Unweighted Cohen's kappa over co-present pairs (None = missing, dropped).

    Reuses cohens_kappa; the caller picks the pair. Raises ValueError when no
    co-present pair exists.
    """
    pairs = [(a, b) for a, b in zip(a_vals, b_vals) if a is not None and b is not None]
    if not pairs:
        raise ValueError("need at least one co-present pair")
    la = [p[0] for p in pairs]
    return cohens_kappa(la, [p[1] for p in pairs])


def majority_or_pending(votes: list, adjudicated=None, allowed: tuple = ()) -> str | None:
    """Majority winner, else the adjudicated value, else None (still pending).

    Reuses majority_vote: unanimous or strict-majority resolves. A split needs
    an adjudicated value inside `allowed`; blank or out-of-allowed stays
    pending (None) rather than raising, so the caller can list it.
    """
    maj = majority_vote(votes)
    if maj is not None:
        return maj
    if adjudicated is not None and adjudicated != "" and (not allowed or adjudicated in allowed):
        return adjudicated
    return None


if __name__ == "__main__":
    y, n = "yes", "no"
    nominal = [[y, y, y], [y, y, y], [y, y, n], [y, n, n], [n, n, n]]
    assert abs(krippendorff_alpha(nominal) - 13 / 27) < 1e-9  # hand-computed fixture
    assert krippendorff_alpha([[2, 2, 2], [3, 3, None]], "ordinal") == 1.0
    assert usable_items([[y, None, None], [y, n, None]]) == 1
    near = krippendorff_alpha([[0, 0], [1, 2], [3, 3], [2, 2]], "ordinal")
    far = krippendorff_alpha([[0, 0], [1, 3], [3, 3], [2, 2]], "ordinal")
    assert near > far  # off-by-one costs less than off-by-two
    assert pairwise_kappa([y, y, None], [y, n, y]) == 0.0
    assert majority_or_pending([y, y, n]) == y
    assert majority_or_pending([y, n, "unsure"]) is None
    assert (
        majority_or_pending([y, n, "unsure"], adjudicated="unsure", allowed=(y, n, "unsure"))
        == "unsure"
    )
    assert (
        majority_or_pending([y, n, "unsure"], adjudicated="maybe", allowed=(y, n, "unsure")) is None
    )
    try:
        krippendorff_alpha([[y, None, None]])
        raise AssertionError("should have raised on no pairable item")
    except ValueError:
        pass
    print("ok", round(krippendorff_alpha(nominal), 4))
