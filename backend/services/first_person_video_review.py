"""Read model for the admin video-approval page.

Joins three sources into one row per video:

* the inventory CSV (title, channel, every known video, including ones not in v10),
* live machine evidence scrolled from the v10 context collection (read-only),
* the human decision from ``first_person_video_decisions`` (kept separate).

Machine fields (``child_spans``, ``speaker_verified_spans``,
``spans_with_voice_method``, ``min_window_cosine``) are never merged with the
human fields; the page shows them side by side.
"""

from __future__ import annotations

import csv
import logging
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Optional

from app.config import settings
from services.first_person_video_decisions import VideoDecision

logger = logging.getLogger(__name__)

VERIFIED_FILTERS = ("none", "partial", "full")
APPROVED_FILTERS = ("approved", "rejected", "undecided")
MAX_PAGE = 200

SCROLL_PAYLOAD_FIELDS = [
    "video_id",
    "speaker_verified",
    "voice_verification_method",
    "min_window_cosine",
    "guru_id",
]


def default_inventory_path() -> Path:
    configured = str(settings.first_person_video_inventory_path or "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[1] / "config" / "first_person_video_inventory.csv"


def _to_int(value: Any) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def load_inventory(path: Optional[Path] = None) -> dict[str, dict[str, Any]]:
    """Inventory rows keyed by video id. Missing file -> empty (the page then shows live data only)."""
    inventory_path = path or default_inventory_path()
    try:
        with open(inventory_path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
    except FileNotFoundError:
        return {}
    except (OSError, csv.Error) as exc:
        logger.warning("[VideoReview] inventory unreadable (%s); using live data only", exc)
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        video_id = (row.get("video_id") or "").strip()
        if not video_id:
            continue
        out[video_id] = {
            "video_id": video_id,
            "title": (row.get("title") or "").strip(),
            "channel": (row.get("channel") or "").strip() or "(unknown)",
            "in_v10": (row.get("in_v10") or "").strip().lower() == "yes",
            "child_spans": _to_int(row.get("child_spans")),
            "speaker_verified_spans": _to_int(row.get("speaker_verified_spans")),
            "spans_with_voice_method": _to_int(row.get("spans_with_voice_method")),
            "guru_ids": [
                g.strip() for g in re.split(r"[|;,]", row.get("guru_ids") or "") if g.strip()
            ],
            "status_note": (row.get("status_note") or "").strip(),
        }
    return out


def aggregate_live(payloads: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per-video machine evidence from child-span payloads. Pure."""
    out: dict[str, dict[str, Any]] = {}
    for payload in payloads:
        video_id = str(payload.get("video_id") or "").strip()
        if not video_id:
            continue
        agg = out.setdefault(
            video_id,
            {
                "child_spans": 0,
                "speaker_verified_spans": 0,
                "spans_with_voice_method": 0,
                "min_window_cosine": None,
                "guru_ids": set(),
            },
        )
        agg["child_spans"] += 1
        if payload.get("speaker_verified") is True:
            agg["speaker_verified_spans"] += 1
        if payload.get("voice_verification_method"):
            agg["spans_with_voice_method"] += 1
        cosine = payload.get("min_window_cosine")
        if isinstance(cosine, (int, float)) and not isinstance(cosine, bool):
            current = agg["min_window_cosine"]
            agg["min_window_cosine"] = cosine if current is None else min(current, cosine)
        guru = str(payload.get("guru_id") or "").strip()
        if guru:
            agg["guru_ids"].add(guru)
    for agg in out.values():
        agg["guru_ids"] = sorted(agg["guru_ids"])
    return out


def scroll_child_payloads(
    client: Any, collection: str, *, page_size: int = 512
) -> list[dict[str, Any]]:
    """Read-only scroll of child-span payload fields. Never writes."""
    from qdrant_client.http.models import FieldCondition, Filter, MatchValue

    flt = Filter(
        must=[FieldCondition(key="record_type", match=MatchValue(value="retrieval_child"))]
    )
    payloads: list[dict[str, Any]] = []
    offset: Any = None
    while True:
        records, offset = client.scroll(
            collection_name=collection,
            scroll_filter=flt,
            limit=page_size,
            offset=offset,
            with_payload=SCROLL_PAYLOAD_FIELDS,
            with_vectors=False,
        )
        payloads.extend(dict(r.payload or {}) for r in records)
        if offset is None:
            break
    return payloads


def machine_speaker_status(child_spans: int, verified_spans: int) -> str:
    if child_spans <= 0:
        return "n/a"
    if verified_spans <= 0:
        return "none"
    return "full" if verified_spans >= child_spans else "partial"


def approval_state(decision: Optional[VideoDecision]) -> str:
    if decision is None or decision.admin_approved is None:
        return "undecided"
    return "approved" if decision.admin_approved else "rejected"


def build_rows(
    inventory: Mapping[str, Mapping[str, Any]],
    live: Optional[Mapping[str, Mapping[str, Any]]],
    decisions: Mapping[str, VideoDecision],
) -> list[dict[str, Any]]:
    """One row per known video. ``live`` is None when Qdrant could not be read."""
    video_ids = set(inventory) | set(live or {}) | set(decisions)
    rows: list[dict[str, Any]] = []
    for video_id in sorted(video_ids):
        inv = inventory.get(video_id, {})
        machine = (live or {}).get(video_id)
        if machine is not None:
            source = "live"
            child, verified = machine["child_spans"], machine["speaker_verified_spans"]
            voice = machine["spans_with_voice_method"]
            cosine = machine["min_window_cosine"]
            guru_ids = machine["guru_ids"]
        else:
            source = "inventory" if inv else "decision_only"
            child = int(inv.get("child_spans", 0))
            verified = int(inv.get("speaker_verified_spans", 0))
            voice = int(inv.get("spans_with_voice_method", 0))
            cosine = None
            guru_ids = list(inv.get("guru_ids", []))
        in_v10 = child > 0 if live is not None else bool(inv.get("in_v10", child > 0))
        decision = decisions.get(video_id)
        state = approval_state(decision)
        blocked = bool(decision and decision.blocks_serving)
        rows.append(
            {
                "video_id": video_id,
                "title": inv.get("title") or "",
                "channel": inv.get("channel") or "(unknown)",
                "youtube_url": f"https://www.youtube.com/watch?v={video_id}",
                "in_v10": in_v10,
                "status_note": inv.get("status_note") or "",
                "machine": {
                    "source": source,
                    "child_spans": child,
                    "speaker_verified_spans": verified,
                    "spans_with_voice_method": voice,
                    "min_window_cosine": cosine,
                    "speaker_status": machine_speaker_status(child, verified),
                    "guru_ids": guru_ids,
                },
                "decision": decision.as_dict() if decision else None,
                "approval_state": state,
                "serving": (
                    "blocked_by_admin" if blocked else ("gates_apply" if in_v10 else "not_in_v10")
                ),
            }
        )
    return rows


def filter_rows(
    rows: list[dict[str, Any]],
    *,
    channel: Optional[str] = None,
    verified: Optional[str] = None,
    approved: Optional[str] = None,
    in_v10: Optional[bool] = None,
    query: Optional[str] = None,
) -> list[dict[str, Any]]:
    needle = (query or "").strip().lower()
    out = []
    for row in rows:
        if channel and row["channel"] != channel:
            continue
        if verified and row["machine"]["speaker_status"] != verified:
            continue
        if approved and row["approval_state"] != approved:
            continue
        if in_v10 is not None and row["in_v10"] != in_v10:
            continue
        if needle and needle not in row["video_id"].lower() and needle not in row["title"].lower():
            continue
        out.append(row)
    return out


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary = {
        "videos": len(rows),
        "in_v10": sum(1 for r in rows if r["in_v10"]),
        "missing_in_v10": sum(1 for r in rows if not r["in_v10"]),
        "approved": sum(1 for r in rows if r["approval_state"] == "approved"),
        "rejected": sum(1 for r in rows if r["approval_state"] == "rejected"),
        "undecided": sum(1 for r in rows if r["approval_state"] == "undecided"),
        "blocked_by_admin": sum(1 for r in rows if r["serving"] == "blocked_by_admin"),
        "machine_speaker": {"none": 0, "partial": 0, "full": 0, "n/a": 0},
    }
    for row in rows:
        summary["machine_speaker"][row["machine"]["speaker_status"]] += 1
    return summary
