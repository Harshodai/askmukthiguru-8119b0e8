#!/usr/bin/env python3
"""Deterministic, merge-only resegmentation of ``first_person_v10`` (dry run by default).

Source of truth (measured 2026-11-16): the v10 child spans themselves (exact
``start_ms``/``end_ms`` + ``verbatim_text`` + hashes). Word-level timing exists on
disk for 454/491 videos (``mass_ingest_2026-10/raw/*_parakeet.json`` and
``transcripts_B/*.json``) but it does NOT index-align with v10 ``word_start``/
``word_end`` and its text differs from ``verbatim_text``, so a mid-span split cannot
be proven verbatim. v1 is therefore merge-only over adjacent spans (plus dedupe);
splitting over-cap clips is a v2 that needs a reviewed alignment step.

Steps, in order: exact-text collapse -> containment drop -> boundary-closing merges.
Nothing is written anywhere except the local audit dir, unless ``--apply`` passes its
guards; ``--apply`` only ever creates a NEW ``first_person_v12*shadow*`` collection.

Usage (host python, cwd backend/):
    .venv/bin/python3 scripts/ops/resegment_v10.py --dry-run --cap-s 90
    .venv/bin/python3 scripts/ops/resegment_v10.py --sweep 60,90,120,160
    .venv/bin/python3 scripts/ops/resegment_v10.py --apply --snapshot-confirmed --approved-by NAME
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import statistics
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
_REPO = _BACKEND.parent

CHUNKER_VERSION = "resegment_v10:merge_v1"
DEFAULT_OUT = _REPO / "audits" / "work" / "resegmentation-2026-11-16"
PROTECTED = frozenset(
    {
        "first_person_v7",
        "first_person_v8",
        "first_person_v9",
        "first_person_v10",
        "first_person_v11",
    }
)

CAP_S = 90.0  # merge/container cap; owner asked for a measured choice (see --sweep)
HARD_MAX_S = 160.0  # reported ceiling; originals above it are flagged, never dropped
MAX_WORDS = 300  # serve-time first_person_max_answer_words default
MIN_WORDS = 15  # invariant 14
MAX_GAP_MS = 1500  # a larger gap means playback would carry audio that is not in the text
MAX_STEPS = 4  # spans tried when closing one defect

# Explicit settings so gate results never depend on .env.
POLICY = SimpleNamespace(
    first_person_min_answer_words=MIN_WORDS,
    first_person_max_answer_words=MAX_WORDS,
    first_person_max_context_words=600,
)

# Reasons from the repo's `_standalone_problem` that a neighbouring span can fix.
FWD_REASONS = frozenset(
    {
        "ends_mid_sentence",
        "dangling_question_tail",
        "dangling_affirmation_tail",
        "incomplete_contrast",
    }
)
# dangling_enumeration is "the third point ..." with the earlier points missing: a HEAD defect.
BWD_REASONS = frozenset(
    {
        "orphan_opener",
        "discourse_opener",
        "severed_lowercase_opener",
        "dangling_fragment",
        "dangling_enumeration",
    }
)
# NEW (no repo detector exists for a promissory *tail*): clip ends on a setup sentence.
_PROMISSORY_TAIL_RE = re.compile(
    r"(?:let\s+(?:us|me)\s+(?:understand|see|look\s+at|explore|explain|share|begin|start)"
    r"|i(?:'ll|\s+will)\s+(?:tell|show|explain|share)\s+you"
    r"|here\s+is\s+(?:what|how|why))\b[^.!?]{0,60}[.:,]?\s*$",
    re.IGNORECASE,
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _words(text: str) -> int:
    return len(text.split())


def _dur(c: dict[str, Any]) -> float:
    return (c["end_ms"] - c["start_ms"]) / 1000.0


# ---------------------------------------------------------------- gates (imported, not reimplemented)
def standalone_problem(text: str) -> Optional[str]:
    from services.first_person_evidence_policy import _standalone_problem

    return _standalone_problem(text, settings_override=POLICY)


def boundary_kinds(text: str, *, soft: bool = True) -> frozenset[str]:
    """Which side needs a neighbour: "bwd" = head defect, "fwd" = tail defect."""
    from ingest.verbatim.boundaries import boundary_defects

    kinds: set[str] = set()
    sp = standalone_problem(text)
    if sp in FWD_REASONS:
        kinds.add("fwd")
    if sp in BWD_REASONS:
        kinds.add("bwd")
    for d in boundary_defects(text.split()):
        if d in (
            "head_conjunction",
            "head_headless_predicate",
            "head_fragment",
            "head_orphan_punctuation",
        ):
            kinds.add("bwd")
        elif d == "tail_dangling_word":
            kinds.add("fwd")
        elif soft and d == "head_lowercase":
            kinds.add("bwd")
        elif soft and d == "tail_no_terminal":
            kinds.add("fwd")
    if _PROMISSORY_TAIL_RE.search(text.strip()):
        kinds.add("fwd")
    return frozenset(kinds)


def content_problem(text: str) -> Optional[str]:
    """A `_standalone_problem` reason a merge cannot fix (event marker, health claim, ...)."""
    sp = standalone_problem(text)
    return None if sp in FWD_REASONS or sp in BWD_REASONS else sp


# ---------------------------------------------------------------- dedupe
def _is_gate_clean(c: dict[str, Any]) -> bool:
    return (
        c.get("quality_status") != "quarantined"
        and standalone_problem(c["verbatim_text"]) is None
        and MIN_WORDS <= _words(c["verbatim_text"]) <= MAX_WORDS
    )


def collapse_exact_duplicates(
    clips: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep one per identical-text group. Different guru_id in a group = attribution
    conflict: keep all, flag, escalate (never pick a winner)."""
    groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for c in clips:
        groups[_sha(c["verbatim_text"])].append(c)
    dropped: list[dict[str, Any]] = []
    drop_ids: set[str] = set()
    for members in groups.values():
        if len(members) < 2:
            continue
        if len({m["guru_id"] for m in members}) > 1:
            for m in members:
                m.setdefault("_flags", []).append("duplicate_text_attribution_conflict")
            continue
        members.sort(
            key=lambda m: (not m.get("speaker_verified"), m["video_id"], m["start_ms"], m["_id"])
        )
        keep = members[0]
        for m in members[1:]:
            drop_ids.add(m["_id"])
            dropped.append(
                {
                    "point_id": m["_id"],
                    "video_id": m["video_id"],
                    "start_ms": m["start_ms"],
                    "end_ms": m["end_ms"],
                    "reason": "exact_duplicate_text",
                    "kept_point_id": keep["_id"],
                }
            )
    return [c for c in clips if c["_id"] not in drop_ids], dropped


def drop_contained(
    clips: list[dict[str, Any]], cap_s: float
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Drop A when another clip of the same video+guru strictly contains it AND that
    container is gate-clean and within the cap (else the servable piece would be lost)."""
    by_video: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for c in clips:
        by_video[c["video_id"]].append(c)
    dropped: list[dict[str, Any]] = []
    drop_ids: set[str] = set()
    for vid_clips in by_video.values():
        for a in vid_clips:
            for b in vid_clips:
                if b is a or b["guru_id"] != a["guru_id"]:
                    continue
                inside = b["start_ms"] <= a["start_ms"] and b["end_ms"] >= a["end_ms"]
                if not inside or (b["start_ms"], b["end_ms"]) == (a["start_ms"], a["end_ms"]):
                    continue
                if _dur(b) <= cap_s and _is_gate_clean(b):
                    drop_ids.add(a["_id"])
                    dropped.append(
                        {
                            "point_id": a["_id"],
                            "video_id": a["video_id"],
                            "start_ms": a["start_ms"],
                            "end_ms": a["end_ms"],
                            "reason": "contained_in_clean_clip_under_cap",
                            "kept_point_id": b["_id"],
                        }
                    )
                    break
    return [c for c in clips if c["_id"] not in drop_ids], dropped


# ---------------------------------------------------------------- merge
def _join(unit: list[dict[str, Any]]) -> str:
    return " ".join(c["verbatim_text"] for c in unit)


def mergeable(
    a: dict[str, Any], b: dict[str, Any], why: Optional[collections.Counter] = None
) -> bool:
    """May `b` directly follow `a` in one clip? Counts the first blocking reason."""

    def no(reason: str) -> bool:
        if why is not None:
            why[reason] += 1
        return False

    if a["video_id"] != b["video_id"] or a.get("parent_unit_id") != b.get("parent_unit_id"):
        return no("different_parent")
    if b["start_ms"] < a["end_ms"]:
        return no("overlap")
    if b["start_ms"] - a["end_ms"] > MAX_GAP_MS:
        return no("gap_too_large")
    if a["guru_id"] != b["guru_id"]:
        return no("different_guru")
    if not (a.get("speaker_verified") is True and b.get("speaker_verified") is True):
        return no("unverified_speaker")
    if a.get("voice_verification_method") != b.get("voice_verification_method"):
        return no("different_voice_method")
    if "quarantined" in (a.get("quality_status"), b.get("quality_status")):
        return no("quarantined")
    if any(x.get("question_span_id") or x.get("host_question_span_id") for x in (a, b)):
        return no("host_question")
    for f in ("rights_cleared", "domain_rights_status", "caption_status"):
        if a.get(f) != b.get(f):
            return no("rights_mismatch")
    return True


def _fits(unit: list[dict[str, Any]], cap_s: float) -> bool:
    return (unit[-1]["end_ms"] - unit[0]["start_ms"]) / 1000.0 <= cap_s and _words(
        _join(unit)
    ) <= MAX_WORDS


def close_group(
    units: list[list[dict[str, Any]]], cap_s: float, soft: bool, why: collections.Counter
) -> list[dict[str, Any]]:
    """Merge adjacent units to fix head/tail defects (in place). Returns records of unclosed ones."""
    unclosed: list[dict[str, Any]] = []
    i = 0
    while i < len(units):
        u = units[i]
        kinds = boundary_kinds(_join(u), soft=soft)
        if not kinds:
            i += 1
            continue
        kind = "bwd" if "bwd" in kinds else "fwd"
        fixed = False
        for steps in range(1, MAX_STEPS + 1):
            lo, hi = (i - steps, i) if kind == "bwd" else (i, i + steps)
            if lo < 0 or hi >= len(units):
                why["no_neighbour"] += 1
                break
            if any(not mergeable(units[k][-1], units[k + 1][0], why) for k in range(lo, hi)):
                break
            cand = [c for x in units[lo : hi + 1] for c in x]
            if not _fits(cand, cap_s):
                why["over_cap"] += 1
                break
            ctext = _join(cand)
            ck = boundary_kinds(ctext, soft=soft)
            parts_cp = {content_problem(c["verbatim_text"]) for c in cand}
            cp = content_problem(ctext)
            if kind not in ck and ck <= kinds and (cp is None or cp in parts_cp):
                units[lo : hi + 1] = [cand]
                i = lo
                fixed = True
                break
        if not fixed:
            unclosed.append(
                {
                    "video_id": u[0]["video_id"],
                    "start_ms": u[0]["start_ms"],
                    "end_ms": u[-1]["end_ms"],
                    "point_id": u[0]["_id"],
                    "needs": sorted(kinds),
                }
            )
            for c in u:
                c.setdefault("_flags", []).append(f"unclosed_{kind}")
            i += 1
    return unclosed


# ---------------------------------------------------------------- output clips
def _new_span_id(video: str, start: int, end: int, src_ids: list[str]) -> str:
    return _sha(f"{CHUNKER_VERSION}:{video}:{start}:{end}:{'|'.join(src_ids)}")


def point_ids(payload: dict[str, Any]) -> tuple[str, str]:
    """(serving id, invariant-4 id). The v10-schema serving store verifies
    id == uuid5(NS, source_span_id) (first_person_context_store ~L823/L1332), so that
    is the id a servable shadow must carry; the invariant-4 id is recorded alongside."""
    from services.first_person_context_store import point_id_for_record
    from services.first_person_store import make_first_person_point_id

    return (
        point_id_for_record(payload["source_span_id"]),
        make_first_person_point_id(
            payload["transcript_hash"], payload["start_ms"], payload["end_ms"]
        ),
    )


def merged_payload(unit: list[dict[str, Any]]) -> dict[str, Any]:
    from ingest.verbatim.asr_cleaner import clean_verbatim_text

    first, last = unit[0], unit[-1]
    text = clean_verbatim_text(_join(unit))
    src_ids = [c["source_span_id"] for c in unit]
    p = {k: v for k, v in first.items() if not k.startswith("_")}
    p.update(
        verbatim_text=text,
        source_transcript_text=" ".join(
            str(c.get("source_transcript_text") or c["verbatim_text"]) for c in unit
        ),
        transcript_hash=_sha(text),  # invariant 13: both hashes change in the same step
        source_text_hash=_sha(text),
        start_ms=first["start_ms"],
        end_ms=last["end_ms"],
        word_start=first.get("word_start"),
        word_end=last.get("word_end"),
        source_span_id=_new_span_id(first["video_id"], first["start_ms"], last["end_ms"], src_ids),
        previous_span_id=first.get("previous_span_id"),
        next_span_id=last.get("next_span_id"),
        resegment_source_span_ids=src_ids,
        chunker_version=CHUNKER_VERSION,
        boundary_status="repaired" if not boundary_kinds(text) else "uncertain",
        completeness_status=(
            "complete"
            if all(c.get("completeness_status") == "complete" for c in unit)
            else "uncertain"
        ),
    )
    p["inv4_point_id"] = point_ids(p)[1]
    return p


def resegment(
    points: list[dict[str, Any]], *, cap_s: float = CAP_S, soft: bool = True
) -> dict[str, Any]:
    """points: Qdrant records {"id", "payload"}. Pure function of its input."""
    children = [
        {**p["payload"], "_id": p["id"]}
        for p in points
        if p["payload"].get("record_type") == "retrieval_child"
    ]
    parents = {
        p["payload"]["parent_unit_id"]: p["payload"]
        for p in points
        if p["payload"].get("record_type") == "parent_unit"
    }
    children.sort(key=lambda c: (c["video_id"], c["start_ms"], c["end_ms"], c["_id"]))
    kept, dropped = collapse_exact_duplicates(list(children))
    kept, dropped2 = drop_contained(kept, cap_s)
    dropped += dropped2

    groups: dict[tuple[str, str], list[dict[str, Any]]] = collections.defaultdict(list)
    for c in kept:
        groups[(c["video_id"], c.get("parent_unit_id") or "")].append(c)
    why: collections.Counter = collections.Counter()
    out: list[dict[str, Any]] = []
    unclosed: list[dict[str, Any]] = []
    for key in sorted(groups):
        units = [[c] for c in sorted(groups[key], key=lambda c: (c["start_ms"], c["end_ms"]))]
        unclosed += close_group(units, cap_s, soft, why)
        for u in units:
            flags = [f for c in u for f in c.get("_flags", [])]
            if len(u) == 1:
                payload = {k: v for k, v in u[0].items() if not k.startswith("_")}
                pid, change = u[0]["_id"], "unchanged"
            else:
                payload = merged_payload(u)
                pid, change = point_ids(payload)[0], "merged"
                if payload["verbatim_text"] != _join(u):
                    flags.append("asr_cleaner_changed_text")
            if _dur(payload) > cap_s:
                flags.append("over_cap_unsplit_v2")
            if _dur(payload) > HARD_MAX_S:
                flags.append("over_hard_max")
            out.append(
                {
                    "point_id": pid,
                    "payload": payload,
                    "change": change,
                    "flags": sorted(set(flags)),
                    "source_point_ids": [c["_id"] for c in u],
                }
            )

    # rebuild prev/next chains and parents over the kept set (chains never cross parents)
    by_parent: dict[tuple[str, str], list[dict[str, Any]]] = collections.defaultdict(list)
    for o in out:
        by_parent[(o["payload"]["video_id"], o["payload"].get("parent_unit_id") or "")].append(o)
    new_parents: list[dict[str, Any]] = []
    changed_parents = 0
    for (_vid, parent_id), os_ in by_parent.items():
        os_.sort(key=lambda o: (o["payload"]["start_ms"], o["payload"]["end_ms"]))
        for a, b in zip(os_, os_[1:]):
            a["payload"]["next_span_id"] = b["payload"]["source_span_id"]
            b["payload"]["previous_span_id"] = a["payload"]["source_span_id"]
        os_[0]["payload"]["previous_span_id"] = None
        os_[-1]["payload"]["next_span_id"] = None
        old = parents.get(parent_id)
        if old:
            ids = [o["payload"]["source_span_id"] for o in os_]
            if ids != list(old["ordered_source_span_ids"]):
                changed_parents += 1
                old = {
                    **old,
                    "ordered_source_span_ids": ids,
                    "start_ms": os_[0]["payload"]["start_ms"],
                    "end_ms": os_[-1]["payload"]["end_ms"],
                    "parent_text_hash": _sha(" ".join(o["payload"]["verbatim_text"] for o in os_)),
                }
            new_parents.append(old)
    out.sort(
        key=lambda o: (o["payload"]["video_id"], o["payload"]["start_ms"], o["payload"]["end_ms"])
    )
    return {
        "before": children,
        "after": out,
        "dropped": dropped,
        "unclosed": unclosed,
        "blocked_reasons": dict(why),
        "parents_before": len(parents),
        "parents_after": len(new_parents),
        "parents_changed": changed_parents,
        "parents": new_parents,
    }


# ---------------------------------------------------------------- scorecard
def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """rows: payload dicts with verbatim_text/start_ms/end_ms/video_id."""
    n = len(rows)
    secs = sorted(_dur(r) for r in rows)
    by_video: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for r in rows:
        by_video[r["video_id"]].append(r)
    contained = sum(
        1
        for vc in by_video.values()
        for a in vc
        if any(
            b is not a
            and b["start_ms"] <= a["start_ms"]
            and b["end_ms"] >= a["end_ms"]
            and (b["start_ms"], b["end_ms"]) != (a["start_ms"], a["end_ms"])
            for b in vc
        )
    )
    texts = collections.Counter(_sha(r["verbatim_text"]) for r in rows)
    dup = sum(v for v in texts.values() if v > 1)
    reasons: collections.Counter = collections.Counter(
        standalone_problem(r["verbatim_text"]) for r in rows
    )
    boundary = sum(v for k, v in reasons.items() if k in FWD_REASONS or k in BWD_REASONS)
    return {
        "clips": n,
        "videos": len(by_video),
        "seconds": {
            "median": round(statistics.median(secs), 1),
            "p95": round(secs[min(n - 1, int(0.95 * n))], 1),
            "max": round(secs[-1], 1),
        },
        "pct_18_25s": round(100 * sum(18 <= s <= 25 for s in secs) / n, 1),
        "pct_outside_8_60s": round(100 * sum(not 8 <= s <= 60 for s in secs) / n, 1),
        "over_90s": sum(s > 90 for s in secs),
        "over_160s": sum(s > 160 for s in secs),
        "under_15_words": sum(_words(r["verbatim_text"]) < MIN_WORDS for r in rows),
        "contained": contained,
        "pct_contained": round(100 * contained / n, 1),
        "duplicate_text_clips": dup,
        "pct_duplicate_text": round(100 * dup / n, 1),
        "standalone_gate_pass_pct": round(100 * reasons[None] / n, 1),
        "standalone_fail_boundary_fixable": boundary,
        "standalone_fail_content": n - reasons[None] - boundary,
        "standalone_reasons": {str(k): v for k, v in reasons.most_common()},
        "top_video_share_pct": round(100 * max(len(v) for v in by_video.values()) / n, 1),
    }


def scorecard(res: dict[str, Any], cap_s: float, soft: bool) -> dict[str, Any]:
    from ingest.verbatim.asr_cleaner import clean_verbatim_text

    merged = [o for o in res["after"] if o["change"] == "merged"]
    return {
        "schema": "resegment-v10-scorecard-v1",
        "date": "2026-11-16",
        "params": {
            "cap_s": cap_s,
            "hard_max_s": HARD_MAX_S,
            "max_words": MAX_WORDS,
            "min_words": MIN_WORDS,
            "max_gap_ms": MAX_GAP_MS,
            "soft_boundaries": soft,
            "chunker_version": CHUNKER_VERSION,
        },
        "before": metrics(res["before"]),
        "after": metrics([o["payload"] for o in res["after"]]),
        "counts": {
            "dropped_exact_duplicate": sum(
                d["reason"] == "exact_duplicate_text" for d in res["dropped"]
            ),
            "dropped_contained": sum(d["reason"].startswith("contained") for d in res["dropped"]),
            "merged_clips": len(merged),
            "source_spans_consumed_by_merges": sum(len(o["source_point_ids"]) for o in merged),
            "merged_clips_text_changed_by_asr_cleaner": sum(
                "asr_cleaner_changed_text" in o["flags"] for o in merged
            ),
            "unchanged_clips_cleaner_would_change_left_untouched": sum(
                clean_verbatim_text(r["verbatim_text"]) != r["verbatim_text"] for r in res["before"]
            ),
            "unclosed_flagged": len(res["unclosed"]),
            "over_cap_unsplit": sum("over_cap_unsplit_v2" in o["flags"] for o in res["after"]),
            "duplicate_attribution_conflicts": sum(
                "duplicate_text_attribution_conflict" in o["flags"] for o in res["after"]
            ),
            "merge_blocked_reasons": res["blocked_reasons"],
            "parents_before": res["parents_before"],
            "parents_after": res["parents_after"],
            "parents_changed": res["parents_changed"],
        },
    }


def write_outputs(res: dict[str, Any], card: dict[str, Any], out: Path) -> None:
    """JSONL carries ids/timing/counts and at most the first 10 words (repo is public)."""
    out.mkdir(parents=True, exist_ok=True)
    with (out / "proposed_clips.jsonl").open("w") as fh:
        for o in res["after"]:
            p = o["payload"]
            fh.write(
                json.dumps(
                    {
                        "point_id": o["point_id"],
                        "video_id": p["video_id"],
                        "start_ms": p["start_ms"],
                        "end_ms": p["end_ms"],
                        "words": _words(p["verbatim_text"]),
                        "change_type": o["change"],
                        "source_point_ids": o["source_point_ids"],
                        "flags": o["flags"],
                        "first_10_words": " ".join(p["verbatim_text"].split()[:10]),
                        "source_text_hash": p["source_text_hash"],
                        "chunker_version": p.get("chunker_version"),
                    }
                )
                + "\n"
            )
    with (out / "dropped_clips.jsonl").open("w") as fh:
        for d in res["dropped"]:
            fh.write(json.dumps(d) + "\n")
    (out / "unclosed_clips.json").write_text(json.dumps(res["unclosed"], indent=1))
    (out / f"scorecard_cap{int(card['params']['cap_s'])}.json").write_text(
        json.dumps(card, indent=1)
    )


# ---------------------------------------------------------------- IO
def load_points(
    source: str, *, url: str, source_json: Optional[str], with_vectors: bool = False
) -> list[dict[str, Any]]:
    """Read-only. Offline JSON export or a Qdrant scroll."""
    if source_json:
        return json.loads(Path(source_json).read_text())
    from qdrant_client import QdrantClient

    client = QdrantClient(url=url)
    pts: list[dict[str, Any]] = []
    off = None
    while True:
        recs, off = client.scroll(
            source, limit=500, offset=off, with_payload=True, with_vectors=with_vectors
        )
        pts += [{"id": str(r.id), "payload": r.payload, "vector": r.vector} for r in recs]
        if off is None:
            return pts


# ---------------------------------------------------------------- apply (guarded; creates a NEW collection only)
def validate_target(target: str, source: str) -> None:
    if target in PROTECTED or target == source:
        raise SystemExit(f"refusing protected/source collection {target!r}")
    if not (target.startswith("first_person_v12") and "shadow" in target):
        raise SystemExit(f"target must look like first_person_v12*shadow*, got {target!r}")


def check_apply_guards(args: argparse.Namespace) -> None:
    """Runs before any network client exists."""
    if not args.snapshot_confirmed or not (args.approved_by or "").strip():
        raise SystemExit("--apply requires --snapshot-confirmed and --approved-by <name>")
    validate_target(args.target_collection, args.source_collection)


def create_shadow_collection(client: Any, source: str, target: str) -> None:
    """New collection with the source's vector/sparse/hnsw/quantization config and payload indexes."""
    from qdrant_client.models import HnswConfigDiff, PayloadSchemaType

    if target in {c.name for c in client.get_collections().collections}:
        raise SystemExit(f"{target!r} already exists; refusing (never overwritten)")
    info = client.get_collection(source)
    cfg = info.config
    client.create_collection(
        target,
        vectors_config=cfg.params.vectors,
        sparse_vectors_config=cfg.params.sparse_vectors,
        hnsw_config=HnswConfigDiff(**cfg.hnsw_config.model_dump()),
        quantization_config=cfg.quantization_config,
    )
    for field, schema in (info.payload_schema or {}).items():  # same payload indexes as the source
        client.create_payload_index(target, field, PayloadSchemaType(schema.data_type.value))


def apply_build(
    res: dict[str, Any], points: list[dict[str, Any]], args: argparse.Namespace
) -> dict[str, Any]:
    from qdrant_client import QdrantClient
    from qdrant_client.models import PointStruct

    from services.first_person_context_store import parent_point_id
    from services.qdrant.utils import QdrantUtils

    client = QdrantClient(url=args.qdrant_url)
    create_shadow_collection(client, args.source_collection, args.target_collection)
    vec = {p["id"]: p["vector"] for p in points}
    from services.embedding_service import EmbeddingService

    emb = EmbeddingService()
    batch: list[Any] = []
    for o in res["after"]:
        if o["change"] == "unchanged":
            vector = vec[o["point_id"]]  # identical text, identical embedding
        else:
            r = emb.encode_batch([o["payload"]["verbatim_text"]])
            vector = {
                "passage_dense": r["dense"][0],
                "passage_sparse": QdrantUtils.sparse_dict_to_vector(r["sparse"][0]),
            }
        batch.append(PointStruct(id=o["point_id"], vector=vector, payload=o["payload"]))
        if len(batch) >= 128:
            client.upsert(args.target_collection, batch, wait=True)
            batch = []
    for par in res["parents"]:
        batch.append(PointStruct(id=parent_point_id(par["parent_unit_id"]), vector={}, payload=par))
    if batch:
        client.upsert(args.target_collection, batch, wait=True)
    return {
        "target": args.target_collection,
        "children": len(res["after"]),
        "parents": len(res["parents"]),
        "approved_by": args.approved_by,
    }


def verify_target(res: dict[str, Any], client: Any, target: str) -> dict[str, Any]:
    from services.first_person_context_store import point_id_for_record

    bad_hash = bad_id = n = 0
    off = None
    while True:
        recs, off = client.scroll(
            target, limit=500, offset=off, with_payload=True, with_vectors=False
        )
        for r in recs:
            p = r.payload
            if p.get("record_type") != "retrieval_child":
                continue
            n += 1
            bad_hash += _sha(p["verbatim_text"]) != p["source_text_hash"]
            bad_id += str(r.id) != point_id_for_record(p["source_span_id"])
        if off is None:
            break
    return {
        "children": n,
        "expected": len(res["after"]),
        "bad_hash": bad_hash,
        "bad_point_id": bad_id,
    }


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", default=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--snapshot-confirmed", action="store_true")
    ap.add_argument("--approved-by", default="")
    ap.add_argument("--source-collection", default="first_person_v10")
    ap.add_argument("--target-collection", default="first_person_v12_shadow")
    ap.add_argument("--qdrant-url", default="http://localhost:6333")
    ap.add_argument("--source-json", default=None, help="offline [{id,payload}] export")
    ap.add_argument("--cap-s", type=float, default=CAP_S)
    ap.add_argument("--sweep", default="", help="comma list of caps; scorecard each")
    ap.add_argument(
        "--no-soft", action="store_true", help="only hard boundary defects trigger merges"
    )
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args(argv)
    if args.apply:
        check_apply_guards(args)
    soft = not args.no_soft
    points = load_points(
        args.source_collection,
        url=args.qdrant_url,
        source_json=args.source_json,
        with_vectors=args.apply,
    )
    caps = [float(c) for c in args.sweep.split(",") if c] or [args.cap_s]
    for cap in caps:
        res = resegment(points, cap_s=cap, soft=soft)
        card = scorecard(res, cap, soft)
        write_outputs(res, card, Path(args.out) / (f"cap{int(cap)}" if len(caps) > 1 else "."))
        print(
            json.dumps(
                {
                    "cap_s": cap,
                    "before": card["before"]["clips"],
                    "after": card["after"],
                    "counts": card["counts"],
                },
                indent=1,
            )
        )
    if args.apply:
        print(json.dumps(apply_build(res, points, args)))
        from qdrant_client import QdrantClient

        print(
            json.dumps(
                verify_target(res, QdrantClient(url=args.qdrant_url), args.target_collection)
            )
        )
    return 0


# ---------------------------------------------------------------- self-check
def _fake(i: int, text: str, start: int, end: int, **kw: Any) -> dict[str, Any]:
    p = {
        "record_type": "retrieval_child",
        "video_id": "vid",
        "guru_id": "krishnaji",
        "parent_unit_id": "par",
        "source_span_id": f"s{i}",
        "verbatim_text": text,
        "start_ms": start,
        "end_ms": end,
        "speaker_verified": True,
        "voice_verification_method": "m",
        "quality_status": "verified_verbatim",
        "rights_cleared": True,
        "domain_rights_status": "licensed",
        "caption_status": "auto",
        "completeness_status": "complete",
    }
    p.update(kw)
    return {"id": f"id{i}", "payload": p}


if __name__ == "__main__":
    if len(sys.argv) > 1:
        raise SystemExit(main())
    a = "Anger is a signal that your inner state is asking for attention and care right now, and"
    b = "when you pause and breathe you can see what the anger is protecting within you today."
    r = resegment([_fake(1, a, 0, 10000), _fake(2, b, 10200, 20000)], cap_s=90)
    assert len(r["after"]) == 1 and r["after"][0]["change"] == "merged", r["after"]
    m = r["after"][0]["payload"]
    assert m["source_text_hash"] == m["transcript_hash"] == _sha(m["verbatim_text"])
    assert m["chunker_version"] == CHUNKER_VERSION
    print("resegment_v10 self-check passed")
