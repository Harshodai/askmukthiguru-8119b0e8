"""Cross-video diversity (MMR) for first-person candidate pools.

A single long discourse can occupy every candidate slot: ``FirstPersonContextStore.retrieve``
returns the ``limit_parents`` highest-scoring parents, and near-identical spans from one video
routinely cluster at the top. That spends the whole harness budget on one teacher moment and
starves the other videos in the corpus.

This module caps how many candidates one video may contribute and orders the surviving pool by
Maximal Marginal Relevance, so a second video is evaluated instead of a redundant sibling.

Contract (additive, never destructive):

* every input candidate is returned exactly once;
* a candidate deferred by the per-video cap moves to the tail in its original relative order, so
  a caller that walks the whole list still sees it;
* text is never edited, generated, or dropped — only the order changes;
* any failure (missing video id, non-finite score, bad similarity) degrades to the input order.

No third-party dependency: similarity is Jaccard overlap over normalised word sets.
"""

from __future__ import annotations

import logging
import math
import re
from collections.abc import Callable, Sequence
from typing import Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_MAX_PER_VIDEO = 2
DEFAULT_MMR_LAMBDA = 0.7

_WORD_RE = re.compile(r"[a-z0-9']+")
_STOPWORDS = frozenset(
    "a an the and or but if then so of to in on at for with from by is are was were be been "
    "being it its this that these those you your we our i me my he she they them his her as "
    "not no do does did have has had will would can could there here what which who whom".split()
)


def _word_set(text: str) -> frozenset[str]:
    return frozenset(
        token for token in _WORD_RE.findall((text or "").lower()) if token not in _STOPWORDS
    )


def jaccard_similarity(left: str, right: str) -> float:
    """Token-overlap similarity in ``[0, 1]``; 0.0 when either side is empty."""
    l_words, r_words = _word_set(left), _word_set(right)
    if not l_words or not r_words:
        return 0.0
    union = l_words | r_words
    return len(l_words & r_words) / len(union)


def _get(candidate: Any, key: str, default: Any = None) -> Any:
    if isinstance(candidate, dict):
        return candidate.get(key, default)
    return getattr(candidate, key, default)


def _finite_score(candidate: Any, relevance_key: str) -> float:
    try:
        value = float(_get(candidate, relevance_key, 0.0) or 0.0)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return value if math.isfinite(value) else 0.0


def _video_of(candidate: Any, video_key: str) -> str:
    return str(_get(candidate, video_key, "") or "").strip()


def _text_of(candidate: Any, text_key: str) -> str:
    return str(_get(candidate, text_key, "") or "")


def apply_cross_video_diversity(
    candidates: Sequence[Any],
    *,
    max_per_video: int = DEFAULT_MAX_PER_VIDEO,
    mmr_lambda: float = DEFAULT_MMR_LAMBDA,
    video_key: str = "video_id",
    relevance_key: str = "score",
    text_key: str = "text",
    similarity_fn: Optional[Callable[[str, str], float]] = None,
) -> tuple[list[Any], int]:
    """Reorder ``candidates`` by MMR with a per-video cap.

    Args:
        candidates: Anything with ``video_id`` / ``score`` / ``text`` attributes or dict keys.
        max_per_video: How many candidates one video may contribute to the head. ``<= 0``
            disables the cap (pure MMR).
        mmr_lambda: 1.0 = relevance only, 0.0 = maximum diversity.
        video_key / relevance_key / text_key: Field names for attribute or dict access.
        similarity_fn: Optional ``(text_a, text_b) -> float``; defaults to word Jaccard.

    Returns:
        ``(ordered, deferred_count)``. ``ordered`` contains every input candidate exactly once:
        the diverse head first, then the deferred tail in original order.
    """
    items = list(candidates)
    if len(items) < 2:
        return items, 0

    sim = similarity_fn or jaccard_similarity
    lam = mmr_lambda
    if not isinstance(lam, (int, float)) or not math.isfinite(float(lam)):
        lam = DEFAULT_MMR_LAMBDA
    lam = min(1.0, max(0.0, float(lam)))
    cap = int(max_per_video)

    # Deterministic seed order: best relevance first, ties by original position.
    indexed = list(enumerate(items))
    try:
        indexed.sort(key=lambda pair: (-_finite_score(pair[1], relevance_key), pair[0]))
    except (TypeError, ValueError):
        return items, 0

    remaining = indexed
    selected: list[Any] = []
    selected_texts: list[str] = []
    per_video: dict[str, int] = {}
    deferred: list[Any] = []

    while remaining:
        best_pair: Optional[tuple[int, Any]] = None
        best_value = -math.inf
        for position, (_, candidate) in enumerate(remaining):
            video = _video_of(candidate, video_key)
            if cap > 0 and video and per_video.get(video, 0) >= cap:
                continue
            relevance = _finite_score(candidate, relevance_key)
            text = _text_of(candidate, text_key)
            redundancy = 0.0
            if selected_texts and text:
                try:
                    redundancy = max(sim(text, prior) for prior in selected_texts)
                except Exception:  # noqa: BLE001 - diversity must never break serving
                    redundancy = 0.0
            value = lam * relevance - (1.0 - lam) * redundancy
            if value > best_value:
                best_value = value
                best_pair = (position, candidate)

        if best_pair is None:
            # Every remaining candidate is at its video cap: keep them, in order.
            deferred.extend(candidate for _, candidate in remaining)
            break

        position, chosen = best_pair
        selected.append(chosen)
        chosen_text = _text_of(chosen, text_key)
        if chosen_text:
            selected_texts.append(chosen_text)
        video = _video_of(chosen, video_key)
        if video:
            per_video[video] = per_video.get(video, 0) + 1
        remaining = remaining[:position] + remaining[position + 1 :]

    ordered = selected + deferred
    if len(ordered) != len(items):
        # Defensive: never lose a candidate to a bookkeeping defect.
        logger.warning(
            "[CrossVideoDiversity] reorder lost candidates (%d != %d); keeping input order",
            len(ordered),
            len(items),
        )
        return items, 0
    return ordered, len(deferred)


if __name__ == "__main__":  # pragma: no cover - manual smoke check
    pool = [
        {"video_id": "aaaaaaaaaaa", "score": 0.91, "text": "the mind is a warring state"},
        {"video_id": "aaaaaaaaaaa", "score": 0.90, "text": "the mind is a warring state today"},
        {"video_id": "aaaaaaaaaaa", "score": 0.89, "text": "the mind is a warring state now"},
        {"video_id": "bbbbbbbbbbb", "score": 0.70, "text": "observe the breath gently"},
    ]
    ordered, deferred = apply_cross_video_diversity(pool, max_per_video=2)
    assert [c["video_id"] for c in ordered] == [
        "aaaaaaaaaaa",
        "aaaaaaaaaaa",
        "bbbbbbbbbbb",
        "aaaaaaaaaaa",
    ], ordered
    assert deferred == 1
    assert len(ordered) == len(pool)
    print("cross_video_diversity self-check ok")
