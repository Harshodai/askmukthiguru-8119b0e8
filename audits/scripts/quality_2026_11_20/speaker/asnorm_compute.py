"""OFFLINE ECAPA compute for speaker AS-norm. Read-only Qdrant scroll; no writes anywhere but --out.

Run host-side:  nice -n 10 backend/.venv/bin/python3 asnorm_compute.py --out DIR [--limit-spans 3 --threads 1]
Stages (all resume-safe, one checkpoint file per video under DIR/ckpt and DIR/cohort):
  population -> DIR/population.jsonl ; cohort -> impostor slice embeddings ; spans -> window embeddings + verdicts.
Reuses backend scripts.ops.windowed_ecapa_v1_scorer (windowed_verdict, score_against_references,
read_slice, _slide_windows, is_silent, _unit, load_embedder, load_references) and build_impostor_slices.
"""
from __future__ import annotations
import argparse, collections, json, os, random, sys, time
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[4]
BACKEND = REPO / "backend"
sys.path.insert(0, str(BACKEND))
AUDIO = Path.home() / "mukthiguru_attribution_data/audio_archive/wavs"
SPEAKER_JSON = Path.home() / "mukthiguru_attribution_data/bakeoff_2026-09-25/raw"
COLLECTION = "first_person_v12_shadow"
KEYS = ["speaker_verified", "voice_score", "voice_margin", "voice_threshold_applied", "voice_verification_method",
        "guru_id", "video_id", "start_ms", "end_ms", "speaker_verification_reason"]
SEED = 20261120  # fixed so the stratified sample is reproducible


def scroll_population(url: str, n_pass: int) -> list[dict]:
    from qdrant_client import QdrantClient
    c = QdrantClient(url=url, timeout=60)
    rows, off = [], None
    while True:
        pts, off = c.scroll(COLLECTION, limit=512, offset=off, with_payload=KEYS, with_vectors=False,
                            scroll_filter={"must": [{"key": "record_type", "match": {"value": "retrieval_child"}}]})
        rows += [{"point_id": str(p.id), **p.payload} for p in pts]
        if off is None:
            break
    rej = [dict(r, group="reject") for r in rows if not r.get("speaker_verified")]
    ok = [r for r in rows if r.get("speaker_verified")]
    by_vid = collections.defaultdict(list)
    for r in ok:
        by_vid[r.get("video_id")].append(r)
    rnd = random.Random(SEED)
    for v in by_vid.values():
        rnd.shuffle(v)
    picked, i = [], 0  # round-robin over videos = stratified by video
    vids = sorted(by_vid)
    while len(picked) < n_pass and any(by_vid.values()):
        for v in vids:
            if by_vid[v] and len(picked) < n_pass:
                picked.append(dict(by_vid[v].pop(), group="pass"))
    print(f"children={len(rows)} rejected={len(rej)} passing_total={len(ok)} passing_sampled={len(picked)}", flush=True)
    return rej + picked


def embed_windows(audio, embedder, sc):
    """Per-window unit embeddings for non-silent 3s/1.5s windows (batched call of the same encode_batch)."""
    import torch
    wins = [w for w in sc._slide_windows(audio) if not sc.is_silent(w)]
    out = []
    with torch.no_grad():
        for i in range(0, len(wins), 16):
            b = embedder.encode_batch(torch.from_numpy(np.stack(wins[i:i + 16]))).squeeze(1).cpu().numpy().astype(np.float32)
            out += [sc._unit(v) for v in b]
    return [v for v in out if v is not None]


def _atomic_write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(data, allow_nan=False))
    tmp.replace(path)


def span_record(row, embedder, sc, refs, cal):
    s, e = sc.served_window(int(row["start_ms"]), int(row["end_ms"]))
    vid = row.get("video_id") or ""
    audio, err = sc.read_slice(AUDIO / f"{vid}.wav", s, e)
    base = {"point_id": row["point_id"], "audio_err": err}
    if audio is None:
        return base
    embs = embed_windows(audio, embedder, sc)
    if not embs:
        return {**base, "audio_err": "no_nonsilent_windows"}
    wscores = [sc.score_against_references(v, refs) for v in embs]
    guru = str(row.get("guru_id") or "")
    verdict, _r, stats = sc.windowed_verdict(wscores, guru, cal["cosine_floor"], cal["margin_threshold"],
                                             int(cal.get("max_failing_windows", 0)))
    span = sc._unit(np.mean(embs, axis=0))
    win_cos = []
    for w in wscores:
        val = w.get("scores", {}).get(guru) if isinstance(w, dict) else None
        if val is None or (isinstance(val, float) and np.isnan(val)):
            win_cos.append(None)
        else:
            win_cos.append(round(float(val), 4))
    return {**base, "emb": span.tolist(), "n_windows": len(embs),
            "win_cos": win_cos,
            "win_pred": [w.get("predicted") if isinstance(w, dict) else None for w in wscores],
            "win_verdict": verdict, "win_stats": stats}


def cohort_slices(max_per_video: int, max_total: int) -> list[dict]:
    from scripts.ops.build_impostor_slices import slices_for_video
    rows = []
    for p in sorted(SPEAKER_JSON.glob("*_speaker.json")):
        vid = p.name[:-len("_speaker.json")]
        if not (AUDIO / f"{vid}.wav").is_file():
            continue
        try:
            rows += slices_for_video(vid, json.loads(p.read_text()), max_per_video=max_per_video)
        except (OSError, json.JSONDecodeError):
            continue
    random.Random(SEED).shuffle(rows)
    return rows[:max_total]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--qdrant", default="http://localhost:6333")
    ap.add_argument("--n-pass", type=int, default=400)
    ap.add_argument("--limit-spans", type=int, default=0, help="validation: only this many spans+cohort slices")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--max-minutes", type=float, default=90)
    ap.add_argument("--cohort-per-video", type=int, default=2)
    ap.add_argument("--cohort-max", type=int, default=400)
    a = ap.parse_args()
    t0 = time.time()
    import torch
    torch.set_num_threads(a.threads)
    out = Path(a.out)
    (out / "ckpt").mkdir(parents=True, exist_ok=True)
    (out / "cohort").mkdir(exist_ok=True)
    pop_f = out / "population.jsonl"
    if pop_f.exists():
        pop = [json.loads(l) for l in pop_f.open()]
    else:
        pop = scroll_population(a.qdrant, a.n_pass)
        tmp_pop = pop_f.with_suffix(pop_f.suffix + f".tmp.{os.getpid()}")
        tmp_pop.write_text("".join(json.dumps(r, allow_nan=False) + "\n" for r in pop))
        tmp_pop.replace(pop_f)
    import scripts.ops.windowed_ecapa_v1_scorer as sc
    cal = json.loads((BACKEND / "config/windowed_ecapa_calibration.json").read_text())
    refs = sc.load_references(BACKEND / "config/ecapa_guru_references.npz")
    embedder = sc.load_embedder(Path.home() / ".cache/huggingface", device="cpu")
    deadline = t0 + a.max_minutes * 60
    capped = False

    # cohort (impostor) slices
    cs = cohort_slices(a.cohort_per_video, a.cohort_max)
    if a.limit_spans:
        cs = cs[:a.limit_spans]
    cf = out / "cohort" / ("cohort_validate.json" if a.limit_spans else "cohort.json")
    if not cf.exists():
        recs = []
        for i, c in enumerate(cs):
            audio, err = sc.read_slice(AUDIO / f"{c['video_id']}.wav", c["start_ms"], c["end_ms"])
            embs = embed_windows(audio, embedder, sc) if audio is not None else []
            if embs:
                recs.append({"slice_id": c["slice_id"], "video_id": c["video_id"], "emb": sc._unit(np.mean(embs, axis=0)).tolist()})
            if i % 50 == 0:
                print(f"cohort {i}/{len(cs)} t={time.time()-t0:.0f}s", flush=True)
        _atomic_write_json(cf, recs)
    print("cohort embeddings:", len(json.loads(cf.read_text())), flush=True)

    # spans, per video, resume-safe
    by_vid = collections.defaultdict(list)
    for r in pop:
        vid = r.get("video_id")
        if vid:
            by_vid[vid].append(r)
    todo = sorted(by_vid)
    random.Random(SEED).shuffle(todo)  # representative partial coverage if the wall cap hits
    done_n = 0
    for vid in todo:
        f = out / "ckpt" / (f"{vid}.validate.json" if a.limit_spans else f"{vid}.json")
        if f.exists():
            continue
        if time.time() > deadline:
            capped = True
            print("WALL CAP reached; partial results", flush=True)
            break
        rows = by_vid[vid][: a.limit_spans or None]
        _atomic_write_json(f, [span_record(r, embedder, sc, refs, cal) for r in rows])
        done_n += len(rows)
        print(f"video {vid} spans={len(rows)} t={time.time()-t0:.0f}s", flush=True)
        if a.limit_spans and done_n >= a.limit_spans:
            break
    run_file = out / ("run_validate.json" if a.limit_spans else "run.json")
    _atomic_write_json(run_file, {"capped": capped, "wall_s": round(time.time() - t0), "threads": a.threads, "device": "cpu"})
    print(f"done wall={time.time()-t0:.0f}s capped={capped}")


if __name__ == "__main__":
    main()
