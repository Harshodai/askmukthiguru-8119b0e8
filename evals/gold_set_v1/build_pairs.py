"""Build the annotator sheets for gold_set_v1 from questions.jsonl. Read-only against Qdrant.

Run host-side from backend/ (so backend/.env resolves; never in Docker):
    cd backend && .venv/bin/python3 ../evals/gold_set_v1/build_pairs.py

Retrieval reuses .work/autoresearch_fp/build_cache.py (which mirrors
FirstPersonPipeline.execute retrieval): encode_single_full -> FirstPersonStore.search_hybrid
(limit=80, dedup_limit=40, teacher filter) -> integrity gate (check_availability=False) ->
content-quality gate (production flag is ON, so clips failing it are never served and are skipped).
build_cache.main() is NOT called: it would overwrite the autoresearch candidates.json.

Writes (all label columns blank: humans fill them, never this script):
  pairs.csv          every (question, clip) row + `assignment` (A, B or A+B overlap)
  annotator_A.csv    rows for annotator A (assignment A or A+B)
  annotator_B.csv    rows for annotator B (assignment B or A+B)
  pairs_scores.csv   system scores keyed by pair_id. NEVER give this to annotators (bias).
"""

from __future__ import annotations

import csv
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / ".work" / "autoresearch_fp"))

import build_cache as bc  # noqa: E402  (sets backend sys.path; imports are read-only)

SEED = 20261011
TOP_K_ON_TOPIC = 3
OVERLAP_FRACTION = 0.20
PAD_MS = 250  # CITATION_PLAYBACK_PAD_S (invariant 6)

LABEL_COLS = [
    "relevance_0_3",
    "complete_yes_no",
    "speaker_is_teacher_yes_no_unsure",
    "risk_yes_no",
    "notes",
]
SHEET_COLS = [
    "pair_id",
    "question_id",
    "question_type",
    "question",
    "clip_text",
    "speaker_label",
    "video_url_with_timestamp",
    "duration_s",
] + LABEL_COLS
SCORE_COLS = [
    "pair_id",
    "question_id",
    "question_type",
    "cand_rank",
    "rrf_rank",
    "rrf_score",
    "dense_cosine",
    "rail_blocked",
    "rail_reason",
    "standalone_problem",
    "point_id",
    "shown_by",
]


def load_questions() -> list[dict]:
    rows = [
        json.loads(line)
        for line in (HERE / "questions.jsonl").read_text().splitlines()
        if line.strip()
    ]
    return [r for r in rows if not r.get("_header")]


def retrieve(ctx: dict, text: str, k: int) -> tuple[list[dict], dict]:
    """Top-k clips that pass integrity + content-quality gates, in production RRF order."""
    teacher = bc.requested_teacher(text)
    dist = ctx["serene"].assess_distress(text)
    crisis = bool(dist and dist.level.value >= bc.DistressLevel.SEVERE.value)
    topic = bc.match_blocked_topic(text)
    enc = ctx["emb"].encode_single_full(text)
    dense = [float(x) for x in enc["dense"]]
    sp = enc.get("sparse") or {}
    sparse = (
        {"indices": [int(i) for i in sp], "values": [float(v) for v in sp.values()]} if sp else None
    )
    practice = any(
        w in text.lower()
        for w in ("practice", "meditat", "technique", "exercise", "sadhana", "kriya")
    )
    raw = ctx["store"].search_hybrid(
        dense,
        sparse,
        teacher_id=teacher,
        limit=80,
        dedup_limit=40,
        allow_same_video_distinct_spans=practice,
    )
    out = []
    for rrf_rank, clip in enumerate(raw):
        if len(out) >= k:
            break
        if not bc._passes_integrity_gate(clip, check_availability=False):
            continue
        if not bc._passes_content_quality_gate(clip):
            continue
        out.append(
            {
                **clip,
                "_rrf_rank": rrf_rank,
                "_dense_cosine": round(bc._cosine_similarity(dense, clip.get("passage_dense")), 6),
                "_standalone": bc._standalone_problem(clip.get("verbatim_text") or "") or "",
            }
        )
    rail = {
        "rail_blocked": bool(crisis or topic),
        "rail_reason": "crisis" if crisis else (topic[0] if topic else ""),
    }
    return out, rail


def make_rows(q: dict, clips: list[dict], rail: dict) -> list[tuple[dict, dict]]:
    shown_by = (
        "retrieval rank (integrity+CQ gates)"
        if q["type"] == "on_topic"
        else "retrieval top-1 BEFORE serve-time LLM/rail gates; production may abstain"
    )
    rows = []
    for rank, c in enumerate(clips):
        pid = f"{q['id']}_r{rank}"
        start_s = max(0, int(c["start_ms"]) - PAD_MS) // 1000
        sheet = {
            "pair_id": pid,
            "question_id": q["id"],
            "question_type": q["type"],
            "question": q["text"],
            "clip_text": c.get("verbatim_text") or "",
            "speaker_label": c.get("speaker") or "",
            "video_url_with_timestamp": f"https://www.youtube.com/watch?v={c['video_id']}&t={start_s}s",
            "duration_s": round((int(c["end_ms"]) - int(c["start_ms"])) / 1000, 1),
            **{col: "" for col in LABEL_COLS},
        }
        score = {
            "pair_id": pid,
            "question_id": q["id"],
            "question_type": q["type"],
            "cand_rank": rank,
            "rrf_rank": c["_rrf_rank"],
            "rrf_score": float(c.get("score", 0.0)),
            "dense_cosine": c["_dense_cosine"],
            "standalone_problem": c["_standalone"],
            "point_id": str(c["point_id"]),
            "shown_by": shown_by,
            **rail,
        }
        rows.append((sheet, score))
    return rows


def assign(sheets: list[dict], rng: random.Random) -> None:
    """Shuffle in place, mark 20% as A+B overlap, split the rest alternately A/B."""
    rng.shuffle(sheets)
    n_overlap = round(len(sheets) * OVERLAP_FRACTION)
    overlap = set(rng.sample(range(len(sheets)), n_overlap))
    turn = 0
    for i, row in enumerate(sheets):
        if i in overlap:
            row["assignment"] = "A+B"
        else:
            row["assignment"] = "AB"[turn % 2]
            turn += 1


def write_csv(path: Path, rows: list[dict], cols: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    client = bc.QdrantClient(url=bc.QDRANT_URL)
    ctx = {
        "store": bc.FirstPersonStore(collection=bc.COLLECTION, client=client),
        "emb": bc.EmbeddingService(),
        "serene": bc.SereneMindEngine(),
    }
    sheets, scores, empty = [], [], []
    for q in load_questions():
        k = TOP_K_ON_TOPIC if q["type"] == "on_topic" else 1
        clips, rail = retrieve(ctx, q["text"], k)
        if len(clips) < k:
            empty.append((q["id"], len(clips)))
        for sheet, score in make_rows(q, clips, rail):
            sheets.append(sheet)
            scores.append(score)
        print(
            f"{q['id']:7} clips={len(clips)} rail={rail['rail_reason'] or '-'} :: {q['text'][:60]}"
        )
    assign(sheets, random.Random(SEED))
    write_csv(HERE / "pairs.csv", sheets, SHEET_COLS + ["assignment"])
    write_csv(HERE / "annotator_A.csv", [r for r in sheets if "A" in r["assignment"]], SHEET_COLS)
    write_csv(HERE / "annotator_B.csv", [r for r in sheets if "B" in r["assignment"]], SHEET_COLS)
    write_csv(HERE / "pairs_scores.csv", scores, SCORE_COLS)
    print(
        f"pairs={len(sheets)} overlap={sum(r['assignment'] == 'A+B' for r in sheets)} short={empty}"
    )


if __name__ == "__main__":
    main()
