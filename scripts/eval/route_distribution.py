"""Measure where answers actually end up: the route census over a fixed set.

`grounded_partial_evidence` is the excerpt-dump fallback — a real answer was
generated and then discarded. Its share is the single best proxy for "does this
system answer the question or hand you the sources?", and before this script it
could only be eyeballed one request at a time.

The question set is FIXED and checked in, so two runs are comparable. It spans
the shapes that behave differently in the pipeline: greeting, simple factual,
multi-concept/comparative, reflective, and practice-seeking.

Usage (backend up, from backend/):
    .venv/bin/python ../scripts/eval/route_distribution.py --out before.json
    # ... change something ...
    .venv/bin/python ../scripts/eval/route_distribution.py --out after.json --compare before.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.request
from collections import Counter
from pathlib import Path

BASE = "http://127.0.0.1:8000"

# Fixed set. Edit deliberately — changing it invalidates comparison with any
# previously recorded run.
QUESTIONS = [
    ("greeting", "hello"),
    ("simple", "What is the Beautiful State?"),
    ("simple", "What is Soul Sync?"),
    ("simple", "What does Deeksha mean in these teachings?"),
    ("comparative", "What is the difference between the Beautiful State and the Suffering State?"),
    ("comparative", "How does Soul Sync differ from Deeksha?"),
    ("comparative", "How do the teachings relate Oneness to the ending of suffering?"),
    ("reflective", "Why do I keep suffering even when my life looks fine?"),
    ("reflective", "What do the teachings say about resentment that will not lift?"),
    ("practice", "How should someone with very little time begin a practice?"),
    ("practice", "What is taught about practising when the mind will not settle?"),
    ("factual", "What is said about the role of the breath in these teachings?"),
]

# Routes that mean "we did not deliver a synthesized answer".
FALLBACK_ROUTES = {
    "grounded_partial_evidence",
    "grounded_partial_fallback",
    "no_context_short_circuit",
    "limited_comparison_fallback",
    "handle_fallback",
    "fallback",
}


def _req(path: str, payload=None, tok: str | None = None, timeout: int = 400):
    headers = {"Content-Type": "application/json"}
    if tok:
        headers["X-Session-Id"] = tok
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def ask(question: str, max_wait: int = 400) -> dict:
    tok = _req("/api/auth/anon-session", {})["token"]
    t0 = time.time()
    d = _req("/api/chat", {"messages": [], "user_message": question, "session_id": tok}, tok)
    if d.get("job_id"):
        while time.time() - t0 < max_wait:
            time.sleep(3)
            j = _req(f"/api/jobs/{d['job_id']}", None, tok)
            if j.get("status") in ("completed", "succeeded", "done", "failed", "error"):
                d = j.get("result") or j
                break
    d["_elapsed_s"] = round(time.time() - t0, 1)
    return d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="route_distribution.json")
    ap.add_argument("--compare", help="A previous run's JSON, to diff against.")
    ap.add_argument("--skip-cached", action="store_true",
                    help="Drop cache hits from the shares — they reflect an older run's routing.")
    args = ap.parse_args()

    rows = []
    for shape, q in QUESTIONS:
        d = ask(q)
        row = {
            "shape": shape,
            "question": q,
            "route": d.get("route_decision"),
            "grounding": d.get("grounding_state"),
            "faithfulness": d.get("faithfulness_score"),
            "cache_hit": bool(d.get("cache_hit")),
            "citations": len(d.get("citations") or []),
            "elapsed_s": d.get("_elapsed_s"),
        }
        rows.append(row)
        print(f"  {row['elapsed_s']:6.1f}s {str(row['route']):28s} {str(row['grounding']):10s} "
              f"cache={row['cache_hit']} {q[:48]}", flush=True)

    scored = [r for r in rows if not (args.skip_cached and r["cache_hit"])]
    n = len(scored) or 1
    fallbacks = [r for r in scored if (r["route"] or "") in FALLBACK_ROUTES]
    lat = sorted(r["elapsed_s"] for r in scored)
    # `answered_share` is the trustworthy quality signal: a non-fallback route
    # that shipped at least one citation.
    #
    # `grounded_share` is reported but NOT to be used for A/B judgement.
    # `grounding_state` is derived by app/grounding.py, which branches on
    # `verification["method"]` — and 17 of the 20 verification dicts in
    # rag/nodes/verification.py never set that key, so most real outcomes fall
    # through to the conservative "abstained" default. Measured 2026-09-13: a
    # tier2_simple answer with 1 citation, 10 scored claims and faithfulness 1.0
    # was labelled `abstained`. Until every verification path stamps a method,
    # this number moves for reasons unrelated to answer quality.
    answered = [
        r for r in scored
        if (r["route"] or "") not in FALLBACK_ROUTES
        and (r["route"] or "") != "instant_greeting"
        and r["citations"] > 0
    ]
    report = {
        "n": len(scored),
        "fallback_share": round(len(fallbacks) / n, 4),
        "answered_share": round(len(answered) / n, 4),
        "grounded_share_UNRELIABLE": round(
            sum(1 for r in scored if r["grounding"] == "grounded") / n, 4
        ),
        "abstained": sum(1 for r in scored if r["grounding"] == "abstained"),
        "cache_hits": sum(1 for r in rows if r["cache_hit"]),
        "median_latency_s": statistics.median(lat) if lat else None,
        "routes": dict(Counter(r["route"] for r in scored)),
        "fallback_by_shape": dict(Counter(r["shape"] for r in fallbacks)),
        "rows": rows,
    }
    Path(args.out).write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=2))

    if args.compare:
        prev = json.loads(Path(args.compare).read_text())
        print("\n--- vs", args.compare, "---")
        for key in ("fallback_share", "answered_share", "median_latency_s"):
            before, after = prev.get(key), report.get(key)
            if isinstance(before, (int, float)) and isinstance(after, (int, float)):
                print(f"  {key}: {before} -> {after}  ({after - before:+.4f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
