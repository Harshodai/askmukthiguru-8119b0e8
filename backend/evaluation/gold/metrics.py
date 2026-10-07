"""Gold-set evaluation metrics for the first-person verbatim answer path.

`overlap_frac`/`passage_hits_ranges`/`bootstrap_ci_by_video` are ported
near-verbatim from
/Users/harshodaikolluru/mukthiguru_attribution_data/bakeoff_2026-09-25/{scoring.py,scoring_lib.py}
(that tree is outside this repo and synthetic-question-only, so it cannot be
imported directly — this is the reuse, not a rewrite). `clopper_pearson_upper`
is new: bake-off scoring.py never needed a hard error bound, only point
estimates + bootstrap CIs.

Row contract (a "scored row" — callers build these by joining adjudicated
gold labels to one system's predictions; nothing here computes predictions):

    id, video_id, group_id (set => credit is any-of an equivalence group)
    answerable: bool
    confident: bool          # system chose to answer rather than abstain
    top1_clip_id, topk_clip_ids: list[str]
    top1_video_id, top1_start, top1_end
    gold_ranges: list[{"video_id","start","end"}]   # acceptable answer set
    top1_speaker, gold_speaker                       # for wrong-speaker rate
    displayed_text, gold_verbatim_text               # for verbatim mismatch
    pred_start_ms, gold_start_ms                     # timestamp-error subset
"""

from __future__ import annotations

import math
import random

N_BOOT = 2000
RNG_SEED = 42


# --- ported from bakeoff scoring_lib.py -------------------------------------


def overlap_frac(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    inter = min(a_end, b_end) - max(a_start, b_start)
    if inter <= 0:
        return 0.0
    denom = min(a_end - a_start, b_end - b_start)
    return inter / denom if denom > 0 else 0.0


def passage_hits_ranges(clip: dict, ranges: list[dict], threshold: float = 0.5) -> bool:
    for r in ranges:
        if r["video_id"] != clip["video_id"]:
            continue
        if overlap_frac(clip["start"], clip["end"], r["start"], r["end"]) >= threshold:
            return True
    return False


# --- ported from bakeoff scoring.py -----------------------------------------


def bootstrap_ci_by_video(
    rows: list[dict], key: str, video_key: str = "video_id", n_boot: int = N_BOOT
) -> dict:
    """Cluster (not row-level) bootstrap: errors correlate within a video, so
    resampling videos (not rows) is what makes the CI honest."""
    by_video: dict[str, list[dict]] = {}
    for r in rows:
        by_video.setdefault(r.get(video_key) or "GROUP", []).append(r)
    videos = list(by_video)
    if not videos:
        return {"mean": None, "ci_low": None, "ci_high": None, "n": 0, "n_videos": 0}
    rng = random.Random(RNG_SEED)
    point = sum(r[key] for r in rows) / len(rows)
    boots = []
    for _ in range(n_boot):
        sample = [r for v in (rng.choice(videos) for _ in videos) for r in by_video[v]]
        if sample:
            boots.append(sum(r[key] for r in sample) / len(sample))
    boots.sort()
    lo = boots[int(0.025 * len(boots))] if boots else None
    hi = boots[int(0.975 * len(boots)) - 1] if boots else None
    return {
        "mean": round(point, 4),
        "ci_low": round(lo, 4) if lo is not None else None,
        "ci_high": round(hi, 4) if hi is not None else None,
        "n": len(rows),
        "n_videos": len(videos),
    }


# --- new: exact one-sided Clopper-Pearson upper bound, stdlib-only ----------


def clopper_pearson_upper(
    n_errors: int | None = None,
    n_confident: int | None = None,
    alpha: float = 0.05,
    *,
    k_errors: int | None = None,
    n_total: int | None = None,
    delta: float | None = None,
) -> float:
    """One-sided upper bound U such that P(X <= n_errors | n_confident, U) = alpha.
    Equivalent to the Beta(n_errors+1, n_confident-n_errors).ppf(1-alpha) form,
    solved by bisection on the binomial CDF so no scipy dependency is needed —
    n_errors is always tiny (0-3) so the CDF sum is cheap regardless of n."""
    if k_errors is not None:
        n_errors = k_errors
    if n_total is not None:
        n_confident = n_total
    if delta is not None:
        alpha = delta

    if n_errors is None or n_confident is None:
        raise ValueError("Must provide errors and total count")
    if n_confident <= 0:
        raise ValueError("n_confident must be positive")
    if n_errors >= n_confident:
        return 1.0

    # Bisect on the regularized incomplete beta function I_p(n_errors+1, n_confident-n_errors)
    # using a log-space stable evaluation. This avoids the comb*p^k*(1-p)^(n-k) overflow.
    def _log_beta_cdf(p: float) -> float:
        """log of sum_{k=0}^{n_errors} C(n,k)*p^k*(1-p)^(n-k) via log-space accumulation."""
        if p <= 0.0:
            return math.log(1.0) if n_errors >= 0 else -math.inf
        if p >= 1.0:
            return 0.0
        log_p, log_1mp = math.log(p), math.log(1 - p)
        log_total = -math.inf
        log_term = (
            math.lgamma(n_confident + 1)
            - math.lgamma(0 + 1)
            - math.lgamma(n_confident - 0 + 1)
            + 0 * log_p
            + n_confident * log_1mp
        )
        for k in range(n_errors + 1):
            if k > 0:
                log_term += log_p - log_1mp + math.log(n_confident - k + 1) - math.log(k)
            log_total = (
                log_total
                if log_total > log_term
                else math.log1p(math.exp(log_total - log_term)) + log_term
            )
        return log_total

    log_alpha = math.log(alpha)
    lo, hi = 0.0, 1.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if _log_beta_cdf(mid) > log_alpha:
            lo = mid
        else:
            hi = mid
    return hi


# --- headline metrics --------------------------------------------------------


def precision_confident(rows: list[dict]) -> dict:
    confident = [r for r in rows if r["confident"]]
    correct = [r for r in confident if _is_correct(r, group=True)]
    return bootstrap_ci_by_video(
        [
            {"video_id": r["video_id"], "correct": 1.0 if _is_correct(r, group=True) else 0.0}
            for r in confident
        ],
        "correct",
    ) | {"n_correct": len(correct), "n_confident": len(confident)}


def coverage(rows: list[dict]) -> float:
    return sum(1 for r in rows if r["confident"]) / len(rows) if rows else 0.0


def abstention_rate(rows: list[dict]) -> float:
    return 1.0 - coverage(rows)


def _is_correct(row: dict, group: bool) -> bool:
    if not row.get("top1_video_id"):
        return False
    clip = {"video_id": row["top1_video_id"], "start": row["top1_start"], "end": row["top1_end"]}
    ranges = row["gold_ranges"] if (group or not row.get("group_id")) else []
    return passage_hits_ranges(clip, ranges)


def topk_hit_rate(rows: list[dict], k: int, group: bool = False) -> dict:
    """Strict (group=False, single-answer questions only) or group-level
    (any clip in the acceptable-answer set/equivalence group) top-k hit rate."""
    pool = [r for r in rows if r["answerable"] and (group or not r.get("group_id"))]
    scored = []
    for r in pool:
        hit = any(
            passage_hits_ranges({"video_id": vid, "start": s, "end": e}, r["gold_ranges"])
            for vid, s, e in _topk_clips(r, k)
        )
        scored.append({"video_id": r["video_id"], "hit": 1.0 if hit else 0.0})
    return bootstrap_ci_by_video(scored, "hit")


def _topk_clips(row: dict, k: int) -> list[tuple]:
    """Best-effort: rows carry only top1 coordinates plus a clip-id list for
    ranks 2..k; a caller wanting exact top-3 overlap must supply per-clip
    coordinates in `topk_ranges` (falls back to just top-1 otherwise)."""
    if "topk_ranges" in row:
        return [(c["video_id"], c["start"], c["end"]) for c in row["topk_ranges"][:k]]
    if row.get("top1_video_id"):
        return [(row["top1_video_id"], row["top1_start"], row["top1_end"])]
    return []


def wrong_speaker_rate(rows: list[dict]) -> float:
    confident = [r for r in rows if r["confident"] and r.get("top1_clip_id")]
    if not confident:
        return 0.0
    wrong = sum(
        1 for r in confident if r.get("gold_speaker") and r.get("top1_speaker") != r["gold_speaker"]
    )
    return round(wrong / len(confident), 4)


def verbatim_mismatch_rate(rows: list[dict]) -> float:
    labeled = [
        r
        for r in rows
        if r.get("displayed_text") is not None and r.get("gold_verbatim_text") is not None
    ]
    if not labeled:
        return 0.0
    mismatched = sum(1 for r in labeled if r["displayed_text"] not in r["gold_verbatim_text"])
    return round(mismatched / len(labeled), 4)


def timestamp_error_ms(rows: list[dict]) -> dict:
    diffs = sorted(
        abs(r["pred_start_ms"] - r["gold_start_ms"])
        for r in rows
        if r.get("pred_start_ms") is not None and r.get("gold_start_ms") is not None
    )
    if not diffs:
        return {"mean_ms": None, "median_ms": None, "p95_ms": None, "n": 0}
    return {
        "mean_ms": round(sum(diffs) / len(diffs), 1),
        "median_ms": diffs[len(diffs) // 2],
        "p95_ms": diffs[min(int(0.95 * len(diffs)), len(diffs) - 1)],
        "n": len(diffs),
    }


if __name__ == "__main__":
    assert overlap_frac(0, 10, 5, 8) == 1.0
    assert overlap_frac(0, 10, 20, 30) == 0.0
    assert abs(clopper_pearson_upper(0, 299) - 0.01) < 0.001
    assert abs(clopper_pearson_upper(2, 628) - 0.01) < 0.001
    assert clopper_pearson_upper(0, 10) > clopper_pearson_upper(0, 1000)

    rows = [
        {
            "id": "q1",
            "video_id": "v1",
            "group_id": None,
            "answerable": True,
            "confident": True,
            "top1_clip_id": "c1",
            "top1_video_id": "v1",
            "top1_start": 10.0,
            "top1_end": 20.0,
            "gold_ranges": [{"video_id": "v1", "start": 10.0, "end": 20.0}],
            "top1_speaker": "krishnaji",
            "gold_speaker": "krishnaji",
            "displayed_text": "love is stillness",
            "gold_verbatim_text": "true love is stillness within",
            "pred_start_ms": 10000,
            "gold_start_ms": 10050,
        },
        {
            "id": "q2",
            "video_id": "v2",
            "group_id": None,
            "answerable": True,
            "confident": False,
            "top1_clip_id": None,
            "top1_video_id": None,
            "top1_start": None,
            "top1_end": None,
            "gold_ranges": [{"video_id": "v2", "start": 0.0, "end": 5.0}],
            "top1_speaker": None,
            "gold_speaker": "preethaji",
            "displayed_text": None,
            "gold_verbatim_text": None,
            "pred_start_ms": None,
            "gold_start_ms": None,
        },
    ]
    assert coverage(rows) == 0.5
    assert abstention_rate(rows) == 0.5
    prec = precision_confident(rows)
    assert prec["n_confident"] == 1 and prec["n_correct"] == 1
    assert wrong_speaker_rate(rows) == 0.0
    assert verbatim_mismatch_rate(rows) == 0.0  # displayed_text is a true substring of gold
    rows[0]["displayed_text"] = "love is fabricated"
    assert verbatim_mismatch_rate(rows) == 1.0  # not a substring -> mismatch
    ts = timestamp_error_ms(rows)
    assert ts["n"] == 1 and ts["mean_ms"] == 50.0
    top1 = topk_hit_rate(rows, 1)
    assert top1["mean"] == 0.5  # v2's abstain still counts as a miss for coverage-of-hits
    print("ok", prec, ts)
