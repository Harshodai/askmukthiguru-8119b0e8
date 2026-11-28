#!/usr/bin/env python3
"""Local OpenRouter stub for capacity tests: canned replies, realistic latency.

Point a LOCAL backend at it with ``OPENROUTER_BASE_URL=http://127.0.0.1:9099/v1``.
It answers ``POST /v1/chat/completions`` only, never calls out, and refuses to bind
anywhere but loopback. ``GET /stats`` returns calls per (model, kind) so a load run can
report LLM calls per chat. No real key is needed and nothing is billed.

Latency is a per-model lognormal (median and sigma below, seconds), set from measured
OpenRouter round trips on the live path: Haiku scorer/gate ~1.3 s, Llama-8B ~0.5 s.
Override with ``--haiku-s`` / ``--fast-s`` / ``--sigma``.

Reply policy (so the first-person lane runs its real code, not a short circuit):
  * answerability gate -> "YES"
  * relevance scorer   -> N scores, ``--serve-ratio`` of questions score >= 2 (serve),
    the rest score 1 (abstain); chosen by hash of the question so it is repeatable
  * anything else      -> a short canned sentence (HyDE / classify / reflection)
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import random
import re
import sys
import time
from collections import Counter

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()
STATS: Counter[str] = Counter()
CFG = {
    "haiku_s": 1.3,
    "fast_s": 0.5,
    "other_s": 1.0,
    "sigma": 0.35,
    "serve_ratio": 0.7,
    "supabase_s": 0.06,
}
STARTED = time.time()


def _kind(system: str, response_format: object) -> str:
    low = system.lower()
    if "question classifier" in low:
        return "answerability"
    if isinstance(response_format, dict) and "relevance_scores" in json.dumps(response_format):
        return "relevance_json"
    if "comma-separated integers" in low:
        return "relevance_csv"
    if "judge whether a verbatim teaching clip" in low:
        return "sufficiency"
    return "other"


def _scores(user: str) -> list[int]:
    m = re.search(r"\((\d+) total", user)
    n = int(m.group(1)) if m else max(1, len(re.findall(r"(?m)^\[\d+\] ", user)))
    q = re.search(r"Question: (.*)", user)
    h = int(hashlib.sha256((q.group(1) if q else user).encode()).hexdigest(), 16) % 1000
    serve = h < CFG["serve_ratio"] * 1000
    return [3 if (serve and i == 0) else (2 if serve and i == 1 else 1) for i in range(n)]


def _latency(model: str) -> float:
    base = (
        CFG["haiku_s"]
        if "haiku" in model or "anthropic" in model
        else CFG["fast_s"]
        if "llama" in model
        else CFG["other_s"]
    )
    return base * random.lognormvariate(0.0, CFG["sigma"])


@app.get("/stats")
async def stats() -> dict:
    return {"uptime_s": round(time.time() - STARTED, 1), "calls": dict(STATS)}


@app.post("/v1/chat/completions")
async def completions(request: Request) -> JSONResponse:
    body = await request.json()
    model = str(body.get("model", ""))
    msgs = body.get("messages") or []
    system = next((str(m.get("content", "")) for m in msgs if m.get("role") == "system"), "")
    user = next((str(m.get("content", "")) for m in reversed(msgs) if m.get("role") == "user"), "")
    kind = _kind(system, body.get("response_format"))
    STATS[f"{model}|{kind}"] += 1
    STATS["total"] += 1
    await asyncio.sleep(_latency(model))
    if kind == "answerability":
        text = "YES"
    elif kind == "relevance_json":
        text = json.dumps({"scores": _scores(user)})
    elif kind == "relevance_csv":
        text = ",".join(str(s) for s in _scores(user))
    elif kind == "sufficiency":
        text = "SUFFICIENT"
    else:
        text = "Inner peace grows when attention rests in the present moment."
    return JSONResponse(
        {
            "id": "stub",
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": max(1, len(system + user) // 4),
                "completion_tokens": 8,
                "cost": 0.0,
            },
        }
    )


@app.api_route("/rest/v1/{path:path}", methods=["GET", "POST", "PATCH", "PUT", "DELETE", "HEAD"])
async def supabase_rest_stub(path: str, request: Request) -> JSONResponse:
    """Fast empty PostgREST answer so a local backend never writes to (or waits on) a real DB.

    Set SUPABASE_URL to this server. ~60 ms latency stands in for a hosted Supabase round trip.
    """
    STATS["supabase_rest"] += 1
    await asyncio.sleep(CFG["supabase_s"] * random.lognormvariate(0.0, CFG["sigma"]))
    return JSONResponse(
        [] if request.method == "GET" else [{}], status_code=200 if request.method == "GET" else 201
    )


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9099)
    ap.add_argument("--haiku-s", type=float, default=CFG["haiku_s"])
    ap.add_argument("--fast-s", type=float, default=CFG["fast_s"])
    ap.add_argument("--sigma", type=float, default=CFG["sigma"])
    ap.add_argument("--serve-ratio", type=float, default=CFG["serve_ratio"])
    a = ap.parse_args()
    if a.host not in {"127.0.0.1", "localhost", "::1"}:
        sys.exit("refusing to bind a non-loopback address")
    CFG.update(haiku_s=a.haiku_s, fast_s=a.fast_s, sigma=a.sigma, serve_ratio=a.serve_ratio)
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
