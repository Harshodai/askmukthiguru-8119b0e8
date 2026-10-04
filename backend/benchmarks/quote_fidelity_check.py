"""Fail a benchmark run when a rendered teacher quote is not what the source says.

The ruthless benchmarks pass an answer on formatting: a quote is present, no
bullets, an audio strip exists. None of them check that the quoted words are in
the cited video, that the named speaker is the one in that video, that the
title is real, or that the timestamp lands where the words are. This script
checks all four against the stored Qdrant payloads and exits 1 on any failure.

Usage (from backend/):

    # answers.md: rendered answers, one "## Case <n>" heading per answer.
    # First-person hero quotes live in first_person_v7; chat quotes in
    # spiritual_wisdom_contextual. --collection may be repeated: a video's
    # payloads are read from every collection given.
    python3 benchmarks/quote_fidelity_check.py --answers answers.md \
        --qdrant-url http://localhost:6333 --collection spiritual_wisdom_contextual

    # offline, against a JSON dump of the source records
    python3 benchmarks/quote_fidelity_check.py --answers answers.json \
        --sources-json sources.json

``--answers`` is markdown (split on ``## Case``/``#### Case`` headings) or a JSON
list of ``{"case": ..., "answer": ...}``. ``--titles-csv`` may supply real
YouTube titles (``video_id,title`` columns, e.g.
``../docs/attribution/ekam_speaker_request.csv``) for videos whose stored title is
just the id; speaker labels from that file are NOT used, because its own README
says they are unverified.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.quote_fidelity import (  # noqa: E402
    AttributedQuote,
    SourceRecord,
    cross_case_conflicts,
    parse_attributed_quotes,
    source_from_payloads,
    verify_quote,
)

_CASE_RE = re.compile(r"^#{2,4}\s*Case\s+([^\n:]+)", re.MULTILINE | re.IGNORECASE)


def load_answers(path: Path) -> list[tuple[str, str]]:
    raw = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        return [
            (str(a.get("case", i + 1)), a.get("answer", "")) for i, a in enumerate(json.loads(raw))
        ]
    marks = list(_CASE_RE.finditer(raw))
    if not marks:
        return [("1", raw)]
    return [
        (
            m.group(1).strip(),
            raw[m.end() : marks[i + 1].start() if i + 1 < len(marks) else len(raw)],
        )
        for i, m in enumerate(marks)
    ]


def fetch_from_qdrant(url: str, collection: str, video_id: str) -> list[dict]:
    from qdrant_client import QdrantClient, models

    client = QdrantClient(url=url, api_key=os.environ.get("QDRANT_API_KEY") or None, timeout=30)
    urls = [
        f"https://www.youtube.com/watch?v={video_id}",
        f"https://youtube.com/watch?v={video_id}",
        f"https://youtu.be/{video_id}",
    ]
    flt = models.Filter(
        should=[
            models.FieldCondition(key="video_id", match=models.MatchValue(value=video_id)),
            models.FieldCondition(key="source_url", match=models.MatchAny(any=urls)),
        ]
    )
    payloads, offset = [], None
    while True:
        points, offset = client.scroll(
            collection_name=collection,
            scroll_filter=flt,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        payloads.extend(p.payload or {} for p in points)
        if offset is None:
            break
    payloads.sort(key=lambda p: (p.get("chunk_index") or 0, p.get("start_ms") or 0))
    return payloads


def load_titles_csv(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8") as f:
        return {row["video_id"]: row["title"] for row in csv.DictReader(f) if row.get("video_id")}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--answers", type=Path, required=True)
    ap.add_argument("--qdrant-url", default=os.environ.get("QDRANT_URL"))
    ap.add_argument(
        "--collection",
        action="append",
        help="repeatable; default first_person_v7 + spiritual_wisdom_contextual",
    )
    ap.add_argument(
        "--sources-json", type=Path, help="{video_id: [payload, ...]} instead of Qdrant"
    )
    ap.add_argument("--titles-csv", type=Path)
    ap.add_argument("--json-out", type=Path)
    args = ap.parse_args(argv)

    quotes: list[AttributedQuote] = []
    for case, answer in load_answers(args.answers):
        quotes.extend(parse_attributed_quotes(answer, case=case))
    if not quotes:
        print("No attributed quotes found in the answers; nothing was verified.")
        return 0

    offline = json.loads(args.sources_json.read_text()) if args.sources_json else None
    if offline is None and not args.qdrant_url:
        print("Need --qdrant-url or --sources-json: a quote cannot be verified without its source.")
        return 2
    titles = load_titles_csv(args.titles_csv) if args.titles_csv else {}
    collections = args.collection or ["first_person_v7", "spiritual_wisdom_contextual"]

    cache: dict[str, SourceRecord | None] = {}
    rows, failed = [], 0
    for q in quotes:
        if q.video_id not in cache:
            payloads = (
                offline.get(q.video_id, [])
                if offline is not None
                else [
                    p
                    for coll in collections
                    for p in fetch_from_qdrant(args.qdrant_url, coll, q.video_id)
                ]
            )
            src = source_from_payloads(q.video_id, payloads) if payloads else None
            if src and titles.get(q.video_id) and (not src.title or src.title == q.video_id):
                src.title = titles[q.video_id]
            cache[q.video_id] = src
        v = verify_quote(q, cache[q.video_id])
        failed += not v.ok
        src = cache[q.video_id]
        rows.append(
            {
                "case": q.case,
                "video_id": q.video_id,
                "shown_speaker": q.speaker,
                "shown_title": q.title,
                "stored_title": src.title if src else None,
                "stored_teacher_id": src.teacher_id if src else None,
                "start_seconds": q.start_seconds,
                "verdict": "PASS" if v.ok else "FAIL",
                "failures": v.failures,
                "missing_sentences": v.missing_sentences,
            }
        )
        print(
            f"[{rows[-1]['verdict']}] case {q.case} · {q.video_id} · {q.speaker} · {', '.join(v.failures) or 'ok'}"
        )
        for s in v.missing_sentences:
            print(f"        not in source: {s[:110]}")

    conflicts = cross_case_conflicts(quotes)
    for c in conflicts:
        print(f"[FAIL] cross-case: {c}")

    if args.json_out:
        args.json_out.write_text(
            json.dumps({"quotes": rows, "conflicts": conflicts}, indent=2, ensure_ascii=False)
        )

    total = len(quotes)
    print(f"\n{total - failed}/{total} quotes verified; {len(conflicts)} cross-case conflicts.")
    return 1 if failed or conflicts else 0


if __name__ == "__main__":
    sys.exit(main())
