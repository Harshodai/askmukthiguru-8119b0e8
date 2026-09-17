"""Build per-teacher voice profiles from verbatim guru speech in Qdrant.

This is the repeatable onboarding path for teacher N+1: point it at the
collection, it partitions by ``teacher_id``, keeps only verbatim speech, fits a
style centroid per teacher, and validates each one against a machine-prose
negative control before writing it. Nothing here is hand-written per teacher.

    .venv/bin/python -m scripts.ops.build_voice_profiles --dry-run
    .venv/bin/python -m scripts.ops.build_voice_profiles --apply

WHY A VERBATIM FILTER IS MANDATORY
----------------------------------
Audited 2026-09-15: ``raptor_level=1`` chunks (3,448 of 12,904 points, 21.6% of
corpus words) are LLM-written RAPTOR summaries, and they are OVER-SELECTED by
retrieval on doctrinal questions — ~36% of retrieved context words, a ~1.7x
over-representation. Their register is article prose: median 115 words, 92.5%
contain no "you", nominalization density 7.5/100 words.

Fitting a "how the Guru speaks" centroid on all 12,904 points would encode that
article voice as the target and then score it as success. The filter is the
whole point of the instrument.

The leaf chunks are not automatically usable either: 74.8% are a single sentence
and 73.8% contain no "you" — the ingestion pipeline chunked continuous discourse
into de-personalised propositions ("A person's parents are the people's
parents"). Only chunks that still read as continuous address are kept.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from datetime import UTC, datetime

from services.voice.style import (
    MIN_WORDS_FOR_SCORE,
    ProfileProvenance,
    build_profile,
    save_profile,
    strip_chunk_headers,
    validate_profile,
)

DEFAULT_COLLECTION = "spiritual_wisdom_contextual"
DEFAULT_QDRANT = "http://localhost:6333"

# Structural test for "this chunk is still continuous spoken address".
# Used when no ingestion-time provenance stamp is available.
MIN_SENTENCES = 3
MIN_SECOND_PERSON = 2
MIN_WORDS = 60

_SENT_RE = re.compile(r"[.!?]")
_YOU_RE = re.compile(r"\b(?:you|your|yourself)\b", re.I)

# Ingestion-side provenance field, owned by the corpus/ingest lane. When it
# exists we prefer it over our structural heuristic. Absent today (2026-09-15).
PROVENANCE_FIELD = "provenance"
VERBATIM_VALUES = {"verbatim", "verbatim_speech", "transcript"}


def scroll(qdrant: str, collection: str, fields: list[str]) -> list[dict]:
    """Page the whole collection. Qdrant has no auth in this environment."""
    url = f"{qdrant}/collections/{collection}/points/scroll"
    out: list[dict] = []
    offset = None
    while True:
        body: dict = {"limit": 1000, "with_payload": fields, "with_vector": False}
        if offset is not None:
            body["offset"] = offset
        req = urllib.request.Request(
            url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.load(resp)["result"]
        out.extend(p["payload"] for p in result["points"])
        offset = result.get("next_page_offset")
        if not offset:
            return out


def is_verbatim(payload: dict, body: str) -> bool:
    """True when this chunk is the teacher actually speaking, at length.

    Prefers an ingestion-time provenance stamp; falls back to structure.
    """
    stamp = str(payload.get(PROVENANCE_FIELD) or "").strip().lower()
    if stamp:
        return stamp in VERBATIM_VALUES
    if payload.get("raptor_level") == 1:
        return False
    return (
        len(body.split()) >= MIN_WORDS
        and len(_SENT_RE.findall(body)) >= MIN_SENTENCES
        and len(_YOU_RE.findall(body)) >= MIN_SECOND_PERSON
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--qdrant", default=DEFAULT_QDRANT)
    ap.add_argument("--collection", default=DEFAULT_COLLECTION)
    ap.add_argument("--apply", action="store_true", help="write profiles to disk")
    ap.add_argument("--dry-run", action="store_true", help="report only (default)")
    args = ap.parse_args(argv)
    if not args.apply:
        args.dry_run = True

    payloads = scroll(
        args.qdrant,
        args.collection,
        ["text", "teacher_id", "raptor_level", PROVENANCE_FIELD],
    )
    print(f"scanned {len(payloads)} points from {args.collection}")

    verbatim: dict[str, list[str]] = {}
    machine: list[str] = []
    for payload in payloads:
        body = strip_chunk_headers(payload.get("text") or "")
        if not body:
            continue
        if payload.get("raptor_level") == 1:
            machine.append(body)
            continue
        if is_verbatim(payload, body):
            verbatim.setdefault(str(payload.get("teacher_id") or "unknown"), []).append(body)

    total = sum(len(v) for v in verbatim.values())
    print(f"verbatim speech chunks: {total}  |  machine-prose control: {len(machine)}")
    if not machine:
        print("ERROR: no negative control available; cannot validate profiles", file=sys.stderr)
        return 1

    exit_code = 0
    for teacher_id, samples in sorted(verbatim.items(), key=lambda kv: -len(kv[1])):
        usable = [s for s in samples if len(s.split()) >= MIN_WORDS_FOR_SCORE]
        # Hold out every 5th sample so validation is not scored on fitted data.
        holdout = usable[::5]
        fit = [s for i, s in enumerate(usable) if i % 5]
        if len(fit) < 30:
            print(f"  {teacher_id:22s} SKIP — only {len(fit)} fit samples (need >= 30)")
            continue
        provenance = ProfileProvenance(
            source_collection=args.collection,
            teacher_filter=f"teacher_id={teacher_id}",
            verbatim_criteria=(
                f"{PROVENANCE_FIELD} in {sorted(VERBATIM_VALUES)} if stamped, else "
                f"raptor_level=0 and >={MIN_WORDS} words and >={MIN_SENTENCES} sentences "
                f"and >={MIN_SECOND_PERSON} second-person pronouns"
            ),
            built_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        profile = build_profile(teacher_id, fit, provenance=provenance)
        report = validate_profile(profile, holdout, machine)
        profile = profile.model_copy(
            update={"provenance": profile.provenance.model_copy(update={"validation": report})}
        )
        ok = "CERTIFIED" if profile.is_certified else "NOT CERTIFIED"
        print(
            f"  {teacher_id:22s} fit={len(fit):5d} holdout={len(holdout):4d} "
            f"AUC={report.get('auc', 0):.3f} "
            f"human={report.get('human_median', 0):.2f} machine={report.get('machine_median', 0):.2f} "
            f"[{ok}]"
        )
        if not profile.is_certified:
            exit_code = 1
        if args.apply:
            print(f"      wrote {save_profile(profile)}")

    if args.dry_run:
        print("\ndry run — nothing written; re-run with --apply")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
