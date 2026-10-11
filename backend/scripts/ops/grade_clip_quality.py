#!/usr/bin/env python3
"""Grade EVERY stored first-person clip for self-containedness, risk and ASR garbling (read-only).

Why: an independent blind judge found only ~13-15% of stored clips are clean, self-contained teachings
(2026-10-11). Serve-time gates compensate per query; this grades the whole corpus once so a "grade A only"
policy can be measured offline before any change to serving.

Reads a collection (Qdrant, read-only scroll), asks a scorer model for one JSON object per clip, appends
one JSON line per clip to --out (resumable: ids already in --out are skipped). Writes NOTHING to Qdrant.
No generated teaching text: the model only returns booleans and a 0-3 score.

Run inside the backend container (it holds the provider client and policy):
    docker cp backend/scripts/ops/grade_clip_quality.py mukthiguru-backend:/tmp/
    docker exec -w /app -e PYTHONPATH=/app mukthiguru-backend python3 -u /tmp/grade_clip_quality.py \
        --collection first_person_v8 --out /tmp/quality_grades.jsonl
The scorer model must be allowed by the OpenRouter policy (OPENROUTER_EXTRA_ALLOWED_MODELS).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

_SYSTEM = (
    "You grade ONE recorded teaching clip (ASR text, punctuation unreliable) that may be shown to a seeker "
    "on its own. Be strict. Reply with ONLY one line of JSON, no prose, with keys: "
    '"starts_complete" (true only if the clip begins at the start of a thought: no orphan opener such as '
    '"these are", "it is possible", "because", no reference to something not in the clip), '
    '"ends_complete" (true only if it ends at the end of a thought: not mid-sentence, not before the point), '
    '"value" (0-3: 0 fragment, 1 weak, 2 good self-contained teaching, 3 excellent), '
    '"risk" (true if it promises outcomes/wealth/miracles, makes a medical or healing claim, cites '
    '"science has proven", or is threat-like), "garbled" (true if obvious ASR garbage would embarrass on '
    'screen), "event_bound" (true if it only makes sense at one event, day, room or audience).'
)
_BATCH_NOTE = (
    " You will receive SEVERAL numbered clips. Reply with ONLY one JSON array with exactly one object per clip, "
    'in order, each object also carrying "n" (the clip number).'
)
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)
_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


def _scroll(qdrant_url: str, collection: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    offset = None
    while True:
        body: dict[str, Any] = {"limit": 256, "with_payload": True, "with_vector": False}
        if offset:
            body["offset"] = offset
        req = urllib.request.Request(
            f"{qdrant_url}/collections/{collection}/points/scroll",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        res = json.load(urllib.request.urlopen(req, timeout=60))["result"]  # nosec B310 - operator-supplied URL
        out += [{"id": str(p["id"]), **p["payload"]} for p in res["points"]]
        offset = res.get("next_page_offset")
        if not offset:
            return out


def parse_grade(raw: Any) -> dict[str, Any] | None:
    """Strict parse of the scorer reply; None when unusable (the caller retries or records a failure)."""
    match = _JSON_RE.search(str(raw or ""))
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return None
    flags = ("starts_complete", "ends_complete", "risk", "garbled", "event_bound")
    value = data.get("value")
    if not all(isinstance(data.get(k), bool) for k in flags):
        return None
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 3:
        return None
    return {**{k: data[k] for k in flags}, "value": value}


def parse_batch(raw: Any, size: int) -> dict[int, dict[str, Any]]:
    """Map clip number -> grade for every well-formed object in a JSON-array reply (missing/bad ones are omitted)."""
    match = _ARRAY_RE.search(str(raw or ""))
    if not match:
        return {}
    try:
        items = json.loads(match.group(0))
    except ValueError:
        return {}
    out: dict[int, dict[str, Any]] = {}
    for item in items if isinstance(items, list) else []:
        grade = parse_grade(json.dumps(item)) if isinstance(item, dict) else None
        n = item.get("n") if isinstance(item, dict) else None
        if grade and isinstance(n, int) and 1 <= n <= size:
            out[n] = grade
    return out


def grade_letter(g: dict[str, Any]) -> str:
    """A = complete both ends, no risk/garble/event, value >= 2.  B = same but value 1 or one end incomplete.  C = rest."""
    clean = not (g["risk"] or g["garbled"] or g["event_bound"])
    if clean and g["starts_complete"] and g["ends_complete"] and g["value"] >= 2:
        return "A"
    if clean and (g["starts_complete"] or g["ends_complete"]) and g["value"] >= 1:
        return "B"
    return "C"


async def _grade_all(args: argparse.Namespace) -> None:
    from services.openrouter_service import (
        OpenRouterService,
    )  # imported here: only exists in the backend image

    clips = _scroll(args.qdrant_url, args.collection)
    done = set()
    if Path(args.out).exists():
        done = {json.loads(line)["id"] for line in open(args.out) if line.strip()}
    todo = [c for c in clips if c["id"] not in done]
    print(f"{len(clips)} clips, {len(done)} already graded, {len(todo)} to do", flush=True)
    svc = OpenRouterService()
    sem = asyncio.Semaphore(args.concurrency)
    lock = asyncio.Lock()
    counts = {"ok": 0, "fail": 0}

    async def record(clip: dict[str, Any], grade: dict[str, Any] | None, err: str) -> None:
        row = {"id": clip["id"], "video_id": clip.get("video_id"), "speaker": clip.get("speaker")}
        if grade:
            row.update(grade, grade_letter=grade_letter(grade))
            counts["ok"] += 1
        else:
            row.update(error=err or "unparseable", grade_letter="ERR")
            counts["fail"] += 1
        async with lock:
            with open(args.out, "a") as fh:
                fh.write(json.dumps(row) + "\n")
            n = counts["ok"] + counts["fail"]
            if n % 60 == 0:
                print(f"  {n}/{len(todo)} ok={counts['ok']} fail={counts['fail']}", flush=True)

    async def batch(group: list[dict[str, Any]]) -> None:
        body = "\n\n".join(
            f"[{i}] ({round((c['end_ms'] - c['start_ms']) / 1000)} s)\n{(c.get('verbatim_text') or '')[:1500]}"
            for i, c in enumerate(group, 1)
        )
        grades: dict[int, dict[str, Any]] = {}
        err = ""
        async with sem:
            for _ in range(3):
                try:
                    raw = await svc.generate(
                        system_prompt=_SYSTEM + _BATCH_NOTE,
                        user_prompt=body,
                        temperature=0.0,
                        model=args.model,
                        max_tokens=4096,
                        # "deep" lifts the provider output ceiling (fast=800 truncates a 6-clip JSON array)
                        operation="deep",
                    )
                except Exception as exc:  # noqa: BLE001 - recorded, never silently dropped
                    err = f"{type(exc).__name__}: {str(exc)[:80]}"
                    continue
                grades = parse_batch(raw, len(group))
                if len(grades) == len(group):
                    break
        for i, clip in enumerate(group, 1):
            await record(clip, grades.get(i), err)

    size = args.batch
    await asyncio.gather(*(batch(todo[i : i + size]) for i in range(0, len(todo), size)))
    print(f"done ok={counts['ok']} fail={counts['fail']}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--collection", default="first_person_v8")
    ap.add_argument("--qdrant-url", default="http://qdrant:6333")
    ap.add_argument("--out", default="/tmp/quality_grades.jsonl")
    ap.add_argument("--model", default="anthropic/claude-haiku-5.5")
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument(
        "--batch", type=int, default=6, help="clips per request (rate limit is requests/minute)"
    )
    asyncio.run(_grade_all(ap.parse_args()))
    return 0


if __name__ == "__main__":
    # ponytail self-check: pure functions only, no network.
    ok = parse_grade(
        '{"starts_complete":true,"ends_complete":true,"value":3,"risk":false,"garbled":false,"event_bound":false}'
    )
    assert ok and grade_letter(ok) == "A"
    assert parse_grade("sure! here you go") is None and parse_grade('{"value":9}') is None
    two = '[{"n":1,"starts_complete":true,"ends_complete":true,"value":2,"risk":false,"garbled":false,"event_bound":false},{"n":3,"value":9}]'
    assert list(parse_batch(two, 2)) == [1] and parse_batch("nope", 2) == {}
    assert grade_letter({**ok, "risk": True}) == "C"
    sys.exit(main() if len(sys.argv) > 1 else 0)
