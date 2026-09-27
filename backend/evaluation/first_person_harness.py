"""Pinned first-person evaluation harness.

One question file (SHA-256 pinned below), one scorer, one fixed denominator — so
"v2 vs v5" or "rerank on vs off" is decided by the same measurement every time.
Three earlier evaluations of the same 116 questions disagreed because each used a
different scratch scorer and a different denominator (83 vs 89).

It runs the real serving pipeline (FirstPersonPipeline), so top-1 is exactly the
clip a seeker would be served. Read-only against Qdrant; no Redis cache.

Honest limits (state them with every number):
- The questions are AI-authored from the indexed transcripts, not real seekers,
  so this measures ranking within the indexed set, not coverage.
- 89 answerable questions from 8 videos: the video-clustered 95% CI is wide.
- ``host_like`` is a text heuristic, not a human audit of who is speaking.

Usage (inside the backend container, which has Qdrant + the embedding model):
    python -m evaluation.first_person_harness run --collection first_person_v5 --out /tmp/v5.json
    python -m evaluation.first_person_harness run --collection first_person_v5 --rerank --out /tmp/v5r.json
    python -m evaluation.first_person_harness compare /tmp/v2.json /tmp/v5.json
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

from evaluation.gold.metrics import bootstrap_ci_by_video, passage_hits_ranges

QUESTIONS_PATH = Path(__file__).parent / "datasets" / "first_person_bakeoff_2026-09-25.json"
QUESTIONS_SHA256 = "acb635fc899dcd850ff0b7c9d2fb4bfddd6826e78baad71f32eecc2af16848c8"

_HOST_STEMS = re.compile(
    r"^(so|now|and|what|why|how|when|is|are|do|does|can|could|would|will|namaste)\b", re.IGNORECASE
)


class HarnessError(RuntimeError):
    pass


def load_questions(path: Path = QUESTIONS_PATH, expected_sha256: str = QUESTIONS_SHA256) -> list[dict]:
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected_sha256:
        raise HarnessError(f"{path} sha256 {actual} != pinned {expected_sha256}; refusing to score a changed set")
    return json.loads(raw)["questions"]


def looks_host_like(text: str) -> bool:
    """Bake-off heuristic (ported from scoring_lib.py): a question, or a short
    opener in a host's register. A proxy for host speech, not a speaker check."""
    t = (text or "").strip()
    if not t:
        return False
    if t.endswith("?"):
        return True
    first = re.split(r"(?<=[.!?])\s", t, maxsplit=1)[0]
    return len(first.split()) <= 14 and bool(_HOST_STEMS.match(first))


def score_row(question: dict, citation: dict | None) -> dict:
    """One row per question. A missing top-1 clip on an answerable question is a miss."""
    row = {
        "id": question["id"],
        "video_id": question["video_id"],
        "answerable": bool(question["answerable"]),
        "near_miss": bool(question.get("near_miss")),
        "top1": None,
        "hit": False,
        "host_like": False,
    }
    if citation:
        clip = {
            "video_id": citation["video_id"],
            "start": citation["start_ms"] / 1000.0,
            "end": citation["end_ms"] / 1000.0,
        }
        row["top1"] = {**clip, "speaker": citation.get("speaker"), "point_id": citation.get("point_id")}
        row["host_like"] = looks_host_like(citation.get("verbatim_text", ""))
        if row["answerable"]:
            row["hit"] = passage_hits_ranges(clip, question["answer_ranges"])
    return row


def summarize(rows: list[dict], latencies_ms: list[float]) -> dict:
    answerable = [dict(r, hit=int(r["hit"])) for r in rows if r["answerable"]]
    served = [dict(r, host_like=int(r["host_like"])) for r in rows if r["top1"]]
    lat = sorted(latencies_ms)
    return {
        "n_questions": len(rows),
        "n_answerable": len(answerable),  # fixed denominator: misses and errors stay in
        "top1_hit": bootstrap_ci_by_video(answerable, "hit"),
        "host_like_top1": bootstrap_ci_by_video(served, "host_like") if served else None,
        "n_errors": sum(1 for r in rows if r.get("status") == "error"),
        "status_counts": _count(r.get("status") for r in rows),
        "latency_ms": {
            "p50": round(statistics.median(lat), 1) if lat else None,
            "p95": round(lat[min(len(lat) - 1, math.ceil(0.95 * len(lat)) - 1)], 1) if lat else None,
        },
    }


def _count(values) -> dict:
    out: dict[str, int] = {}
    for v in values:
        out[str(v)] = out.get(str(v), 0) + 1
    return out


def mcnemar_exact(a_rows: list[dict], b_rows: list[dict]) -> dict:
    """Paired comparison on answerable questions: exact two-sided binomial test on
    the discordant pairs (B right & A wrong vs A right & B wrong)."""
    a = {r["id"]: r for r in a_rows if r["answerable"]}
    b = {r["id"]: r for r in b_rows if r["answerable"]}
    if set(a) != set(b):
        raise HarnessError("runs were scored on different question sets")
    b_wins = sorted(q for q in a if b[q]["hit"] and not a[q]["hit"])
    a_wins = sorted(q for q in a if a[q]["hit"] and not b[q]["hit"])
    n, k = len(a_wins) + len(b_wins), min(len(a_wins), len(b_wins))
    p = min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2**n) if n else 1.0
    return {"a_wins": a_wins, "b_wins": b_wins, "n_discordant": n, "p_value_two_sided": round(p, 4)}


def _git_sha() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return None  # inside the container there is no .git; the run records None, not a guess


async def run(collection: str, rerank: bool) -> dict:
    from app.api.first_person import _make_rerank_fn
    from app.config import settings
    from services.embedding_service import get_embedding_service
    from services.first_person_pipeline import FirstPersonPipeline
    from services.first_person_store import FirstPersonStore

    questions = load_questions()
    embedding = get_embedding_service()
    store = FirstPersonStore(collection=collection)
    rerank_fn = _make_rerank_fn(embedding, asyncio.get_running_loop(), timeout_s=30.0) if rerank else None
    # No Redis: every question is a real retrieval. No calibration profile override:
    # the pipeline loads whatever FIRST_PERSON_CALIBRATION_PATH points at, as serving does.
    pipeline = FirstPersonPipeline(store=store, redis_client=None, rerank_fn=rerank_fn)

    rows, latencies = [], []
    for q in questions:
        status, citation = "error", None
        try:
            enc = await embedding.encode_single_full_async(q["question"])
            sparse = enc.get("sparse") or {}
            res = await asyncio.to_thread(
                pipeline.execute,
                query=q["question"],
                query_dense_vector=enc["dense"],
                query_sparse_vector={"indices": list(sparse), "values": list(sparse.values())} if sparse else None,
                max_clips=3,
            )
            status = res.status
            latencies.append(res.latency_ms)
            citation = res.citations[0] if res.citations else None
        except Exception as e:  # counted as a miss and reported, never dropped
            print(f"[harness] {q['id']} failed: {e}", file=sys.stderr)
        row = score_row(q, citation)
        row["status"] = status
        rows.append(row)

    return {
        "collection": collection,
        "rerank": rerank,
        "questions_sha256": QUESTIONS_SHA256,
        "git_sha": _git_sha(),
        "serve_unregistered": bool(getattr(settings, "first_person_serve_unregistered", False)),
        "calibration_path": getattr(settings, "first_person_calibration_path", ""),
        "ran_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "summary": summarize(rows, latencies),
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--collection", required=True)
    r.add_argument("--rerank", action="store_true")
    r.add_argument("--out", type=Path, required=True)
    c = sub.add_parser("compare")
    c.add_argument("a", type=Path)
    c.add_argument("b", type=Path)
    args = ap.parse_args(argv)

    if args.cmd == "run":
        result = asyncio.run(run(args.collection, args.rerank))
        args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        print(json.dumps({k: result[k] for k in ("collection", "rerank", "summary")}, indent=2))
        return 0

    a, b = (json.loads(p.read_text()) for p in (args.a, args.b))
    for run_ in (a, b):
        if run_["questions_sha256"] != QUESTIONS_SHA256:
            raise HarnessError(f"{run_['collection']} was scored on a different question file")
    out = {
        "a": {k: a[k] for k in ("collection", "rerank")} | {"top1_hit": a["summary"]["top1_hit"]},
        "b": {k: b[k] for k in ("collection", "rerank")} | {"top1_hit": b["summary"]["top1_hit"]},
        "paired": mcnemar_exact(a["rows"], b["rows"]),
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
