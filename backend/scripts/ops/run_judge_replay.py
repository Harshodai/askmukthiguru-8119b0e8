#!/usr/bin/env python3
"""Replay a graded run's served answers through the serving judge, per rubric (v1 / v2).

For each served row (non-empty citations and answer) the judge is called once per rubric with
the question and the served answer text as the single clip (the answer carries no fixed
prefix or suffix, so it is sent as is). Accept means ``select_index`` returned an index at the
configured minimum score. Grader labels come from grades.json: a row is "showable" when BOTH
graders say showable, "rejected" when EITHER says not_showable, otherwise "mixed" (left out of
the rates). An indeterminate judge result is counted on its own, never as accept or reject.

Spend: without --dry-run this makes paid calls, so it refuses unless --i-have-logged-the-spend.
Run inside the backend container with PYTHONPATH=/app:

    PYTHONPATH=/app python /app/scripts/ops/run_judge_replay.py --dry-run --rows rows.jsonl --grades grades.json
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

INDETERMINATE = -1
COST_PER_CALL_USD = 0.03  # worst-case reservation per call

# (question, clip_text, rubric) -> (pick, relevance score or None); pick 0 | None | INDETERMINATE
Judge = Callable[[str, str, str], Awaitable[tuple[Optional[int], Optional[int]]]]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def served_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if r.get("citations") and str(r.get("answer") or "").strip()]


def grader_label(grades: dict[str, Any], row_id: str) -> str:
    """showable (both showable) | rejected (either not_showable) | mixed."""
    verdicts = [(grades.get(k) or {}).get(row_id, {}).get("verdict") for k in ("first", "second")]
    if all(v == "showable" for v in verdicts):
        return "showable"
    if any(v == "not_showable" for v in verdicts):
        return "rejected"
    return "mixed"


def clip_texts_by_hash(rows: list[dict[str, Any]]) -> dict[str, str]:
    """sha256[:12] of citations[0].text -> text, the hash run_negative_controls uses."""
    out: dict[str, str] = {}
    for r in rows:
        if not r.get("citations"):
            continue
        text = (r["citations"][0].get("text") or "").strip()
        if text:
            out[hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]] = text
    return out


def plan(n_served: int, n_neg: int, rubrics: list[str]) -> dict[str, Any]:
    calls = (n_served + n_neg) * len(rubrics)
    return {
        "served_rows": n_served,
        "negatives": n_neg,
        "rubrics": rubrics,
        "max_calls": calls,
        "worst_case_reservation_usd": round(calls * COST_PER_CALL_USD, 4),
    }


def _verdict(pick: Optional[int]) -> str:
    return "indeterminate" if pick == INDETERMINATE else ("accept" if pick == 0 else "reject")


async def run_replay(
    rows: list[dict[str, Any]],
    grades: dict[str, Any],
    negatives: list[dict[str, Any]],
    texts: dict[str, str],
    rubrics: list[str],
    judge: Judge,
) -> dict[str, Any]:
    table: list[dict[str, Any]] = []
    for r in rows:
        entry: dict[str, Any] = {
            "id": r["id"],
            "grader": grader_label(grades, r["id"]),
            "both_showable": grader_label(grades, r["id"]) == "showable",
        }
        for rub in rubrics:
            pick, score = await judge(r["question"], str(r["answer"]).strip(), rub)
            entry[rub] = {"verdict": _verdict(pick), "score": score}
        table.append(entry)
    neg_table: list[dict[str, Any]] = []
    for c in negatives:
        text = texts.get(c["clip_sha256_12"])
        if text is None:
            raise KeyError(f"clip {c['clip_sha256_12']} for {c['control_id']} not in rows file")
        entry = {"id": c["control_id"]}
        for rub in rubrics:
            pick, score = await judge(c["question"], text, rub)
            entry[rub] = {"verdict": _verdict(pick), "score": score}
        neg_table.append(entry)
    return {
        "rows": table,
        "negatives": neg_table,
        "summary": {rub: summarize(table, neg_table, rub) for rub in rubrics},
    }


def _rate(num: int, den: int) -> Optional[float]:
    return round(num / den, 4) if den else None


def summarize(table: list[dict[str, Any]], negatives: list[dict[str, Any]], rub: str) -> dict:
    def n(label: str, verdict: str) -> int:
        return sum(r["grader"] == label and r[rub]["verdict"] == verdict for r in table)

    kept_show, rej_show = n("showable", "accept"), n("showable", "reject")
    kept_bad, rej_bad = n("rejected", "accept"), n("rejected", "reject")
    nv = [x[rub]["verdict"] for x in negatives]
    abstained, served = nv.count("reject"), nv.count("accept")
    return {
        "showable_rows_kept": kept_show,
        "showable_rows_total_decided": kept_show + rej_show,
        "recall_of_showable": _rate(kept_show, kept_show + rej_show),
        "rejected_rows_judge_rejected": rej_bad,
        "rejected_rows_total_decided": kept_bad + rej_bad,
        "reject_rate_of_grader_rejected": _rate(rej_bad, kept_bad + rej_bad),
        "kept_rows": kept_show + kept_bad,
        "precision_of_kept": _rate(kept_show, kept_show + kept_bad),
        "indeterminate_rows": sum(r[rub]["verdict"] == "indeterminate" for r in table),
        "mixed_rows_excluded": sum(r["grader"] == "mixed" for r in table),
        "negatives_abstain_rate": _rate(abstained, abstained + served),
        "negatives_indeterminate": nv.count("indeterminate"),
    }


def _real_judge() -> Judge:
    from app.config import settings
    from app.dependencies import _create_llm_service
    from services import first_person_judge as fj

    llm = _create_llm_service()
    minimum = int(settings.first_person_relevance_min_score)
    timeout_s = float(settings.first_person_relevance_timeout_s)

    async def judge(q: str, text: str, rubric: str) -> tuple[Optional[int], Optional[int]]:
        scores: list[int] = []
        pick = await fj.judge_select_async(
            q,
            [{"verbatim_text": text}],
            llm,
            minimum=minimum,
            timeout_s=timeout_s,
            scores_out=scores,
            rubric=rubric,
        )
        return pick, (scores[0] if scores else None)

    return judge


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rows", type=Path, required=True)
    ap.add_argument("--grades", type=Path, required=True)
    ap.add_argument("--negatives", type=Path)
    ap.add_argument("--rubric", choices=["v1", "v2", "both"], default="both")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--i-have-logged-the-spend", action="store_true")
    args = ap.parse_args(argv)

    rubrics = ["v1", "v2"] if args.rubric == "both" else [args.rubric]
    all_rows = load_jsonl(args.rows)
    rows = served_rows(all_rows)[: args.limit]
    negatives = load_jsonl(args.negatives)[: args.limit] if args.negatives else []
    info = plan(len(rows), len(negatives), rubrics)
    if args.dry_run:
        print(json.dumps(info))
        return 0
    if not args.i_have_logged_the_spend:
        print(
            "refusing: paid calls need --i-have-logged-the-spend (or use --dry-run)",
            file=sys.stderr,
        )
        return 2
    grades = json.loads(args.grades.read_text(encoding="utf-8"))
    result = asyncio.run(
        run_replay(rows, grades, negatives, clip_texts_by_hash(all_rows), rubrics, _real_judge())
    )
    result["plan"] = info
    text = json.dumps(result, indent=2)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
