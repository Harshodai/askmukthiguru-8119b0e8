#!/usr/bin/env python3
"""Run the owner-only first-person local review candidate preview from a shell.

This is the **zero-infrastructure** way to exercise the local review mode:
no server, no Qdrant, no alias, no Redis, no LLM. It reads the immutable
Phase-4 candidate manifests through the pinned contract and prints what the
mode would serve, with the same verification the HTTP route performs.

Every answer — and every citation — carries the canonical two-line
owner-only label::

    REVIEW CANDIDATE — NOT PUBLIC RELEASE
    AUTOMATED EVIDENCE — NOT HUMAN-CERTIFIED ATTRIBUTION

The attribution behind a citation is automated evidence (a pinned ECAPA model
scored against an anchor-derived reference), not a human certification.

Exit codes
----------
=====  ===================================================================
0      The query was answered (or honestly abstained) by the local review
       mode.
1      The mode refused to start: a pinned artifact is missing, unreadable,
       or stale/modified. Fail closed. Nothing was served.
2      Bad usage.
=====  ===================================================================

Usage
-----
    python backend/scripts/ops/fp_local_review_preview.py "What is meditation?"
    python backend/scripts/ops/fp_local_review_preview.py --teacher krishnaji "fear"
    python backend/scripts/ops/fp_local_review_preview.py --status
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _resolve_backend_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "services" / "first_person_local_review.py").is_file():
            return candidate
        nested = candidate / "backend"
        if (nested / "services" / "first_person_local_review.py").is_file():
            return nested
    raise RuntimeError(f"cannot locate the backend package root from {here}")


_BACKEND = _resolve_backend_root()
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.first_person_local_review import (  # noqa: E402
    REVIEW_LABEL_LINES,
    LocalReviewError,
    LocalReviewService,
    load_local_review_config,
)


def _print_label() -> None:
    """Print the owner-only label. It is never optional."""
    print("=" * 78)
    for line in REVIEW_LABEL_LINES:
        print(line)
    print("=" * 78)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("query", nargs="*", help="the question to run")
    parser.add_argument("--teacher", default="both", help="preethaji | krishnaji | both")
    parser.add_argument("--max-clips", type=int, default=3)
    parser.add_argument("--contract", default=None, help="path to the local-review contract")
    parser.add_argument("--root", default=None, help="repository root the artifacts resolve against")
    parser.add_argument("--status", action="store_true", help="print the startup state and exit")
    parser.add_argument("--json", action="store_true", help="print the raw answer payload")
    args = parser.parse_args(argv)

    try:
        config = load_local_review_config(args.contract, repo_root=args.root)
        service = LocalReviewService(config)
        info = service.startup_check()
    except LocalReviewError as exc:
        _print_label()
        print(f"[fp-local-review] REFUSED: {exc}", file=sys.stderr)
        return 1

    if args.status:
        _print_label()
        print(json.dumps(info, indent=2, sort_keys=True))
        return 0

    query = " ".join(args.query).strip()
    if not query:
        print("[fp-local-review] no query given (use --status for the startup state)", file=sys.stderr)
        return 2

    answer = service.query(query, teacher_id=args.teacher, max_clips=args.max_clips)
    if args.json:
        print(json.dumps(answer.to_dict(), indent=2, sort_keys=True, ensure_ascii=False))
        return 0

    meta = answer.metadata
    _print_label()
    print(f"evidence     : {meta.get('evidence_policy')}  (not human-certified)")
    print(f"corpus       : {meta.get('corpus_version')}  tier={meta.get('tier')}")
    print(f"collection   : {meta.get('collection')}  (qdrant reads={meta.get('qdrant_reads')})")
    print(f"status       : {answer.status}  abstain={answer.abstain_reason}")
    print("=" * 78)
    print(answer.answer_text)
    for index, citation in enumerate(answer.citations, start=1):
        print("-" * 78)
        for line in REVIEW_LABEL_LINES:
            print(line)
        print(f"[{index}] {citation['guru_id']}  span={citation['source_span_id']}")
        print(
            f"    audio {citation['audio_start_ms']}-{citation['audio_end_ms']} ms  "
            f"({citation['playback_start_seconds']}-{citation['playback_end_seconds']} s)"
        )
        print(f"    text_hash  {citation['source_text_hash']}")
        print(f"    speaker    {citation['speaker_verdict']}  cosine={citation['cosine']} "
              f"floor={citation['cosine_floor']}")
        print(f"    rights     {citation['rights_status']}")
        print(f"    source     {citation['playback_url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
