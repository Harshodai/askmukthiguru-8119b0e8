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
    METHOD_ECAPA_WINDOWED_V1,
    STATUS_PENDING_VOICE_CHECK,
    assert_speaker_write_allowed,
    automated_voice_fields,
    speaker_write_violations,
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


def decide_windowed(
    payload: dict[str, Any],
    windowed_verdict_row: Optional[dict[str, Any]],
    now: str,
    calibration: Optional[dict[str, Any]] = None,
    recheck: bool = False,
) -> tuple[str, dict[str, Any]]:
    """Return (outcome, payload updates) for a windowed ECAPA verdict. No evidence writes nothing.

    Acts on any child that has not been windowed yet (``voice_verification_method``
    is not ``windowed_v1``) — that covers pending children as well as the legacy
    span-slice and centroid rows, which are re-scored by the same pass. With
    ``recheck=True`` an already-windowed row is re-evaluated too (``--recheck-windowed``),
    which is how a stale score written under an older rule gets corrected.

    The recorded ``voice_score`` is the **worst** window cosine, never the mean: the
    gate is per-window, so a mean above the floor with one window below it is not a
    pass, and a stored mean could not be re-checked against the stored floor
    (review F2 / ``L-WINDOW-GATE-SCORES-WITH-ITS-WORST-WINDOW-1``).
    """
    if not windowed_verdict_row:
        return "windowed_no_evidence", {}
    if payload.get("voice_verification_method") == METHOD_ECAPA_WINDOWED_V1 and not recheck:
        return "not_pending", {}
    group = windowed_verdict_row.get("verdict_group")
    if group == "verified":
        verified = True
    elif group == "refused":
        verified = False
    else:
        # ``not_run`` / ``indeterminate``: no window scored. Never a refusal — the
        # row may simply lack audio, and demoting a legacy verified span on the
        # absence of evidence is a different (louder) decision than a refusal.
        return "windowed_no_evidence", {}

    # The gated statistic first; explicit ``cosine`` only for non-scorer callers.
    cosine = windowed_verdict_row.get("span_cosine_min")
    if cosine is None:
        cosine = windowed_verdict_row.get("cosine")
    if cosine is None:
        return "windowed_no_evidence", {}

    margin = windowed_verdict_row.get("span_margin_min")
    if margin is None:
        margin = windowed_verdict_row.get("margin")

    cal = calibration or {}
    c_floor = windowed_verdict_row.get("cosine_floor") or cal.get("cosine_floor")
    m_floor = windowed_verdict_row.get("margin_threshold") or cal.get("margin_threshold")

    model_rev = windowed_verdict_row.get("model_revision") or windowed_verdict_row.get("speaker_model_revision")
    cal_id = windowed_verdict_row.get("windowed_calibration_revision") or windowed_verdict_row.get(
        "calibration_revision"
    )

    evidence = {
        "cosine": cosine,
        "margin": margin,
        "cosine_floor": c_floor,
        "margin_threshold": m_floor,
    }

    fields = automated_voice_fields(
        verified=verified,
        evidence=evidence,
        model_revision=model_rev,
        calibration_id=cal_id,
        verified_at=now,
        window_check="pass" if verified else "fail",
        method=METHOD_ECAPA_WINDOWED_V1,
    )
    if "voice_score" not in fields:
        # Missing threshold, model revision or calibration id: the record cannot
        # state a score it cannot source. Leave the row untouched.
        return "windowed_no_evidence", {}
    if verified and fields.get("speaker_verified") is not True:
        return "guard_refused", {}
    updates = {k: v for k, v in fields.items() if k in ALLOWED_KEYS}
    assert_speaker_write_allowed({**payload, **updates})
    if verified:
        return "promoted", updates
    return ("demoted" if payload.get("speaker_verified") is True else "ecapa_failed"), updates


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
    ap.add_argument("--verdicts-jsonl", default="")
    ap.add_argument("--windows-jsonl", default="")
    ap.add_argument("--report", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--snapshot", default="", help="snapshot name taken just before this apply")
    ap.add_argument("--before-out", default="")
    ap.add_argument("--verified-at", default=dt.datetime.now(dt.UTC).isoformat())
    ap.add_argument("--windowed-verdicts-jsonl", default="", help="optional windowed ECAPA verdicts jsonl")
    ap.add_argument("--windowed-calibration", default="", help="optional windowed calibration json")
    ap.add_argument(
        "--recheck-windowed",
        action="store_true",
        help=(
            "re-evaluate rows already written as ecapa_voxceleb_windowed_v1, correcting a "
            "score stamped under an older rule. Only the voice keys are rewritten."
        ),
    )
    ap.add_argument(
        "--clear-refused-timestamps",
        action="store_true",
        help=(
            "repair only: clear voice_verified_at on children whose speaker_verified is not "
            "True. A refused span was never verified, so a verification timestamp on it "
            "misstates history (review F3). Nothing else is touched."
        ),
    )
    ap.add_argument(
        "--demote-invalid",
        action="store_true",
        help=(
            "repair only: demote any child that claims speaker_verified=true but violates the "
            "write rule in domain.speaker_provenance (e.g. the 12 legacy centroid rows). The "
            "evidence keys stay; only the claim is withdrawn (review F1)."
        ),
    )
    a = ap.parse_args(argv)

    if a.collection != SHADOW_COLLECTION:
        print(f"refusing: this writer only targets {SHADOW_COLLECTION}", file=sys.stderr)
        return 2
    if a.clear_refused_timestamps and a.demote_invalid:
        print("refusing: --clear-refused-timestamps and --demote-invalid are separate repairs", file=sys.stderr)
        return 2
    if (
        not a.clear_refused_timestamps
        and not a.demote_invalid
        and not a.windowed_verdicts_jsonl
        and not (a.verdicts_jsonl and a.windows_jsonl)
    ):
        print("refusing: either --windowed-verdicts-jsonl or both (--verdicts-jsonl and --windows-jsonl) required", file=sys.stderr)
        return 2
    if a.apply and not (a.snapshot and a.before_out):
        print("refusing --apply: --snapshot and --before-out are required", file=sys.stderr)
        return 2
    children = scroll_children(a.qdrant_url, a.collection)
    plan: list[tuple[str, dict, dict]] = []
    counts: Counter[str] = Counter()

    if a.demote_invalid:
        for pid, payload in children:
            if payload.get("speaker_verified") is not True:
                counts["already_unverified"] += 1
                continue
            violations = speaker_write_violations(payload)
            if not violations:
                counts["valid_untouched"] += 1
                continue
            method = str(payload.get("voice_verification_method") or "no_method")
            counts[f"demoted:{method}"] += 1
            for violation in violations:
                counts[f"reason:{violation.split(':')[0]}"] += 1
            plan.append(
                (
                    pid,
                    payload,
                    {
                        "speaker_verified": False,
                        "speaker_verification_status": STATUS_PENDING_VOICE_CHECK,
                        "voice_verification_method": None,
                        "voice_verified_at": None,
                    },
                )
            )
    elif a.clear_refused_timestamps:
        for pid, payload in children:
            if payload.get("speaker_verified") is True:
                counts["verified_untouched"] += 1
                continue
            if payload.get("voice_verified_at") is None:
                counts["no_timestamp"] += 1
                continue
            counts["timestamp_cleared"] += 1
            plan.append((pid, payload, {"voice_verified_at": None}))
    elif a.windowed_verdicts_jsonl:
        cal = json.loads(Path(a.windowed_calibration).read_text()) if a.windowed_calibration else {}
        windowed_dict = _jsonl(a.windowed_verdicts_jsonl)
        for pid, payload in children:
            sid = payload.get("source_span_id")
            if sid not in windowed_dict:
                counts["not_in_windowed_set"] += 1
                continue
            outcome, updates = decide_windowed(
                payload, windowed_dict.get(sid), a.verified_at, cal, recheck=a.recheck_windowed
            )
            counts[outcome] += 1
            if updates:
                plan.append((pid, payload, updates))
    else:
        verdicts, windows = _jsonl(a.verdicts_jsonl), _jsonl(a.windows_jsonl)
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
