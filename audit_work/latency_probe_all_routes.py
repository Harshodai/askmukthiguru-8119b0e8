#!/usr/bin/env python3
"""Bounded cross-tier latency probe for local engineering evidence.

The query list is a benchmark fixture, not production routing logic. Each
request receives a fresh signed anonymous session and is polled through the
public queued-job contract. Results are JSONL with only bounded public result
metadata; prompts are included solely as local benchmark labels.
"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://localhost:8000"
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


def request(method, path, payload=None, headers=None, timeout=30):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def bounded_result(body):
    result = body.get("result") if isinstance(body, dict) else None
    if not isinstance(result, dict):
        result = body if isinstance(body, dict) else {}
    verification = result.get("verification")
    if isinstance(verification, dict):
        verification = {k: verification.get(k) for k in ("passed", "method", "citations_verified") if k in verification}
    timings = result.get("node_timings")
    if isinstance(timings, dict):
        timings = {str(k): timings[k] for k in timings if isinstance(timings[k], (int, float))}
    return {
        "status": body.get("status") if isinstance(body, dict) else None,
        "latency_ms": result.get("latency_ms"),
        "node_timings": timings,
        "route_decision": result.get("route_decision"),
        "query_tier": result.get("query_tier"),
        "cache_hit": result.get("cache_hit"),
        "intent": result.get("intent"),
        "grounding_state": result.get("grounding_state"),
        "model_provider": result.get("model_provider"),
        "model_used": result.get("model_used"),
        "verification": verification,
        "error": body.get("error") if isinstance(body, dict) else None,
    }


def one(label, query, lang):
    started = time.perf_counter()
    try:
        _, session = request("POST", "/api/auth/anon-session", {}, timeout=15)
        token = session.get("token")
        if not token:
            return {"label": label, "query": query, "language": lang, "error": "missing session token"}
        status, admission = request(
            "POST", "/api/chat",
            {"user_message": query, "language": lang, "session_id": token, "messages": []},
            headers={"X-Session-Id": token}, timeout=30,
        )
        row = {"label": label, "query": query, "language": lang, "admission_status": status, "job_id": admission.get("job_id")}
        if status != 202 or not admission.get("job_id"):
            row["admission"] = admission
            return row
        final = {}
        polls = 0
        for _ in range(720):
            polls += 1
            time.sleep(0.25)
            _, final = request("GET", f"/api/jobs/{admission['job_id']}", headers={"X-Session-Id": token}, timeout=20)
            if final.get("status") in {"completed", "failed", "cancelled"}:
                break
        row.update({"polls": polls, "wall_ms": round((time.perf_counter() - started) * 1000, 2)})
        row.update(bounded_result(final))
        return row
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as exc:
        return {"label": label, "query": query, "language": lang, "wall_ms": round((time.perf_counter() - started) * 1000, 2), "error": type(exc).__name__ + ": " + str(exc)[:240]}


def main():
    output_path = sys.argv[1] if len(sys.argv) > 1 else "audit_work/latency_probe_all_routes.jsonl"
    rows = [one(*item) for item in QUERIES]
    with open(output_path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    for row in rows:
        print(json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    main()
