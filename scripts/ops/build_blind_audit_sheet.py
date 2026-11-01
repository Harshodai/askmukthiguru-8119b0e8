#!/usr/bin/env python3
"""Blind listening sheet for the V7 speaker audit (read-only: Qdrant reads, local WAV cuts).

    build:  python scripts/ops/build_blind_audit_sheet.py build --key KEY.json --collection first_person_v11 \
                --wav-dir ~/mukthiguru_attribution_data/audio_archive/wavs --out-dir SHEET_DIR --key-out KEY_DIR
    score:  python scripts/ops/build_blind_audit_sheet.py score --key KEY.json --answers SHEET_DIR/answers.csv \
                --key-map KEY_DIR/sheet_key.json --out reviews.jsonl
    (then: python scripts/ops/speaker_audit.py gate --sample KEY.json --reviews reviews.jsonl --out gate.json)

The sheet folder holds numbered clips (001.wav ...), ``answers.csv`` and ``index.html``. It never
carries the teacher, video id, score or model verdict; the mapping lives in ``--key-out``, a different
folder. Each clip is the exact served window (start-250 ms .. end+250 ms, capped at the file).
Choices are blank by default. Exit 2 on invalid input.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import urllib.request
import wave
from pathlib import Path

PAD_MS = 250
CHOICES = ("sri_krishnaji", "sri_preethaji", "host_or_interviewer", "other", "unclear")
MIN_CLIP_MS = 2000


def fetch_windows(qdrant_url: str, collection: str, span_ids: set[str]) -> dict[str, dict]:
    found: dict[str, dict] = {}
    offset = None
    while True:
        body: dict = {"limit": 256, "with_payload": True, "with_vector": False}
        if offset:
            body["offset"] = offset
        req = urllib.request.Request(
            f"{qdrant_url}/collections/{collection}/points/scroll",
            json.dumps(body).encode(),
            {"content-type": "application/json"},
        )
        result = json.load(urllib.request.urlopen(req, timeout=60))["result"]
        for point in result["points"]:
            payload = point["payload"]
            if (
                payload.get("record_type") == "retrieval_child"
                and payload.get("source_span_id") in span_ids
            ):
                found[payload["source_span_id"]] = payload
        offset = result.get("next_page_offset")
        if not offset:
            return found


def cut_clip(wav_path: Path, start_ms: int, end_ms: int, out_path: Path) -> int:
    with wave.open(str(wav_path), "rb") as src:
        rate, total = src.getframerate(), src.getnframes()
        first = max(0, int((start_ms - PAD_MS) * rate / 1000))
        last = min(total, int((end_ms + PAD_MS) * rate / 1000))
        src.setpos(first)
        frames = src.readframes(last - first)
        with wave.open(str(out_path), "wb") as dst:
            dst.setparams(src.getparams())
            dst.writeframes(frames)
    return int((last - first) * 1000 / rate)


def build(args: argparse.Namespace) -> int:
    key = json.loads(Path(args.key).read_text())
    spans = key["spans"]
    windows = fetch_windows(args.qdrant_url, args.collection, {s["source_span_id"] for s in spans})
    missing = [s["source_span_id"][:12] for s in spans if s["source_span_id"] not in windows]
    if missing:
        print(f"spans not found in {args.collection}: {missing}", file=sys.stderr)
        return 2
    short = [
        s["source_span_id"][:12]
        for s in spans
        if windows[s["source_span_id"]]["end_ms"] - windows[s["source_span_id"]]["start_ms"]
        < MIN_CLIP_MS
    ]
    if short:
        print(f"clips under {MIN_CLIP_MS} ms are not allowed: {short}", file=sys.stderr)
        return 2
    order = sorted(spans, key=lambda s: s["source_span_id"])
    random.Random(f"{key['seed']}|sheet").shuffle(order)
    out_dir, key_dir = Path(args.out_dir), Path(args.key_out)
    if out_dir.resolve() == key_dir.resolve() or key_dir.resolve() in out_dir.resolve().parents:
        print("--key-out must be a different folder from --out-dir", file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)
    key_dir.mkdir(parents=True, exist_ok=True)
    mapping, names = {}, []
    for number, span in enumerate(order, 1):
        payload = windows[span["source_span_id"]]
        name = f"{number:03d}.wav"
        length = cut_clip(
            Path(args.wav_dir) / f"{payload['video_id']}.wav",
            payload["start_ms"],
            payload["end_ms"],
            out_dir / name,
        )
        mapping[name] = {
            "source_span_id": span["source_span_id"],
            "guru_id": span["guru_id"],
            "video_id": payload["video_id"],
            "clip_ms": length,
        }
        names.append(name)
    (key_dir / "sheet_key.json").write_text(json.dumps(mapping, indent=1))
    with (out_dir / "answers.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["clip", "choice"])
        writer.writerows((name, "") for name in names)
    items = "".join(
        f'<li><b>{name}</b> <audio controls preload="none" src="{name}"></audio> '
        + "".join(
            f'<label><input type="radio" name="{name}" value="{c}"> {c.replace("_", " ")}</label> '
            for c in CHOICES
        )
        + "</li>"
        for name in names
    )
    (out_dir / "index.html").write_text(
        "<!doctype html><meta charset=utf-8><title>Speaker listen</title>"
        "<style>body{font:15px system-ui;max-width:60rem;margin:1rem auto;padding:0 1rem}"
        "li{margin:.7rem 0;list-style:none}label{margin-right:.6rem}</style><h1>Who is speaking?</h1>"
        "<p>Listen to each clip. Choose one option; nothing is pre-selected. When done press the button "
        "and paste the result into answers.csv.</p>"
        f"<ol>{items}</ol><button id=go>Copy answers as CSV</button><pre id=out></pre>"
        "<script>document.getElementById('go').onclick=function(){var r=['clip,choice'];"
        "document.querySelectorAll('li').forEach(function(li){var c=li.querySelector('input:checked');"
        "r.push(li.querySelector('b').textContent+','+(c?c.value:''))});var t=r.join('\\n');"
        "document.getElementById('out').textContent=t;"
        "if(navigator.clipboard)navigator.clipboard.writeText(t).catch(function(){})}</script>"
    )
    print(f"{len(names)} clips -> {out_dir}; key map -> {key_dir / 'sheet_key.json'}")
    return 0


def score(args: argparse.Namespace) -> int:
    mapping = json.loads(Path(args.key_map).read_text())
    answers = {
        r["clip"]: (r["choice"] or "").strip() for r in csv.DictReader(Path(args.answers).open())
    }
    bad = sorted(c for c in answers.values() if c and c not in CHOICES)
    if bad or set(answers) != set(mapping):
        print(
            f"invalid answers: {bad} / clips match key: {set(answers) == set(mapping)}",
            file=sys.stderr,
        )
        return 2
    with Path(args.out).open("w") as out:
        for clip, info in sorted(mapping.items()):
            record = {
                "source_span_id": info["source_span_id"],
                "review_choice": answers.get(clip) or None,
            }
            out.write(json.dumps(record) + "\n")
    print(f"{sum(1 for v in answers.values() if v)} of {len(mapping)} answered -> {args.out}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--key", required=True)
    b.add_argument("--collection", required=True)
    b.add_argument("--qdrant-url", default="http://localhost:6333")
    b.add_argument("--wav-dir", required=True)
    b.add_argument("--out-dir", required=True)
    b.add_argument("--key-out", required=True)
    s = sub.add_parser("score")
    s.add_argument("--key", required=True)
    s.add_argument("--answers", required=True)
    s.add_argument("--key-map", required=True)
    s.add_argument("--out", required=True)
    args = parser.parse_args()
    return build(args) if args.cmd == "build" else score(args)


if __name__ == "__main__":
    sys.exit(main())
