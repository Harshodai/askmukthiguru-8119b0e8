#!/usr/bin/env python3
"""42-Question Latency, Answerability, and Zero-Hallucination Benchmark Suite.

Evaluates frozen29 (29 on-topic queries) + ooc13 (13 out-of-corpus queries)
against the first-person context-harness pipeline.
"""

from __future__ import annotations

import hashlib
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ENDPOINT = "http://localhost:8000/api/first-person/query"
PACE_SECONDS = 1.5
BACKOFF_429_SECONDS = 30.0


def query_first_person(query: str, max_retries: int = 3) -> dict[str, Any]:
    payload = json.dumps({"query": query, "cache_bypass": True}).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    for attempt in range(max_retries):
        try:
            t0 = time.monotonic()
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                wall_ms = (time.monotonic() - t0) * 1000.0
                data["_wall_ms"] = round(wall_ms, 2)
                return data
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries - 1:
                print(f"[429 Rate Limited] Backing off {BACKOFF_429_SECONDS}s...", file=sys.stderr)
                time.sleep(BACKOFF_429_SECONDS)
                continue
            return {
                "status": "http_error",
                "error": f"HTTP {e.code}: {e.reason}",
                "citations": [],
                "latency_ms": 0,
            }
        except Exception as e:
            return {"status": "client_error", "error": str(e), "citations": [], "latency_ms": 0}
    return {"status": "error", "error": "Max retries exceeded", "citations": [], "latency_ms": 0}


_SHELL_TEXTS = (
    "Related, not a direct answer. Two separate recordings, each quoted exactly:",
    "Two separate recordings, each quoted exactly:",
    "Related, not a direct answer:",
    "Related, not a direct answer",
)


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _strip_shell(text: str) -> str:
    """Remove the deterministic response template around the quoted teaching.

    Only known shell strings, blockquote markers and the wrapping quotes are
    removed; teacher words are never rewritten, so the comparison below stays an
    exact-text check rather than a similarity score.
    """
    cleaned = _normalize(text)
    for shell in _SHELL_TEXTS:
        cleaned = cleaned.replace(shell, " ")
    cleaned = cleaned.replace("> ", " ").replace(">", " ")
    cleaned = _normalize(cleaned)
    if cleaned.startswith('"') and cleaned.endswith('"') and len(cleaned) > 2:
        cleaned = _normalize(cleaned[1:-1])
    return cleaned


def _first_quoted_span(text: str) -> str | None:
    start = text.find('"')
    if start == -1:
        return None
    end = text.find('"', start + 1)
    if end == -1:
        return None
    return _normalize(text[start + 1 : end])


def verify_zero_hallucination(answer_text: str, citations: list[dict[str, Any]]) -> dict[str, Any]:
    """Verify that every substantive token in answer_text originates verbatim from citations.

    Zero hallucination requires BOTH an exact text match against the cited
    verbatim text (a single citation, or all citations concatenated in order,
    after removing the deterministic template shell) AND no answer word missing
    from that text. A merely non-empty word overlap is not evidence of anything,
    so it never passes.
    """
    import re
    from collections import Counter

    if not citations:
        return {"zero_hallucination": False, "reason": "No citations provided for served answer"}

    normalized_citations = [_normalize(c.get("verbatim_text", "")) for c in citations]
    joined_citations = _normalize(" ".join(t for t in normalized_citations if t))
    candidates = {joined_citations, *normalized_citations} - {""}

    stripped = _strip_shell(answer_text)
    exact_match = stripped in candidates
    if not exact_match:
        # Older layouts wrap the clip in quotes plus an em-dash attribution;
        # the quoted segment still has to equal the cited text exactly.
        quoted = _first_quoted_span(_normalize(answer_text))
        exact_match = bool(quoted) and quoted in candidates

    answer_counter = Counter(re.findall(r"\b\w+\b", stripped.lower()))
    corpus_counter = Counter(re.findall(r"\b\w+\b", joined_citations.lower()))
    unmatched_words = list((answer_counter - corpus_counter).elements())

    return {
        "zero_hallucination": bool(exact_match and not unmatched_words),
        "exact_match": exact_match,
        "method": "exact_text_plus_bag_of_words",
        "total_answer_words": sum(answer_counter.values()),
        "unmatched_words_count": len(unmatched_words),
        "unmatched_words": unmatched_words[:10],
    }


def verify_citation(cit: dict[str, Any]) -> dict[str, Any]:
    """Verify cryptographic integrity and field validity of a citation."""
    verbatim_text = cit.get("verbatim_text", "")
    expected_hash = hashlib.sha256(verbatim_text.encode("utf-8")).hexdigest()
    
    actual_hash = cit.get("transcript_hash") or cit.get("source_text_hash") or cit.get("video_transcript_hash")
    hash_valid = (actual_hash == expected_hash)
    
    has_video_id = bool(cit.get("video_id"))
    has_start_ms = "start_ms" in cit and cit["start_ms"] >= 0
    has_end_ms = "end_ms" in cit and cit["end_ms"] > cit.get("start_ms", 0)
    has_speaker = bool(cit.get("speaker"))
    is_verbatim = bool(cit.get("is_verbatim", False))
    
    all_valid = hash_valid and has_video_id and has_start_ms and has_end_ms and has_speaker and is_verbatim
    return {
        "citation_valid": all_valid,
        "hash_valid": hash_valid,
        "has_video_id": has_video_id,
        "has_start_ms": has_start_ms,
        "has_end_ms": has_end_ms,
        "has_speaker": has_speaker,
        "is_verbatim": is_verbatim,
    }


def main() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    eval_dir = base_dir / "evals" / "first_person"
    out_dir = base_dir / ".work" / "benchmark_42"
    out_dir.mkdir(parents=True, exist_ok=True)

    f29_path = eval_dir / "frozen29.jsonl"
    ooc13_path = eval_dir / "ooc13.jsonl"

    questions: list[dict[str, Any]] = []
    with open(f29_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                item["source_file"] = "frozen29.jsonl"
                questions.append(item)

    with open(ooc13_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                item["source_file"] = "ooc13.jsonl"
                questions.append(item)

    print(f"=== Starting 42-Question First-Person Benchmark Suite ===")
    print(f"Loaded {len(questions)} queries: 29 on-topic (frozen29) + 13 negative controls (ooc13)\n")

    results = []
    for i, q in enumerate(questions, 1):
        qid = q.get("id") or f"q_{i:02d}"
        q_text = q.get("question") or q.get("text")
        kind = q.get("kind", "unknown")
        src_file = q.get("source_file")

        res = query_first_person(q_text)
        status = res.get("status")
        abstain_reason = res.get("abstain_reason") or res.get("answerability") or "none"
        citations = res.get("citations") or []
        is_direct = res.get("is_direct_answer", False)
        timings = res.get("stage_timings") or {}
        tot_ms = timings.get("total_ms", res.get("latency_ms", 0.0))
        wall_ms = res.get("_wall_ms", tot_ms)
        ans_text = res.get("answer_text") or ""

        # Zero-hallucination verification
        zh_report = {"zero_hallucination": True, "exact_match": True}
        if status in ("success", "weak_match"):
            zh_report = verify_zero_hallucination(ans_text, citations)

        # Exact citation verification
        cit_reports = [verify_citation(c) for c in citations]
        all_cits_valid = all(cr["citation_valid"] for cr in cit_reports) if cit_reports else True

        record = {
            "index": i,
            "id": qid,
            "source_file": src_file,
            "kind": kind,
            "question": q_text,
            "status": status,
            "is_direct_answer": is_direct,
            "abstain_reason": abstain_reason,
            "n_citations": len(citations),
            "citations": citations,
            "citation_verification": cit_reports,
            "all_citations_valid": all_cits_valid,
            "zero_hallucination_report": zh_report,
            "zero_hallucination": zh_report.get("zero_hallucination", True),
            "audio_clips": len(res.get("audio_playback_clips") or []),
            "stage_timings": timings,
            "latency_ms": tot_ms,
            "wall_ms": wall_ms,
            "answer_preview": ans_text[:120].replace("\n", " "),
        }
        results.append(record)

        prov = citations[0].get("provenance_kind") if citations else "none"
        spk_v = citations[0].get("speaker_verified") if citations else False
        zh_flag = "ZH=PASS" if zh_report.get("zero_hallucination", True) else "ZH=FAIL"
        cit_flag = "CIT=PASS" if all_cits_valid else "CIT=FAIL"

        print(
            f"[{i:02d}/42] {qid:<6} ({kind:<13}): status={status:<10} direct={str(is_direct):<5} "
            f"cits={len(citations)} prov={prov:<16} {zh_flag} {cit_flag} lat={tot_ms:6.1f}ms wall={wall_ms:6.1f}ms"
        )
        time.sleep(PACE_SECONDS)

    # Save detailed per-query results
    detailed_path = out_dir / "benchmark_42_detailed_results.json"
    with open(detailed_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    # Compute aggregate metrics
    n_total = len(results)
    served = [r for r in results if r["status"] in ("success", "weak_match") and r["n_citations"] > 0]
    direct_served = [r for r in served if r["is_direct_answer"]]
    weak_served = [r for r in served if not r["is_direct_answer"]]
    abstained = [r for r in results if r["status"] == "abstained"]
    crisis = [r for r in results if r["status"] == "crisis_redirect"]
    errors = [r for r in results if r["status"] in ("error", "http_error", "client_error")]

    # Out of corpus leak check
    ooc_results = [r for r in results if r["kind"] == "out_of_corpus"]
    ooc_leaks = [r for r in ooc_results if r["status"] in ("success", "weak_match")]

    # Reasons breakdown
    reasons: dict[str, int] = {}
    for r in results:
        reason = r["abstain_reason"]
        reasons[reason] = reasons.get(reason, 0) + 1

    # Latencies
    all_latencies = [r["latency_ms"] for r in results if r["latency_ms"] > 0]
    all_wall = [r["wall_ms"] for r in results if r["wall_ms"] > 0]

    def calc_quantiles(vals: list[float]) -> dict[str, float]:
        if not vals:
            return {"p50": 0.0, "p90": 0.0, "p95": 0.0, "min": 0.0, "max": 0.0, "mean": 0.0}
        vals_sorted = sorted(vals)
        n = len(vals_sorted)
        p50 = statistics.median(vals_sorted)
        p90 = vals_sorted[int(0.90 * n)] if n >= 10 else vals_sorted[-1]
        p95 = vals_sorted[int(0.95 * n)] if n >= 20 else vals_sorted[-1]
        return {
            "p50": round(p50, 1),
            "p90": round(p90, 1),
            "p95": round(p95, 1),
            "min": round(min(vals_sorted), 1),
            "max": round(max(vals_sorted), 1),
            "mean": round(statistics.mean(vals_sorted), 1),
        }

    pipeline_latency = calc_quantiles(all_latencies)
    wall_latency = calc_quantiles(all_wall)

    # Served vs Abstained latencies
    served_latencies = [r["latency_ms"] for r in served if r["latency_ms"] > 0]
    abstained_latencies = [r["latency_ms"] for r in abstained if r["latency_ms"] > 0]
    served_latency_q = calc_quantiles(served_latencies)
    abstained_latency_q = calc_quantiles(abstained_latencies)

    # Per-stage timings median
    def stage_p50(key: str) -> float:
        vals = [r["stage_timings"].get(key, 0.0) for r in results if r["stage_timings"].get(key, 0.0) > 0]
        return round(statistics.median(vals), 1) if vals else 0.0

    # Zero-hallucination metrics
    zh_passed = sum(1 for r in served if r["zero_hallucination"])
    zh_rate = (zh_passed / len(served) * 100.0) if served else 100.0

    # Citation verification metrics
    cit_passed = sum(1 for r in served if r["all_citations_valid"])
    cit_rate = (cit_passed / len(served) * 100.0) if served else 100.0

    summary = {
        "suite": "42-Question First-Person Benchmark",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_queries": n_total,
        "served_count": len(served),
        "direct_answer_count": len(direct_served),
        "weak_match_count": len(weak_served),
        "abstained_count": len(abstained),
        "crisis_redirect_count": len(crisis),
        "error_count": len(errors),
        "ooc_total": len(ooc_results),
        "ooc_leaks_count": len(ooc_leaks),
        "reasons_breakdown": reasons,
        "pipeline_latency_ms": pipeline_latency,
        "wall_latency_ms": wall_latency,
        "served_latency_ms": served_latency_q,
        "abstained_latency_ms": abstained_latency_q,
        "stage_timings_p50_ms": {
            "answerability_ms": stage_p50("answerability_ms"),
            "retrieval_ms": stage_p50("retrieval_ms"),
            "integrity_ms": stage_p50("integrity_ms"),
            "rerank_ms": stage_p50("rerank_ms"),
            "scorer_ms": stage_p50("scorer_ms"),
            "assembly_ms": stage_p50("assembly_ms"),
            "total_ms": pipeline_latency["p50"],
        },
        "zero_hallucination": {
            "served_evaluated": len(served),
            "zero_hallucination_passed": zh_passed,
            "zero_hallucination_rate_pct": zh_rate,
            "hallucinated_tokens_count": 0 if zh_passed == len(served) else sum(r["zero_hallucination_report"].get("unmatched_words_count", 0) for r in served),
        },
        "citation_verification": {
            "served_evaluated": len(served),
            "citations_valid_count": cit_passed,
            "citation_validity_rate_pct": cit_rate,
            "hash_mismatches": sum(1 for r in served if not r["all_citations_valid"]),
        },
    }

    summary_path = out_dir / "benchmark_42_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 60)
    print("=== 42-QUESTION FIRST-PERSON BENCHMARK SUMMARY ===")
    print("=" * 60)
    print(f"Total Queries Evaluated:       {n_total}")
    print(f"Served (Total):                {len(served)} ({len(served)/n_total*100:.1f}%)")
    print(f"  - Direct Answers (Harness):  {len(direct_served)}")
    print(f"  - Related / Weak Match:      {len(weak_served)}")
    print(f"Abstained:                     {len(abstained)} ({len(abstained)/n_total*100:.1f}%)")
    print(f"Crisis Redirect:               {len(crisis)}")
    print(f"Errors:                        {len(errors)}")
    print(f"Out-of-Corpus Leak Count:      {len(ooc_leaks)} (Must be 0)")
    print("-" * 60)
    print("Abstain / Refusal Reasons Breakdown:")
    for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f"  - {reason:<32}: {count}")
    print("-" * 60)
    print("Latency Metrics (ms):")
    print(f"  Pipeline Latency : P50={pipeline_latency['p50']}ms | P90={pipeline_latency['p90']}ms | P95={pipeline_latency['p95']}ms (Mean={pipeline_latency['mean']}ms)")
    print(f"  Wall-Clock Latency: P50={wall_latency['p50']}ms | P90={wall_latency['p90']}ms | P95={wall_latency['p95']}ms (Mean={wall_latency['mean']}ms)")
    print(f"  Served Latency    : P50={served_latency_q['p50']}ms | P90={served_latency_q['p90']}ms | P95={served_latency_q['p95']}ms")
    print(f"  Abstained Latency : P50={abstained_latency_q['p50']}ms | P90={abstained_latency_q['p90']}ms | P95={abstained_latency_q['p95']}ms")
    print("-" * 60)
    print("Stage Timings P50 (ms):")
    for stage, t in summary["stage_timings_p50_ms"].items():
        print(f"  - {stage:<20}: {t:6.1f}ms")
    print("-" * 60)
    print("Zero-Hallucination & Integrity Verification:")
    print(f"  Zero-Hallucination Rate:     {zh_rate:.1f}% ({zh_passed}/{len(served)} served answers)")
    print(f"  Hallucinated Tokens Count:   {summary['zero_hallucination']['hallucinated_tokens_count']}")
    print(f"  Citation Validity Rate:      {cit_rate:.1f}% ({cit_passed}/{len(served)} served answers)")
    print(f"  Cryptographic Hash Matches:  {cit_passed}/{len(served)}")
    print("=" * 60)
    print(f"Artifacts saved to:\n  {summary_path}\n  {detailed_path}")


if __name__ == "__main__":
    main()
