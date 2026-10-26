#!/usr/bin/env python3
"""Mine real seeker questions from speaker-labelled recording turns.

**Read-only and offline.** Every gold question so far is AI-written (audit
2026-10-25, review R1). Interviews and satsang Q&A already hold real questions:
a host or guest asks, then the teacher answers. This tool pairs each such
question with the teacher turn(s) that follow it, so a test set has real
phrasing and a clip that answers it by construction.

Input: JSONL, one speaker-labelled turn per line, in time order per video:

    {"video_id": "abc", "start_ms": 1000, "end_ms": 9000,
     "speaker_role": "host" | "guest" | "guru" | "unknown", "text": "..."}

Output: JSONL, one candidate per line, plus a summary. A question turn is
test INPUT only. It is host or guest speech, so it is never served, never
indexed, and never shown as the teacher's words. Every row carries
``reviewed: false``: a human confirms the question is a real, self-contained
seeker question and that the answer span answers it before it enters a gold set.

Usage:
    python -m scripts.ops.mine_seeker_questions turns.jsonl --out pairs.jsonl \\
        --summary summary.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

QUESTION_ROLES = frozenset({"host", "guest"})
ANSWER_ROLE = "guru"
MIN_QUESTION_WORDS = 4
MAX_QUESTION_WORDS = 60
MAX_GAP_MS = 30_000  # the teacher must start answering within 30 s
MAX_ANSWER_TURNS = 3
MAX_ANSWER_MS = 120_000

# Question types follow the 14 types in the core-answer-quality review (§1); a
# keyword guess only, to help a human stratify. It never decides anything.
_TYPE_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("practice", re.compile(r"\b(how (do|can|should) i (practi[sc]e|meditate)|meditation|soul ?sync|serene mind)\b", re.I)),
    ("relationship", re.compile(r"\b(husband|wife|spouse|partner|marriage|parents?|children|child|family|relationship)\b", re.I)),
    ("grief", re.compile(r"\b(death|died|loss|lost (my|a)|grief|mourning)\b", re.I)),
    ("emotion", re.compile(r"\b(anxi\w+|fear|anger|angry|sad\w*|depress\w*|stress\w*|lonel\w+|worr\w+|overwhelm\w+)\b", re.I)),
    ("concept", re.compile(r"\b(what is|what does|meaning of|beautiful state|consciousness|enlightenment|awakening)\b", re.I)),
)  # fmt: skip


def classify(question: str) -> str:
    for name, pattern in _TYPE_RULES:
        if pattern.search(question):
            return name
    return "other"


def _words(text: str) -> int:
    return len(text.split())


def is_seeker_question(turn: dict[str, Any]) -> bool:
    """A host/guest turn that is a real question of usable length."""
    if str(turn.get("speaker_role", "")).lower() not in QUESTION_ROLES:
        return False
    text = str(turn.get("text", "")).strip()
    if "?" not in text:
        return False
    return MIN_QUESTION_WORDS <= _words(text) <= MAX_QUESTION_WORDS


def _by_video(turns: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for turn in turns:
        grouped.setdefault(str(turn.get("video_id", "")), []).append(turn)
    for rows in grouped.values():
        rows.sort(key=lambda t: (int(t.get("start_ms", 0)), int(t.get("end_ms", 0))))
    return grouped


def mine(turns: Iterable[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    """Yield one candidate per question that a teacher turn answers in time."""
    for video_id, rows in _by_video(turns).items():
        if not video_id:
            continue
        for i, turn in enumerate(rows):
            if not is_seeker_question(turn):
                continue
            q_end = int(turn.get("end_ms", 0))
            answer: list[dict[str, Any]] = []
            for nxt in rows[i + 1 :]:
                role = str(nxt.get("speaker_role", "")).lower()
                if role != ANSWER_ROLE:
                    if answer:
                        break  # the teacher's run ended
                    if is_seeker_question(nxt):
                        break  # a new qualifying question intervened before an answer started
                    if int(nxt.get("start_ms", 0)) - q_end > MAX_GAP_MS:
                        break
                    continue  # another host line before the answer starts
                if not answer and int(nxt.get("start_ms", 0)) - q_end > MAX_GAP_MS:
                    break
                start_0 = (
                    int(answer[0].get("start_ms", 0)) if answer else int(nxt.get("start_ms", 0))
                )
                prospective_duration = int(nxt.get("end_ms", 0)) - start_0
                # A long FIRST teacher turn is still the answer: refusing it would
                # drop the question entirely (and long teachings are exactly the
                # high-value ones). Only a turn that grows an existing answer past
                # the cap stops collection.
                if answer and prospective_duration > MAX_ANSWER_MS:
                    break
                answer.append(nxt)
                if len(answer) >= MAX_ANSWER_TURNS or prospective_duration >= MAX_ANSWER_MS:
                    break
            if not answer:
                continue
            question = str(turn["text"]).strip()
            yield {
                "video_id": video_id,
                "question": question,
                "question_start_ms": int(turn.get("start_ms", 0)),
                "question_end_ms": q_end,
                "question_speaker_role": str(turn.get("speaker_role", "")).lower(),
                "answer_start_ms": int(answer[0].get("start_ms", 0)),
                "answer_end_ms": int(answer[-1].get("end_ms", 0)),
                "answer_text": " ".join(str(a.get("text", "")).strip() for a in answer),
                "type_guess": classify(question),
                "use": "test_input_only_never_served",
                "reviewed": False,
            }


def read_turns(path: Path) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{n}: not JSON ({exc})") from exc
            if not isinstance(row, dict):
                raise SystemExit(f"{path}:{n}: expected an object")
            turns.append(row)
    return turns


def summarize(rows: list[dict[str, Any]], total_turns: int) -> dict[str, Any]:
    return {
        "turns_read": total_turns,
        "candidates": len(rows),
        "videos_with_candidates": len({r["video_id"] for r in rows}),
        "by_type_guess": dict(Counter(r["type_guess"] for r in rows)),
        "reviewed": 0,
        "note": "All candidates need human review before they enter a gold set.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("turns", type=Path, help="JSONL of speaker-labelled turns")
    parser.add_argument("--out", type=Path, required=True, help="candidate pairs JSONL")
    parser.add_argument("--summary", type=Path, help="summary JSON")
    args = parser.parse_args(argv)

    input_path = args.turns.resolve()
    out_path = args.out.resolve()
    summary_path = args.summary.resolve() if args.summary else None
    paths = [input_path, out_path]
    if summary_path is not None:
        paths.append(summary_path)
    if len(paths) != len(set(paths)):
        raise SystemExit("Input, output, and summary paths must all be distinct.")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)

    turns = read_turns(args.turns)
    rows = list(mine(turns))
    with args.out.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary = summarize(rows, len(turns))
    if args.summary:
        args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
