#!/usr/bin/env python3
"""OKF contradiction-pair surfacing (R4 curation loop).

Finds candidate entries where the two teachers may disagree on the same
topic so reviewers can DUAL-PRESENT them with teacher labels.

REPORT-ONLY: reads compiled.json (or a scratch copy), writes a candidate
list. Never merges, edits, or deletes doctrine. Stdlib only, 0 LLM calls.

Usage:
    python3 scripts/ops/okf_contradiction_scan.py
    python3 scripts/ops/okf_contradiction_scan.py --compiled /tmp/copy.json \\
        --out /tmp/contra.json --threshold 0.3 --limit 50
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COMPILED = REPO_ROOT / "memory" / "okf" / "compiled.json"

_HEADING_RE = re.compile(
    r"#{1,6}\s*(summary|key teachings|quotes|related concepts|source context)\b"
)
_WORD_RE = re.compile(r"[a-z0-9]+")


def _word_set(text: str) -> set[str]:
    return set(_WORD_RE.findall(_HEADING_RE.sub(" ", (text or "").lower())))


def _teacher_side(teacher: str) -> str | None:
    t = (teacher or "").strip().lower()
    if "preetha" in t:
        return "preethaji"
    if "krishna" in t:
        return "krishnaji"
    return None  # 'both'/shared entries are context, not a side


def find_contradiction_candidates(
    entries: list[dict], threshold: float = 0.3, limit: int = 50
) -> list[dict]:
    """Cross-teacher pairs with high lexical overlap = same topic, maybe disagree."""
    pre = [e for e in entries if _teacher_side(str(e.get("teacher", ""))) == "preethaji"]
    kri = [e for e in entries if _teacher_side(str(e.get("teacher", ""))) == "krishnaji"]
    sets = {id(e): _word_set(f"{e.get('title', '')} {e.get('body', '')}") for e in pre + kri}
    pairs: list[dict] = []
    for a in pre:
        wa = sets[id(a)]
        if not wa:
            continue
        for b in kri:
            wb = sets[id(b)]
            if not wb:
                continue
            union = wa | wb
            jacc = len(wa & wb) / len(union) if union else 0.0
            if jacc >= threshold:
                shared = sorted((wa & wb) - {"the", "and", "with", "from", "that"})
                pairs.append(
                    {
                        "a_title": a.get("title", ""),
                        "a_teacher": a.get("teacher", ""),
                        "a_path": a.get("path", ""),
                        "b_title": b.get("title", ""),
                        "b_teacher": b.get("teacher", ""),
                        "b_path": b.get("path", ""),
                        "jaccard": round(jacc, 3),
                        "shared_terms": shared[:12],
                        "recommendation": "dual-present with teacher labels; never merge",
                    }
                )
    pairs.sort(key=lambda p: p["jaccard"], reverse=True)
    return pairs[:limit]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Surface both-teacher disagree candidates.")
    ap.add_argument("--compiled", default=str(DEFAULT_COMPILED))
    ap.add_argument("--out", default="")
    ap.add_argument("--threshold", type=float, default=0.3)
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args(argv)

    data = json.loads(Path(args.compiled).read_text(encoding="utf-8"))
    entries = data.get("entries", [])
    pairs = find_contradiction_candidates(entries, args.threshold, args.limit)

    n_pre = sum(1 for e in entries if _teacher_side(str(e.get("teacher", ""))) == "preethaji")
    n_kri = sum(1 for e in entries if _teacher_side(str(e.get("teacher", ""))) == "krishnaji")
    print(f"entries={len(entries)} preethaji={n_pre} krishnaji={n_kri}")
    print(f"contradiction candidates (threshold={args.threshold}): {len(pairs)}")
    for p in pairs[:10]:
        print(f"  {p['jaccard']:.2f} | {p['a_title'][:60]!r} <-> {p['b_title'][:60]!r}")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps({"candidate_pairs": pairs}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"report written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
