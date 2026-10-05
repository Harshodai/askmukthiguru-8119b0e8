"""Phase 2 answerability-gate validation (plan REVISION 2026-09-30).

Scores the REAL ``_answerability_check`` (same function the pipeline wires in)
against the pinned first-person datasets:

- the 27 ``answerable: false`` out-of-corpus questions from the bakeoff set —
  the exact class Audit B measured being served as direct answers (3/3 leak),
- every answerable question: 89 bakeoff + the golden-25 paraphrase set when
  present — a gate that abstains on these is a false refusal, i.e. the fix
  would have traded one P0 for another.

Reports leak rate, false-refusal rate, indeterminate count and latency
p50/p95, and writes the full JSON (per-question verdicts included).

Paced at GATE_PACE_S between calls: OpenRouterService enforces a 20 RPM
budget through ONE Redis sliding window shared with the live backend, and a
call that trips the limiter sleeps inside generate() until the gate
budget cancels it — that would show up as a false indeterminate.

Run (container, repo .claude/ is NOT mounted here — copy the output out):

    docker exec mukthiguru-backend python -m evaluation.run_answerability_validation \
        --out /tmp/answerability_validation_2026-09-30.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

# Expected dataset shape, verified 2026-09-30 against the pinned files. A
# different count means the dataset changed under us — fail loudly, never
# quietly score a different set than the audit referred to.
EXPECTED_OOC = 27
EXPECTED_ANSWERABLE_BAKEOFF = 89
GOLDEN_ANSWERABLE = 25


def _percentile(sorted_vals: list[float], p: float) -> float | None:
    if not sorted_vals:
        return None
    idx = min(len(sorted_vals) - 1, max(0, int(round(p * len(sorted_vals))) - 1))
    return round(sorted_vals[idx], 1)


def _git_sha() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return None  # container has no .git; record None, never a guess


def _tally(rows: list[dict]) -> dict:
    n = len(rows)
    yes = sum(1 for r in rows if r["verdict"] == "yes")
    no = sum(1 for r in rows if r["verdict"] == "no")
    ind = sum(1 for r in rows if r["verdict"] == "indeterminate")
    return {
        "n": n,
        "yes": yes,
        "no": no,
        "indeterminate": ind,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--out", type=Path, default=Path("/tmp/answerability_validation_2026-09-30.json")
    )
    args = ap.parse_args(argv)

    from app.config import settings
    from evaluation.first_person_harness import (
        GATE_PACE_S,
        GOLDEN_PARAPHRASE_PATH,
        QUESTIONS_PATH,
        _make_llm_service,
        load_questions,
    )
    from services.first_person_pipeline import _ANSWERABILITY_TIMEOUT_S, _answerability_check

    if not settings.first_person_answerability_check_enabled:
        print(
            "FATAL: first_person_answerability_check_enabled is false; refusing to 'validate' a disabled gate",
            file=sys.stderr,
        )
        return 2

    llm_service, llm_name = _make_llm_service()
    if llm_service is None:
        # Never write a validation JSON that did not actually call the model.
        print("FATAL: no llm_service available; nothing was validated", file=sys.stderr)
        return 2

    bakeoff = load_questions(path=QUESTIONS_PATH, pin_check=True)
    ooc = [q for q in bakeoff if not q["answerable"]]
    answerable = [(q, "bakeoff") for q in bakeoff if q["answerable"]]

    if len(ooc) != EXPECTED_OOC:
        print(
            f"FATAL: expected exactly {EXPECTED_OOC} answerable:false rows, found {len(ooc)}",
            file=sys.stderr,
        )
        return 2
    if len(answerable) != EXPECTED_ANSWERABLE_BAKEOFF:
        print(
            f"FATAL: expected exactly {EXPECTED_ANSWERABLE_BAKEOFF} answerable bakeoff rows, "
            f"found {len(answerable)}",
            file=sys.stderr,
        )
        return 2

    golden_sha = None
    if GOLDEN_PARAPHRASE_PATH.is_file():
        golden = load_questions(path=GOLDEN_PARAPHRASE_PATH, pin_check=True)
        golden = [q for q in golden if q.get("answerable", True)]
        if len(golden) != GOLDEN_ANSWERABLE:
            print(
                f"FATAL: golden set has {len(golden)} answerable rows, expected {GOLDEN_ANSWERABLE}",
                file=sys.stderr,
            )
            return 2
        answerable += [(q, "golden_25") for q in golden]
        golden_sha = hashlib.sha256(GOLDEN_PARAPHRASE_PATH.read_bytes()).hexdigest()

    work = [(q, "ooc") for q in ooc] + [(q, subset) for q, subset in answerable]

    rows: list[dict] = []
    started = time.monotonic()
    for i, (q, subset) in enumerate(work, 1):
        query = q["question"]
        t0 = time.perf_counter()
        verdict = _answerability_check(query, llm_service)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        rows.append(
            {
                "id": q["id"],
                "subset": subset,
                "question": query,
                "verdict": {True: "yes", False: "no"}.get(verdict, "indeterminate"),
                "latency_ms": round(latency_ms, 1),
            }
        )
        print(
            f"[{i}/{len(work)}] {subset} {q['id']} -> {rows[-1]['verdict']} ({latency_ms:.0f}ms)",
            flush=True,
        )
        if i < len(work):
            time.sleep(GATE_PACE_S)

    ooc_rows = [r for r in rows if r["subset"] == "ooc"]
    ans_rows = [r for r in rows if r["subset"] != "ooc"]
    ooc_t, ans_t = _tally(ooc_rows), _tally(ans_rows)
    ooc_t["leak_rate"] = round(ooc_t["yes"] / ooc_t["n"], 4)  # OOC answered YES = served direct
    ans_t["false_refusal_rate"] = round((ans_t["no"] + ans_t["indeterminate"]) / ans_t["n"], 4)
    lat = sorted(r["latency_ms"] for r in rows)

    result = {
        "script": "evaluation/run_answerability_validation.py",
        "ran_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "git_sha": _git_sha(),
        "llm_service": llm_name,
        "model": settings.openrouter_generation_model,
        "flag": settings.first_person_answerability_check_enabled,
        "timeout_s": _ANSWERABILITY_TIMEOUT_S,
        "pace_s": GATE_PACE_S,
        "rpm_limit": settings.openrouter_rpm_limit,
        "datasets": {
            "bakeoff": {
                "path": str(QUESTIONS_PATH),
                "sha256": hashlib.sha256(QUESTIONS_PATH.read_bytes()).hexdigest(),
            },
            "golden_25": {"path": str(GOLDEN_PARAPHRASE_PATH), "sha256": golden_sha},
        },
        "counts": {
            "ooc": len(ooc_rows),
            "answerable_bakeoff": EXPECTED_ANSWERABLE_BAKEOFF,
            "answerable_golden_25": len(ans_rows) - EXPECTED_ANSWERABLE_BAKEOFF,
            "total_calls": len(rows),
        },
        "ooc": ooc_t,
        "answerable": ans_t,
        "indeterminate_total": sum(1 for r in rows if r["verdict"] == "indeterminate"),
        "latency_ms": {"p50": _percentile(lat, 0.50), "p95": _percentile(lat, 0.95)},
        "wall_clock_s": round(time.monotonic() - started, 1),
        "rows": rows,
    }
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")

    print(
        json.dumps(
            {
                k: result[k]
                for k in ("counts", "ooc", "answerable", "indeterminate_total", "latency_ms")
            },
            indent=2,
        )
    )
    print(f"wrote {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
