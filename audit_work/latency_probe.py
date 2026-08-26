#!/usr/bin/env python3
import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://localhost:8000"
QUERIES = [
    ("english_simple", "What is the beautiful state?", "en"),
    ("english_stillness", "What is stillness?", "en"),
    ("english_comparison", "What is the difference between stillness and the beautiful state?", "en"),
    ("hindi", "नमस्ते गुरुजी, सुंदर अवस्था क्या है?", "hi"),
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


def summary(label, query, lang, token, admission, final_body, elapsed_ms, polls):
    result = final_body.get("result") if isinstance(final_body, dict) else None
    if not isinstance(result, dict):
        result = final_body if isinstance(final_body, dict) else {}
    verification = result.get("verification")
    if isinstance(verification, dict):
        verification = {
            k: verification.get(k)
            for k in ("passed", "method", "citations_verified")
            if k in verification
        }
    return {
        "label": label,
        "query": query,
        "language": lang,
        "admission_status": admission.get("status"),
        "job_id": admission.get("job_id"),
        "status": final_body.get("status") if isinstance(final_body, dict) else None,
        "polls": polls,
        "wall_ms": round(elapsed_ms, 2),
        "latency_ms": result.get("latency_ms"),
        "node_timings": result.get("node_timings"),
        "route_decision": result.get("route_decision"),
        "query_tier": result.get("query_tier"),
        "cache_hit": result.get("cache_hit"),
        "intent": result.get("intent"),
        "grounding_state": result.get("grounding_state"),
        "model_provider": result.get("model_provider"),
        "model_used": result.get("model_used"),
        "verification": verification,
        "error": final_body.get("error") if isinstance(final_body, dict) else None,
    }


def main():
    output_path = sys.argv[1] if len(sys.argv) > 1 else "audit_work/latency_probe_latest.jsonl"
    rows = []
    for label, query, lang in QUERIES:
        started = time.perf_counter()
        try:
            _, session = request("POST", "/api/auth/anon-session", {}, timeout=15)
            token = session.get("token")
            if not token:
                rows.append({"label": label, "error": "missing session token"})
                continue
            admission_status, admission = request(
                "POST",
                "/api/chat",
                {"user_message": query, "language": lang, "session_id": token, "messages": []},
                headers={"X-Session-Id": token},
                timeout=30,
            )
            if admission_status != 202 or not admission.get("job_id"):
                rows.append({"label": label, "query": query, "admission_status": admission_status, "admission": admission})
                continue
            job_id = admission["job_id"]
            final_body = {}
            polls = 0
            for _ in range(720):
                polls += 1
                time.sleep(0.25)
                _, body = request(
                    "GET",
                    f"/api/jobs/{job_id}",
                    headers={"X-Session-Id": token},
                    timeout=20,
                )
                final_body = body
                if body.get("status") in {"completed", "failed", "cancelled"}:
                    break
            rows.append(summary(label, query, lang, token, {"status": admission_status, **admission}, final_body, (time.perf_counter() - started) * 1000, polls))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as exc:
            rows.append({"label": label, "query": query, "language": lang, "wall_ms": round((time.perf_counter() - started) * 1000, 2), "error": type(exc).__name__ + ": " + str(exc)[:240]})
    with open(output_path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    for row in rows:
        print(json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    main()
