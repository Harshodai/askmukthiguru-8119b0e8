#!/usr/bin/env python3
"""Summarize AskMukthiGuru latency probe records into an evidence ledger."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main(path: str) -> None:
    records = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    print("label\twall_ms\tbackend_ms\tnode_sum_ms\twrapper_gap_ms\twall_minus_backend_ms\tquery_tier\tgrounding\tverification\tcache")
    for record in records:
        nodes = record.get("node_timings") or {}
        node_sum = sum(float(value) for value in nodes.values())
        backend = record.get("latency_ms")
        wall = float(record.get("wall_ms", 0))
        wrapper_gap = (float(backend) - node_sum) if backend is not None else None
        wall_gap = (wall - float(backend)) if backend is not None else None
        verification = (record.get("verification") or {}).get("method")
        print(
            "\t".join(
                [
                    str(record.get("label", "")),
                    f"{wall:.1f}",
                    f"{float(backend):.1f}" if backend is not None else "",
                    f"{node_sum:.1f}",
                    f"{wrapper_gap:.1f}" if wrapper_gap is not None else "",
                    f"{wall_gap:.1f}" if wall_gap is not None else "",
                    str(record.get("query_tier", "")),
                    str(record.get("grounding_state", "")),
                    str(verification or ""),
                    str(bool(record.get("cache_hit"))),
                ]
            )
        )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {sys.argv[0]} JSONL")
    main(sys.argv[1])
