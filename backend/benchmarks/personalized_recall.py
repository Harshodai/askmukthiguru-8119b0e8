"""Personalized recall benchmark — handoff Track B exit gate (B8).

20 queries of the form "what did I tell you about X" against a seeded fake
memory store, exercising the real `memory_relevance_gate` /
`inject_memory_context` node contract from rag.memory. Reports:

  - recall: fraction of queries whose expected fact lands in memory_context
  - p95 latency delta (memory ON vs OFF) in ms
  - avg token delta per turn (chars // 4 estimate)
  - no-regression proxy: skip-intent turns must bypass the service entirely
    (zero fetch calls) and leave state keys untouched

Exit gates (handoff §B8): recall >= 80%, p95 delta <= 200ms, token delta
<= 900 tokens/turn avg, skip correctness == 100%.

Fully offline: FakeMemoryService (keyword-overlap scoring), no Supabase, no
Qdrant, no LLM calls.

Usage:
    cd backend && .venv/bin/python benchmarks/personalized_recall.py --smoke
    cd backend && .venv/bin/python benchmarks/personalized_recall.py --out /tmp/recall.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.memory import inject_memory_context, memory_relevance_gate  # noqa: E402

USER_ID = str(uuid.uuid4())

# Boilerplate words stripped before scoring (the "what did I tell you" shell).
_BOILERPLATE = frozenset(
    "what did tell you i me my about recall remember know do does is are the a an".split()
)

# (kind, text) seed rows. Query keywords (below) were chosen so each query's
# distinctive words appear ONLY in its target row.
_CORE_ROWS = [
    "User lives in Pune.",
    "User works as a school teacher.",
    "User prefers Telugu; language for discourses.",
    "User follows a vegetarian diet since childhood.",
    "User asks healing prayers for mother.",
    "User speaks Tamil at home.",
    "User runs a small bakery business.",
    "User has a peanut allergy.",
]

_EPISODIC_ROWS = [
    "User keeps a daily meditation practice.",
    "User brings a three-year vipassana background.",
    "User holds Krishna as favorite deity.",
    "User visited Ekam in March with family.",
    "User feels anger toward a sibling.",
    "User set a Serene Mind goal: finish the 21-day course.",
    "User follows a morning sadhana routine at 5am.",
    "User made a donation to the festival fund.",
    "Chanting brings the user peace: Om Namah Shivaya.",
    "User grieves father lost last year.",
    "User keeps nightly reading: Bhagavad Gita.",
    "User plans a Tirupati pilgrimage in December.",
]

_SUMMARY_ROWS = [
    {"summary": "Long talk on Ekam teachings and stillness.", "topics": ["Ekam"]},
    {"summary": "Guided meditation troubleshooting session.", "topics": ["meditation"]},
]

# (query, expected substring of memory_context)
RECALL_QUERIES: list[tuple[str, str]] = [
    ("What did you record about where I live?", "Pune"),
    ("What did I tell you about my work?", "school teacher"),
    ("What did I tell you about my meditation practice?", "meditation practice"),
    ("What is my vipassana background?", "three-year"),
    ("Who is my favorite deity?", "Krishna"),
    ("What language do I prefer for discourses?", "Telugu"),
    ("When did I visit Ekam?", "Ekam"),
    ("What did I tell you about my anger?", "anger"),
    ("What did I tell you about my diet?", "vegetarian"),
    ("What is my Serene Mind goal?", "21-day"),
    ("What did I tell you about my mother?", "mother"),
    ("What did I tell you about my morning routine?", "5am"),
    ("What did I tell you about my donation?", "donation"),
    ("Which languages do I speak at home?", "Tamil"),
    ("What brings me peace?", "Om Namah Shivaya"),
    ("What did I tell you about my business?", "bakery"),
    ("What did I tell you about my father?", "father"),
    ("What did I tell you about my nightly reading?", "Bhagavad Gita"),
    ("What did I tell you about my allergy?", "peanut"),
    ("What did I tell you about my pilgrimage plans?", "Tirupati"),
]

# Skip-intent turns: the gate must bypass the service (no-regression proxy).
SKIP_TURNS: list[tuple[str, str]] = [
    ("hi", "CASUAL"),
    ("Namaste!", "CASUAL"),
    ("What is Deeksha?", "doctrine_lookup"),
    ("Tell me about the Four Sacred Secrets.", "doctrine_lookup"),
    ("Thank you, Guru.", "CASUAL"),
]


def _keywords(text: str) -> list[str]:
    words = [w.strip(".,!?;:'\"()").lower() for w in text.split()]
    return [w for w in words if len(w) >= 4 and w not in _BOILERPLATE]


def _overlap_score(query_words: list[str], row_text: str) -> float:
    """Fraction of query keywords matching the row (substring, either way)."""
    if not query_words:
        return 0.0
    row = row_text.lower()
    hits = 0
    for kw in query_words:
        if kw in row:
            hits += 1
            continue
        if any(len(w) >= 4 and (w in kw or kw in w) for w in row.split()):
            hits += 1
    return hits / len(query_words)


class FakeMemoryService:
    """Deterministic MemoryService read-surface over the seed rows."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def get_core(self, user_id):
        self.calls.append(("get_core", user_id))
        return [{"content": t} for t in _CORE_ROWS]

    async def search_semantic(self, user_id, query, limit=5, min_similarity=0.6):
        self.calls.append(("search_semantic", user_id, query, limit))
        scored = sorted(
            ((_overlap_score(_keywords(query), t), t) for t in _CORE_ROWS + _EPISODIC_ROWS),
            key=lambda pair: pair[0],
            reverse=True,
        )
        return [{"claim": t, "confidence": 0.8} for s, t in scored if s >= 0.3][:limit]

    async def recent_summaries(self, user_id, limit=3):
        self.calls.append(("recent_summaries", user_id, limit))
        return _SUMMARY_ROWS[:limit]


def _p(percentile: float, values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(percentile / 100 * len(ordered)))]


async def _run(queries, skip_turns):
    svc = FakeMemoryService()
    detail = []
    on_ms: list[float] = []
    off_ms: list[float] = []
    token_delta: list[int] = []
    hits = 0

    for question, expected in queries:
        state = {
            "question": question,
            "intent": "QUERY",
            "user_id": USER_ID,
            "detected_language": "en",
            "memory_context": "",
        }
        assert memory_relevance_gate(state) == "inject", question

        t0 = time.perf_counter()
        out = await inject_memory_context(state, memory_service=svc)
        on_ms.append((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        _ = {"memory_context": ""}  # OFF baseline: no fetch, empty context
        off_ms.append((time.perf_counter() - t0) * 1000)

        ctx = out.get("memory_context", "")
        hit = expected.lower() in ctx.lower()
        hits += hit
        token_delta.append(len(ctx) // 4)
        detail.append({"query": question, "expected": expected, "hit": hit})

    skip_ok = 0
    for question, intent in skip_turns:
        before = len(svc.calls)
        state = {
            "question": question,
            "intent": intent,
            "user_id": USER_ID,
            "detected_language": "en",
            "memory_context": "",
        }
        gate = memory_relevance_gate(state)
        out = await inject_memory_context(state, memory_service=svc)
        ok = gate == "skip" and "memory_context" not in out and len(svc.calls) == before
        skip_ok += ok
        detail.append({"query": question, "intent": intent, "skip_ok": bool(ok)})

    n = len(queries)
    return {
        "n_queries": n,
        "n_skip_turns": len(skip_turns),
        "recall": round(hits / n, 4) if n else 0.0,
        "hits": hits,
        "p95_on_ms": round(_p(95, on_ms), 2),
        "p95_off_ms": round(_p(95, off_ms), 2),
        "p95_delta_ms": round(_p(95, on_ms) - _p(95, off_ms), 2),
        "avg_token_delta": round(sum(token_delta) / len(token_delta), 1) if token_delta else 0.0,
        "skip_correctness": round(skip_ok / len(skip_turns), 4) if skip_turns else 1.0,
        "detail": detail,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--smoke", action="store_true", help="5 queries + 2 skips, fast CI pass")
    p.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent / "reports" / "personalized_recall.json",
    )
    args = p.parse_args(argv)

    queries = RECALL_QUERIES[:5] if args.smoke else RECALL_QUERIES
    skip_turns = SKIP_TURNS[:2] if args.smoke else SKIP_TURNS

    report = asyncio.run(_run(queries, skip_turns))

    gates = {
        "recall_ge_80": report["recall"] >= 0.80,
        "p95_delta_le_200ms": report["p95_delta_ms"] <= 200.0,
        "token_delta_le_900": report["avg_token_delta"] <= 900.0,
        "skip_correctness_100": report["skip_correctness"] == 1.0,
    }
    report["gates"] = gates
    report["pass"] = all(gates.values())

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2))
    print(f"recall={report['recall']} ({report['hits']}/{report['n_queries']})")
    print(
        f"p95 ON={report['p95_on_ms']}ms OFF={report['p95_off_ms']}ms delta={report['p95_delta_ms']}ms"
    )
    print(f"avg token delta={report['avg_token_delta']}/turn skip={report['skip_correctness']}")
    print(f"gates={gates} -> {'PASS' if report['pass'] else 'FAIL'}")
    print(f"Wrote {args.out}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
