#!/usr/bin/env python3
"""Compare two four-class AskMukthiGuru latency probe JSONL runs."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def load(path: str) -> dict[str, dict]:
    return {row["label"]: row for row in (json.loads(line) for line in Path(path).read_text().splitlines() if line.strip())}


def node_sum(row: dict) -> float:
    return sum(float(value) for value in (row.get("node_timings") or {}).values())


def quality(row: dict) -> str:
    verification = row.get("verification") or {}
    return "; ".join(
        [
            f"grounding={row.get('grounding_state')}",
            f"verification={verification.get('method')}",
            f"passed={verification.get('passed')}",
            f"citations_verified={verification.get('citations_verified')}",
            f"intent={row.get('intent')}",
            f"tier={row.get('query_tier')}",
            f"cache={row.get('cache_hit')}",
        ]
    )


def main(before_path: str, after_path: str) -> None:
    before, after = load(before_path), load(after_path)
    print("# Controlled latency experiment\n")
    print("Baseline: synchronized-main uncached four-class run. Treatment: `RAG_USE_HYDE=false`, `RAG_MAX_REWRITES=1`, `CACHE_MODE=memory`; same query strings, local Docker stack, n=1 per class. This is directional evidence, not p50/p95.\n")
    print("| Class | Baseline backend ms | Treatment backend ms | Delta ms | Delta % | Baseline node ms | Treatment node ms | Baseline quality | Treatment quality |")
    print("|---|---:|---:|---:|---:|---:|---:|---|---|")
    for label in before:
        b, a = before[label], after.get(label, {})
        if b.get("latency_ms") is None or a.get("latency_ms") is None:
            print(f"| {label} | unavailable | unavailable | — | — | — | — | {quality(b)} | {quality(a)} |")
            continue
        bms, ams = float(b["latency_ms"]), float(a["latency_ms"])
        delta = ams - bms
        pct = (delta / bms * 100) if bms else 0.0
        print(f"| {label} | {bms:.1f} | {ams:.1f} | {delta:+.1f} | {pct:+.1f}% | {node_sum(b):.1f} | {node_sum(a):.1f} | {quality(b)} | {quality(a)} |")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(f"usage: {sys.argv[0]} BEFORE.jsonl AFTER.jsonl")
    main(sys.argv[1], sys.argv[2])
