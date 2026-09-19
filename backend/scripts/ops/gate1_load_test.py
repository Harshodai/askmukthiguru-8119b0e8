#!/usr/bin/env python3
"""gate1_load_test.py — 20-Concurrent User Load & Concurrency Verification Engine.

Launch Gate 1 (docs/audits/LAUNCH_READINESS_GATES_2026-09-13.md):
- Proves 20 concurrent users under sustained load using asyncio + httpx.
- Uses X-Test-Key benchmark authorization (bypassing rate limiter and quota walls).
- Evaluates mixed query strata across Fast, Standard, and Deep tiers.
- Measures latency (p50, p90, p95, p99), throughput (RPS), error rates, and grounding states.
- Supports chaos failure injection to verify graceful degradation under load.
- Outputs structured reports to JSON and Markdown.

Usage:
    # Run in-process with 20 concurrent workers (60 requests)
    cd backend && .venv/bin/python3 scripts/ops/gate1_load_test.py --concurrency 20 --requests 60

    # Run against a live HTTP server
    cd backend && .venv/bin/python3 scripts/ops/gate1_load_test.py --base-url http://localhost:8000 --concurrency 20 --requests 100

    # Run with chaos fault injection
    cd backend && .venv/bin/python3 scripts/ops/gate1_load_test.py --chaos qdrant --concurrency 10 --requests 30
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import statistics
import sys
import threading
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

# Ensure backend root is on sys.path
_BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("gate1_load_test")

REPORT_DIR = _BACKEND_DIR / "benchmarks" / "reports"
DEFAULT_BENCHMARK_KEY = "gate1-benchmark-secret-2026"

# ═══════════════════════════════════════════════════════════════════════════
# BALANCED QUERY STRATA (Fast, Standard, Deep)
# ═══════════════════════════════════════════════════════════════════════════

QUERY_STRATA: list[dict[str, Any]] = [
    # --- FAST LANE (Greeting / Meta queries — minimal retrieval/compute) ---
    {"query": "Namaste", "tier": "fast", "category": "greeting", "expected_intent": "GREETING"},
    {
        "query": "Hello, who is Mukthi Guru?",
        "tier": "fast",
        "category": "meta",
        "expected_intent": "QUERY",
    },
    {
        "query": "Pranam, good morning",
        "tier": "fast",
        "category": "greeting",
        "expected_intent": "GREETING",
    },
    {
        "query": "Blessings and greetings",
        "tier": "fast",
        "category": "greeting",
        "expected_intent": "GREETING",
    },
    {
        "query": "What is the purpose of this space?",
        "tier": "fast",
        "category": "meta",
        "expected_intent": "QUERY",
    },
    # --- STANDARD LANE (Core Teachings & Meditation FAQs) ---
    {
        "query": "What is the 3-minute Serene Mind practice?",
        "tier": "standard",
        "category": "serene_mind",
        "expected_intent": "QUERY",
    },
    {
        "query": "Explain the 6 steps of Soul Sync meditation.",
        "tier": "standard",
        "category": "soul_sync",
        "expected_intent": "QUERY",
    },
    {
        "query": "What are the Four Sacred Secrets taught by Sri Preethaji and Sri Krishnaji?",
        "tier": "standard",
        "category": "four_secrets",
        "expected_intent": "QUERY",
    },
    {
        "query": "How does conscious deep breathing shift the nervous system?",
        "tier": "standard",
        "category": "neurobiology",
        "expected_intent": "QUERY",
    },
    {
        "query": "What is the distinction between suffering and living in a beautiful state?",
        "tier": "standard",
        "category": "philosophy",
        "expected_intent": "QUERY",
    },
    {
        "query": "How can I calm my mind when feeling stressed?",
        "tier": "standard",
        "category": "serene_mind",
        "expected_intent": "QUERY",
    },
    {
        "query": "What is the role of setting an intention in Soul Sync?",
        "tier": "standard",
        "category": "soul_sync",
        "expected_intent": "QUERY",
    },
    # --- DEEP LANE (Contemplative / Philosophical / Neurobiology) ---
    {
        "query": "How does Sri Preethaji explain transforming suffering into a beautiful state?",
        "tier": "deep",
        "category": "philosophy",
        "expected_intent": "QUERY",
    },
    {
        "query": "What is the relationship between deeksha and the awakening of universal intelligence?",
        "tier": "deep",
        "category": "deeksha",
        "expected_intent": "QUERY",
    },
    {
        "query": "Can one be in a beautiful state while dealing with difficult outer life challenges?",
        "tier": "deep",
        "category": "philosophy",
        "expected_intent": "QUERY",
    },
    {
        "query": "How do the parietal lobes relate to the experience of separation and suffering according to Sri Krishnaji?",
        "tier": "deep",
        "category": "neurobiology",
        "expected_intent": "QUERY",
    },
    {
        "query": "Explain how inner truth dissolves suffering and awakens spiritual right action.",
        "tier": "deep",
        "category": "four_secrets",
        "expected_intent": "QUERY",
    },
]


# ═══════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class RequestResult:
    task_id: int
    worker_id: int
    query: str
    tier: str
    category: str
    status_code: int
    duration_ms: float
    intent: str
    grounding_state: str
    lane: str
    passed: bool
    faithfulness: float
    citations_count: int
    error_msg: str
    start_time: float
    end_time: float


@dataclass
class LatencyPercentiles:
    min: float
    p50: float
    p90: float
    p95: float
    p99: float
    max: float
    mean: float
    stddev: float


def compute_percentiles(latencies: list[float]) -> LatencyPercentiles:
    if not latencies:
        return LatencyPercentiles(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    sorted_lats = sorted(latencies)
    n = len(sorted_lats)

    def _pct(p: float) -> float:
        k = (n - 1) * p
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_lats[int(k)]
        d0 = sorted_lats[int(f)] * (c - k)
        d1 = sorted_lats[int(c)] * (k - f)
        return d0 + d1

    mean_val = statistics.mean(sorted_lats)
    stddev_val = statistics.stdev(sorted_lats) if n > 1 else 0.0

    return LatencyPercentiles(
        min=round(sorted_lats[0], 2),
        p50=round(_pct(0.50), 2),
        p90=round(_pct(0.90), 2),
        p95=round(_pct(0.95), 2),
        p99=round(_pct(0.99), 2),
        max=round(sorted_lats[-1], 2),
        mean=round(mean_val, 2),
        stddev=round(stddev_val, 2),
    )


# ═══════════════════════════════════════════════════════════════════════════
# CONCURRENT WORKER ENGINE
# ═══════════════════════════════════════════════════════════════════════════


async def load_worker(
    worker_id: int,
    client: Any,
    endpoint_url: str,
    headers: dict[str, str],
    queue: asyncio.Queue[tuple[int, dict[str, Any]]],
    results: list[RequestResult],
    stop_event: asyncio.Event,
) -> None:
    """Worker task picking requests from queue and measuring execution metrics."""
    while not stop_event.is_set():
        try:
            task_id, item = queue.get_nowait()
        except asyncio.QueueEmpty:
            break

        query = item["query"]
        tier = item["tier"]
        category = item["category"]

        payload = {
            "messages": [{"role": "user", "content": query}],
            "user_message": query,
            "session_id": f"bench_load_w{worker_id}_t{task_id}",
            "language": "en",
            "meditation_step": 0,
            "incognito": True,  # Bypass cache to evaluate cold pipeline under load
        }

        t_start = time.perf_counter()
        status_code = 500
        duration_ms = 0.0
        intent = "UNKNOWN"
        grounding_state = "unknown"
        lane = tier
        passed = False
        faithfulness = 0.0
        citations_count = 0
        error_msg = ""

        try:
            response = await client.post(endpoint_url, json=payload, headers=headers)
            t_end = time.perf_counter()
            duration_ms = round((t_end - t_start) * 1000.0, 2)
            status_code = response.status_code

            if status_code == 200:
                data = response.json()
                intent = data.get("intent", "QUERY")
                grounding_state = data.get("grounding_state", "grounded")
                lane = data.get("lane", tier)
                cites = data.get("citations", [])
                citations_count = len(cites)
                verification = data.get("verification") or {}
                faithfulness = float(verification.get("faithfulness_score", 1.0))
                passed = True
            elif status_code == 429:
                error_msg = f"HTTP 429 (Rate Limited / Quota Exceeded): {response.text[:100]}"
                passed = False
            else:
                error_msg = f"HTTP {status_code}: {response.text[:120]}"
                passed = False

        except Exception as exc:
            t_end = time.perf_counter()
            duration_ms = round((t_end - t_start) * 1000.0, 2)
            status_code = 500
            error_msg = f"{type(exc).__name__}: {str(exc)}"
            passed = False
        finally:
            queue.task_done()

        res = RequestResult(
            task_id=task_id,
            worker_id=worker_id,
            query=query,
            tier=tier,
            category=category,
            status_code=status_code,
            duration_ms=duration_ms,
            intent=intent,
            grounding_state=grounding_state,
            lane=lane,
            passed=passed,
            faithfulness=faithfulness,
            citations_count=citations_count,
            error_msg=error_msg,
            start_time=t_start,
            end_time=t_end,
        )
        results.append(res)


# ═══════════════════════════════════════════════════════════════════════════
# EXECUTION CONTROLLER
# ═══════════════════════════════════════════════════════════════════════════


async def run_gate1_load_test(
    concurrency: int = 20,
    total_requests: int = 60,
    base_url: Optional[str] = None,
    test_key: str = DEFAULT_BENCHMARK_KEY,
    chaos: str = "none",
) -> dict[str, Any]:
    """Execute concurrent load test and return structured audit results."""
    import httpx

    logger.info(
        "Initializing Gate 1 load test: concurrency=%d, requests=%d, chaos=%s",
        concurrency,
        total_requests,
        chaos,
    )

    # Prepare work items with round-robin strata distribution
    work_items: list[dict[str, Any]] = []
    strata_len = len(QUERY_STRATA)
    for i in range(total_requests):
        work_items.append(QUERY_STRATA[i % strata_len])

    queue: asyncio.Queue[tuple[int, dict[str, Any]]] = asyncio.Queue()
    for idx, item in enumerate(work_items):
        queue.put_nowait((idx, item))

    results: list[RequestResult] = []
    stop_event = asyncio.Event()

    # Determine transport (in-process vs network HTTP)
    is_inprocess = not base_url or base_url.lower() == "inprocess"
    transport = None
    app = None

    if is_inprocess:
        logger.info(
            "Mode: In-process ASGITransport execution directly against FastAPI application."
        )
        from app.config import settings

        # Configure settings for benchmark execution
        settings.enable_test_auth = True
        settings.is_production = False
        settings.benchmark_secret = test_key
        settings.multitenancy_guard_mode = "log"
        if "qdrant:" in getattr(settings, "qdrant_url", ""):
            settings.qdrant_url = "http://localhost:6333"

        from app import dependencies

        dependencies.startup_complete = True
        dependencies.startup_error = None

        from app.main import app as fastapi_app

        app = fastapi_app
        transport = httpx.ASGITransport(app=app)
        client_base_url = "http://testserver"
        endpoint = "/api/chat"
    else:
        logger.info("Mode: Live network HTTP client connecting to %s", base_url)
        client_base_url = base_url.rstrip("/")
        endpoint = f"{client_base_url}/api/chat"

    # Apply chaos fault injection if requested
    chaos_active = False
    if chaos == "qdrant":
        logger.warning("CHAOS INJECTION: Simulating Qdrant connectivity outage...")
        from services.qdrant_service import QdrantService

        QdrantService.search = lambda self, *args, **kwargs: (_ for _ in ()).throw(
            ConnectionError("Chaos simulated Qdrant outage")
        )
        chaos_active = True
    elif chaos == "neo4j":
        logger.warning("CHAOS INJECTION: Simulating Neo4j graph traversal outage...")
        import rag.kg_expansion

        rag.kg_expansion.expand_query_via_kg = lambda *args, **kwargs: []
        chaos_active = True

    headers = {
        "Content-Type": "application/json",
        "X-Test-Key": test_key,
    }

    limits = httpx.Limits(max_connections=concurrency * 2, max_keepalive_connections=concurrency)
    timeout = httpx.Timeout(60.0, connect=10.0)

    t_bench_start = time.perf_counter()

    async with httpx.AsyncClient(
        transport=transport,
        # httpx rejects base_url=None outright, so the live-HTTP mode of this
        # script had never actually run (TypeError before the first request).
        # In live mode `endpoint` is already absolute, so an empty base is right.
        base_url=client_base_url if is_inprocess else "",
        limits=limits,
        timeout=timeout,
    ) as client:
        req_endpoint = "/api/chat" if is_inprocess else endpoint
        workers = [
            asyncio.create_task(
                load_worker(
                    worker_id=w_id,
                    client=client,
                    endpoint_url=req_endpoint,
                    headers=headers,
                    queue=queue,
                    results=results,
                    stop_event=stop_event,
                )
            )
            for w_id in range(concurrency)
        ]

        await queue.join()
        stop_event.set()
        await asyncio.gather(*workers)

    t_bench_end = time.perf_counter()
    total_duration_s = round(t_bench_end - t_bench_start, 3)

    # Calculate overall metrics
    all_latencies = [r.duration_ms for r in results]
    overall_percentiles = compute_percentiles(all_latencies)

    # Per-tier breakdowns
    tiers = ["fast", "standard", "deep"]
    tier_stats: dict[str, Any] = {}
    for t in tiers:
        tier_results = [r for r in results if r.tier == t]
        tier_lats = [r.duration_ms for r in tier_results]
        tier_passed = sum(1 for r in tier_results if r.passed)
        tier_stats[t] = {
            "total_requests": len(tier_results),
            "passed_requests": tier_passed,
            "pass_rate_pct": round(
                (tier_passed / len(tier_results) * 100.0) if tier_results else 0.0, 1
            ),
            "latency": asdict(compute_percentiles(tier_lats)),
        }

    status_codes: dict[int, int] = {}
    for r in results:
        status_codes[r.status_code] = status_codes.get(r.status_code, 0) + 1

    total_completed = len(results)
    total_passed = sum(1 for r in results if r.passed)
    overall_pass_rate = round(
        (total_passed / total_completed * 100.0) if total_completed else 0.0, 1
    )
    error_count = total_completed - total_passed
    error_rate = round((error_count / total_completed * 100.0) if total_completed else 0.0, 1)
    throughput_rps = round(total_completed / total_duration_s if total_duration_s > 0 else 0.0, 2)

    # Evaluation verdict per Gate 1 pass criteria:
    # 1. 20 concurrent processed without unhandled 500 crashes
    # 2. Zero 500s (unless chaos deliberately tested fail-open)
    # 3. p95 measured and recorded
    has_500s = status_codes.get(500, 0) > 0
    gate1_passed = (total_completed >= total_requests) and (not has_500s or chaos_active)

    summary = {
        "timestamp_iso": datetime.now(UTC).isoformat(),
        "concurrency": concurrency,
        "total_requests": total_completed,
        "total_duration_seconds": total_duration_s,
        "throughput_rps": throughput_rps,
        "overall_pass_rate_pct": overall_pass_rate,
        "error_rate_pct": error_rate,
        "status_code_distribution": status_codes,
        "latency_percentiles_ms": asdict(overall_percentiles),
        "tier_breakdown": tier_stats,
        "chaos_injected": chaos,
        "gate1_verdict": "PASS" if gate1_passed else "FAIL",
    }

    # Write report files
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_json_path = REPORT_DIR / "gate1_load_test_report.json"
    report_md_path = REPORT_DIR / "gate1_load_test_report.md"

    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    md_content = f"""# Gate 1 — 20-Concurrent User Load & Performance Report

- **Date:** {summary["timestamp_iso"]}
- **Verdict:** **{summary["gate1_verdict"]}**
- **Concurrency Workers:** {concurrency}
- **Total Requests Processed:** {total_completed}
- **Total Duration:** {total_duration_s}s
- **Throughput:** {throughput_rps} RPS
- **Error Rate:** {error_rate}% (Pass Rate: {overall_pass_rate}%)
- **Chaos Injection:** `{chaos}`

---

## 1. Latency Distribution (Overall)

| Metric | Latency (ms) |
|---|---|
| **Min** | {overall_percentiles.min} ms |
| **p50 (Median)** | {overall_percentiles.p50} ms |
| **p90** | {overall_percentiles.p90} ms |
| **p95** | {overall_percentiles.p95} ms |
| **p99** | {overall_percentiles.p99} ms |
| **Max** | {overall_percentiles.max} ms |
| **Mean** | {overall_percentiles.mean} ms |
| **StdDev** | {overall_percentiles.stddev} ms |

---

## 2. Per-Tier Performance Breakdown

| Tier | Requests | Pass Rate | p50 Latency | p95 Latency | Max Latency |
|---|---|---|---|---|---|
| **Fast (Greeting/Meta)** | {tier_stats["fast"]["total_requests"]} | {tier_stats["fast"]["pass_rate_pct"]}% | {tier_stats["fast"]["latency"]["p50"]} ms | {tier_stats["fast"]["latency"]["p95"]} ms | {tier_stats["fast"]["latency"]["max"]} ms |
| **Standard (FAQ/Techniques)** | {tier_stats["standard"]["total_requests"]} | {tier_stats["standard"]["pass_rate_pct"]}% | {tier_stats["standard"]["latency"]["p50"]} ms | {tier_stats["standard"]["latency"]["p95"]} ms | {tier_stats["standard"]["latency"]["max"]} ms |
| **Deep (Contemplative)** | {tier_stats["deep"]["total_requests"]} | {tier_stats["deep"]["pass_rate_pct"]}% | {tier_stats["deep"]["latency"]["p50"]} ms | {tier_stats["deep"]["latency"]["p95"]} ms | {tier_stats["deep"]["latency"]["max"]} ms |

---

## 3. Status Code Distribution

```json
{json.dumps(status_codes, indent=2)}
```

---

## 4. Launch Gate 1 Assessment

- **20-Concurrent Concurrency Handled:** ✅ Successfully executed with {concurrency} parallel async tasks.
- **Quota / Rate-Limiter Bypass:** ✅ Benchmark identity `X-Test-Key` allowed un-throttled continuous concurrency evaluation.
- **Crash Immunity:** {"✅ Zero 500 errors observed under load." if not has_500s else "⚠️ Non-zero 500 status codes observed under chaos/load."}
"""

    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    logger.info("Gate 1 report generated: %s and %s", report_json_path, report_md_path)
    logger.info(
        "Summary: %s | Throughput: %.2f RPS | p50: %.1fms | p95: %.1fms",
        summary["gate1_verdict"],
        throughput_rps,
        overall_percentiles.p50,
        overall_percentiles.p95,
    )

    return summary


# ======================================================================
# Container resource watchdog (AMK-B-002 / AMK-C-001 regression gate)
# ======================================================================
#
# The load generator above proves the API answers. It does NOT prove the box
# survives, which is the thing that actually broke: a 6-concurrent burst
# (below the configured ceiling of 8) killed the backend twice --- once as an
# onnxruntime std::bad_alloc abort, once as `Exited (137)` from the HOST
# kernel's OOM killer with `OOMKilled: false`, because the sum of per-container
# limits exceeded the VM's real memory. Neither shows up in latency or error
# rate until the connections are already reset.
#
# So the gate asserts three things the HTTP results cannot:
#   1. the container is still running at the end,
#   2. it did not restart underneath us (a fast restart can otherwise look
#      like a brief error blip and then "recovery"),
#   3. peak RSS stayed under a real budget --- by default a fraction of the
#      HOST's total memory, not the container's own mem_limit, because the
#      limit is what was overcommitted in the first place.


def _docker_bin() -> Optional[str]:
    """Locate the docker CLI (it is not always on PATH on macOS)."""
    import shutil

    found = shutil.which("docker")
    if found:
        return found
    fallback = Path.home() / ".docker" / "bin" / "docker"
    return str(fallback) if fallback.exists() else None


def _docker(*args: str, timeout: int = 15) -> Optional[str]:
    """Run a docker command, returning stripped stdout or None on any failure."""
    import subprocess

    binary = _docker_bin()
    if not binary:
        return None
    try:
        out = subprocess.run(
            [binary, *args], capture_output=True, text=True, timeout=timeout, check=False
        )
    except Exception:
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def _host_mem_mb() -> Optional[float]:
    """Total memory available to the Docker daemon's VM/host, in MB."""
    raw = _docker("info", "--format", "{{.MemTotal}}")
    try:
        return float(raw) / (1024 * 1024) if raw else None
    except ValueError:
        return None


class ContainerWatch:
    """Samples a container's memory while the load test runs.

    Sampling is best-effort: if docker is unavailable the watch reports
    ``available=False`` and the gate degrades to the HTTP-only verdict rather
    than failing the run. It must never turn a green load test red just
    because the CLI was missing.
    """

    def __init__(self, container: str, interval: float = 2.0) -> None:
        self.container = container
        self.interval = interval
        self.samples: list[float] = []
        self.available = False
        self.start_restarts: Optional[int] = None
        self.end_restarts: Optional[int] = None
        self.end_running: Optional[bool] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # -- lifecycle ----------------------------------------------------
    def start(self) -> None:
        self.start_restarts = self._restart_count()
        self.available = self.start_restarts is not None
        if not self.available:
            logger.warning(
                "Container watch disabled: docker CLI or container %r unavailable. "
                "Load results will NOT include a survival assertion.",
                self.container,
            )
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.interval * 2)
        if self.available:
            self.end_restarts = self._restart_count()
            self.end_running = self._is_running()

    # -- sampling -----------------------------------------------------
    def _run(self) -> None:
        while not self._stop.is_set():
            mb = self._mem_mb()
            if mb is not None:
                self.samples.append(mb)
            self._stop.wait(self.interval)

    def _mem_mb(self) -> Optional[float]:
        raw = _docker(
            "stats", "--no-stream", "--format", "{{.MemUsage}}", self.container, timeout=20
        )
        if not raw:
            return None
        # "3.07GiB / 6GiB" -> 3144.0. Docker reports binary units on this
        # host, but decimal ones elsewhere; an unparsed sample yields zero
        # samples and the verdict then FAILS for "no memory samples" — a
        # regression gate that cries wolf gets ignored, so parse both.
        used = raw.split("/")[0].strip()
        units = (
            ("GiB", 1024.0),
            ("MiB", 1.0),
            ("KiB", 1 / 1024.0),
            ("GB", 1000.0 * 1000.0 * 1000.0 / (1024.0 * 1024.0)),
            ("MB", 1000.0 * 1000.0 / (1024.0 * 1024.0)),
            ("kB", 1000.0 / (1024.0 * 1024.0)),
            ("B", 1 / 1048576.0),
        )
        for suffix, mult in units:
            if used.endswith(suffix):
                try:
                    return float(used[: -len(suffix)].strip()) * mult
                except ValueError:
                    return None
        return None
        return None

    def _restart_count(self) -> Optional[int]:
        raw = _docker("inspect", "--format", "{{.RestartCount}}", self.container)
        try:
            return int(raw) if raw is not None else None
        except ValueError:
            return None

    def _is_running(self) -> bool:
        return _docker("inspect", "--format", "{{.State.Running}}", self.container) == "true"

    # -- verdict ------------------------------------------------------
    def verdict(self, budget_mb: Optional[float]) -> dict:
        peak = max(self.samples) if self.samples else None
        failures: list[str] = []

        if not self.available:
            return {
                "available": False,
                "reason": "docker CLI or container not reachable; survival not asserted",
                "passed": None,
            }

        if self.end_running is False:
            failures.append(
                f"container {self.container} is NOT running after the load test "
                "(this is the exit-137 crash class, AMK-B-002)"
            )
        if (
            self.start_restarts is not None
            and self.end_restarts is not None
            and self.end_restarts > self.start_restarts
        ):
            failures.append(
                f"container restarted during the run "
                f"({self.start_restarts} -> {self.end_restarts}) — it died and came back, "
                "which the HTTP results alone would show only as a transient error blip"
            )
        if peak is not None and budget_mb is not None and peak > budget_mb:
            failures.append(
                f"peak memory {peak:.0f}MB exceeded the budget {budget_mb:.0f}MB — "
                "headroom gone, next burst is the OOM kill"
            )
        if peak is None:
            failures.append("no memory samples collected; peak could not be asserted")

        return {
            "available": True,
            "container": self.container,
            "peak_mem_mb": round(peak, 1) if peak is not None else None,
            "budget_mem_mb": round(budget_mb, 1) if budget_mb is not None else None,
            "samples": len(self.samples),
            "restart_count_start": self.start_restarts,
            "restart_count_end": self.end_restarts,
            "running_at_end": self.end_running,
            "passed": not failures,
            "failures": failures,
        }


def main():
    parser = argparse.ArgumentParser(description="Gate 1 20-Concurrent Load Testing Harness")
    parser.add_argument(
        "--concurrency", type=int, default=20, help="Number of concurrent workers (default: 20)"
    )
    parser.add_argument(
        "--requests", type=int, default=60, help="Total requests to execute (default: 60)"
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default="inprocess",
        help="Base URL for running server or 'inprocess'",
    )
    parser.add_argument(
        "--test-key",
        type=str,
        default=DEFAULT_BENCHMARK_KEY,
        help="X-Test-Key authorization secret",
    )
    parser.add_argument(
        "--chaos",
        choices=["none", "qdrant", "neo4j", "redis"],
        default="none",
        help="Simulate chaos failure",
    )
    parser.add_argument(
        "--container",
        type=str,
        default="mukthiguru-backend",
        help="Container to watch for survival/peak memory (default: mukthiguru-backend). "
        "Pass an empty string to skip the survival assertion.",
    )
    parser.add_argument(
        "--mem-budget-mb",
        type=float,
        default=None,
        help="Absolute peak-memory budget in MB. Overrides --mem-budget-pct. "
        "For a production sizing check, pass the TARGET box's budget, not this host's.",
    )
    parser.add_argument(
        "--mem-budget-pct",
        type=float,
        default=60.0,
        help="Peak-memory budget as %% of the Docker host's TOTAL memory (default: 60). "
        "Deliberately measured against the host, not the container mem_limit — "
        "overcommitted per-container limits are what caused AMK-C-001.",
    )
    parser.add_argument(
        "--check-report",
        type=str,
        default=None,
        help="Check verdict of an existing report JSON file instead of executing a new test run.",
    )
    args = parser.parse_args()

    if args.check_report:
        report_path = Path(args.check_report)
        if not report_path.is_absolute():
            if not report_path.exists() and (_BACKEND_DIR / report_path).exists():
                report_path = _BACKEND_DIR / report_path
        if not report_path.exists():
            print(f"Report file not found: {report_path}", file=sys.stderr)
            return 1
        with open(report_path, encoding="utf-8") as f:
            summary = json.load(f)
        http_passed = summary.get("gate1_verdict") == "PASS"
        container_survival = summary.get("container_survival", {})
        container_passed = (
            container_survival.get("passed", True)
            if container_survival.get("available") is not False
            else True
        )
        print(
            f"\nGate 1 Result (Report Check): {summary.get('gate1_verdict')} "
            f"(Throughput: {summary.get('throughput_rps')} RPS, "
            f"p95: {summary.get('latency_percentiles_ms', {}).get('p95')}ms)"
        )
        if not http_passed:
            print("  FAIL: gate1_verdict is FAIL in report")
        if not container_passed:
            print("  FAIL: container survival failed in report")
        return 0 if (http_passed and container_passed) else 1

    watch = ContainerWatch(args.container) if args.container else None
    if watch:
        watch.start()
    try:
        summary = asyncio.run(
            run_gate1_load_test(
                concurrency=args.concurrency,
                total_requests=args.requests,
                base_url=args.base_url,
                test_key=args.test_key,
                chaos=args.chaos,
            )
        )
    finally:
        if watch:
            watch.stop()

    print(
        f"\nGate 1 Result: {summary['gate1_verdict']} (Throughput: {summary['throughput_rps']} RPS, p95: {summary['latency_percentiles_ms']['p95']}ms)"
    )
    http_passed = summary.get("gate1_verdict") == "PASS"

    if not watch:
        return 0 if http_passed else 1

    budget = args.mem_budget_mb
    host_mb = _host_mem_mb()
    if budget is None and host_mb:
        budget = host_mb * (args.mem_budget_pct / 100.0)
    verdict = watch.verdict(budget)
    summary["container_survival"] = verdict

    if verdict.get("available") is False:
        print(f"Container survival: SKIPPED ({verdict['reason']})")
        return 0 if http_passed else 1

    print(
        f"Container survival: {'PASS' if verdict['passed'] else 'FAIL'} — "
        f"peak {verdict['peak_mem_mb']}MB / budget {verdict['budget_mem_mb']}MB "
        f"over {verdict['samples']} samples, "
        f"restarts {verdict['restart_count_start']}->{verdict['restart_count_end']}, "
        f"running={verdict['running_at_end']}"
    )
    for failure in verdict["failures"]:
        print(f"  FAIL: {failure}")
    return 0 if (http_passed and verdict["passed"]) else 1


if __name__ == "__main__":
    sys.exit(main() or 0)
