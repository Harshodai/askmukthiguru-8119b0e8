#!/usr/bin/env python3
"""Gold-label CLI for the first-person calibration gate.

The calibration gate needs 299 CONFIDENT HUMAN gold labels with 0 errors
(see backend/CLAUDE.md; 290 AI/self labels in backend/.work/autoresearch_fp/
are hints, never gold). This tool makes those human hours cheap:

  - one keypress per field (relevance 1-3, completeness f/i, risk),
  - auto-resume across sessions (append-only gold_labels.jsonl + state file),
  - `--order hard` first (default): borderline AI labels (relevance 2,
    completeness disagreement) land earliest so the first labelling hour
    carries the most calibration value,
  - `--status` gives progress + ETA without opening the TUI.

Usage
-----
    .venv/bin/python -m scripts.ops.gold_label_cli \
        --candidates .work/autoresearch_fp/to_label.jsonl \
        --ai-labels  .work/autoresearch_fp/labels.jsonl \
        --out        .work/gold_labels/gold_labels.jsonl

Keys inside the TUI:
    1 2 3   relevance (1=unrelated, 2=related-not-direct, 3=direct answer)
    f / i   complete / incomplete thought
    y / n   risk flag (safety-sensitive content)
    c       confirm & save current label  (sets rater=human, confidence=ok)
    s       skip  ·  u undo last  ·  p progress  ·  h help  ·  q quit
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

GOLD_TARGET = 299
_RELEVANCE = {"1", "2", "3"}
KEYS_HELP = (
    "  1/2/3 relevance · f/i complete · y/n risk · c confirm · s skip · u undo · p status · q quit"
)


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def hard_score(item: dict, ai: dict | None) -> int:
    """Lower = label this earlier. Borderline (AI said 2) and AI-incomplete
    items are exactly where a wrong serving threshold bites, so they go first.
    Everything else falls back to listing order (stable)."""
    if not ai:
        return 5
    if ai.get("relevance") == 2:
        return 0
    if ai.get("relevance") == 3 and not ai.get("complete", True):
        return 1
    if ai.get("relevance") == 3:
        return 2
    return 3


def order_candidates(cands: list[dict], ai_by_id: dict[str, dict], order: str) -> list[dict]:
    cands = list(cands)
    if order == "hard":
        cands.sort(key=lambda it: (hard_score(it, ai_by_id.get(it["id"])), it["id"]))
    return cands


def print_item(item: dict, ai: dict | None, idx: int, n: int, done_ids: set[str]) -> None:
    print(
        f"\n[{idx}/{n}]  {item['id']}  ·  {item.get('speaker', '?')}  ·  {item.get('duration_s', '?')}s"
    )
    print(f"  Q: {item.get('question', '?')}")
    clip = (item.get("clip", "") or "").strip()
    print("  clip:")
    print("    " + clip[:600] + ("…" if len(clip) > 600 else ""))
    if ai:
        print(
            f"  [ai-hint] relevance={ai.get('relevance')} complete={ai.get('complete')} "
            f"risk={ai.get('risk')}  (hint only — never gold)"
        )
    if item["id"] in done_ids:
        print("  [already gold — re-confirm overrides]")
    print(
        "  1/2/3 relevance · f/i complete · y/n risk · c confirm & save · s skip · u undo · p progress · q quit"
    )


def status(args: argparse.Namespace, out_path: Path) -> int:
    gold = load_jsonl(out_path)
    n_done = len({g["id"] for g in gold})
    cands = load_jsonl(Path(args.candidates))
    print(f"gold={n_done}/{GOLD_TARGET}  ({max(GOLD_TARGET - n_done, 0)} to go)")
    print(f"candidates={len(cands)}  out={out_path}")
    if gold:
        conf = sum(1 for g in gold if g.get("confidence") == "ok")
        print(f"confident(ok)={conf}  confident!={len(gold) - conf}")
        rel = {r: sum(1 for g in gold if g.get("relevance") == r) for r in ("1", "2", "3")}
        print(f"relevance split: {rel}  complete={sum(1 for g in gold if g.get('complete'))}")
    return 0


def run(args: argparse.Namespace) -> int:
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cands = load_jsonl(Path(args.candidates))
    ai_by_id: dict[str, dict] = {}
    if args.ai_labels and Path(args.ai_labels).exists():
        ai_by_id = {a["id"]: a for a in load_jsonl(Path(args.ai_labels))}

    gold = load_jsonl(out_path)
    gold_by_id = {g["id"]: g for g in gold}
    order = order_candidates(cands, ai_by_id, args.order)
    rater = args.rater or getpass.getuser()

    print(f"{len(cands)} candidates · {len(gold_by_id)} already gold · target {GOLD_TARGET}")
    idx = 0
    while idx < len(order) and len(gold_by_id) < GOLD_TARGET:
        item = order[idx]
        cur = gold_by_id.get(item["id"], {})
        lab = {
            "relevance": cur.get("relevance"),
            "complete": cur.get("complete"),
            "risk": cur.get("risk", False),
        }
        extra: dict[str, str] = {}
        done = False
        redo = False
        print_item(
            item, ai_by_id.get(item["id"]), idx + 1, len(order), {item["id"]} & set(gold_by_id)
        )
        while True:
            try:
                k = input("  > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\ninterrupted — labels already saved stay saved")
                return 0
            if k == "c":
                if lab["relevance"] is None or lab["complete"] is None:
                    print("  need relevance (1/2/3) AND completeness (f/i) before confirm")
                    continue
                extra = {
                    "confidence": "ok",
                    "rater": rater,
                    "labelled_at": datetime.now(UTC).isoformat(),
                }
                done = True
                break
            elif k in _RELEVANCE:
                lab["relevance"] = k
            elif k == "f":
                lab["complete"] = True
            elif k == "i":
                lab["complete"] = False
            elif k == "y":
                lab["risk"] = True
            elif k == "n":
                lab["risk"] = False
            elif k == "p":
                print(
                    f"  gold={len(gold_by_id)}/{GOLD_TARGET}  remaining={GOLD_TARGET - len(gold_by_id)}"
                )
            elif k == "s":
                break
            elif k == "u":
                if gold and out_path.exists():
                    removed = gold.pop()
                    with out_path.open("w") as fh:
                        for g in gold:
                            fh.write(json.dumps(g) + "\n")
                    gold_by_id = {g["id"]: g for g in gold}
                    print(f"  undone last label ({removed['id']})")
                idx = max(idx - 1, 0)
                redo = True
                break
            elif k == "q":
                print(f"\nsaved so far: {len(gold_by_id)}")
                return 0
            elif k == "h":
                print(KEYS_HELP)
            else:
                print("  ? (h for help)")
        if redo:
            continue
        if done:
            rec = {
                "id": item["id"],
                "question": item.get("question"),
                **{k: v for k, v in lab.items()},
                **extra,
            }
            gold.append(rec)
            gold_by_id[item["id"]] = rec
            with out_path.open("a") as fh:
                fh.write(json.dumps(rec) + "\n")
            idx += 1
        else:
            idx += 1
    status(args, out_path)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--candidates", required=True, help="to_label.jsonl")
    ap.add_argument("--ai-labels", help="AI hint labels jsonl (display only)")
    ap.add_argument("--out", required=True, help="gold_labels.jsonl output (append)")
    ap.add_argument("--order", choices=["hard", "file"], default="hard")
    ap.add_argument("--status", action="store_true", help="print progress, exit")
    ap.add_argument("--rater", help="rater name for gold rows")
    args = ap.parse_args(argv)
    if args.status:
        return status(args, Path(args.out))
    return run(args)


if __name__ == "__main__":
    # Import-time sanity: ordering and identical-id collapse must not explode.
    demo = [{"id": "a"}, {"id": "b"}]
    assert order_candidates(demo, {"a": {"relevance": 3, "complete": True}}, "hard")[0]["id"] == "a"
    assert hard_score({"id": "x"}, {"relevance": 2}) == 0
    sys.exit(main())
