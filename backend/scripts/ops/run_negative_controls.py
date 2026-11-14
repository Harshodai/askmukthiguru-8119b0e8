#!/usr/bin/env python3
"""Run the first-person negative-control set through the judge decision (no serving path).

Each control pairs a question with a clip that answers a DIFFERENT question, so the right
outcome is abstain. The runner makes the same decision the harness makes on that single clip:
the per-clip judge, then (with --comparative) the comparative call. Clip text is resolved
read-only from the graded rows file the builder used (matched by sha256[:12]); it is held in
memory only and never written. Output carries control ids and clip hashes, never text.

Spend: without --dry-run it makes paid calls, so it refuses unless --i-have-logged-the-spend
(the project keeps a spend log: docs/operations/SPEND_LOG_2026.md).

    cd backend && .venv/bin/python -m scripts.ops.run_negative_controls --dry-run --comparative
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Optional

from scripts.ops.graded_run_preflight import REPO

CONTROLS = REPO / "evals" / "first_person" / "negative_controls.jsonl"
DEFAULT_ROWS = (
    Path.home() / "mukthiguru_attribution_data" / "graded_runs" / "20261112-graded-6" / "rows.jsonl"
)
SET_NAME = "frozen116"  # same set the builder drew clips from

# (question, clip_text) -> index 0 (serve) | None (abstain) | INDETERMINATE (-1)
Decide = Callable[[str, str], Awaitable[Optional[int]]]


def load_controls(path: Path = CONTROLS) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def clip_texts_by_hash(rows_path: Path) -> dict[str, str]:
    """sha256[:12] -> clip text, exactly as build_negative_controls._clip_pool hashes it."""
    out: dict[str, str] = {}
    for line in rows_path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line) if line.strip() else {}
        if row.get("set") != SET_NAME or not row.get("citations"):
            continue
        text = (row["citations"][0].get("text") or "").strip()
        if text:
            out[hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]] = text
    return out


def plan(n_pairs: int, comparative: bool, cost_per_call: float) -> dict[str, Any]:
    """Worst case: every pair reaches the comparative call too."""
    calls = n_pairs * (2 if comparative else 1)
    return {
        "pairs": n_pairs,
        "max_calls": calls,
        "worst_case_reservation_usd": round(calls * cost_per_call, 4),
    }


async def run_pairs(
    controls: list[dict[str, Any]],
    texts: dict[str, str],
    judge: Decide,
    comparative: Optional[Decide] = None,
) -> dict[str, Any]:
    """Verdict per control id: 'abstain', 'serve' or 'indeterminate'. Missing clip text raises."""
    verdicts: dict[str, dict[str, str]] = {}
    for c in controls:
        text = texts.get(c["clip_sha256_12"])
        if text is None:
            raise KeyError(f"clip {c['clip_sha256_12']} for {c['control_id']} not in rows file")
        pick = await judge(c["question"], text)
        if pick == 0 and comparative is not None:
            pick = await comparative(c["question"], text)
        verdicts[c["control_id"]] = {
            "clip_sha256_12": c["clip_sha256_12"],
            "verdict": "serve" if pick == 0 else ("abstain" if pick is None else "indeterminate"),
        }
    counts = {
        k: sum(v["verdict"] == k for v in verdicts.values())
        for k in ("abstain", "serve", "indeterminate")
    }
    n = len(verdicts)
    return {
        "verdicts": verdicts,
        "counts": counts,
        "n": n,
        "abstain_rate": round(counts["abstain"] / n, 4) if n else 0.0,
    }


def _real_deciders(comparative: bool) -> tuple[Decide, Optional[Decide]]:
    from app.config import settings
    from app.dependencies import _create_llm_service
    from services import first_person_judge as fj

    llm = _create_llm_service()
    minimum = int(settings.first_person_relevance_min_score)
    timeout_s = float(settings.first_person_relevance_timeout_s)

    async def judge(q: str, text: str) -> Optional[int]:
        return await fj.judge_select_async(
            q, [{"verbatim_text": text}], llm, minimum=minimum, timeout_s=timeout_s
        )

    async def cmp_(q: str, text: str) -> Optional[int]:
        return await fj.comparative_select_async(
            q, [{"verbatim_text": text}], llm, timeout_s=timeout_s
        )

    return judge, (cmp_ if comparative else None)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--controls", type=Path, default=CONTROLS)
    ap.add_argument("--rows", type=Path, default=DEFAULT_ROWS)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--comparative", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--i-have-logged-the-spend", action="store_true")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)

    from app.config import settings

    controls = load_controls(args.controls)[: args.limit]
    info = plan(len(controls), args.comparative, float(settings.openrouter_max_request_cost_usd))
    if args.dry_run:
        print(json.dumps(info))
        return 0
    if not args.i_have_logged_the_spend:
        print(
            "refusing: paid calls need --i-have-logged-the-spend (or use --dry-run)",
            file=sys.stderr,
        )
        return 2
    judge, cmp_ = _real_deciders(args.comparative)
    result = asyncio.run(run_pairs(controls, clip_texts_by_hash(args.rows), judge, cmp_))
    result["plan"] = info
    result["comparative"] = args.comparative
    text = json.dumps(result, indent=2)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
