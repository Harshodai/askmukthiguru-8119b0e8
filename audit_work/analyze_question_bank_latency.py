"""Merge and analyze question-bank latency waves.

Only bounded benchmark rows are read. No question or answer text is emitted.
The analyzer prefers a retry row when the original row was excluded, preserving
valid cache-free samples while exposing all exclusions.
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def load_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    included = [row for row in rows if row.get("included") is True and isinstance(row.get("latency_ms"), (int, float))]
    quality_valid = [row for row in included if row.get("quality", {}).get("quality_valid") is True]
    backend = [float(row["latency_ms"]) for row in included]
    wall = [float(row["wall_ms"]) for row in included if isinstance(row.get("wall_ms"), (int, float))]
    exclusions = Counter(str(row.get("excluded_reason") or row.get("error") or "unknown") for row in rows if row.get("included") is not True)
    http_status = Counter(str(row.get("http_status")) for row in rows if row.get("http_status") is not None)
    query_tiers = Counter(str(row.get("query_tier") or "unknown") for row in rows)
    intents = Counter(str(row.get("intent") or "unknown") for row in included)
    ready = len(included) >= 20
    result: dict[str, Any] = {
        "n_total": len(rows),
        "n_included_cache_free": len(included),
        "n_quality_valid": len(quality_valid),
        "quality_rate_on_included": round(len(quality_valid) / len(included), 4) if included else None,
        "n_excluded": len(rows) - len(included),
        "exclusion_reasons": dict(exclusions),
        "http_statuses": dict(http_status),
        "observed_query_tiers": dict(query_tiers),
        "observed_intents": dict(intents),
        "backend_mean_ms": round(statistics.mean(backend), 2) if backend else None,
        "wall_mean_ms": round(statistics.mean(wall), 2) if wall else None,
        "backend_p50_ms": round(percentile(backend, 0.50), 2) if ready else None,
        "backend_p95_ms": round(percentile(backend, 0.95), 2) if ready else None,
        "wall_p50_ms": round(percentile(wall, 0.50), 2) if len(wall) >= 20 else None,
        "wall_p95_ms": round(percentile(wall, 0.95), 2) if len(wall) >= 20 else None,
        "percentiles_status": "reported" if ready else "suppressed_need_20_included",
    }
    return result


def merge_rows(full_rows: list[dict[str, Any]], retry_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    by_case: dict[str, dict[str, Any]] = {row["case_id"]: row for row in full_rows if row.get("case_id")}
    replaced: list[str] = []
    for row in retry_rows:
        case_id = row.get("case_id")
        if not case_id:
            continue
        previous = by_case.get(case_id)
        if previous is None or previous.get("included") is not True:
            by_case[case_id] = row
            replaced.append(case_id)
    return list(by_case.values()), sorted(replaced)


def markdown_report(merged: list[dict[str, Any]], full_rows: list[dict[str, Any]], retry_rows: list[dict[str, Any]], manifest: dict[str, Any], replaced: list[str]) -> str:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_tier: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_language: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in merged:
        grouped[str(row.get("benchmark_stratum") or "unknown")].append(row)
        by_category[str(row.get("source_category") or "unknown")].append(row)
        by_tier[str(row.get("query_tier") or "unknown")].append(row)
        by_language[str(row.get("language") or "unknown")].append(row)

    lines = [
        "# AskMukthiGuru Question-Bank Cache-Free Benchmark v1",
        "",
        "## Scope and validity",
        "",
        f"This report analyzes the complete normalized question bank ({manifest['case_count']} cases across {len(manifest['category_counts'])} source categories) using the source hash `{manifest['source_sha256']}`. The full wave produced {len(full_rows)} rows; its first transport-failure transition was retained as invalid evidence. A retry wave covered the previously failed categories with {len(retry_rows)} rows, and the merged report prefers retry rows only where the original row was excluded.",
        "",
        "Only rows with `included=true`, `cache_hit=false`, a completed job, and a non-cache route are eligible for latency statistics. HTTP failures, timeouts, cache-signal ambiguity, and incomplete jobs remain visible in exclusion tables but are not converted into latency values. Percentiles are reported only for groups with at least 20 included cache-free samples. These are local exploratory measurements, not production performance claims.",
        "",
        "## Overall coverage",
        "",
        "| Measure | Result |",
        "|---|---:|",
        f"| Manifest cases | {manifest['case_count']} |",
        f"| Full-wave rows | {len(full_rows)} |",
        f"| Retry-wave rows | {len(retry_rows)} |",
        f"| Merged unique cases | {len(merged)} |",
        f"| Cases replaced by valid retry rows | {len(replaced)} |",
        f"| Merged included cache-free rows | {sum(row.get('included') is True for row in merged)} |",
        f"| Merged quality-valid rows | {sum(row.get('quality', {}).get('quality_valid') is True for row in merged)} |",
        "",
        "## Observed query-tier latency",
        "",
        "The application’s public `query_tier` is reported as observed telemetry. It is not inferred from a fixture name, and the bank currently does not provide a complete expected-tier label for every case. `unknown` commonly represents deterministic safety paths that do not select a graph tier.",
        "",
        "| Observed tier | Included | Quality-valid | Backend mean ms | Backend p50 ms | Backend p95 ms | Wall mean ms | Wall p50 ms | Wall p95 ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for key in sorted(by_tier):
        item = aggregate(by_tier[key])
        lines.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(key, item["n_included_cache_free"], item["n_quality_valid"], item["backend_mean_ms"] or "—", item["backend_p50_ms"] or "—", item["backend_p95_ms"] or "—", item["wall_mean_ms"] or "—", item["wall_p50_ms"] or "—", item["wall_p95_ms"] or "—"))
    lines.extend(["", "## Benchmark strata", "", "| Stratum | Total | Included | Quality-valid | Backend mean ms | Backend p50 ms | Backend p95 ms | Exclusions |", "|---|---:|---:|---:|---:|---:|---:|---|"])
    for key in sorted(grouped):
        item = aggregate(grouped[key])
        lines.append(f"| {key} | {item['n_total']} | {item['n_included_cache_free']} | {item['n_quality_valid']} | {item['backend_mean_ms'] or '—'} | {item['backend_p50_ms'] or '—'} | {item['backend_p95_ms'] or '—'} | {json.dumps(item['exclusion_reasons'], ensure_ascii=False)} |")
    lines.extend(["", "## Source-category results", "", "| Category | Total | Included | Quality-valid | Backend mean ms | Backend p50 ms | Backend p95 ms | Observed tiers |", "|---|---:|---:|---:|---:|---:|---:|---|"])
    for key in sorted(by_category):
        item = aggregate(by_category[key])
        lines.append(f"| {key} | {item['n_total']} | {item['n_included_cache_free']} | {item['n_quality_valid']} | {item['backend_mean_ms'] or '—'} | {item['backend_p50_ms'] or '—'} | {item['backend_p95_ms'] or '—'} | {json.dumps(item['observed_query_tiers'], ensure_ascii=False)} |")
    lines.extend(["", "## Language results", "", "| Language | Total | Included | Quality-valid | Backend mean ms | Backend p50 ms | Backend p95 ms |", "|---|---:|---:|---:|---:|---:|---:|"])
    for key in sorted(by_language):
        item = aggregate(by_language[key])
        lines.append(f"| {key} | {item['n_total']} | {item['n_included_cache_free']} | {item['n_quality_valid']} | {item['backend_mean_ms'] or '—'} | {item['backend_p50_ms'] or '—'} | {item['backend_p95_ms'] or '—'} |")
    exclusion = aggregate(merged)
    lines.extend(["", "## Exclusions and reliability", "", f"The merged set has {exclusion['n_excluded']} excluded rows. The full wave entered a near-immediate HTTP-error regime after its first 185 valid rows. The retry wave recovered most categories but encountered explicit HTTP 429 rate limits in late cases. These are reliability and capacity findings, not latency measurements.", "", "| Exclusion reason | Count |", "|---|---:|"])
    for key, value in sorted(exclusion["exclusion_reasons"].items()):
        lines.append(f"| {key} | {value} |")
    lines.extend(["", "## Quality and safety gates", "", "The benchmark retains separate quality validity from latency inclusion. A row may be cache-free and timed but still fail its bank checks because required terms were absent, citations were insufficient, a rejected term appeared, the expected safety outcome did not match, or the result was an honest abstention/partial fallback. The `quality_valid` count is therefore the gate for quality-valid latency, not a claim that every included response passed.", "", "| Gate | Interpretation |", "|---|---|", "| Cache-free | `cache_hit=false` and non-cache route |", "| Grounding/citation | Bank terms and minimum citations checked in memory; raw answers are not persisted |", "| Safety | Distress/refusal cases require blocked/safety-redirect behavior where specified |", "| Public contract | Banned internal/public fields are scanned recursively; no violations were permitted for quality-valid rows |", "| Tenant/privacy | This wave used fresh anonymous sessions and bounded response fields; cross-tenant destructive tests were not induced by the latency runner |", "", "## Findings and next actions", "", "1. **The runtime has a capacity/rate-limit seam.** The full wave’s late HTTP failures and the retry wave’s explicit 429s mean a future repeated benchmark must include cooldowns, provider-rate telemetry, and a separate capacity test; it must not treat a sequential 420-case run as a stable provider-capacity baseline.", "2. **Tier routing is materially mixed.** Many bank categories resolve to `tier2_simple`, while complex categories also produce `tier3_complex` and `standard`. The benchmark should add reviewed expected-route labels or route-family assertions before any route-specific optimization claim.", "3. **Deep and multilingual tails remain the dominant latency risk.** Valid category results show multi-second to tens-of-seconds tails, while fast deterministic safety paths can complete near zero backend milliseconds. Output-budget and reranker changes require held-out quality gates before activation.", "4. **Quality is not closed.** Several doctrine and multilingual cases are cache-free but quality-invalid due grounded partial/abstained outputs or missing expected terms. This is an evidence-quality problem, not a reason to weaken citations, abstention, or safety.", "5. **The next valid percentile sprint should be stratified rather than full-bank repeated.** Run at least 20 route-correct, quality-valid, cache-disabled samples for each target tier/stratum after cooldown, with separate single-client and controlled-concurrency waves.", "", "## Evidence references", "", "[1]: ./question_bank_latency_manifest_v1.json — normalized 420-case manifest and source hash.", "[2]: ./question_bank_latency_full_v2_summary.json — first full-wave bounded summary; late HTTP-error regime excluded from latency claims.", "[3]: ./question_bank_latency_retry_v1_summary.json — retry-wave bounded summary with explicit rate-limit exclusions.", "[4]: ./question_bank_latency_full_v2.jsonl — full-wave raw bounded rows.", "[5]: ./question_bank_latency_retry_v1.jsonl — retry-wave raw bounded rows.", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--full", type=Path, required=True)
    parser.add_argument("--retry", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    full_rows = load_rows(args.full)
    retry_rows = load_rows(args.retry)
    merged, replaced = merge_rows(full_rows, retry_rows)
    result = {
        "analysis_version": "question-bank-latency-analysis-v1",
        "manifest_source_sha256": manifest["source_sha256"],
        "full_rows": len(full_rows),
        "retry_rows": len(retry_rows),
        "merged_rows": len(merged),
        "replaced_case_count": len(replaced),
        "replaced_case_ids": replaced,
        "overall": aggregate(merged),
        "by_query_tier": {key: aggregate([row for row in merged if str(row.get("query_tier") or "unknown") == key]) for key in sorted({str(row.get("query_tier") or "unknown") for row in merged})},
        "by_stratum": {key: aggregate([row for row in merged if str(row.get("benchmark_stratum") or "unknown") == key]) for key in sorted({str(row.get("benchmark_stratum") or "unknown") for row in merged})},
        "by_category": {key: aggregate([row for row in merged if str(row.get("source_category") or "unknown") == key]) for key in sorted({str(row.get("source_category") or "unknown") for row in merged})},
        "by_language": {key: aggregate([row for row in merged if str(row.get("language") or "unknown") == key]) for key in sorted({str(row.get("language") or "unknown") for row in merged})},
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output_md.write_text(markdown_report(merged, full_rows, retry_rows, manifest, replaced), encoding="utf-8")
    print(json.dumps({"json": str(args.output_json), "markdown": str(args.output_md), "merged_rows": len(merged), "included": result["overall"]["n_included_cache_free"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
