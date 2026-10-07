"""Temperature-0 stability probe for the Phase-2 answerability gate.

Evidence gate that must pass BEFORE the planned one-line temperature fix
(abstention plan, 2026-10-03): the provider default temperature=0.1 shuffles
borderline verdicts between runs (observed leak band 26-30% = +/-2 of the 27
OOC rows). This probe runs the REAL ``_answerability_check`` on the
verdict-critical rows of a prior full validation, ``--reps`` times each, with
``temperature=0.0`` injected through a wrapper — the core pipeline file stays
untouched until this probe proves determinism.

Row selection from the prior validation JSON (priority order, capped at
``--max-rows``):
  1. leak class : OOC rows the gate answered "yes"  (served out-of-domain)
  2. FR class   : answerable rows answered "no" / "indeterminate"
  3. controls   : first 2 stable OOC "no" + first 2 stable answerable "yes"

Exit codes: 0 = every row deterministic across reps (fix may ship),
1 = at least one row shuffled (fix must NOT ship), 2 = setup failure.

Honesty rules inherited from evaluation/run_answerability_validation.py:
refuse to run with the gate flag disabled or without an LLM service, pace at
GATE_PACE_S (shared 20 RPM Redis limiter), and never write a JSON for a run
that did not actually call the model.

Run (container; repo .claude/ is NOT mounted — copy the output out):

    docker exec mukthiguru-backend python -m scripts.ops.answerability_stability_probe \
        --prior-json /tmp/answerability_r4_2026-10-03.json \
        --out /tmp/answerability_stability_probe_2026-10-03.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path


class _TempForcedLLM:
    """Wraps a real LLM service, forcing a fixed temperature on every call."""

    def __init__(self, inner, temperature: float) -> None:
        self._inner = inner
        self.temperature = temperature
        self.seen_temperatures: list = []

    def generate(self, *args, **kwargs):
        kwargs["temperature"] = self.temperature
        self.seen_temperatures.append(kwargs["temperature"])
        return self._inner.generate(*args, **kwargs)


def _select_rows(prior_rows: list[dict], max_rows: int) -> list[dict]:
    leaks = [r for r in prior_rows if r["subset"] == "ooc" and r["verdict"] == "yes"]
    frs = [
        r
        for r in prior_rows
        if r["subset"] != "ooc" and r["verdict"] in ("no", "indeterminate")
    ]
    control_ooc = [r for r in prior_rows if r["subset"] == "ooc" and r["verdict"] == "no"][:2]
    control_ans = [
        r for r in prior_rows if r["subset"] != "ooc" and r["verdict"] == "yes"
    ][:2]
    selected: list[dict] = []
    for group in (leaks, frs, control_ooc, control_ans):
        for row in group:
            if len(selected) >= max_rows:
                return selected
            if row["id"] not in {r["id"] for r in selected}:
                selected.append(row)
    return selected


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--prior-json", type=Path, required=True, help="Full validation JSON (e.g. R4)")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--max-rows", type=int, default=16)
    ap.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Temperature injected into every call (0.1 = provider-default control arm)",
    )
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)

    from app.config import settings
    from evaluation.first_person_harness import GATE_PACE_S, _make_llm_service
    from services.first_person_pipeline import (
        _ANSWERABILITY_TIMEOUT_S,
        _answerability_check,
    )

    if not settings.first_person_answerability_check_enabled:
        print("FATAL: answerability gate flag is false; refusing to probe a disabled gate", file=sys.stderr)
        return 2

    llm_service, llm_name = _make_llm_service()
    if llm_service is None:
        print("FATAL: no llm_service available; nothing was probed", file=sys.stderr)
        return 2

    prior = json.loads(args.prior_json.read_text())
    prior_rows = prior.get("rows") or []
    if not prior_rows:
        print("FATAL: prior JSON has no rows", file=sys.stderr)
        return 2

    selected = _select_rows(prior_rows, args.max_rows)
    if not selected:
        print("FATAL: selection produced no rows", file=sys.stderr)
        return 2

    probe = _TempForcedLLM(llm_service, args.temperature)
    started = time.monotonic()
    out_rows: list[dict] = []
    call_i = 0
    for row in selected:
        verdicts: list[str] = []
        latencies: list[float] = []
        for _rep in range(args.reps):
            if call_i > 0:
                time.sleep(GATE_PACE_S)  # shared 20 RPM limiter — pace every call
            call_i += 1
            t0 = time.perf_counter()
            verdict = _answerability_check(row["question"], probe)
            latency_ms = (time.perf_counter() - t0) * 1000.0
            verdicts.append({True: "yes", False: "no"}.get(verdict, "indeterminate"))
            latencies.append(round(latency_ms, 1))
        stable = len(set(verdicts)) == 1
        out_rows.append(
            {
                "id": row["id"],
                "subset": row["subset"],
                "question": row["question"],
                "prior_verdict": row["verdict"],
                "verdicts": verdicts,
                "stable": stable,
                "changed_vs_prior": verdicts[0] != row["verdict"],
                "latencies_ms": latencies,
            }
        )
        print(
            f"{row['id']} ({row['subset']}) prior={row['verdict']} "
            f"reps={verdicts} stable={stable}",
            flush=True,
        )

    unstable = [r for r in out_rows if not r["stable"]]
    changed = [r for r in out_rows if r["changed_vs_prior"]]
    result = {
        "script": "scripts/ops/answerability_stability_probe.py",
        "ran_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "llm_service": llm_name,
        "prior_json": {
            "path": str(args.prior_json),
            "sha256": hashlib.sha256(args.prior_json.read_bytes()).hexdigest(),
        },
        "temperature": args.temperature,
        "reps": args.reps,
        "timeout_s": _ANSWERABILITY_TIMEOUT_S,
        "pace_s": GATE_PACE_S,
        "rows": out_rows,
        "summary": {
            "n_rows": len(out_rows),
            "n_stable": len(out_rows) - len(unstable),
            "n_unstable": len(unstable),
            "n_changed_vs_prior": len(changed),
            "deterministic": not unstable,
            "wall_clock_s": round(time.monotonic() - started, 1),
        },
    }
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps(result["summary"], indent=2),
        flush=True,
    )
    print(f"temperature injections: {len(probe.seen_temperatures)} calls, all {args.temperature} = {all(t == args.temperature for t in probe.seen_temperatures)}")
    print(f"wrote {args.out}")
    return 0 if not unstable else 1


if __name__ == "__main__":
    sys.exit(main())
