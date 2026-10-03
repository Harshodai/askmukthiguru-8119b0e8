"""
Mukthi Guru — Silver Relevance Label Generator (B1 Protocol)

Generates non-authoritative silver labels for adjudication queue prioritization.
STRICT INVARIANTS (Section 6 of antigravity_handoff_prompt.md):
  - Silver labels are stored separately in gold_pilot/silver_*.json.
  - Silver labels are NEVER written into gold CSV sheets (judge_a, judge_b, adjudicated).
  - Silver labels MUST NOT be shown to a human annotator before they have labelled (blind protocol).
  - All output is explicitly stamped 'status: silver/unverified' and never reported as ground truth.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from evaluation.verbatim_metrics import normalize_speech

logger = logging.getLogger(__name__)


def generate_silver_label_for_row(
    question_text: str,
    clip_text: str,
    threshold: float = 0.35,
) -> dict[str, Any]:
    """
    Generate a heuristic silver label for a single (question, candidate_clip) pair.
    Uses token overlap and key term intersection.
    """
    q_norm = normalize_speech(question_text).lower()
    c_norm = normalize_speech(clip_text).lower()

    q_words = set(q_norm.split())
    # Exclude common stop words
    stop_words = {
        "what",
        "is",
        "the",
        "how",
        "to",
        "in",
        "of",
        "and",
        "a",
        "an",
        "do",
        "does",
        "can",
        "why",
    }
    content_words = q_words - stop_words
    if not content_words:
        content_words = q_words

    # Word-boundary match, not substring — `in` matched "love" inside "glove".
    matched_words = [w for w in content_words if re.search(rf"\b{re.escape(w)}\b", c_norm)]
    overlap_score = len(matched_words) / len(content_words) if content_words else 0.0

    proposed = "yes" if overlap_score >= threshold else "no"

    return {
        "silver_label": proposed,
        "confidence": round(overlap_score, 4),
        "status": "silver/unverified",
        "evidence": {
            "matched_keywords": matched_words,
            "keyword_overlap_ratio": round(overlap_score, 4),
            "clip_length_chars": len(clip_text),
        },
    }


def generate_silver_file(
    relevance_rows: list[dict[str, Any]],
    output_json_path: Path,
    threshold: float = 0.35,
) -> list[dict[str, Any]]:
    """
    Generate a silver labels JSON file from candidate relevance rows.
    """
    silver_results: list[dict[str, Any]] = []

    for r in relevance_rows:
        qid = r.get("question_id", "")
        q_text = r.get("question_text", "")
        cid = r.get("clip_id", "")
        vid = r.get("video_id", "")
        text = r.get("text", "")

        silver_info = generate_silver_label_for_row(
            question_text=q_text,
            clip_text=text,
            threshold=threshold,
        )

        silver_results.append(
            {
                "question_id": qid,
                "question_text": q_text,
                "clip_id": cid,
                "video_id": vid,
                "start": r.get("start"),
                "end": r.get("end"),
                "silver_label": silver_info["silver_label"],
                "confidence": silver_info["confidence"],
                "status": silver_info["status"],
                "evidence": silver_info["evidence"],
            }
        )

    # Save to JSON
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_json_path, mode="w", encoding="utf-8") as f:
        json.dump({"silver_rows": silver_results, "count": len(silver_results)}, f, indent=2)

    logger.info(f"[Silver] Wrote {len(silver_results)} silver labels to {output_json_path}")
    return silver_results
