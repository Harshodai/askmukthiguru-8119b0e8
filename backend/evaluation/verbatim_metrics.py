"""Speech-Aware Verbatim & Timestamp Precision Metrics — Invariant B2.

Evaluates quote fidelity against spoken audio transcripts and video citation timestamps.

Research Basis (2024-2025 TREC RAG / UMBRELA Standards):
- Exact substring is too brittle on speech (fails on minor ASR punctuation/casing drift).
- Bag-of-words F1 ignores word order (allows scrambled words).
- BERTScore is banned (assigns >0.92 to paraphrased text with 0 exact teacher words).
- Order-preserving Normalized Longest Common Subsequence (LCS) is the primary metric.
- Asymmetric timestamp window [-10.0s, +2.0s] rewards conversational lead-in and
  strictly penalizes starting after speech begins (truncation).
"""

from __future__ import annotations

import math
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Optional

CONTRACTIONS = {
    "don't": "do not",
    "can't": "cannot",
    "won't": "will not",
    "it's": "it is",
    "that's": "that is",
    "i'm": "i am",
    "you're": "you are",
    "we're": "we are",
    "they're": "they are",
    "isn't": "is not",
    "aren't": "are not",
    "wasn't": "was not",
    "weren't": "were not",
    "hasn't": "has not",
    "haven't": "have not",
    "doesn't": "does not",
    "didn't": "did not",
    "couldn't": "could not",
    "shouldn't": "should not",
    "wouldn't": "would not",
}


def normalize_speech(text: str) -> str:
    """Normalize speech transcript text for robust verbatim matching."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text).lower()
    for contraction, expansion in CONTRACTIONS.items():
        text = text.replace(contraction, expansion)
    # Strip non-alphanumeric characters except spaces
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def evaluate_verbatim_quote(
    candidate_quote: str,
    reference_transcript: str,
    lcs_threshold: float = 0.95,
) -> dict[str, Any]:
    """
    Evaluate whether a candidate quote is an authentic verbatim excerpt of the reference.

    Hierarchy:
    1. Exact normalized substring match -> 1.0
    2. Character and Token-level Longest Common Subsequence (LCS) ratio >= threshold
    """
    cand_norm = normalize_speech(candidate_quote)
    ref_norm = normalize_speech(reference_transcript)

    if not cand_norm:
        return {
            "is_verbatim": False,
            "method": "empty_quote",
            "score": 0.0,
            "char_lcs_ratio": 0.0,
            "token_lcs_ratio": 0.0,
        }

    # 1. Exact normalized substring match
    if cand_norm in ref_norm:
        return {
            "is_verbatim": True,
            "method": "exact_normalized_substring",
            "score": 1.0,
            "char_lcs_ratio": 1.0,
            "token_lcs_ratio": 1.0,
        }

    # 2. Character LCS Matcher
    char_matcher = SequenceMatcher(None, cand_norm, ref_norm)
    c_match = char_matcher.find_longest_match(0, len(cand_norm), 0, len(ref_norm))
    char_lcs_ratio = c_match.size / len(cand_norm) if cand_norm else 0.0

    # 3. Token-order Sequence Matcher -- true matched-token ratio, not the
    # longest CONTIGUOUS run (one wrong word mid-quote would otherwise split
    # the run in two and roughly halve the score).
    token_lcs_ratio = _aligned_token_ratio(cand_norm.split(), ref_norm.split())

    is_verbatim = (token_lcs_ratio >= lcs_threshold) or (char_lcs_ratio >= lcs_threshold)

    return {
        "is_verbatim": is_verbatim,
        "method": "lcs_sequence_match" if is_verbatim else "below_threshold",
        "score": max(char_lcs_ratio, token_lcs_ratio),
        "char_lcs_ratio": round(char_lcs_ratio, 4),
        "token_lcs_ratio": round(token_lcs_ratio, 4),
    }


def _aligned_token_ratio(cand: list[str], ref: list[str]) -> float:
    """Matched tokens over max(candidate length, aligned reference span).

    The reference is a whole transcript, so the quote is first anchored on its
    longest exact run and re-matched inside a small window around it. Dividing
    by the aligned span as well as the candidate penalises BOTH a substituted
    word and a dropped one (e.g. a missing "not"), which a candidate-only
    denominator scores as a perfect 1.0.
    """
    if not cand or not ref:
        return 0.0
    anchor = SequenceMatcher(None, cand, ref, autojunk=False).find_longest_match(
        0, len(cand), 0, len(ref)
    )
    if anchor.size == 0:
        return 0.0
    slack = len(cand) // 10 + 2
    lo = max(0, anchor.b - anchor.a - slack)
    window = ref[lo : anchor.b + (len(cand) - anchor.a) + slack]
    blocks = [
        b
        for b in SequenceMatcher(None, cand, window, autojunk=False).get_matching_blocks()
        if b.size
    ]
    matched = sum(b.size for b in blocks)
    ref_span = blocks[-1].b + blocks[-1].size - blocks[0].b
    return matched / max(len(cand), ref_span)


def parse_timestamp_seconds(val: Any) -> Optional[float]:
    """Parse float, integer, 'MM:SS', or '?t=124s' / '&t=124' into float seconds."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    m = re.search(r"[?&]t=(\d+)s?", s)
    if m:
        return float(m.group(1))
    if ":" in s:
        parts = s.split(":")
        try:
            if len(parts) == 2:
                return float(parts[0]) * 60 + float(parts[1])
            elif len(parts) == 3:
                return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        except ValueError:
            return None
    try:
        return float(s)
    except ValueError:
        return None


def evaluate_timestamp_precision(
    pred_start: float,
    pred_end: float,
    gt_start: float,
    gt_end: float,
    lead_tol_s: float = 10.0,
    lag_tol_s: float = 2.0,
) -> dict[str, Any]:
    """
    Evaluate temporal citation accuracy with asymmetric lead/lag tolerance.

    Invariants:
    - Starting early (negative onset_error) is acceptable up to lead_tol_s (conversational lead-in).
    - Starting late (positive onset_error) truncates speech and is penalized strictly.
    - Computes 1D Temporal IoU (tIoU) across intervals.
    """
    onset_error = pred_start - gt_start  # Negative = early, Positive = late
    is_valid_onset = -lead_tol_s <= onset_error <= lag_tol_s

    # 1D Temporal IoU
    inter = max(0.0, min(pred_end, gt_end) - max(pred_start, gt_start))
    union = max(pred_end, gt_end) - min(pred_start, gt_start)
    tiou = inter / union if union > 0 else 0.0

    # Continuous UX Score
    if -3.0 <= onset_error <= 1.0:
        ux_score = 1.0
    elif onset_error > 1.0:
        ux_score = math.exp(-(onset_error - 1.0) / 3.0)  # Sharp dropoff for late starts
    else:
        ux_score = math.exp(-(-onset_error - 3.0) / 8.0)  # Gentle dropoff for early starts

    return {
        "onset_error_s": round(onset_error, 2),
        "is_valid_onset": is_valid_onset,
        "tiou": round(tiou, 4),
        "hit_3s": abs(onset_error) <= 3.0,
        "hit_5s": abs(onset_error) <= 5.0,
        "ux_score": round(ux_score, 4),
    }
