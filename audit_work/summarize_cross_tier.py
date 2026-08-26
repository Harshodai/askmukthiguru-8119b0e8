#!/usr/bin/env python3
"""Summarize real cross-tier probe JSONL into bounded engineering evidence."""
from __future__ import annotations
import json
import statistics
import sys
from collections import defaultdict

path = sys.argv[1] if len(sys.argv) > 1 else "audit_work/latency_probe_all_routes.jsonl"
rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
completed = [r for r in rows if r.get("status") == "completed" and isinstance(r.get("latency_ms"), (int, float))]
print("# Cross-tier latency summary")
print(f"records={len(rows)} completed={len(completed)}")
print("\n## Per request")
print("label\tlang\ttier\troute\tbackend_ms\twall_ms\tresidual_ms\tstage_sum_ms\tgrounding\tverification")
for r in completed:
    timings = r.get("node_timings") or {}
    stage_sum = sum(v for v in timings.values() if isinstance(v, (int, float)))
    backend = float(r["latency_ms"])
    print("\t".join(str(x) for x in [
        r.get("label"), r.get("language"), r.get("query_tier"), r.get("route_decision"),
        round(backend, 1), round(float(r.get("wall_ms", 0)), 1), round(backend - stage_sum, 1), round(stage_sum, 1),
        r.get("grounding_state"), (r.get("verification") or {}).get("method"),
    ]))

by_tier = defaultdict(list)
by_route = defaultdict(list)
by_lang = defaultdict(list)
for r in completed:
    by_tier[r.get("query_tier")].append(r)
    by_route[r.get("route_decision")].append(r)
    by_lang[r.get("language")].append(r)

def block(title, groups):
    print(f"\n## {title}")
    print("group\tn\tmean_ms\tmin_ms\tmax_ms\tmedian_ms\tmean_residual_ms\tgrounded_or_safe")
    for key, group in sorted(groups.items(), key=lambda item: str(item[0])):
        values = [float(r["latency_ms"]) for r in group]
        residuals = []
        safe = 0
        for r in group:
            stage_sum = sum(v for v in (r.get("node_timings") or {}).values() if isinstance(v, (int, float)))
            residuals.append(float(r["latency_ms"]) - stage_sum)
            if r.get("grounding_state") in {"grounded", "safety_redirect"}:
                safe += 1
        print("\t".join(str(x) for x in [key, len(group), round(statistics.mean(values), 1), round(min(values), 1), round(max(values), 1), round(statistics.median(values), 1), round(statistics.mean(residuals), 1), f"{safe}/{len(group)}"]))

block("By tier", by_tier)
block("By route decision", by_route)
block("By language", by_lang)

stage_totals = defaultdict(list)
for r in completed:
    for stage, value in (r.get("node_timings") or {}).items():
        if isinstance(value, (int, float)):
            stage_totals[stage].append(float(value))
print("\n## Stage contribution")
print("stage\tn\tmean_ms\tmax_ms")
for stage, values in sorted(stage_totals.items(), key=lambda item: -max(item[1])):
    print(f"{stage}\t{len(values)}\t{statistics.mean(values):.1f}\t{max(values):.1f}")
