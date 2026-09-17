"""Measure how close answers sit to a teacher's own recorded speech.

    .venv/bin/python -m benchmarks.guru_voice_benchmark --file benchmarks/reports/live_golden_eval_answers.json
    .venv/bin/python -m benchmarks.guru_voice_benchmark --calibrate
    .venv/bin/python -m benchmarks.guru_voice_benchmark --text "some answer text"

REPLACED WHOLESALE 2026-09-15. The previous version could not fail:

* On any provider error it fell into a synthetic branch that scored
  ``REFERENCE_VOICE`` — a hardcoded string in
  ``services/guru_voice_langhanam.py`` — against a rubric derived from that same
  string, and reported 5.0/5.0.
* ``--skip-llm-judge`` set ``provider=None`` without setting ``degraded=True``,
  so the report claimed ``degraded: false`` while running rule-based only.
* Its rubric REWARDED the phrase "Our ancients in India", which LANGHANAM rule 6
  explicitly forbids and which occurs 0 times in 2,700 sentences of the
  teachers' real speech.

This version scores against measured per-teacher profiles built from verbatim
corpus speech (``services/voice/profiles/*.json``), and every profile has to
pass a negative-control validation before it is usable as a gate. There is no
LLM judge and therefore no self-preference bias
(https://arxiv.org/pdf/2410.21819); the largest study of LLM style imitation
avoided LLM judges for the same reason (https://arxiv.org/pdf/2509.14543).

Reference points printed with every run, so a number is never reported naked.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

from app.config import settings
from services.voice.style import (
    MIN_WORDS_FOR_SCORE,
    load_profile,
    strip_chunk_headers,
)

DEFAULT_TEACHER = "preethaji_krishnaji"


def _answers_from(path: Path) -> list[tuple[str, str]]:
    """Pull (question, answer) pairs out of the eval report shapes we produce."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("results", payload) if isinstance(payload, dict) else payload
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        answer = row.get("answer") or row.get("after") or row.get("response") or ""
        if answer:
            out.append((row.get("question") or row.get("q") or "", answer))
    return out


def _report(profile, scored: list[tuple[float, str, str]]) -> None:
    distances = [s[0] for s in scored]
    ref = profile.provenance.validation
    print(
        f"\nteacher profile: {profile.teacher_id}  (n={profile.provenance.sample_count} verbatim chunks)"
    )
    print(f"  certified: {profile.is_certified}   validation AUC={ref.get('auc', 0):.3f}")
    print("\nREFERENCE POINTS (same metric, same profile)")
    print(
        f"  verbatim guru speech ....... {ref.get('human_median', float('nan')):.2f}   <- the target"
    )
    print(
        f"  LLM-written summary prose .. {ref.get('machine_median', float('nan')):.2f}   <- the failure mode"
    )
    print(f"\nSCORED {len(scored)} answers")
    if not scored:
        return
    print(f"  median .. {statistics.median(distances):.2f}")
    print(f"  mean .... {statistics.mean(distances):.2f}")
    machine = ref.get("machine_median", 1.64)
    worse = sum(1 for d in distances if d > machine)
    print(f"  worse than machine prose: {worse}/{len(scored)}")
    scored.sort(reverse=True)
    print("\nWORST 3 (with the features driving the distance)")
    for dist, question, answer in scored[:3]:
        print(f"\n  [{dist:.2f}] {question[:68]}")
        print(f"        {answer[:150].strip().replace(chr(10), ' ')}...")
        for name, obs, ref_mean, z in profile.explain(answer, 3):
            print(f"          {name:26s} observed={obs:7.2f} guru={ref_mean:7.2f} z={z:+.1f}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", type=Path, help="eval report JSON with answers")
    ap.add_argument("--text", help="score a single string")
    ap.add_argument("--teacher", default=DEFAULT_TEACHER)
    ap.add_argument(
        "--calibrate",
        action="store_true",
        help="print the metric's own reference points and prove it discriminates",
    )
    ap.add_argument(
        "--max-distance",
        type=float,
        default=None,
        help=(
            "exit non-zero if the median exceeds this (CI gate); "
            "defaults to settings.guru_voice_gate_score"
        ),
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="write the scored report as JSON; defaults to settings.guru_voice_benchmark_output",
    )
    args = ap.parse_args(argv)

    # Both settings are listed in tests/test_wiring_invariants.py NEVER_FLAG_DEAD:
    # if they go unread, that is a real finding, not scan noise. The previous
    # benchmark read them; this one must too, or the gate silently stops being
    # configurable and the report stops landing where operators look for it.
    gate = args.max_distance
    if gate is None:
        gate = getattr(settings, "guru_voice_gate_score", None)
    out_path = args.out
    if out_path is None:
        configured_out = getattr(settings, "guru_voice_benchmark_output", "")
        out_path = Path(configured_out) if configured_out else None

    profile = load_profile(args.teacher)
    if profile is None:
        print(
            f"no profile for {args.teacher!r}. Build one:\n"
            f"  .venv/bin/python -m scripts.ops.build_voice_profiles --apply",
            file=sys.stderr,
        )
        return 2
    if not profile.is_certified:
        print(
            f"WARNING: profile {args.teacher!r} is NOT certified "
            f"({profile.provenance.validation}); treat numbers as indicative, not a gate.",
            file=sys.stderr,
        )

    if args.calibrate:
        v = profile.provenance.validation
        print(json.dumps({"teacher": profile.teacher_id, **v}, indent=2))
        return 0 if profile.is_certified else 1

    if args.text:
        text = strip_chunk_headers(args.text)
        print(f"distance {profile.distance(text):.2f}")
        for name, obs, ref_mean, z in profile.explain(text):
            print(f"  {name:26s} observed={obs:7.2f} guru={ref_mean:7.2f} z={z:+.1f}")
        return 0

    if not args.file:
        ap.error("pass --file, --text, or --calibrate")

    pairs = _answers_from(args.file)
    scored = [
        (profile.distance(a), q, a) for q, a in pairs if len(a.split()) >= MIN_WORDS_FOR_SCORE
    ]
    _report(profile, scored)

    if out_path is not None and scored:
        median = statistics.median([s[0] for s in scored])
        payload = {
            "teacher": profile.teacher_id,
            "validation": profile.provenance.validation,
            "count": len(scored),
            "median_distance": round(median, 4),
            "gate": gate,
            "scores": [{"distance": round(d, 4), "question": q} for d, q, _a in scored],
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2))
        print(f"\nreport written: {out_path}")

    if gate is not None and scored:
        median = statistics.median([s[0] for s in scored])
        if median > gate:
            print(f"\nGATE FAILED: median {median:.2f} > {gate}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
