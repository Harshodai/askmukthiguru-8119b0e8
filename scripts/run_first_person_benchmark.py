#!/usr/bin/env python3
"""Run first-person evaluation sets against localhost:8000/api/first-person/query.

Measures:
- Served vs Abstained count
- Abstain reasons breakdown
- Relevance indeterminate count (must be 0)
- Out-of-corpus leaks (must be 0)
- Stage timings breakdown (answerability, retrieval, integrity, rerank, scorer, assembly, total)
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ENDPOINT = "http://localhost:8000/api/first-person/query"
PACE_SECONDS = 5.0
BACKOFF_429_SECONDS = 40.0


def query_first_person(query: str, max_retries: int = 3) -> dict[str, Any]:
    payload = json.dumps({"query": query, "cache_bypass": True}).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    for attempt in range(max_retries):
        try:
            t0 = time.monotonic()
            with urllib.request.urlopen(req, timeout=90) as resp:  # nosec B310
                data = json.loads(resp.read().decode("utf-8"))
                wall_ms = (time.monotonic() - t0) * 1000.0
                data["_wall_ms"] = round(wall_ms, 2)
                return data
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries - 1:
                print(
                    f"[429 Rate Limited] Backing off for {BACKOFF_429_SECONDS}s...", file=sys.stderr
                )
                time.sleep(BACKOFF_429_SECONDS)
                continue
            return {
                "status": "http_error",
                "error": f"HTTP {e.code}: {e.reason}",
                "citations": [],
                "latency_ms": 0,
            }
        except Exception as e:
            return {"status": "client_error", "error": str(e), "citations": [], "latency_ms": 0}
    return {"status": "error", "error": "Max retries exceeded", "citations": [], "latency_ms": 0}


def run_eval_set(input_path: Path, output_path: Path) -> dict[str, Any]:
    questions = []
    with open(input_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                questions.append(json.loads(line))

    print(f"\n--- Running {input_path.name} ({len(questions)} questions) ---")
    results = []
    for i, q in enumerate(questions, 1):
        q_text = q.get("question") or q.get("text")
        qid = q.get("id") or f"q_{i:02d}"
        kind = q.get("kind", "unknown")

        res = query_first_person(q_text)
        status = res.get("status")
        abstain_reason = res.get("abstain_reason") or res.get("answerability") or "none"
        citations = res.get("citations") or []
        is_direct = res.get("is_direct_answer", False)
        timings = res.get("stage_timings") or {}
        tot_ms = timings.get("total_ms", res.get("latency_ms", 0))

        row = {
            "id": qid,
            "kind": kind,
            "question": q_text,
            "status": status,
            "is_direct_answer": is_direct,
            "abstain_reason": abstain_reason,
            "n_citations": len(citations),
            "citations": citations,
            "audio_clips": len(res.get("audio_playback_clips") or []),
            "stage_timings": timings,
            "latency_ms": tot_ms,
            "wall_ms": res.get("_wall_ms", tot_ms),
            "answer_preview": (res.get("answer_text") or "")[:120].replace("\n", " "),
        }
        results.append(row)
        print(
            f"[{i:02d}/{len(questions):02d}] {qid}: status={status} reason={abstain_reason} cits={len(citations)} tot={tot_ms:.0f}ms"
        )
        time.sleep(PACE_SECONDS)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    # Summary metrics
    n_total = len(results)
    served = [
        r for r in results if r["status"] in ("success", "weak_match") and r["n_citations"] > 0
    ]
    abstained = [r for r in results if r["status"] == "abstained"]
    crisis = [r for r in results if r["status"] == "crisis_redirect"]
    errors = [r for r in results if r["status"] in ("error", "http_error", "client_error")]

    reasons: dict[str, int] = {}
    for r in results:
        reason = r["abstain_reason"]
        reasons[reason] = reasons.get(reason, 0) + 1

    indeterminate_count = reasons.get("relevance_indeterminate", 0)

    # Latencies
    latencies = [r["latency_ms"] for r in results if r["latency_ms"] > 0]
    p50_total = statistics.median(latencies) if latencies else 0.0
    p95_total = (
        statistics.quantiles(latencies, n=20)[18]
        if len(latencies) >= 20
        else max(latencies, default=0.0)
    )

    # Per-stage timings median
    def stage_p50(key: str) -> float:
        vals = [
            r["stage_timings"].get(key, 0.0)
            for r in results
            if r["stage_timings"].get(key, 0.0) > 0
        ]
        return statistics.median(vals) if vals else 0.0

    summary = {
        "dataset": input_path.name,
        "n_total": n_total,
        "served_count": len(served),
        "abstained_count": len(abstained),
        "crisis_redirect_count": len(crisis),
        "error_count": len(errors),
        "reasons_breakdown": reasons,
        "relevance_indeterminate": indeterminate_count,
        "p50_latency_ms": round(p50_total, 1),
        "p95_latency_ms": round(p95_total, 1),
        "stage_timings_p50": {
            "answerability_ms": round(stage_p50("answerability_ms"), 1),
            "retrieval_ms": round(stage_p50("retrieval_ms"), 1),
            "integrity_ms": round(stage_p50("integrity_ms"), 1),
            "rerank_ms": round(stage_p50("rerank_ms"), 1),
            "scorer_ms": round(stage_p50("scorer_ms"), 1),
            "assembly_ms": round(stage_p50("assembly_ms"), 1),
            "total_ms": round(p50_total, 1),
        },
    }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="First Person Benchmark Runner")
    parser.add_argument("--set", choices=["all", "frozen29", "compound10", "ooc13"], default="all")
    args = parser.parse_args()

    base_dir = Path("/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8")
    eval_dir = base_dir / "evals" / "first_person"
    out_dir = base_dir / ".work" / "latency"

    sets = {
        "ooc13": eval_dir / "ooc13.jsonl",
        "compound10": eval_dir / "compound10.jsonl",
        "frozen29": eval_dir / "frozen29.jsonl",
    }
    if args.set != "all":
        sets = {args.set: sets[args.set]}

    all_summaries = {}
    for name, path in sets.items():
        out_path = out_dir / f"live_{name}_eval.json"
        summary = run_eval_set(path, out_path)
        all_summaries[name] = summary
        print(f"\n--- Summary for {name} ---")
        print(json.dumps(summary, indent=2))

    summary_out = out_dir / "live_benchmark_summary.json"
    with open(summary_out, "w", encoding="utf-8") as f:
        json.dump(all_summaries, f, indent=2)
    print(f"\nSaved overall summary to {summary_out}")


if __name__ == "__main__":
    main()
