from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import requests

BASE_URL = (
    sys.argv[1].rstrip("/")
    if len(sys.argv) > 1
    else "https://askmukthiguru-8119b0e8-production.up.railway.app"
)
ATTEMPTS = int(sys.argv[2]) if len(sys.argv) > 2 else 8
DELAY_SECONDS = float(sys.argv[3]) if len(sys.argv) > 3 else 20
ENDPOINTS = ("/api/health", "/health", "/api/health/ready")


def probe(path: str) -> dict[str, object]:
    url = urljoin(BASE_URL + "/", path.lstrip("/"))
    started = time.perf_counter()
    try:
        response = requests.get(url, timeout=(5, 15), allow_redirects=False)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        body = response.text[:500].replace("\n", " ")
        content_type = response.headers.get("content-type", "")
        ready = response.status_code == 200
        if "json" in content_type:
            try:
                payload = response.json()
                ready = ready and payload.get("ready") is True
            except ValueError:
                ready = False
        return {
            "path": path,
            "status": response.status_code,
            "latency_ms": elapsed_ms,
            "content_type": content_type,
            "body_preview": (
                body if "text" in content_type or "json" in content_type else "<non-text>"
            ),
            "ready": ready,
        }
    except requests.RequestException as exc:
        return {
            "path": path,
            "status": None,
            "latency_ms": None,
            "error_type": type(exc).__name__,
            "ready": False,
        }


records: list[dict[str, object]] = []
for attempt in range(1, ATTEMPTS + 1):
    batch = {
        "attempt": attempt,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "probes": [probe(path) for path in ENDPOINTS],
    }
    records.append(batch)
    print(json.dumps(batch, ensure_ascii=True))
    if any(item.get("ready") for item in batch["probes"]):
        Path("/tmp/railway_readiness.json").write_text(
            json.dumps({"base_url": BASE_URL, "ready": True, "records": records}, indent=2),
            encoding="utf-8",
        )
        raise SystemExit(0)
    if attempt < ATTEMPTS:
        time.sleep(DELAY_SECONDS)

Path("/tmp/railway_readiness.json").write_text(
    json.dumps({"base_url": BASE_URL, "ready": False, "records": records}, indent=2),
    encoding="utf-8",
)
raise SystemExit(2)
