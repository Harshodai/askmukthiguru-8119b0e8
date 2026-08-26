"""Repeated queued latency benchmark with explicit cache and percentile discipline.

This runner is measurement-only: it does not alter routing or globally flush Redis.
By default it expects the backend to run with LATENCY_BENCHMARK_CACHE_DISABLED=true.
Any cache-served sample is excluded from latency statistics. Percentiles are
suppressed until --runs reaches the configured minimum (default 20).
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

BASE = os.environ.get("ASKMUKTHIGURU_BASE", "http://localhost:8000")
QUERIES = [
    ("fast_casual", "Namaste Guruji", "en"),
    ("fast_factual", "What is Soul Sync?", "en"),
    ("fast_meditation", "Guide me through a short calming breathing practice.", "en"),
    ("standard_factual", "How does meditation transform daily awareness over time?", "en"),
    ("standard_reflective", "Why does stillness feel difficult when the mind is restless?", "en"),
    ("deep_comparison", "Compare stillness with the beautiful state and explain how they relate.", "en"),
    ("deep_multihop", "How do attention, thought, and inner silence relate in practice? Explain the sequence.", "en"),
    ("distress", "I feel overwhelmed and need a calm grounding practice.", "en"),
    ("temporal", "What is happening in the world today?", "en"),
    ("hindi_simple", "नमस्ते गुरुजी, सुंदर अवस्था क्या है?", "hi"),
    ("hindi_comparison", "स्थिरता और सुंदर अवस्था में क्या अंतर है?", "hi"),
    ("telugu_simple", "గురూజీ, అందమైన స్థితి అంటే ఏమిటి?", "te"),
]


def request(method: str, path: str, payload=None, headers=None, timeout: float = 120):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def bounded_result(body: dict) -> dict:
    result = body.get("result") if isinstance(body.get("result"), dict) else body
    verification = result.get("verification")
    if isinstance(verification, dict):
        verification = {
            key: verification.get(key)
            for key in ("passed", "method", "citations_verified")
            if key in verification
        }
    return {
        "latency_ms": result.get("latency_ms"),
        "route_decision": result.get("route_decision"),
        "query_tier": result.get("query_tier"),
        "cache_hit": result.get("cache_hit"),
        "intent": result.get("intent"),
        "grounding_state": result.get("grounding_state"),
        "model_provider": result.get("model_provider"),
        "verification": verification,
    }


def one(label: str, query: str, language: str, poll_interval: float, request_timeout: float, cache_mode: str) -> dict:
    started = time.perf_counter()
    row = {
        "label": label,
        "language": language,
        "cache_mode": cache_mode,
        "included": False,
    }
    try:
        _, session = request("POST", "/api/auth/anon-session", {}, timeout=15)
        token = session.get("token")
        if not token:
            row["error"] = "missing_session_token"
            return row
        status, admission = request(
            "POST",
            "/api/chat",
            {"user_message": query, "language": language, "session_id": token, "messages": []},
            headers={"X-Session-Id": token},
            timeout=request_timeout,
        )
        row.update({"admission_status": status, "job_id": admission.get("job_id")})
        if status != 202 or not admission.get("job_id"):
            row["error"] = "admission_failed"
            return row
        final = {}
        for poll_count in range(1, 1201):
            time.sleep(poll_interval)
            _, final = request(
                "GET",
                f"/api/jobs/{admission['job_id']}",
                headers={"X-Session-Id": token},
                timeout=20,
            )
            if final.get("status") in {"completed", "failed", "cancelled"}:
                row["polls"] = poll_count
                break
        row.update(bounded_result(final))
        row["status"] = final.get("status")
        cache_hit = row.get("cache_hit")
        route_decision = str(row.get("route_decision") or "").lower()
        if row.get("status") != "completed":
            row["excluded_reason"] = "not_completed"
        elif cache_hit is not False:
            row["excluded_reason"] = "cache_signal_not_false"
        elif "cache" in route_decision or route_decision == "doctrine":
            row["excluded_reason"] = "cache_route_decision"
        else:
            row["included"] = True
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as exc:
        row["error"] = type(exc).__name__
    row["wall_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return row


def percentile(values: list[float], probability: float) -> float:
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    fraction = position - lower
    return values[lower] + (values[upper] - values[lower]) * fraction


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--min-percentile-samples", type=int, default=20)
    parser.add_argument("--poll-interval", type=float, default=0.25)
    parser.add_argument("--request-timeout", type=float, default=120)
    parser.add_argument("--labels", default="")
    parser.add_argument(
        "--cache-mode",
        choices=("disabled", "exclude_hits", "warm_shared"),
        default="disabled",
        help="Expected cache policy; disabled requires the backend benchmark flag.",
    )
    parser.add_argument("--output", default="audit_work/latency_benchmark_repeated.jsonl")
    args = parser.parse_args()
    if args.runs < 1:
        raise SystemExit("--runs must be positive")
    selected = {label.strip() for label in args.labels.split(",") if label.strip()}
    fixtures = [item for item in QUERIES if not selected or item[0] in selected]
    if not fixtures:
        raise SystemExit("No matching labels")

    rows = []
    for run in range(1, args.runs + 1):
        for label, query, language in fixtures:
            row = one(label, query, language, args.poll_interval, args.request_timeout, args.cache_mode)
            row["run"] = run
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")

    by_label: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_label[row["label"]].append(row)
    summaries = []
    for label, sample_rows in by_label.items():
        backend = [
            float(row["latency_ms"])
            for row in sample_rows
            if row.get("included") is True and isinstance(row.get("latency_ms"), (int, float))
        ]
        wall = [
            float(row["wall_ms"])
            for row in sample_rows
            if row.get("included") is True and isinstance(row.get("wall_ms"), (int, float))
        ]
        enough = len(backend) >= args.min_percentile_samples
        summaries.append(
            {
                "label": label,
                "n_total": len(sample_rows),
                "n_backend": len(backend),
                "n_observed": sum(isinstance(row.get("latency_ms"), (int, float)) for row in sample_rows),
                "n_included": sum(row.get("included") is True for row in sample_rows),
                "n_excluded": sum(row.get("included") is not True for row in sample_rows),
                "cache_hits": sum(bool(row.get("cache_hit")) for row in sample_rows),
                "backend_mean_ms": round(statistics.mean(backend), 2) if backend else None,
                "backend_p50_ms": round(percentile(backend, 0.50), 2) if enough else None,
                "backend_p95_ms": round(percentile(backend, 0.95), 2) if enough else None,
                "wall_mean_ms": round(statistics.mean(wall), 2) if wall else None,
                "wall_p50_ms": round(percentile(wall, 0.50), 2) if len(wall) >= args.min_percentile_samples else None,
                "wall_p95_ms": round(percentile(wall, 0.95), 2) if len(wall) >= args.min_percentile_samples else None,
                "percentiles_status": "reported" if enough else f"suppressed_need_{args.min_percentile_samples}_backend_samples",
            }
        )
    summary_path = output.with_name(output.stem + "_summary.json")
    summary_path.write_text(
        json.dumps(
            {
                "base_url": BASE,
                "runs": args.runs,
                "cache_mode": args.cache_mode,
                "cache_free_only": args.cache_mode in {"disabled", "exclude_hits"},
                "percentile_min_samples": args.min_percentile_samples,
                "rows": summaries,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"summary": str(summary_path), "samples": len(rows)}, indent=2))


if __name__ == "__main__":
    main()
