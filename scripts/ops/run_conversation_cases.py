#!/usr/bin/env python3
"""Drive the draft conversation cases through `/api/chat`, turn by turn (open-work row T-E7).

The 24 rows in ``evals/first_person/conversation_cases_draft.jsonl`` are AI-authored DRAFTS
(``status: draft_needs_owner_review``). Until now nothing consumed them, so they changed no
measurement. This runner measures what the system actually did on each turn — route, grounding
state, citations, latency — and writes it next to the run.

It never turns a draft into a label
-----------------------------------
* Output rows carry ``row_status: draft_needs_owner_review`` and ``authored_by`` from the input.
* A case's ``expected`` string is copied verbatim into the record and **never** scored as a pass or
  a fail: only a human can say whether the observed behaviour is acceptable.
* The one mechanical signal is ``turn2_citation_overlap``: did turn 2 cite any video turn 1 cited?
  A resolved follow-up usually retrieves near the first turn's topic, while an unresolved one
  searches a bare "why does that happen?". It is a hint, not a verdict, and it is recorded as such.

Spend and safety
----------------
Every turn is a real chat request and therefore may spend model money, so the default is a dry run.
Executing needs ``--execute --i-have-logged-the-spend`` (the project keeps
``docs/operations/SPEND_LOG_2026.md``). One anonymous session is used per case and the runner
respects the 429 retry-after header instead of hammering the limiter.

    # what would run (no network)
    python3 scripts/ops/run_conversation_cases.py --dry-run
    # execute and write the run
    python3 scripts/ops/run_conversation_cases.py --execute --i-have-logged-the-spend --run-id <id>

Exit status is the contract: 0 completed, 2 refused or unusable input.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
CASES = REPO / "evals" / "first_person" / "conversation_cases_draft.jsonl"
DEFAULT_OUT = Path.home() / "mukthiguru_attribution_data" / "conversation_runs"
VIDEO_ID_RE = re.compile(r"(?:v=|youtu\.be/|embed/)([A-Za-z0-9_-]{11})")


# ── input ────────────────────────────────────────────────────────────────────
def load_cases(path: Path = CASES) -> list[dict[str, Any]]:
    """Every case row. A `_header` row is documentation, not a case, and is dropped."""
    cases: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("_header"):
            continue
        cases.append(row)
    return cases


def case_turns(case: dict[str, Any]) -> list[str]:
    """A multi-turn case carries `turns`; a single-turn case carries one `question`."""
    turns = case.get("turns")
    if turns:
        return [str(t) for t in turns]
    question = case.get("question")
    return [str(question)] if question else []


def plan(cases: list[dict[str, Any]], limit: int | None) -> dict[str, Any]:
    """Turns to send, and the per-case turn budget the anonymous limiter allows."""
    chosen = cases[:limit] if limit else cases
    return {
        "cases": len(chosen),
        "turns": sum(len(case_turns(c)) for c in chosen),
        "categories": sorted({c.get("category", "?") for c in chosen}),
        "cases_with_history_requirement": sum(1 for c in chosen if c.get("turn2_must_use_history")),
    }


# ── wire ─────────────────────────────────────────────────────────────────────
def _video_ids(citations: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for c in citations or []:
        vid = c.get("video_id") or c.get("videoId")
        if not vid:
            url = str(c.get("url") or c.get("source_url") or "")
            match = VIDEO_ID_RE.search(url)
            vid = match.group(1) if match else None
        if vid and vid not in out:
            out.append(str(vid))
    return out


def build_turn_record(
    case: dict[str, Any], turn_index: int, http: int, result: dict[str, Any], wall_seconds: float
) -> dict[str, Any]:
    """One turn, described without storing the seeker's or the teacher's text.

    Citation text and the answer body are deliberately absent: the run is a routing measurement,
    and the negative-control runner set the same precedent (ids and hashes only).
    """
    meta = result.get("route_metadata") or {}
    citations = result.get("citations") or []
    return {
        "case_id": case.get("id"),
        "category": case.get("category"),
        "turn": turn_index + 1,
        "http": http,
        "route": result.get("route_decision"),
        "grounding": result.get("grounding_state"),
        "fp_served": bool(meta.get("fp_served")),
        "abstain_cause": meta.get("abstain_cause"),
        "abstain_reason": meta.get("abstain_reason") or meta.get("reason"),
        "n_citations": len(citations),
        "citation_videos": _video_ids(citations),
        "latency_ms": result.get("latency_ms"),
        "cache_hit": result.get("cache_hit"),
        "notices": result.get("safety_notices") or [],
        "wall_seconds": round(wall_seconds, 2),
    }


def overlap_with_previous(turns: list[dict[str, Any]], index: int) -> float | None:
    """Share of this turn's cited videos that the previous turn also cited (None if uncited).

    A hint, never a verdict: two different questions can legitimately share a clip, and a resolved
    follow-up can still abstain.
    """
    if index < 1:
        return None
    now = set(turns[index].get("citation_videos") or [])
    before = set(turns[index - 1].get("citation_videos") or [])
    if not now:
        return None
    return round(len(now & before) / len(now), 3)


def summarize(records: list[dict[str, Any]], plan_info: dict[str, Any]) -> dict[str, Any]:
    """Counts a human can read without re-deriving them from the rows."""
    groundings: dict[str, int] = {}
    for r in records:
        key = str(r.get("grounding") or "none")
        groundings[key] = groundings.get(key, 0) + 1
    latencies = sorted(
        int(r["latency_ms"]) for r in records if isinstance(r.get("latency_ms"), (int, float))
    )
    p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))] if latencies else None
    history_rows = [r for r in records if r.get("turn") == 2]
    return {
        **plan_info,
        "turns_recorded": len(records),
        "served_turns": sum(1 for r in records if r.get("fp_served")),
        "grounding_counts": dict(sorted(groundings.items())),
        "p95_latency_ms": p95,
        "turn2_cited_anything": sum(1 for r in history_rows if r.get("citation_videos")),
        "turn2_shared_a_video_with_turn1": sum(
            1 for r in history_rows if (r.get("turn2_citation_overlap") or 0) > 0
        ),
        "row_status": "draft_needs_owner_review",
        "note": (
            "Every row is a DRAFT. These are measurements of what the system did, not labels and "
            "not a pass/fail verdict; only a human reviewer can score a draft row."
        ),
    }


def render_markdown(summary: dict[str, Any], run_id: str) -> str:
    lines = [
        f"# Conversation-case run: {run_id}",
        "",
        "Rows are **drafts** (`draft_needs_owner_review`). Nothing here is a pass or a fail.",
        "",
        f"- cases: {summary.get('cases')} ({', '.join(summary.get('categories') or [])})",
        f"- turns recorded: {summary.get('turns_recorded')} of {summary.get('turns')} planned",
        f"- turns served from the corpus: {summary.get('served_turns')}",
        f"- p95 server latency: {summary.get('p95_latency_ms')} ms",
        f"- turn-2 rows that cited anything: {summary.get('turn2_cited_anything')} of "
        f"{summary.get('cases_with_history_requirement', 0)}",
        f"- turn-2 rows sharing a video with turn 1: {summary.get('turn2_shared_a_video_with_turn1')}",
        "",
        "## Grounding states",
        "",
        "| state | turns |",
        "|---|---|",
    ]
    for state, count in summary["grounding_counts"].items():
        lines.append(f"| {state} | {count} |")
    lines += ["", summary["note"], ""]
    return "\n".join(lines)


# ── execution ────────────────────────────────────────────────────────────────
def _ask_turn(client: Any, base: str, tokens: dict[str, Any], body_messages: list[dict], text: str):
    """One turn on one anonymous session, following the same job-polling shape as the capture."""
    if tokens.get("token") is None or tokens.get("used", 0) >= 4:
        for _ in range(25):
            r = client.post(base + "/api/auth/anon-session")
            if r.status_code == 200:
                tokens.update(token=r.json()["token"], used=0)
                break
            time.sleep(float(r.headers.get("retry-after", "8")) + 2)
        else:
            raise SystemExit("anon-session endpoint stayed rate limited")
    tokens["used"] += 1
    headers = {"X-Session-Id": tokens["token"]}
    started = time.time()
    r = client.post(
        base + "/api/chat",
        json={"messages": body_messages, "user_message": text, "session_id": tokens["token"]},
        headers=headers,
    )
    if r.status_code == 202:
        job = r.json()["job_id"]
        deadline = time.time() + 110
        while time.time() < deadline:
            job_body = client.get(base + f"/api/jobs/{job}", headers=headers).json()
            if job_body.get("status") in ("completed", "failed"):
                return r.status_code, job_body.get("result") or {}, time.time() - started
            time.sleep(1.0)
        return r.status_code, {}, time.time() - started
    return r.status_code, (r.json() if r.status_code == 200 else {}), time.time() - started


def run(
    cases: list[dict[str, Any]], base: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    import httpx

    records: list[dict[str, Any]] = []
    cases_out: list[dict[str, Any]] = []
    with httpx.Client(timeout=150) as client:
        for case in cases:
            tokens: dict[str, Any] = {}
            turns: list[dict[str, Any]] = []
            body_messages: list[dict[str, Any]] = []
            for index, text in enumerate(case_turns(case)):
                http, result, wall = _ask_turn(client, base, tokens, body_messages, text)
                record = build_turn_record(case, index, http, result, wall)
                record["turn2_citation_overlap"] = overlap_with_previous(turns + [record], index)
                turns.append(record)
                records.append(record)
                body_messages = body_messages + [
                    {"role": "user", "content": text},
                    # The assistant turn is recorded as a placeholder: the anonymous path never
                    # reads an assistant turn (only the last prior USER turn feeds the resolver).
                    {"role": "assistant", "content": (result.get("response") or "")[:2000]},
                ]
            cases_out.append(
                {
                    "case_id": case.get("id"),
                    "category": case.get("category"),
                    "expected": case.get("expected"),
                    "must_not": case.get("must_not"),
                    "turn2_must_use_history": bool(case.get("turn2_must_use_history")),
                    "row_status": case.get("status", "draft_needs_owner_review"),
                    "authored_by": case.get("authored_by"),
                    "turns": turns,
                }
            )
    return records, cases_out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the draft conversation cases (T-E7)")
    parser.add_argument("--cases-file", type=Path, default=CASES)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--limit", type=int, default=None, help="First N cases only")
    parser.add_argument("--ids", default=None, help="Comma-separated case ids")
    parser.add_argument("--execute", action="store_true", help="Actually send chat requests")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan and stop (default)")
    parser.add_argument(
        "--i-have-logged-the-spend",
        action="store_true",
        help="Required with --execute: the run may spend model money",
    )
    args = parser.parse_args(argv)

    cases = load_cases(args.cases_file)
    if args.ids:
        wanted = {x.strip() for x in args.ids.split(",") if x.strip()}
        cases = [c for c in cases if c.get("id") in wanted]
        if not cases:
            print("FAILED: no case matched --ids", file=sys.stderr)
            return 2
    plan_info = plan(cases, args.limit)
    cases = cases[: args.limit] if args.limit else cases

    if not args.execute or args.dry_run:
        print(json.dumps({"dry_run": True, **plan_info}, indent=2))
        print(
            "nothing was sent. Executing needs --execute --i-have-logged-the-spend.",
            file=sys.stderr,
        )
        return 0

    if not args.i_have_logged_the_spend:
        print(
            "REFUSED: --execute spends model money; log the planned spend in "
            "docs/operations/SPEND_LOG_2026.md and pass --i-have-logged-the-spend",
            file=sys.stderr,
        )
        return 2

    run_id = args.run_id or time.strftime("%Y%m%d-%H%M%S") + "-conversation"
    run_dir = args.out_root.expanduser() / run_id
    if run_dir.exists() and any(run_dir.iterdir()):
        print(f"REFUSED: {run_dir} already exists; use a new --run-id", file=sys.stderr)
        return 2
    run_dir.mkdir(parents=True, exist_ok=True)

    records, cases_out = run(cases, args.base_url)
    summary = summarize(records, plan_info)
    (run_dir / "turns.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in records), encoding="utf-8"
    )
    (run_dir / "cases.jsonl").write_text(
        "".join(json.dumps(c) + "\n" for c in cases_out), encoding="utf-8"
    )
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (run_dir / "summary.md").write_text(render_markdown(summary, run_id), encoding="utf-8")
    print(render_markdown(summary, run_id))
    print(f"wrote {run_dir}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 1:
        # Self-check: the offline half must be correct without a server.
        _cases = load_cases()
        assert len(_cases) == 24, len(_cases)
        _plan = plan(_cases, None)
        assert _plan["cases"] == 24, _plan
        assert _plan["turns"] == 24 + 6, _plan  # 18 single-turn + 6 two-turn cases
        _turns = [
            {"citation_videos": ["a", "b"]},
            {"citation_videos": ["b", "c"]},
            {"citation_videos": []},
        ]
        assert overlap_with_previous(_turns, 1) == 0.5
        assert overlap_with_previous(_turns, 2) is None
        print("self-check ok:", _plan)
        raise SystemExit(0)
    raise SystemExit(main())
