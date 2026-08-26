"""Question-bank-driven cache-disabled end-to-end benchmark.

The runner deliberately stores no question text or answer text in results. It
scores expected terms in memory, then persists bounded metadata, latency, route
signals, and exclusion reasons only.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

BASE = os.environ.get("ASKMUKTHIGURU_BASE", "http://localhost:8000")
BANNED_PUBLIC_KEYS = {
    "memory_context",
    "attachment_context",
    "raw_graph_state",
    "graph_state",
    "route_metadata",
    "safety_state",
    "provider_tokens",
    "prompt",
    "system_prompt",
    "user_prompt",
    "queue_wait_ms",
}


def request(method: str, path: str, payload: Any = None, headers: dict[str, str] | None = None, timeout: float = 120) -> tuple[int, dict[str, Any]]:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def load_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("manifest_version") != "question-bank-latency-v1":
        raise ValueError("Unsupported question-bank manifest version")
    return manifest


def result_object(body: dict[str, Any]) -> dict[str, Any]:
    result = body.get("result") if isinstance(body.get("result"), dict) else body
    return result if isinstance(result, dict) else {}


def answer_text(result: dict[str, Any]) -> str:
    value = result.get("response") or result.get("final_answer") or result.get("answer") or ""
    return value if isinstance(value, str) else str(value)


def public_field_scan(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            key_low = str(key).lower()
            if key_low in BANNED_PUBLIC_KEYS:
                found.add(key_low)
            found.update(public_field_scan(nested))
    elif isinstance(value, list):
        for nested in value:
            found.update(public_field_scan(nested))
    return found


def quality_check(case: dict[str, Any], result: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    text = answer_text(result).casefold()
    required = [str(item).casefold() for item in case.get("must_mention", []) if str(item).strip()]
    any_required = [str(item).casefold() for item in case.get("must_mention_any", []) if str(item).strip()]
    rejected = [str(item).casefold() for item in case.get("reject_if", []) if str(item).strip()]
    missing = [term for term in required if term not in text]
    any_match = [term for term in any_required if term in text]
    rejected_match = [term for term in rejected if term in text]
    citations = result.get("citations") if isinstance(result.get("citations"), list) else []
    citation_count = len(citations)
    expected_citations = int(case.get("min_citations") or 0)
    expected_intent = case.get("expected_intent")
    observed_intent = result.get("intent")
    semantic_public_aliases = {
        "FACTUAL": {"QUERY", "FACTUAL"},
        "FOLLOW_UP": {"QUERY", "FOLLOW_UP"},
        "COMPARATIVE": {"QUERY", "COMPARATIVE"},
        "REASONING": {"QUERY", "REASONING"},
        "APPLICATIONAL": {"QUERY", "APPLICATIONAL"},
    }
    acceptable_intents = semantic_public_aliases.get(str(expected_intent), {expected_intent})
    intent_match = expected_intent is None or observed_intent in acceptable_intents
    expected = str(case.get("expected_outcome") or "")
    blocked = bool(result.get("blocked"))
    grounding = result.get("grounding_state")
    safety_match = True
    if expected == "refuse":
        safety_match = blocked or grounding == "safety_redirect" or expected_intent in {"DISTRESS", "MEDICAL"}
    if expected_intent == "DISTRESS":
        safety_match = blocked or grounding == "safety_redirect" or observed_intent == "DISTRESS"
    banned_keys = sorted(public_field_scan(body))
    passed = (
        not missing
        and (not any_required or bool(any_match))
        and not rejected_match
        and citation_count >= expected_citations
        and intent_match
        and safety_match
        and not banned_keys
    )
    return {
        "quality_valid": passed,
        "required_terms_missing": missing[:8],
        "required_any_match_count": len(any_match),
        "rejected_terms_found": rejected_match[:8],
        "citation_count": citation_count,
        "citations_verified": result.get("citations_verified"),
        "expected_citations": expected_citations,
        "expected_intent": expected_intent,
        "observed_intent": observed_intent,
        "intent_match": intent_match,
        "blocked": blocked,
        "grounding_state": grounding,
        "banned_public_keys": banned_keys,
    }


def bounded_result(body: dict[str, Any]) -> dict[str, Any]:
    result = result_object(body)
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
        "trace_id": result.get("trace_id"),
        "verification": verification,
    }


def new_session(timeout: float = 20) -> tuple[str, dict[str, Any]]:
    _, session = request("POST", "/api/auth/anon-session", {}, timeout=timeout)
    token = session.get("token")
    if not token:
        raise RuntimeError("missing_session_token")
    return token, session


def run_turn(
    case: dict[str, Any],
    token: str,
    history: list[dict[str, str]],
    args: argparse.Namespace,
) -> dict[str, Any]:
    started = time.perf_counter()
    row: dict[str, Any] = {
        "case_id": case["case_id"],
        "source_category": case["source_category"],
        "benchmark_stratum": case["benchmark_stratum"],
        "language": case.get("language") or "en",
        "scenario": case.get("scenario"),
        "turn_index": case.get("turn_index"),
        "is_multi_turn": case.get("is_multi_turn", False),
        "cache_mode": args.cache_mode,
        "included": False,
        "execution_mode": "multi_turn" if case.get("is_multi_turn") else "single_turn",
    }
    try:
        status, admission = request(
            "POST",
            "/api/chat",
            {
                "user_message": case["question"],
                "language": case.get("language") or "en",
                "session_id": token,
                "messages": history,
            },
            headers={"X-Session-Id": token},
            timeout=args.request_timeout,
        )
        row.update({"admission_status": status, "job_id": admission.get("job_id")})
        if status != 202 or not admission.get("job_id"):
            row["excluded_reason"] = "admission_failed"
            return row
        final: dict[str, Any] = {}
        for poll_count in range(1, args.max_polls + 1):
            time.sleep(args.poll_interval)
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
        result = result_object(final)
        row["_answer_for_history"] = answer_text(result)
        if row.get("status") != "completed":
            row["excluded_reason"] = "not_completed"
        elif row.get("cache_hit") is not False:
            row["excluded_reason"] = "cache_signal_not_false"
        elif "cache" in str(row.get("route_decision") or "").lower() or str(row.get("route_decision") or "").lower() == "doctrine":
            row["excluded_reason"] = "cache_route_decision"
        else:
            row["quality"] = quality_check(case, result, final)
            if row["quality"]["banned_public_keys"]:
                row["excluded_reason"] = "public_contract_violation"
            else:
                row["included"] = True
    except urllib.error.HTTPError as exc:
        row["error"] = "HTTPError"
        row["http_status"] = exc.code
        row["http_reason"] = str(exc.reason)[:120]
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, RuntimeError) as exc:
        row["error"] = type(exc).__name__ if not isinstance(exc, RuntimeError) else str(exc)
    row["wall_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return row


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def select_cases(manifest: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    cases = list(manifest["cases"])
    selected_categories = {value.strip() for value in args.categories.split(",") if value.strip()}
    selected_strata = {value.strip() for value in args.strata.split(",") if value.strip()}
    if selected_categories:
        cases = [case for case in cases if case["source_category"] in selected_categories]
    if selected_strata:
        cases = [case for case in cases if case["benchmark_stratum"] in selected_strata]
    if not args.include_multi_turn:
        cases = [case for case in cases if not case.get("is_multi_turn")]
    if args.limit > 0:
        cases = cases[: args.limit]
    return cases


def summarize(rows: list[dict[str, Any]], manifest: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    by_stratum: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_stratum[row["benchmark_stratum"]].append(row)
        by_category[row["source_category"]].append(row)

    def aggregate(group: list[dict[str, Any]]) -> dict[str, Any]:
        included = [row for row in group if row.get("included") and isinstance(row.get("latency_ms"), (int, float))]
        wall = [float(row["wall_ms"]) for row in group if row.get("included") and isinstance(row.get("wall_ms"), (int, float))]
        quality_valid = [row for row in group if row.get("quality", {}).get("quality_valid") is True]
        exclusions = Counter(str(row.get("excluded_reason") or row.get("error") or "unknown") for row in group if not row.get("included"))
        routes = Counter(str(row.get("query_tier") or "unknown") for row in group)
        percentile_ready = len(included) >= 20
        backend_values = [float(row["latency_ms"]) for row in included]
        return {
            "n_total": len(group),
            "n_included": len(included),
            "n_quality_valid": len(quality_valid),
            "n_excluded": len(group) - len(included),
            "exclusion_reasons": dict(exclusions),
            "observed_query_tiers": dict(routes),
            "backend_mean_ms": round(statistics.mean(backend_values), 2) if backend_values else None,
            "backend_p50_ms": round(percentile(backend_values, 0.50), 2) if percentile_ready else None,
            "backend_p95_ms": round(percentile(backend_values, 0.95), 2) if percentile_ready else None,
            "wall_mean_ms": round(statistics.mean(wall), 2) if wall else None,
            "wall_p50_ms": round(percentile(wall, 0.50), 2) if percentile_ready and len(wall) >= 20 else None,
            "wall_p95_ms": round(percentile(wall, 0.95), 2) if percentile_ready and len(wall) >= 20 else None,
            "percentiles_status": "suppressed_need_20_included" if not percentile_ready else "eligible",
        }

    return {
        "manifest_version": manifest["manifest_version"],
        "source_sha256": manifest["source_sha256"],
        "base_url": BASE,
        "cache_mode": args.cache_mode,
        "cache_free_only": args.cache_mode in {"disabled", "exclude_hits"},
        "runs": args.runs,
        "n_rows": len(rows),
        "strata": {key: aggregate(value) for key, value in sorted(by_stratum.items())},
        "categories": {key: aggregate(value) for key, value in sorted(by_category.items())},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="audit_work/question_bank_latency_manifest_v1.json", type=Path)
    parser.add_argument("--output", default="audit_work/question_bank_latency_benchmark_v1.jsonl", type=Path)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--categories", default="")
    parser.add_argument("--strata", default="")
    parser.add_argument("--include-multi-turn", action="store_true")
    parser.add_argument("--cache-mode", choices=("disabled", "exclude_hits"), default="disabled")
    parser.add_argument("--poll-interval", type=float, default=0.25)
    parser.add_argument("--request-timeout", type=float, default=120)
    parser.add_argument("--max-polls", type=int, default=1200)
    args = parser.parse_args()
    if args.runs != 1:
        raise SystemExit("Use one pass per case; repeat the selected manifest explicitly to preserve case identity")
    manifest = load_manifest(args.manifest)
    cases = select_cases(manifest, args)
    if not cases:
        raise SystemExit("No matching cases")
    rows: list[dict[str, Any]] = []
    if args.include_multi_turn:
        cases = sorted(cases, key=lambda case: (case.get("scenario") or "", case.get("turn_index") or 0, case["case_id"]))
    if args.include_multi_turn:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for case in cases:
            grouped[str(case.get("scenario") or case["case_id"])].append(case)
        execution_groups = [
            sorted(group, key=lambda case: case.get("turn_index") or 0)
            for _, group in sorted(grouped.items())
        ]
    else:
        execution_groups = [[case] for case in cases]

    for group in execution_groups:
        token, _ = new_session()
        history: list[dict[str, str]] = []
        for case in group:
            row = run_turn(case, token, history, args)
            answer_for_history = row.pop("_answer_for_history", "")
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
            if row.get("status") == "completed":
                history.extend(
                    [
                        {"role": "user", "content": case["question"]},
                        {"role": "assistant", "content": answer_for_history},
                    ]
                )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    summary_path = args.output.with_name(args.output.stem + "_summary.json")
    summary_path.write_text(json.dumps(summarize(rows, manifest, args), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "summary": str(summary_path), "rows": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
