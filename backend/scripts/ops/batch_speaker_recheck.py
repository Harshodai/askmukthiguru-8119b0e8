#!/usr/bin/env python3
"""Batch speaker-verify pass over unverified clips in a first-person collection.

Reuses the owner-validated 2026-10-11 recheck criteria unchanged
(`speaker_attribution.name_cluster` centroid verdict + `verify_speakers`-style
per-window host check) — see ~/mukthiguru_attribution_data/speaker_recheck_20261011/.

Serving invariant: NEVER invent speaker credit (L-FP-HYBRID-SCAFFOLD-1 /
L-NO-INVENTED-CREDIT-1). A clip earns `speaker_verified=true` only when BOTH
hold:
  1. centroid verdict = verified_match (best teacher clears its voiceprint
     threshold and beats the other by MARGIN), and
  2. per-window check passes: no "O" (host/other) window overlaps the clip and
     no "?" window overlaps it (same strictness that rejected 56% of the
     rechecked sample; per-window requires the video's RAW *_speaker.json from
     the mass-ingest run — clips without it stay untouched).

Modes (--collection is scroll/write target):
    unverified OUT.jsonl
        scroll every clip with speaker_verified not true; write work list.
    run    CLIPS.jsonl OUT.jsonl [--limit N]
        ECAPA centroid verdicts; resume-safe (skips point_ids already in OUT).
    report CLIPS.jsonl OUT.jsonl
        aggregate centroid + per-window outcomes; writes report JSON.
    apply  CLIPS.jsonl OUT.jsonl [--collection first_person_v8] [--report R.json]
        set_payload speaker_verified=true ONLY for rows passing BOTH criteria.
        Everything else (ambiguous / pw reject / no evidence) stays untouched.

Runs host-side on the pilot venv (torch + speechbrain + MPS):
  ~/mukthiguru_attribution_data/bakeoff_2026-09-25/venv/bin/python \\
      -m scripts.ops.batch_speaker_recheck unverified /tmp/unv.jsonl
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
import time
import urllib.request
from pathlib import Path

HOME = Path.home() / "mukthiguru_attribution_data"


def qdrant_scroll(collection: str):
    off = None
    while True:
        body = {
            "limit": 256,
            "with_vector": False,
            "offset": off,
            "with_payload": [
                "video_id",
                "start_ms",
                "end_ms",
                "teacher_id",
                "speaker_verified",
                "channel",
            ],
        }
        req = urllib.request.Request(
            f"http://localhost:6333/collections/{collection}/points/scroll",
            data=json.dumps(body).encode(),
            headers={"content-type": "application/json"},
        )
        r = json.load(urllib.request.urlopen(req))["result"]  # nosec B310 -- fixed http://localhost Qdrant URL
        yield from r["points"]
        off = r.get("next_page_offset")
        if off is None:
            return


def unverified(out_path: str, collection: str) -> int:
    rows = []
    for p in qdrant_scroll(collection):
        pl = p["payload"]
        if pl.get("teacher_id") not in ("preethaji", "krishnaji"):
            continue
        if pl.get("speaker_verified") is True:
            continue
        rows.append(
            {
                "point_id": p["id"],
                "video_id": pl["video_id"],
                "start_ms": pl["start_ms"],
                "end_ms": pl["end_ms"],
                "labelled": {"preethaji": "P", "krishnaji": "K"}[pl["teacher_id"]],
            }
        )
    rows.sort(key=lambda c: (c["video_id"], c["start_ms"]))
    Path(out_path).write_text("\n".join(json.dumps(r) for r in rows) + ("\n" if rows else ""))
    print(f"unverified clips written: {len(rows)} -> {out_path}")
    return len(rows)


def _pw_loader(raw_dir: Path):
    """Per-video window labels; None -> no per-window evidence for that video."""
    cache: dict[str, dict | None] = {}

    def get(vid: str) -> dict | None:
        if vid not in cache:
            p = raw_dir / f"{vid}_speaker.json"
            cache[vid] = json.load(open(p)) if p.exists() else None
        return cache[vid]

    return get


def verify_clip_speaker_strict(
    clip: dict, spk: dict | None, spk_win: dict | None
) -> tuple[bool, dict]:
    """(cent_ok, pw_pass, per_window). Mirrors recheck2.pw(): the clip must pass
    verify_clip_speaker AND show no "O" (non-teacher) or "?" (abstain) window
    overlapping the clip span (±1 s pad). Without per-window speaker evidence
    for the video, responsibility falls to the caller to keep the clip
    unverified (applies never pass when spk_win is None)."""
    from ingest.verbatim.speaker_verify import verify_clip_speaker

    ok = verify_clip_speaker(
        {
            "speaker": {"P": "preethaji", "K": "krishnaji"}[clip["labelled"]],
            "start": clip["start_ms"] / 1000,
            "end": clip["end_ms"] / 1000,
        },
        spk or {},
    )
    counts: collections.Counter = collections.Counter()
    if spk_win and spk_win.get("ok"):
        a, b = clip["start_ms"] / 1000, clip["end_ms"] / 1000
        ov = [
            lab
            for t, lab in zip(spk_win["t_centres"], spk_win["win_lab"])
            if t - 1 < b and t + 1 > a
        ]
        counts = collections.Counter(ov)
    pw_pass = ok and counts.get("O", 0) == 0 and counts.get("?", 0) == 0
    per_window = {
        "n_overlap": sum(counts.values()),
        "n_windows_O": counts.get("O", 0),
        "n_windows_unknown": counts.get("?", 0),
        "n_windows_other_teacher": counts.get("K" if clip["labelled"] == "P" else "P", 0),
    }
    return ok, bool(pw_pass), per_window


def run(clips_path: str, out_path: str, limit: int) -> int:
    _here = Path(__file__).resolve()
    sys.path.insert(0, str(_here.parents[2]))  # backend/ (ingest.verbatim)
    sys.path.insert(0, str(_here.parents[1] / "ops"))  # backend/scripts/ops (speaker_attribution)
    import numpy as np
    import speaker_attribution as sa
    from speechbrain.inference.speaker import EncoderClassifier

    v = np.load(HOME / "voiceprints2.npz")
    vp = {"preethaji": v["preethaji"], "krishnaji": v["krishnaji"]}
    thr = {"P": float(v["thr_preethaji"]), "K": float(v["thr_krishnaji"])}
    enc = EncoderClassifier.from_hparams(
        "speechbrain/spkrec-ecapa-voxceleb",
        savedir=str(HOME / "speaker_recheck_20261011" / "ecapa"),
    )
    import soundfile as sf
    import torch

    torch.set_num_threads(2)
    done = set()
    if Path(out_path).exists():
        done = {json.loads(ln)["point_id"] for ln in open(out_path) if ln.strip()}
    clips = [json.loads(ln) for ln in open(clips_path)]
    clips = [c for c in clips if c["point_id"] not in done][: limit or None]
    SR = sa.SR
    cur_vid, wav = None, None
    t0 = time.time()
    outp = open(out_path, "a")
    with outp:
        for n, c in enumerate(clips, 1):
            rec = {k: c[k] for k in ("point_id", "video_id", "start_ms", "end_ms", "labelled")}
            rec.update(
                score_P=None,
                score_K=None,
                n_windows=None,
                cluster_label=None,
                verdict="no_evidence",
            )
            try:
                if c["video_id"] != cur_vid:
                    wav_path = HOME / "audio_archive" / "wavs" / f"{c['video_id']}.wav"
                    wav, sr = sf.read(wav_path, dtype="float32")
                    if sr != SR:
                        wav = None
                    cur_vid = c["video_id"]
                if wav is not None:
                    a, b = c["start_ms"] // 1000, c["end_ms"] // 1000
                    span = wav[a * SR : b * SR]
                    if len(span) >= SR // 2:
                        import torch as th

                        cut = np.array(
                            [
                                span[max(0, i) : i + int(sa.WIN_S * SR)]
                                for i in range(0, len(span) - int(sa.WIN_S * SR) + 1, SR)
                            ]
                        )
                        cut = np.stack(cut) if len(cut) else None
                        if cut is None or cut.shape[0] < 3:
                            rec["verdict"] = "too_short_windows"
                        else:
                            emb = enc.encode_batch(th.tensor(cut).float()).squeeze(1)
                            ec = (
                                (emb / np.linalg.norm(emb.cpu().numpy(), axis=1, keepdims=True))
                                .cpu()
                                .numpy()
                            )
                            cen = sa.unit_mean(ec)
                            lab = sa.name_cluster(cen, len(ec), vp, thr)
                            rec["n_windows"] = len(ec)
                            rec["cluster_label"] = lab
                            rec["score_P"] = round(float(cen @ vp["preethaji"]), 4)
                            rec["score_K"] = round(float(cen @ vp["krishnaji"]), 4)
                            if lab == rec["labelled"]:
                                rec["verdict"] = "verified_match"
                            elif lab in ("O", "?"):
                                rec["verdict"] = "ambiguous"
                            else:
                                rec["verdict"] = "mismatch"
            except FileNotFoundError:
                rec["verdict"] = "no_wav"
            except Exception as e:  # noqa: BLE001 - report and continue, never crash the batch
                rec["verdict"] = f"error:{type(e).__name__}"
                rec["error"] = str(e)[:120]
            outp.write(json.dumps(rec) + "\n")
            outp.flush()  # crash-safe: MPS memory pressure can kill this long batch
            if n % 10 == 0:
                print(f"  {n}/{len(clips)}  {time.time() - t0:.0f}s  {rec['verdict']}", flush=True)
    print(f"centroid pass done -> {out_path}")
    return 0


def report(clips_path: str, out_path: str) -> int:
    """Aggregate centroid outcomes + per-window pass/fail into one JSON report.
    Write-only decision data; no Qdrant mutations."""
    raw_dir = HOME / "mass_ingest_2026-10" / "raw"
    spk_get = _pw_loader(raw_dir)
    rows = (
        [json.loads(ln) for ln in open(out_path) if ln.strip()] if Path(out_path).exists() else []
    )
    work = {c["point_id"]: c for c in (json.loads(ln) for ln in open(clips_path) if ln.strip())}
    pw_get = _pw_loader_path_cache(rows, spk_get, work)
    out = {
        "collection": "first_person_v8",
        "total": len(work),
        "centroid": dict(collections.Counter(r.get("verdict") for r in rows)),
        "perwindow": pw_get,
        "rows": len(rows),
    }
    rp = Path(out_path).with_name(Path(out_path).stem + "_report.json")
    rp.write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=1)[:800])
    return 0


def _pw_loader_path_cache(rows, spk_get, work):
    cand_pass = reject = no_evidence = 0
    for r in rows:
        if r.get("verdict") != "verified_match":
            continue
        spk_win = spk_get(r["video_id"])
        if spk_win is None:
            no_evidence += 1
            continue
        c = work.get(r["point_id"])
        ok, _pw, per = verify_clip_speaker_strict(c, spk_get(r["video_id"]), spk_win)
        cand_pass += int(ok)
        if not ok:
            reject += 1
    return {"both_pass": cand_pass, "pw_reject": reject, "no_window_evidence": no_evidence}


def apply(clips_path: str, out_path: str, collection: str) -> int:
    from qdrant_client import QdrantClient

    raw_dir = HOME / "mass_ingest_2026-10" / "raw"
    spk_get = _pw_loader(raw_dir)
    work = {c["point_id"]: c for c in (json.loads(ln) for ln in open(clips_path) if ln.strip())}
    rows = [json.loads(ln) for ln in open(out_path) if ln.strip()]
    client = QdrantClient(url="http://localhost:6333")
    verified = []
    for r in rows:
        if r.get("verdict") != "verified_match":
            continue
        spk_win = spk_get(r["video_id"])
        if spk_win is None:
            continue  # no per-window evidence: stay unverified (honest, strict)
        ok, pw_pass, _per = verify_clip_speaker_strict(
            work[r["point_id"]], spk_get(r["video_id"]), spk_win
        )
        if ok and pw_pass and _per["n_windows_unknown"] == 0:
            verified.append(r["point_id"])
    print(f"would verify {len(verified)} of {len(rows)} scored / {len(work)} candidates")
    summary = {
        "candidate_count": len(work),
        "scored": len(rows),
        "verified_pending_apply": len(verified),
        "applied": False,
    }
    if not verified:
        rp = Path(out_path).with_name(Path(out_path).stem + "_apply.json")
        rp.write_text(json.dumps(summary, indent=1))
        return 0
    summary["applied"] = True
    for i in range(0, len(verified), 256):
        chunk = verified[i : i + 256]
        client.set_payload(
            collection_name=collection, payload={"speaker_verified": True}, points=chunk, wait=True
        )
        print(f"  set_payload chunk {len(chunk)}")
    client.close()
    rp = Path(out_path).with_name(Path(out_path).stem + "_apply.json")
    rp.write_text(json.dumps(summary, indent=1))
    print(f"applied {len(verified)} -> {collection}; summary {rp}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("mode", choices=["unverified", "run", "report", "apply"])
    ap.add_argument("clips", help="CLIPS work list")
    ap.add_argument("out", help="centroid results / report json")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--collection", default="first_person_v8")
    args = ap.parse_args(argv)
    if args.mode == "unverified":
        return unverified(args.clips, args.collection)
    if args.mode == "run":
        return run(args.clips, args.out, args.limit)
    if args.mode == "report":
        return report(args.clips, args.out)
    return apply(args.clips, args.out, args.collection)


if __name__ == "__main__":
    sys.exit(main())
