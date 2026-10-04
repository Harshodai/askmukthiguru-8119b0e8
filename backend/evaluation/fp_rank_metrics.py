"""Rank-based retrieval metrics for the first-person golden evals (Wave R-B).

Eval-only, stdlib-only, zero production impact. Supplements the harness's
top-1 / paraphrase-consistency summary with the standard retrieval ladder
(QDRANT_FP_RESEARCH_2026-10-04.md rec#2, OKF R5):

- recall@{5,10} — "is a relevant clip in top-k?" (primary RAG gate)
- MRR — first-hit rank (single-query reciprocal rank; mean over queries)
- NDCG@10 — binary, single-ideal (ideal = hit at rank 1, so NDCG = DCG).
  Documented limitation: our gold labels are span-overlap hits, not graded
  relevance, so this measures rank-discounted hit, not true graded NDCG.
- per-leg logging — recorded by the harness probe (fused RRF scores per
  rank, dense-only top-1, sparse-leg-active flag); agreement summarized here.
- per-class floors (OKF R5) — group rows by ``question_class``
  (standard / unanswerable / comparative / multilingual) instead of trusting
  a single average.
- abstention slice — out-of-corpus rows (answerable=false) expect
  status ``abstained`` (or ``weak_match``: anything but a direct ``success``);
  false refusal = answerable rows with status ``abstained``.

Row contract (additive keys the harness attaches; nothing here touches Qdrant):
    question_class: str (default "standard")
    rank_metrics: {recall_at_5, recall_at_10, reciprocal_rank, ndcg_at_10,
                   n_candidates, first_hit_rank} | None
    legs: {fused_scores, dense_top1_video, dense_top1_point, fused_dense_agree,
           sparse_leg_active} | None
"""

from __future__ import annotations

import math

RANK_KS = (5, 10)
NDCG_K = 10


def recall_at_k(hits: list[bool], k: int) -> float:
    """1.0 if any of the first k ranks is a hit, else 0.0 (empty = miss)."""
    return 1.0 if any(hits[:k]) else 0.0


def reciprocal_rank(hits: list[bool]) -> float:
    """1/rank of the first hit, 0.0 when nothing hits."""
    for i, h in enumerate(hits):
        if h:
            return 1.0 / (i + 1)
    return 0.0


def ndcg_at_k(hits: list[bool], k: int = NDCG_K) -> float:
    """Binary single-ideal NDCG: ideal ranking hits at rank 1 (IDCG = 1.0)."""
    dcg = sum(1.0 / math.log2(i + 2) for i, h in enumerate(hits[:k]) if h)
    return round(dcg, 4)


def score_ranking(
    hit_list: list[bool],
    n_candidates: int = 0,
    ks: tuple[int, ...] = RANK_KS,
    ndcg_k: int = NDCG_K,
) -> dict:
    """Pure score of one ranked list given its per-rank hit flags."""
    first_hit = next((i + 1 for i, h in enumerate(hit_list) if h), None)
    out: dict = {
        "reciprocal_rank": round(reciprocal_rank(hit_list), 4),
        "ndcg_at_10": ndcg_at_k(hit_list, ndcg_k),
        "n_candidates": n_candidates,
        "first_hit_rank": first_hit,
    }
    for k in ks:
        out[f"recall_at_{k}"] = recall_at_k(hit_list, k)
    return out


def _mean(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 4) if xs else None


def summarize_rank_metrics(rows: list[dict]) -> dict:
    """Mean recall@{5,10} / MRR / NDCG@10 over answerable rows that carry
    rank data. Rows without a probe (rank_metrics None) are excluded and
    counted — never scored as zero."""
    pool = [r for r in rows if r.get("answerable") and r.get("rank_metrics")]
    skipped = sum(1 for r in rows if r.get("answerable") and not r.get("rank_metrics"))
    if not pool:
        return {
            "n": 0,
            "n_skipped_no_probe": skipped,
            "recall_at_5": None,
            "recall_at_10": None,
            "mrr": None,
            "ndcg_at_10": None,
        }
    return {
        "n": len(pool),
        "n_skipped_no_probe": skipped,
        "recall_at_5": _mean([r["rank_metrics"]["recall_at_5"] for r in pool]),
        "recall_at_10": _mean([r["rank_metrics"]["recall_at_10"] for r in pool]),
        "mrr": _mean([r["rank_metrics"]["reciprocal_rank"] for r in pool]),
        "ndcg_at_10": _mean([r["rank_metrics"]["ndcg_at_10"] for r in pool]),
    }


def per_class_summary(rows: list[dict]) -> dict:
    """Per-question-class floors (OKF R5): each class reports its own n,
    top-1 hit rate (answerable only), rank means, and abstention behavior.
    No single average across classes — a cascade that never abstains must
    not hide behind a rising NDCG."""
    classes: dict[str, list[dict]] = {}
    for r in rows:
        classes.setdefault(r.get("question_class") or "standard", []).append(r)
    out: dict[str, dict] = {}
    for cls in sorted(classes):
        members = classes[cls]
        answerable = [r for r in members if r.get("answerable")]
        ooc = [r for r in members if not r.get("answerable")]
        ranked = [r for r in answerable if r.get("rank_metrics")]
        out[cls] = {
            "n": len(members),
            "n_answerable": len(answerable),
            "n_unanswerable": len(ooc),
            "top1_hit_rate": _mean([1.0 if r.get("hit") else 0.0 for r in answerable])
            if answerable
            else None,
            "recall_at_5": _mean([r["rank_metrics"]["recall_at_5"] for r in ranked])
            if ranked
            else None,
            "recall_at_10": _mean([r["rank_metrics"]["recall_at_10"] for r in ranked])
            if ranked
            else None,
            "mrr": _mean([r["rank_metrics"]["reciprocal_rank"] for r in ranked])
            if ranked
            else None,
            "ndcg_at_10": _mean([r["rank_metrics"]["ndcg_at_10"] for r in ranked])
            if ranked
            else None,
            "abstain_rate_unanswerable": _mean(
                [1.0 if r.get("status") == "abstained" else 0.0 for r in ooc]
            )
            if ooc
            else None,
        }
    return out


def abstention_summary(rows: list[dict]) -> dict:
    """Abstention contract in one place: OOC rows should abstain (expected
    1.0 — reported, never a CI fail pre-ingest); answerable abstains are the
    false-refusal proxy."""
    ooc = [r for r in rows if not r.get("answerable")]
    ans = [r for r in rows if r.get("answerable")]
    return {
        "n_unanswerable": len(ooc),
        "unanswerable_abstain_rate": _mean(
            [1.0 if r.get("status") == "abstained" else 0.0 for r in ooc]
        )
        if ooc
        else None,
        "unanswerable_non_direct_rate": _mean(
            [1.0 if r.get("status") in ("abstained", "weak_match") else 0.0 for r in ooc]
        )
        if ooc
        else None,
        "n_answerable": len(ans),
        "answerable_abstain_rate": _mean(
            [1.0 if r.get("status") == "abstained" else 0.0 for r in ans]
        )
        if ans
        else None,
    }


def legs_agreement_summary(rows: list[dict]) -> dict:
    """Per-leg probe agreement: share of probed queries where the dense-only
    top-1 video matches the fused top-1 video. Low agreement + fused wins =
    the sparse leg earns its keep; high agreement = fusion adds little."""
    probed = [r for r in rows if r.get("legs")]
    if not probed:
        return {"n_probed": 0, "fused_dense_top1_agree_rate": None, "sparse_leg_active_rate": None}
    return {
        "n_probed": len(probed),
        "fused_dense_top1_agree_rate": _mean(
            [1.0 if r["legs"].get("fused_dense_agree") else 0.0 for r in probed]
        ),
        "sparse_leg_active_rate": _mean(
            [1.0 if r["legs"].get("sparse_leg_active") else 0.0 for r in probed]
        ),
    }


if __name__ == "__main__":
    assert recall_at_k([False, True, False], 5) == 1.0
    assert recall_at_k([False] * 10, 5) == 0.0
    assert recall_at_k([], 5) == 0.0
    assert abs(reciprocal_rank([False, False, True]) - 1 / 3) < 1e-9
    assert reciprocal_rank([True]) == 1.0
    assert reciprocal_rank([False]) == 0.0
    assert ndcg_at_k([True]) == 1.0
    assert ndcg_at_k([False, True]) == round(1 / math.log2(3), 4)
    s = score_ranking([False, True, False])
    assert s["recall_at_5"] == 1.0 and s["first_hit_rank"] == 2
    assert s["reciprocal_rank"] == 0.5
    empty = summarize_rank_metrics([{"answerable": True, "rank_metrics": None}])
    assert empty["n"] == 0 and empty["recall_at_5"] is None
    print("ok")
