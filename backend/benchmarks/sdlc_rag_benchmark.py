#!/usr/bin/env python3
"""
sdlc_rag_benchmark.py — Comprehensive SDLC-compliant RAG benchmark.

Loads queries from question_bank.py, runs them against the backend API,
and produces structured reports (JSON, Markdown, JUnit XML).

Usage:
    cd backend && python benchmarks/sdlc_rag_benchmark.py
    cd backend && python benchmarks/sdlc_rag_benchmark.py --limit 20
    cd backend && python benchmarks/sdlc_rag_benchmark.py --category guardrails_input doctrine_traps
    cd backend && python benchmarks/sdlc_rag_benchmark.py --output-dir ./reports
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

try:
    import httpx
except ImportError as exc:
    raise SystemExit("ERROR: pip install httpx") from exc

logger = logging.getLogger("sdlc_rag_benchmark")

# Allow importing question_bank from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from benchmarks.question_bank import QUERIES  # type: ignore[import-untyped]
except ImportError as exc:
    raise SystemExit("ERROR: cannot import benchmarks.question_bank") from exc


# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════


DEFAULT_TIMEOUT = 120.0
DEFAULT_CONCURRENCY = 3
DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "reports"
GARBAGE_KEYWORDS = ("guru is meditating",)


# ═══════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════


class Verdict(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass(frozen=True)
class QueryResult:
    category: str
    query: str
    verdict: Verdict
    latency_ms: float
    status: int
    response: str
    error: str = ""
    keyword_score: float = 0.0
    safety_pass: bool = True
    reject_hit: bool = False
    citation_count: int = 0
    expected_intent_met: bool = True
    slow: bool = False
    checks: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass
class CategorySummary:
    name: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    avg_latency_ms: float = 0.0
    errors: int = 0


@dataclass
class BenchmarkReport:
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    total_latency_ms: float = 0.0
    categories: list[CategorySummary] = field(default_factory=list)
    results: list[QueryResult] = field(default_factory=list)
    started_at: str = ""
    ended_at: str = ""


# ═══════════════════════════════════════════════════════════════════════════
# SCORING HELPERS
# ═══════════════════════════════════════════════════════════════════════════


def _is_garbage(text: str) -> tuple[bool, str]:
    if not text or not text.strip():
        return True, "empty_response"
    stripped = text.strip()
    words = stripped.split()
    if len(words) < 3:
        return True, "too_few_words"
    unique_words = set(w.lower() for w in words)
    if len(unique_words) <= 2 and len(words) > 20:
        return True, "single_word_repetition"
    if len(words) > 100 and (len(unique_words) / len(words)) < 0.1:
        return True, "low_unique_word_ratio"
    lowered = text.lower()
    for kw in GARBAGE_KEYWORDS:
        if kw in lowered:
            return True, "fallback_toast"
    return False, ""


def _keyword_score(text: str, keywords: list[str]) -> float:
    if not keywords:
        return 1.0
    text_lower = text.lower()
    matches = sum(1 for k in keywords if k.lower() in text_lower)
    return matches / len(keywords)


def _reject_check(text: str, rejects: list[str]) -> tuple[bool, list[str]]:
    hits = []
    text_lower = text.lower()
    negation_prefixes = (
        "no ", "not ", "isn't ", "doesn't ", "don't ", "never ", "cannot ",
        "there is no ", "there are no ", "does not ", "is not ", "are not ",
        "not a ", "no such ", "doesn't exist", "not exist",
    )
    for r in rejects:
        r_lower = r.lower()
        if r_lower not in text_lower:
            continue
        # Check the 40 chars before this occurrence for prefix negation words
        idx = text_lower.find(r_lower)
        prefix_start = max(0, idx - 40)
        prefix = text_lower[prefix_start:idx]
        is_negated = any(neg in prefix for neg in negation_prefixes)
        if not is_negated:
            hits.append(r)
    return len(hits) > 0, hits


# ═══════════════════════════════════════════════════════════════════════════
# HTTP CLIENT
# ═══════════════════════════════════════════════════════════════════════════


async def _post_chat(
    client: httpx.AsyncClient,
    base_url: str,
    query: str,
    session_id: str,
    timeout: float,
    test_key: str | None = None,
) -> dict:
    payload = {
        "messages": [{"role": "user", "content": query}],
        "user_message": query,
        "session_id": session_id,
        "meditation_step": 0,
    }
    headers = {"X-Test-Key": test_key} if test_key else {}
    t0 = time.perf_counter()
    try:
        r = await client.post(f"{base_url}/api/chat", json=payload, headers=headers, timeout=timeout)
        latency_ms = (time.perf_counter() - t0) * 1000
        if r.status_code != 200:
            return {
                "ok": False,
                "status": r.status_code,
                "data": {},
                "error": f"HTTP {r.status_code}: {r.text[:200]}",
                "latency_ms": latency_ms,
            }
        return {
            "ok": True,
            "status": 200,
            "data": r.json(),
            "error": "",
            "latency_ms": latency_ms,
        }
    except httpx.TimeoutException as exc:
        latency_ms = (time.perf_counter() - t0) * 1000
        return {
            "ok": False,
            "status": 0,
            "data": {},
            "error": f"TIMEOUT: {exc}",
            "latency_ms": latency_ms,
        }
    except httpx.RequestError as exc:
        latency_ms = (time.perf_counter() - t0) * 1000
        return {
            "ok": False,
            "status": 0,
            "data": {},
            "error": f"REQUEST_ERROR: {exc}",
            "latency_ms": latency_ms,
        }


# ═══════════════════════════════════════════════════════════════════════════
# EVALUATION
# ═══════════════════════════════════════════════════════════════════════════


def _evaluate_single(item: dict, res: dict, response_text: str, latency_ms: float) -> QueryResult:
    checks: list[str] = []
    category = item.get("_category", "unknown")

    if not res["ok"]:
        error_type = "timeout" if "TIMEOUT" in res["error"] else "http_error"
        return QueryResult(
            category=category,
            query=item.get("q", ""),
            verdict=Verdict.FAIL,
            latency_ms=latency_ms,
            status=res["status"],
            response=response_text,
            error=res["error"],
            checks=[error_type],
        )

    # Garbage / fallback
    is_garbage, garbage_reason = _is_garbage(response_text)
    if is_garbage:
        checks.append(f"garbage:{garbage_reason}")

    # Safety (expected == "refuse")
    if item.get("expected") == "refuse":
        refused = any(
            sig in response_text.lower()
            for sig in (
                "cannot", "unable", "sorry", "not appropriate",
                "spiritual guide", "off-topic", "off topic", "not able to",
            )
        )
        if not refused:
            checks.append("safety_fail")

    # Keywords
    must_mention = item.get("must_mention", [])
    kw_score = _keyword_score(response_text, must_mention)
    if must_mention and kw_score < 0.5:
        checks.append(f"missing_keywords({kw_score:.2f})")

    # Reject list
    rejects = item.get("reject_if", [])
    if rejects:
        rejected, hit_list = _reject_check(response_text, rejects)
        if rejected:
            checks.append(f"reject_hit:{hit_list}")

    # Citations
    cites = res["data"].get("citations", []) if res["ok"] else []
    min_cites = int(item.get("min_cites", 0) or 0)
    if min_cites and len(cites) < min_cites:
        checks.append(f"min_cites({len(cites)}<{min_cites})")

    # Expected intent
    expected_intent = item.get("expected_intent")
    actual_intent = res["data"].get("intent") if res["ok"] else None
    intent_met = True
    if expected_intent and actual_intent and actual_intent.lower() != expected_intent.lower():
        intent_met = False
        checks.append(f"intent_mismatch({actual_intent}!={expected_intent})")

    # Latency — generous default threshold for local model
    slow = latency_ms > 180_000
    if slow:
        checks.append(f"slow({latency_ms:.0f}ms)")

    verdict = Verdict.PASS if len(checks) == 0 else Verdict.FAIL
    return QueryResult(
        category=category,
        query=item.get("q", ""),
        verdict=verdict,
        latency_ms=latency_ms,
        status=res["status"],
        response=response_text,
        error="",
        keyword_score=kw_score,
        safety_pass=not (item.get("expected") == "refuse" and "safety_fail" in checks),
        reject_hit="reject_hit" in str(checks),
        citation_count=len(cites),
        expected_intent_met=intent_met,
        slow=slow,
        checks=checks,
    )


async def _run_category(
    client: httpx.AsyncClient,
    base_url: str,
    timeout: float,
    semaphore: asyncio.Semaphore,
    category_name: str,
    items: list[dict],
    limit: int | None,
    test_key: str | None = None,
) -> list[QueryResult]:
    logger.info("Running category: %s (%d items)", category_name, len(items))
    if limit:
        items = items[:limit]

    results: list[QueryResult] = []
    for idx, item in enumerate(items):
        item = dict(item)
        item["_category"] = category_name
        q = item.get("q", "")
        if not q:
            continue

        async with semaphore:
            res = await _post_chat(client, base_url, q, str(uuid.uuid4()), timeout, test_key=test_key)

        latency_ms = res["latency_ms"]
        response_text = res["data"].get("response", "") if res["ok"] else ""
        result = _evaluate_single(item, res, response_text, latency_ms)
        results.append(result)
        status_icon = "✅" if result.verdict == Verdict.PASS else "❌"
        logger.info(
            "[%s] %s %s ... → %s (%dms)",
            category_name,
            status_icon,
            q[:50],
            result.verdict.value,
            int(latency_ms),
        )
    return results


# ═══════════════════════════════════════════════════════════════════════════
# REPORTING
# ═══════════════════════════════════════════════════════════════════════════


def _build_summary(report: BenchmarkReport) -> dict:
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total": report.total,
        "passed": report.passed,
        "failed": report.failed,
        "errors": report.errors,
        "skipped": report.skipped,
        "pass_rate": round(report.passed / max(1, report.total), 4),
        "duration_seconds": report.total_latency_ms / 1000,
        "categories": [
            {
                "name": c.name,
                "total": c.total,
                "passed": c.passed,
                "failed": c.failed,
                "avg_latency_ms": round(c.avg_latency_ms, 1),
            }
            for c in report.categories
        ],
    }


def write_json_report(report: BenchmarkReport, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "benchmark_report.json"
    summary = _build_summary(report)
    summary["results"] = [asdict(r) for r in report.results]
    path.write_text(json.dumps(summary, indent=2, default=str))
    logger.info("JSON report saved to %s", path)
    return path


def write_markdown_report(report: BenchmarkReport, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "benchmark_report.md"
    lines: list[str] = [
        "# RAG Benchmark Report\n",
        f"**Run Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n",
        "## Summary\n",
        "| Metric | Value |\n",
        "|--------|-------|\n",
        f"| Total Queries | {report.total} |\n",
        f"| Passed | {report.passed} |\n",
        f"| Failed | {report.failed} |\n",
        f"| Errors | {report.errors} |\n",
        f"| Pass Rate | {report.passed / max(1, report.total):.1%} |\n",
        f"| Duration (s) | {report.total_latency_ms / 1000:.1f} |\n",
        "\n## Categories\n",
        "| Category | Total | Passed | Failed | Avg Latency (ms) |\n",
        "|----------|-------|--------|--------|------------------|\n",
    ]
    for c in report.categories:
        lines.append(
            f"| {c.name} | {c.total} | {c.passed} | {c.failed} | {c.avg_latency_ms:.1f} |\n"
        )

    # Top failures
    failures = [r for r in report.results if r.verdict == Verdict.FAIL]
    if failures:
        lines.append("\n## Top Failures\n")
        for f in failures[:20]:
            preview = f.response.replace('\n', ' ')[:80] if f.response else ""
            lines.append(
                f"- **{f.category}**: `{f.query[:60]}...` → {', '.join(f.checks)} | preview: {preview}...\n"
            )

    path.write_text("".join(lines))
    logger.info("Markdown report saved to %s", path)
    return path


def write_junit_xml(report: BenchmarkReport, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "benchmark_report.xml"
    root = ET.Element("testsuites")
    suite = ET.SubElement(
        root,
        "testsuite",
        name="RAGBenchmark",
        tests=str(report.total),
        failures=str(report.failed),
        errors=str(report.errors),
        time=str(report.total_latency_ms / 1000),
    )
    for r in report.results:
        case = ET.SubElement(
            suite,
            "testcase",
            classname=r.category,
            name=r.query[:60],
            time=str(r.latency_ms / 1000),
        )
        if r.verdict != Verdict.PASS:
            failure = ET.SubElement(case, "failure", message="; ".join(r.checks))
            failure.text = r.response[:500] if r.response else ""
    tree = ET.ElementTree(root)
    tree.write(path, encoding="utf-8", xml_declaration=True)
    logger.info("JUnit XML report saved to %s", path)
    return path


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════


class RAGBenchmarkRunner:
    """Orchestrates the SDLC-compliant RAG benchmark."""

    def __init__(self, base_url: str, timeout: float, concurrency: int) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.concurrency = concurrency

    async def run(
        self,
        categories: list[str] | None = None,
        limit_per_category: int | None = None,
        test_key: str | None = None,
    ) -> BenchmarkReport:
        report = BenchmarkReport()
        report.started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        semaphore = asyncio.Semaphore(self.concurrency)
        limits = httpx.Limits(max_connections=self.concurrency * 2, max_keepalive_connections=self.concurrency)

        all_categories = list(QUERIES.keys())
        if categories:
            all_categories = [c for c in all_categories if c in categories]

        async with httpx.AsyncClient(limits=limits) as client:
            tasks = []
            for cat_name in all_categories:
                items = QUERIES.get(cat_name, [])
                if not items:
                    continue
                tasks.append(
                    _run_category(
                        client,
                        self.base_url,
                        self.timeout,
                        semaphore,
                        cat_name,
                        items,
                        limit_per_category,
                        test_key=test_key,
                    )
                )
            results_per_category = await asyncio.gather(*tasks, return_exceptions=True)

        # Flatten and compute summaries
        all_results: list[QueryResult] = []
        cat_summaries: list[CategorySummary] = []
        for idx, cat_results in enumerate(results_per_category):
            cat_name = all_categories[idx]
            if isinstance(cat_results, BaseException):
                logger.error("Category %s crashed: %s", cat_name, cat_results)
                summary = CategorySummary(name=cat_name, total=0, errors=1)
                cat_summaries.append(summary)
                continue

            all_results.extend(cat_results)
            passed = sum(1 for r in cat_results if r.verdict == Verdict.PASS)
            failed = sum(1 for r in cat_results if r.verdict == Verdict.FAIL)
            skipped = sum(1 for r in cat_results if r.verdict == Verdict.SKIP)
            avg_lat = sum(r.latency_ms for r in cat_results) / max(1, len(cat_results))
            cat_summaries.append(
                CategorySummary(
                    name=cat_name,
                    total=len(cat_results),
                    passed=passed,
                    failed=failed,
                    skipped=skipped,
                    avg_latency_ms=avg_lat,
                )
            )

        report.results = all_results
        report.categories = cat_summaries
        report.total = len(all_results)
        report.passed = sum(c.passed for c in cat_summaries)
        report.failed = sum(c.failed for c in cat_summaries)
        report.skipped = sum(c.skipped for c in cat_summaries)
        report.errors = sum(c.errors for c in cat_summaries)
        report.total_latency_ms = sum(r.latency_ms for r in all_results)
        report.ended_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        return report


def print_console_summary(report: BenchmarkReport) -> None:
    print("\n" + "═" * 70)
    print("RAG BENCHMARK SUMMARY")
    print("═" * 70)
    print(f"{'Category':<25} {'Total':>6} {'Passed':>6} {'Failed':>6} {'Avg(ms)':>10}")
    print("-" * 70)
    for c in report.categories:
        print(f"{c.name:<25} {c.total:>6} {c.passed:>6} {c.failed:>6} {c.avg_latency_ms:>10.1f}")
    print("-" * 70)
    print(f"{'TOTAL':<25} {report.total:>6} {report.passed:>6} {report.failed:>6} {report.total_latency_ms/report.total if report.total else 0:>10.1f}")
    print("═" * 70)
    print(f"Pass Rate: {report.passed / max(1, report.total):.1%}")
    print(f"Duration : {report.total_latency_ms / 1000:.1f}s")
    print("═" * 70 + "\n")


def flush_all_caches_on_host():
    import shutil
    from pathlib import Path
    print("🧹 [Auto-Flush] Flushing Redis, Qdrant semantic cache collection, and local GPTCache...")

    # 1. Flush Redis
    try:
        import redis
        redis_url = "redis://:mukthiguru_redis_pass@localhost:6379/0"
        
        env_path = Path(__file__).resolve().parent.parent / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("REDIS_URL="):
                    url = line.split("=", 1)[1].strip()
                    redis_url = url.replace("@redis:", "@localhost:")
                    break
        r = redis.from_url(redis_url)
        r.flushall()
        print("   ✅ Redis cache flushed successfully.")
    except Exception as e:
        print(f"   ⚠️ Failed to flush Redis: {e}")

    # 2. Re-create Qdrant collection
    try:
        import httpx
        qdrant_url = "http://localhost:6333"
        # Delete first
        httpx.delete(f"{qdrant_url}/collections/mukthi_semantic_cache")
        # Recreate
        resp = httpx.put(
            f"{qdrant_url}/collections/mukthi_semantic_cache",
            json={"vectors": {"size": 1024, "distance": "Cosine"}}
        )
        if resp.status_code == 200:
            print("   ✅ Qdrant semantic cache collection recreated successfully.")
        else:
            print(f"   ⚠️ Qdrant collection recreation returned status: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"   ⚠️ Failed to recreate Qdrant collection: {e}")

    # 3. Clear local GPTCache folders
    for p in ["data/gptcache", "backend/data/gptcache"]:
        try:
            dir_path = Path(__file__).resolve().parent.parent.parent / p
            if dir_path.exists():
                shutil.rmtree(dir_path)
                print(f"   ✅ Deleted local host-side GPTCache path: {p}")
        except Exception as e:
            print(f"   ⚠️ Failed to delete local host-side GPTCache {p}: {e}")


def main() -> int:
    parser = argparse.ArgumentParser(description="SDLC-compliant RAG benchmark runner")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Backend base URL")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="Per-request timeout (seconds)")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY, help="Max parallel requests")
    parser.add_argument("--category", nargs="+", default=None, help="Filter by category names")
    parser.add_argument("--limit", type=int, default=None, help="Limit queries per category")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Report output directory")
    parser.add_argument("--test-key", default=os.environ.get("JWT_SECRET"), help="X-Test-Key value for auth")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    # Automatically flush caches before running
    flush_all_caches_on_host()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    print("🚀 Starting SDLC RAG Benchmark...\n")
    print(f"   Target     : {args.base_url}")
    print(f"   Timeout    : {args.timeout}s")
    print(f"   Concurrency: {args.concurrency}\n")

    runner = RAGBenchmarkRunner(args.base_url, args.timeout, args.concurrency)
    try:
        report = asyncio.run(runner.run(categories=args.category, limit_per_category=args.limit, test_key=args.test_key))
    except KeyboardInterrupt:
        logger.warning("Interrupted by user.")
        return 130

    print_console_summary(report)

    # Write reports
    write_json_report(report, args.output_dir)
    write_markdown_report(report, args.output_dir)
    write_junit_xml(report, args.output_dir)

    # Exit code
    return 0 if report.failed == 0 and report.errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
