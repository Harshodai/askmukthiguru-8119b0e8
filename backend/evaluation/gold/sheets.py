"""Blank label-sheet builders.

HARD RULE: these builders never fill in a label, never generate question
text from a target passage, and the relevance sheet never carries a score,
model rank, or which retriever surfaced a candidate — a blind sheet must not
tip a human judge toward the system's own answer.
"""

from __future__ import annotations

import csv
import json
import random
from pathlib import Path

QUESTION_COLUMNS = ["question_id", "author", "question_text", "type", "intended_video_ids", "notes"]
RELEVANCE_COLUMNS = [
    "question_id", "question_text", "clip_id", "video_id", "start", "end", "text",
    "judge_a", "judge_b", "adjudicated", "equivalent_group", "clip_quality",
]
TRANSCRIPT_COLUMNS = [
    "video_id", "segment_start", "segment_end", "verbatim_text", "speaker_turns",
    "word_timestamps", "notes",
]

_TYPE_MIX = ("answerable", "answerable", "answerable", "near_miss", "unanswerable")  # 60/20/20


def build_question_sheet(video_ids: list[str], n_questions: int, max_per_video: int = 3) -> list[dict]:
    """One blank row per question, pre-assigned a target video (round-robin,
    capped at max_per_video) and a type from the 60/20/20 mix — never a
    question_text, which only the human author writes."""
    if n_questions > len(video_ids) * max_per_video:
        raise ValueError(f"{n_questions} questions needs > {len(video_ids)} videos at max_per_video={max_per_video}")
    rows = []
    slots = [vid for vid in video_ids for _ in range(max_per_video)]
    for i in range(n_questions):
        rows.append({
            "question_id": f"Q{i + 1:04d}",
            "author": "",
            "question_text": "",
            "type": _TYPE_MIX[i % len(_TYPE_MIX)],
            "intended_video_ids": slots[i],
            "notes": "",
        })
    return rows


def pool_candidates(
    questions: list[dict], results: dict, clip_meta: dict, modes: tuple[str, ...] = ("R0", "R1", "R2"), top_k: int = 5,
) -> dict[str, list[dict]]:
    """Per-question candidate clips pooled from several retrievers' top-k,
    deduped by clip_id. No score or rank position is kept — pooling only
    decides which clips a human sees, never how they're ordered for judging."""
    pooled: dict[str, list[dict]] = {}
    for q in questions:
        seen: dict[str, dict] = {}
        for mode in modes:
            rank = results["results"].get(mode, {}).get(q["id"], {}).get("rank", [])
            for clip_id in rank[:top_k]:
                if clip_id in clip_meta and clip_id not in seen:
                    m = clip_meta[clip_id]
                    seen[clip_id] = {"clip_id": clip_id, "video_id": m["video_id"], "start": m["start"], "end": m["end"], "text": m["verbatim_text"]}
        pooled[q["id"]] = list(seen.values())
    return pooled


def build_relevance_sheet(questions: list[dict], pooled: dict[str, list[dict]], seed: int = 42) -> list[dict]:
    """Blind relevance-judging sheet: candidate identity/text only, shuffled
    per question so pooling/retriever order never leaks through row order."""
    rng = random.Random(seed)
    rows = []
    for q in questions:
        candidates = list(pooled.get(q["id"], []))
        rng.shuffle(candidates)
        for c in candidates:
            rows.append({
                "question_id": q["id"], "question_text": q["question"],
                "clip_id": c["clip_id"], "video_id": c["video_id"], "start": c["start"], "end": c["end"], "text": c["text"],
                "judge_a": "", "judge_b": "", "adjudicated": "", "equivalent_group": "", "clip_quality": "",
            })
    return rows


def build_transcript_gold_sheet(video_durations: dict[str, float], segment_seconds: float = 600.0) -> list[dict]:
    """One blank row per 10-minute window per video. verbatim_text/
    speaker_turns/word_timestamps are filled by a human watching the video,
    never derived from the (possibly filler-stripped) ASR transcript."""
    rows = []
    for vid, duration in video_durations.items():
        start = 0.0
        while start < duration:
            end = min(start + segment_seconds, duration)
            rows.append({
                "video_id": vid, "segment_start": round(start, 1), "segment_end": round(end, 1),
                "verbatim_text": "", "speaker_turns": "", "word_timestamps": "", "notes": "",
            })
            start = end
    return rows


def write_sheet(rows: list[dict], columns: list[str], csv_path: str | Path, json_path: str | Path) -> None:
    csv_path, json_path = Path(csv_path), Path(json_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    json_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    qsheet = build_question_sheet([f"v{i}" for i in range(5)], n_questions=10)
    assert len(qsheet) == 10
    assert all(set(r) == set(QUESTION_COLUMNS) for r in qsheet)
    assert all(r["question_text"] == "" and r["author"] == "" for r in qsheet)
    types = [r["type"] for r in qsheet]
    assert types.count("answerable") / len(types) == 0.6

    questions = [{"id": "q1", "question": "why?"}]
    results = {"results": {"R0": {"q1": {"rank": ["c1", "c2"]}}, "R1": {"q1": {"rank": ["c2", "c3"]}}}}
    clip_meta = {cid: {"video_id": "v0", "start": 0.0, "end": 1.0, "verbatim_text": cid} for cid in ("c1", "c2", "c3")}
    pooled = pool_candidates(questions, results, clip_meta, modes=("R0", "R1"))
    assert len(pooled["q1"]) == 3
    rel = build_relevance_sheet(questions, pooled)
    assert len(rel) == 3
    assert all(set(r) == set(RELEVANCE_COLUMNS) for r in rel)
    assert all(r["judge_a"] == "" and r["adjudicated"] == "" for r in rel)
    assert not any(k in RELEVANCE_COLUMNS for k in ("score", "rank"))

    tsheet = build_transcript_gold_sheet({"v0": 1250.0})
    assert len(tsheet) == 3  # 0-600, 600-1200, 1200-1250
    assert tsheet[-1]["segment_end"] == 1250.0
    print("ok", len(qsheet), len(rel), len(tsheet))
