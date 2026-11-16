#!/usr/bin/env python3
"""Write per-span ECAPA verdicts onto ``first_person_v12_shadow`` children (payload only).

Why: ``resegment_v2.py`` writes every re-cut span ``speaker_verified=false`` /
``pending_voice_check``; the store serves only ``speaker_verified=true`` with evidence
(CLAUDE.md invariant 23). ``backfill_v10_voice_method.py`` (never committed) would not promote
false->true, so this is the promote path, for the shadow collection ONLY (any other name is
refused).

Inputs are the span-slice regenerator's ``--out-verdicts-jsonl`` (served window, pinned
calibration) and ``score_v10_unchecked_speakers.py --out`` (diarization window check).

Policy (a missing check is never evidence):
* verdict ``verified`` AND window ``window_pass``        -> speaker_verified=true, method v2
* verdict ``refused_*``                                  -> speaker_verified=false, ``ecapa_failed``
* anything else (no verdict, audio failure, ``no_diarization``, verified + ``window_fail``)
  -> untouched, stays ``pending_voice_check``
Fields come from ``domain.speaker_provenance.automated_voice_fields`` and every write passes
``assert_speaker_write_allowed``. Only ``ALLOWED_KEYS`` are written; never text or hashes.

    backend/.venv/bin/python3 backend/scripts/ops/apply_shadow_voice_verdicts.py \\
        --verdicts-jsonl v.jsonl --windows-jsonl w.jsonl --report r.json   # dry run
    ... --apply --snapshot <name> --before-out before.jsonl                # gated write
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Optional

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from domain.speaker_provenance import (  # noqa: E402
    AUTOMATED_PROVENANCE_KEYS,
    STATUS_PENDING_VOICE_CHECK,
    assert_speaker_write_allowed,
    automated_voice_fields,
)

SHADOW_COLLECTION = "first_person_v12_shadow"
ALLOWED_KEYS = (*AUTOMATED_PROVENANCE_KEYS, "speaker_verified")
EVIDENCE_FIELDS = ("cosine", "margin", "cosine_floor", "margin_threshold")


def decide(
    payload: dict[str, Any],
    verdict: Optional[dict[str, Any]],
    window: Optional[dict[str, Any]],
    now: str,
) -> tuple[str, dict[str, Any]]:
    """Return (outcome, payload updates). ``no_evidence`` writes nothing."""
    if payload.get("speaker_verification_status") != STATUS_PENDING_VOICE_CHECK:
        return "not_pending", {}
    if not verdict or verdict.get("source_span_id") != payload.get("source_span_id"):
        return "no_evidence", {}
    group = verdict.get("verdict_group")
    wcheck = (window or {}).get("verdict")
    if group == "refused":
        verified = False
    elif group == "verified" and wcheck == "window_pass":
        verified = True
    else:
        # ECAPA verified + window_fail stays pending: the diarization cue is weak on long
        # re-cut spans and is not evidence of a wrong speaker (owner decision to relax/keep).
        return "no_evidence", {}
    fields = automated_voice_fields(
        verified=verified,
        evidence={k: verdict.get(k) for k in EVIDENCE_FIELDS},
        model_revision=verdict.get("speaker_model_revision"),
        calibration_id=verdict.get("calibration_revision"),
        verified_at=now,
        window_check={"window_pass": "pass", "window_fail": "fail"}.get(wcheck),
    )
    if verified and fields.get("speaker_verified") is not True:
        return "guard_refused", {}  # incomplete record: stays pending
    updates = {k: v for k, v in fields.items() if k in ALLOWED_KEYS}
    assert_speaker_write_allowed({**payload, **updates})
    return ("promoted" if verified else "ecapa_failed"), updates


def _req(url: str, body: Optional[dict] = None, method: str = "POST") -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data, {"Content-Type": "application/json"}, method=method)
    return json.load(urllib.request.urlopen(req, timeout=120))


def scroll_children(url: str, coll: str) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    off = None
    flt = {"must": [{"key": "record_type", "match": {"value": "retrieval_child"}}]}
    while True:
        body = {"limit": 500, "offset": off, "with_payload": True, "with_vector": False, "filter": flt}
        r = _req(f"{url}/collections/{coll}/points/scroll", body)["result"]
        out += [(p["id"], p["payload"]) for p in r["points"]]
        off = r["next_page_offset"]
        if off is None:
            return out


def _jsonl(path: str) -> dict[str, dict]:
    rows = (json.loads(x) for x in Path(path).read_text().splitlines() if x.strip())
    return {r["source_span_id"]: r for r in rows}


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--collection", default=SHADOW_COLLECTION)
    ap.add_argument("--qdrant-url", default="http://localhost:6333")
    ap.add_argument("--verdicts-jsonl", required=True)
    ap.add_argument("--windows-jsonl", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--snapshot", default="", help="snapshot name taken just before this apply")
    ap.add_argument("--before-out", default="")
    ap.add_argument("--verified-at", default=dt.datetime.now(dt.timezone.utc).isoformat())
    a = ap.parse_args(argv)

    if a.collection != SHADOW_COLLECTION:
        print(f"refusing: this writer only targets {SHADOW_COLLECTION}", file=sys.stderr)
        return 2
    if a.apply and not (a.snapshot and a.before_out):
        print("refusing --apply: --snapshot and --before-out are required", file=sys.stderr)
        return 2
    verdicts, windows = _jsonl(a.verdicts_jsonl), _jsonl(a.windows_jsonl)
    children = scroll_children(a.qdrant_url, a.collection)
    plan: list[tuple[str, dict, dict]] = []
    counts: Counter[str] = Counter()
    for pid, payload in children:
        sid = payload.get("source_span_id")
        outcome, updates = decide(payload, verdicts.get(sid), windows.get(sid), a.verified_at)
        counts[outcome] += 1
        if updates:
            plan.append((pid, payload, updates))
    report: dict[str, Any] = {
        "collection": a.collection,
        "mode": "apply" if a.apply else "dry_run",
        "children": len(children),
        "outcomes": dict(counts),
        "written": 0,
    }
    if a.apply:
        snaps = _req(f"{a.qdrant_url}/collections/{a.collection}/snapshots", method="GET")["result"]
        if a.snapshot not in [s["name"] for s in snaps]:
            print(f"refusing --apply: snapshot {a.snapshot!r} not found", file=sys.stderr)
            return 2
        with open(a.before_out, "w") as fh:  # previous values of every key we may write
            for pid, payload, _ in plan:
                before = {k: payload.get(k) for k in ALLOWED_KEYS}
                fh.write(json.dumps({"id": pid, "before": before}) + "\n")
        for pid, _, updates in plan:
            _req(
                f"{a.qdrant_url}/collections/{a.collection}/points/payload?wait=true",
                {"payload": updates, "points": [pid]},
            )
            report["written"] += 1
    Path(a.report).write_text(json.dumps(report, indent=1))
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
