"""Build the first-person negative-control pairs (question paired with a clip from another question).

A negative control is a pair the gate SHOULD abstain on: the clip answers a different question.
No LLM is called here; the scorer is run later, separately, and only when spend is approved.

Source: served rows of a graded run (rows.jsonl). Only ids, question text and SHA-256 prefixes of
clips are written; clip text is never copied into the repo.

Usage:
    backend/.venv/bin/python evals/first_person/build_negative_controls.py \
        --rows ~/mukthiguru_attribution_data/graded_runs/20261112-graded-6/rows.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

SEED = 20261113
SET_NAME = "frozen116"
OUT = Path(__file__).with_name("negative_controls.jsonl")


def _clip_pool(rows: list[dict]) -> list[dict]:
    """One entry per served frozen row: source question id, clip hash prefix, clip text (in memory only)."""
    pool = []
    for row in rows:
        if row.get("set") != SET_NAME or not row.get("citations"):
            continue
        text = (row["citations"][0].get("text") or "").strip()
        if not text:
            continue
        pool.append(
            {
                "source_id": row["id"],
                "clip_sha256_12": hashlib.sha256(text.encode("utf-8")).hexdigest()[:12],
                "text": text,
            }
        )
    return pool


def build(rows: list[dict]) -> list[dict]:
    questions = [r for r in rows if r.get("set") == SET_NAME]
    pool = _clip_pool(rows)
    rng = random.Random(SEED)
    out = []
    for q in questions:
        candidates = [c for c in pool if c["source_id"] != q["id"]]
        if not candidates:
            raise ValueError(f"no clip from another question for {q['id']}")
        pick = rng.choice(candidates)
        out.append(
            {
                "control_id": f"neg_{q['id']}",
                "question_id": q["id"],
                "question": q["question"],
                "clip_source_question_id": pick["source_id"],
                "clip_sha256_12": pick["clip_sha256_12"],
                "expected": "abstain",
                "seed": SEED,
            }
        )
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.rows.read_text(encoding="utf-8").splitlines() if line.strip()]
    controls = build(rows)
    args.out.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in controls), encoding="utf-8")
    print(f"wrote {len(controls)} controls to {args.out}")


if __name__ == "__main__":
    main()
