#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

BASE = "http://localhost:8000"
QUERY = "नमस्ते गुरुजी, सुंदर अवस्था क्या है?"
LANGUAGE = "hi"


def request(method: str, path: str, payload=None, headers=None, timeout=30):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def main(output: str) -> None:
    started = time.perf_counter()
    _, session = request("POST", "/api/auth/anon-session", {}, timeout=15)
    token = session["token"]
    admission_status, admission = request(
        "POST",
        "/api/chat",
        {"user_message": QUERY, "language": LANGUAGE, "session_id": token, "messages": []},
        headers={"X-Session-Id": token},
        timeout=30,
    )
    final = {}
    polls = 0
    for _ in range(720):
        polls += 1
        time.sleep(0.25)
        _, final = request(
            "GET",
            f"/api/jobs/{admission['job_id']}",
            headers={"X-Session-Id": token},
            timeout=20,
        )
        if final.get("status") in {"completed", "failed", "cancelled"}:
            break
    result = final.get("result") if isinstance(final, dict) else {}
    row = {
        "label": "hindi",
        "query": QUERY,
        "language": LANGUAGE,
        "admission_status": admission_status,
        "job_id": admission.get("job_id"),
        "status": final.get("status"),
        "polls": polls,
        "wall_ms": round((time.perf_counter() - started) * 1000, 2),
        "latency_ms": result.get("latency_ms"),
        "node_timings": result.get("node_timings"),
        "query_tier": result.get("query_tier"),
        "grounding_state": result.get("grounding_state"),
        "verification": result.get("verification"),
        "cache_hit": result.get("cache_hit"),
        "error": final.get("error"),
    }
    Path(output).write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "audit_work/latency_probe_hindi_latest.jsonl")
