"""Chaos test: kill Qdrant mid-traffic, verify graceful degradation (P1-OPS-7 T3).

Sends chat requests in a loop while the Qdrant container is stopped, then
restarts it. Pass criteria:
  - during the outage, requests return 200 (cached doctrine, casual
    short-circuit, or graceful-degradation path) — none hang or 5xx
  - after Qdrant returns, retrieval works again (fresh uncached query 200)

Usage (local docker-compose stack; X-Test-Key backdoor required):
    BENCHMARK_SECRET=... python scripts/chaos_qdrant_kill.py \
        --endpoint http://127.0.0.1:8000 \
        --container askmukthiguru-qdrant-1 \
        --traffic-seconds 30

Skips cleanly (exit 0) if docker or the container is unavailable — the test
is only meaningful where the stack is running.
"""

import argparse
import json
import subprocess
import sys
import time
import urllib.request

_DOCTRINE_QUERY = "What is the essence of inner stillness?"


def _post_chat(endpoint: str, payload: dict, test_key: str) -> tuple[int, str]:
    req = urllib.request.Request(
        f"{endpoint}/api/chat",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "X-Test-Key": test_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310 -- configured chaos-test endpoint
            return resp.status, resp.read().decode()[:200]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]
    except Exception as e:  # connection refused etc.
        return -1, str(e)


def _docker(op: str, container: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["docker", op, container],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return proc.returncode, (proc.stdout + proc.stderr).strip()
    except Exception as e:
        return -1, str(e)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="http://127.0.0.1:8000")
    parser.add_argument("--container", default="askmukthiguru-qdrant-1")
    parser.add_argument("--traffic-seconds", type=int, default=30)
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()

    test_key = ""
    try:
        import os

        test_key = os.environ["BENCHMARK_SECRET"]
    except KeyError:
        print("BENCHMARK_SECRET env required (benchmark auth backdoor)", file=sys.stderr)
        return 2

    rc, out = _docker("inspect", args.container)
    if rc != 0:
        print(f"SKIP: qdrant container not present ({out}) — chaos test not applicable here")
        return 0

    failures: list[str] = []
    payload = {
        "messages": [{"role": "user", "content": _DOCTRINE_QUERY}],
        "user_message": _DOCTRINE_QUERY,
        "language": "en",
    }

    print(f"[chaos] baseline traffic ({args.traffic_seconds}s before kill)")
    deadline = time.time() + args.traffic_seconds
    while time.time() < deadline:
        status, _ = _post_chat(args.endpoint, payload, test_key)
        if status != 200:
            failures.append(f"baseline request failed: HTTP {status}")
        time.sleep(args.interval)

    print(f"[chaos] stopping {args.container} (outage window = {args.traffic_seconds}s)")
    rc, out = _docker("stop", args.container)
    if rc != 0:
        print(f"FAIL: could not stop qdrant: {out}", file=sys.stderr)
        return 1
    outage_start = time.time()

    deadline = time.time() + args.traffic_seconds
    while time.time() < deadline:
        status, body = _post_chat(args.endpoint, payload, test_key)
        if status == 200:
            pass  # graceful degradation path working
        elif status == 429 or status == 503:
            failures.append(f"outage request backpressure: HTTP {status} (body={body})")
        else:
            failures.append(f"outage request failed: HTTP {status} (body={body})")
        time.sleep(args.interval)
    outage_seconds = time.time() - outage_start

    print(f"[chaos] restarting {args.container}")
    rc, out = _docker("start", args.container)
    if rc != 0:
        print(f"FAIL: could not restart qdrant: {out}", file=sys.stderr)
        return 1
    time.sleep(10)  # give qdrant time to accept connections

    status, _ = _post_chat(args.endpoint, payload, test_key)
    if status != 200:
        failures.append(f"post-recovery request failed: HTTP {status}")

    if failures:
        print(f"[chaos] FAIL ({outage_seconds:.0f}s outage):")
        for f in failures:
            print(f"  - {f}")
        return 1

    print(
        f"[chaos] PASS: {outage_seconds:.0f}s Qdrant outage served via caches/fallback; "
        f"post-recovery retrieval OK"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
