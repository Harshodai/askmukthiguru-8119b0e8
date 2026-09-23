"""Speaker attribution + quote-safe sentences for teaching videos. Deterministic, local, no LLM.

Pipeline (research: docs/attribution/speaker_attribution_research_report.md):
  embed     2 s ECAPA voice windows over a video's audio (SpeechBrain, Apache-2.0)
  enroll    voiceprints anchored on human-confirmed clips, widened to every video whose
            cluster matches an anchor at >= ENROLL_MIN; non-teacher cohort sets thresholds
  attribute forced-align the corpus transcript (wav2vec2-base-960h via torchaudio, MIT weights),
            label words by voice cluster, snap speaker changes to pauses, gate quotes
  sample    blind random certification sheet of quotable sentences

Abstain by default: a sentence is quotable as a named teacher only if every word is aligned,
one teacher speaks all of it, it is long enough, ends in terminal punctuation, and keeps a guard
margin from both turn edges. Heavy dependencies (torch, torchaudio, speechbrain, soundfile) are
imported lazily so the gating logic is testable without them.

Run from backend/ with the attribution venv (see requirements-speaker-attribution.txt):
  python scripts/ops/speaker_attribution.py embed   --wav a.wav --out a.npz [--hop 1]
  python scripts/ops/speaker_attribution.py enroll  --npz-dir DIR --out vp.npz
  python scripts/ops/speaker_attribution.py attribute --segments canonical_segments.json \
         --wav a.wav --npz a.npz --voiceprints vp.npz --out quotes.json
  python scripts/ops/speaker_attribution.py sample  --quotes-dir DIR --n 299 --out sheet.csv --key key.json
  python scripts/ops/speaker_attribution.py --self-check
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import random
import re
import sys
from pathlib import Path

import numpy as np

WIN_S = 2.0
SR = 16000
CLUSTER_DISTANCE = 0.6          # cosine distance for agglomerative clustering of windows
ENROLL_MIN = 0.75               # cluster-to-anchor cosine to count as an enrollment session
COHORT_MAX = 0.40               # below this against both teachers = non-teacher voice
THRESHOLD_FLOOR = 0.55
COHORT_GAP = 0.10               # threshold = max(floor, highest non-teacher score + gap)
MARGIN = 0.15                   # best teacher must beat the other teacher by this much
MIN_CLUSTER_WINDOWS = 5         # smaller clusters abstain rather than get a name
SNAP_RADIUS_S = 2.0
GATE_MIN_WORDS, GATE_MIN_S = 6, 1.5
GUARD_START_S, GUARD_END_S = 0.5, 0.3
TERMINAL = re.compile(r"[.?!][\"'”’)]*$")

# Human-confirmed anchor moments (user listened and confirmed, 2026-09-22).
ANCHORS = {"preethaji": ("hUmlujE6SN0", 563.0), "krishnaji": ("rGcNJ_Nsuy8", 386.0)}


# ---------------------------------------------------------------- voice
def embed_windows(wav: Path, hop: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Return (window start times, L2-normalised ECAPA embeddings) for non-silent windows."""
    import soundfile as sf
    import torch
    from speechbrain.inference.speaker import EncoderClassifier

    x, sr = sf.read(wav, dtype="float32")
    if sr != SR:
        raise ValueError(f"{wav}: expected {SR} Hz mono, got {sr}")
    enc = EncoderClassifier.from_hparams("speechbrain/spkrec-ecapa-voxceleb")
    w, h = int(WIN_S * SR), int(hop * SR)
    starts = np.arange(0, max(len(x) - w, 1), h)
    rms = np.array([np.sqrt(np.mean(x[s:s + w] ** 2)) for s in starts])
    starts = starts[rms > 0.01]     # absolute floor only; a relative floor silently dropped ~45% of speech
    out = []
    for i in range(0, len(starts), 64):
        batch = torch.stack([torch.from_numpy(x[s:s + w]) for s in starts[i:i + 64]])
        out.append(enc.encode_batch(batch).squeeze(1).numpy())
    e = np.concatenate(out)
    return starts / SR, e / np.linalg.norm(e, axis=1, keepdims=True)


def cluster(e: np.ndarray) -> np.ndarray:
    from sklearn.cluster import AgglomerativeClustering

    return AgglomerativeClustering(n_clusters=None, distance_threshold=CLUSTER_DISTANCE,
                                   metric="cosine", linkage="average").fit_predict(e)


def unit_mean(v) -> np.ndarray:
    m = np.asarray(v).mean(0)
    return m / np.linalg.norm(m)


def name_cluster(cen: np.ndarray, n_windows: int, vp: dict, thr: dict) -> str:
    """P / K / O (non-teacher) / ? (abstain) for one cluster centroid."""
    sp, sk = float(cen @ vp["preethaji"]), float(cen @ vp["krishnaji"])
    if max(sp, sk) < COHORT_MAX:
        return "O"
    if n_windows < MIN_CLUSTER_WINDOWS:
        return "?"
    if sp >= thr["P"] and sp - sk >= MARGIN:
        return "P"
    if sk >= thr["K"] and sk - sp >= MARGIN:
        return "K"
    return "?"


def window_labels(e: np.ndarray, vp: dict, thr: dict) -> np.ndarray:
    lab = cluster(e)
    names = {c: name_cluster(unit_mean(e[lab == c]), int((lab == c).sum()), vp, thr) for c in np.unique(lab)}
    return np.array([names[c] for c in lab])


def enroll(npz_dir: Path) -> dict:
    """Anchor voiceprints, widened across videos; thresholds from the non-teacher cohort."""
    anchors = {}
    for who, (vid, t_anchor) in ANCHORS.items():
        z = np.load(npz_dir / f"{vid}.npz")
        lab = cluster(z["e"])
        c_id = lab[np.argmin(np.abs(z["t"] - t_anchor))]
        anchors[who] = unit_mean(z["e"][lab == c_id])
    sessions = {k: {} for k in anchors}
    cohort = []
    for f in sorted(npz_dir.glob("*.npz")):
        e = np.load(f)["e"]
        if len(e) < 20:
            continue
        lab = cluster(e)
        for c in np.unique(lab):
            if (lab == c).sum() < 10:
                continue
            cen = unit_mean(e[lab == c])
            s = {k: float(cen @ v) for k, v in anchors.items()}
            best = max(s, key=s.get)
            if s[best] >= ENROLL_MIN:
                sessions[best].setdefault(f.stem, cen)
            elif max(s.values()) < COHORT_MAX:
                cohort.append(cen)
    vp = {k: unit_mean(list(v.values())) for k, v in sessions.items()}
    C = np.array(cohort) if cohort else np.zeros((1, len(vp["preethaji"])))
    thr = {k[0].upper(): max(THRESHOLD_FLOOR, float((C @ v).max()) + COHORT_GAP) for k, v in vp.items()}
    return {"vp": vp, "thr": thr, "sessions": {k: sorted(v) for k, v in sessions.items()}, "cohort": len(cohort)}


# ---------------------------------------------------------------- alignment
def align_words(segments: list[dict], wav: Path) -> list[dict]:
    """Forced-align each corpus segment's text; unalignable segments keep segment times, aligned=False."""
    import soundfile as sf
    import torch
    import torchaudio

    audio, sr = sf.read(wav, dtype="float32")
    bundle = torchaudio.pipelines.WAV2VEC2_ASR_BASE_960H
    model = bundle.get_model().eval()
    labels = bundle.get_labels()
    tok = {c: i for i, c in enumerate(labels)}
    words = []
    for si, seg in enumerate(segments):
        raw = seg["text"].split()
        got = _align_one(seg, raw, audio, sr, model, labels, tok, torch, torchaudio)
        for i, w in enumerate(raw):
            s, e = got[i] if got else (seg["start"], seg["end"])
            words.append({"w": w, "start": float(s), "end": float(e), "seg": si, "aligned": bool(got)})
    return words


def _align_one(seg, raw, audio, sr, model, labels, tok, torch, torchaudio):
    clean = [re.sub(r"[^A-Z']", "", w.upper().replace("’", "'")) for w in raw]
    if not raw or any(not c for c in clean):          # digits/symbol-only words: abstain whole segment
        return None
    a = max(0.0, seg["start"] - 0.25)
    x = torch.from_numpy(audio[int(a * sr):int((seg["end"] + 0.25) * sr)]).unsqueeze(0)
    with torch.inference_mode():
        emis = torch.log_softmax(model(x)[0], dim=-1)
    target = [tok[ch] for w in clean for ch in (w + "|")][:-1]
    if emis.shape[1] < len(target):
        return None
    ali, scores = torchaudio.functional.forced_align(emis, torch.tensor([target]), blank=0)
    spans = torchaudio.functional.merge_tokens(ali[0], scores[0].exp())
    ratio = (x.shape[1] / sr) / emis.shape[1]
    groups, cur = [], []
    for s in spans:
        if labels[s.token] == "|":
            groups.append(cur)
            cur = []
        else:
            cur.append(s)
    groups.append(cur)
    groups = [g for g in groups if g]
    if len(groups) != len(raw):
        return None
    return [(a + g[0].start * ratio, a + g[-1].end * ratio) for g in groups]


# ---------------------------------------------------------------- pure gating logic
def label_words(words: list[dict], t_centres: np.ndarray, win_lab: np.ndarray) -> None:
    for w in words:
        mid = (w["start"] + w["end"]) / 2
        i = int(np.argmin(np.abs(t_centres - mid)))
        w["spk"] = str(win_lab[i]) if abs(t_centres[i] - mid) <= WIN_S * 0.75 else "?"
    for i in range(1, len(words) - 1):            # a lone word flanked by one speaker takes it
        if words[i - 1]["spk"] == words[i + 1]["spk"] != words[i]["spk"]:
            words[i]["spk"] = words[i - 1]["spk"]


def snap_changes(words: list[dict], radius: float = SNAP_RADIUS_S) -> int:
    """Move every speaker change to the longest aligned pause within `radius` seconds."""
    moved, i = 0, 1
    while i < len(words):
        if words[i]["spk"] != words[i - 1]["spk"]:
            left, right, t0 = words[i - 1]["spk"], words[i]["spk"], words[i]["start"]
            cand = [j for j in range(1, len(words)) if abs(words[j]["start"] - t0) <= radius
                    and words[j]["aligned"] and words[j - 1]["aligned"]]
            if cand:
                j = max(cand, key=lambda k: words[k]["start"] - words[k - 1]["end"])
                moved += j != i
                for k in range(min(i, j), max(i, j)):
                    words[k]["spk"] = left if k < j else right
                i = max(i, j)
        i += 1
    return moved


def quote_gate(words: list[dict]) -> tuple[list[dict], collections.Counter]:
    """Return quotable sentences and a count of why every other sentence abstained."""
    turns, turn_of = [], {}
    for k, w in enumerate(words):
        if turns and w["spk"] == turns[-1]["spk"]:
            turns[-1]["end_i"] = k
        else:
            turns.append({"spk": w["spk"], "start_i": k, "end_i": k})
        turn_of[k] = len(turns) - 1
    changes = {t["start_i"] for t in turns[1:]}
    sents, a = [], 0
    for k, w in enumerate(words):
        if TERMINAL.search(w["w"]):
            sents.append((a, k))
            a = k + 1
    if a < len(words):
        sents.append((a, len(words) - 1))
    reasons, quotes = collections.Counter(), []
    for a, b in sents:
        why = _why_not(words, a, b, turns[turn_of[a]], changes)
        reasons[why or "QUOTABLE"] += 1
        if not why:
            ws = words[a:b + 1]
            quotes.append({"speaker": ws[0]["spk"], "start": round(ws[0]["start"], 2),
                           "end": round(ws[-1]["end"], 2), "text": " ".join(w["w"] for w in ws)})
    return quotes, reasons


def _why_not(words, a, b, turn, changes) -> str | None:
    ws = words[a:b + 1]
    spk = {w["spk"] for w in ws}
    t_start, t_end = words[turn["start_i"]]["start"], words[turn["end_i"]]["end"]
    if not all(w["aligned"] for w in ws):
        return "unaligned_word"
    if len(spk) != 1:
        return "mixed_speaker"
    if next(iter(spk)) not in ("P", "K"):
        return "not_teacher"
    if len(ws) < GATE_MIN_WORDS or ws[-1]["end"] - ws[0]["start"] < GATE_MIN_S:
        return "too_short"
    if not TERMINAL.search(ws[-1]["w"]):
        return "no_terminal_punct"
    if a in changes:
        return "first_after_change"
    if turn["start_i"] > 0 and ws[0]["start"] - t_start < GUARD_START_S:
        return "near_turn_start"
    if turn["end_i"] < len(words) - 1 and t_end - ws[-1]["end"] < GUARD_END_S:
        return "near_turn_end"
    return None


# ---------------------------------------------------------------- CLI
def _cmd_attribute(args) -> None:
    segs = json.load(open(args.segments))["segments"]
    z, v = np.load(args.npz), np.load(args.voiceprints)
    vp = {"preethaji": v["preethaji"], "krishnaji": v["krishnaji"]}
    thr = {"P": float(v["thr_P"]), "K": float(v["thr_K"])}
    words = align_words(segs, Path(args.wav))
    label_words(words, z["t"] + WIN_S / 2, window_labels(z["e"], vp, thr))
    moved = snap_changes(words)
    quotes, reasons = quote_gate(words)
    json.dump({"words": words, "quotes": quotes, "reasons": reasons}, open(args.out, "w"))
    aligned = sum(w["aligned"] for w in words) / max(len(words), 1)
    print(f"aligned={aligned:.1%} changes_snapped={moved} {dict(reasons)}")


def _cmd_sample(args) -> None:
    pool = [{"video_id": f.stem.removeprefix("quotes_"), **q}
            for f in sorted(Path(args.quotes_dir).glob("quotes_*.json")) for q in json.load(open(f))["quotes"]]
    pick = random.Random(args.seed).sample(pool, min(args.n, len(pool)))
    with open(args.out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["item", "listen", "start_s", "end_s", "text", "who_speaks (P/K/H/O/X)", "text_matches_audio (Y/N)"])
        for i, q in enumerate(pick, 1):
            w.writerow([i, f"https://www.youtube.com/watch?v={q['video_id']}&t={int(q['start'])}s",
                        q["start"], q["end"], q["text"], "", ""])
    json.dump([{"item": i, **q} for i, q in enumerate(pick, 1)], open(args.key, "w"), indent=1)
    print(f"pool={len(pool)} sampled={len(pick)}")


def _self_check() -> None:
    def mk(w, s, e, spk):
        return {"w": w, "start": s, "end": e, "aligned": True, "spk": spk}

    # host asks, 1.2 s pause, teacher answers; the teacher's first word leaked into the host turn
    words = [mk("Do", 0.0, 0.2, "O"), mk("you", 0.25, 0.4, "O"), mk("agree?", 0.45, 0.8, "O"),
             mk("Yes", 2.0, 2.3, "O")]
    words += [mk(f"w{i}", 2.4 + i * 0.3, 2.6 + i * 0.3, "P") for i in range(8)] + [mk("true.", 5.0, 5.3, "P")]
    words += [mk(f"x{i}", 5.6 + i * 0.3, 5.8 + i * 0.3, "P") for i in range(8)] + [mk("done.", 8.3, 8.6, "P")]
    assert snap_changes(words) == 1 and words[3]["spk"] == "P", "change should snap to the 1.2 s pause"
    quotes, reasons = quote_gate(words)
    assert reasons["not_teacher"] == 1 and reasons["first_after_change"] == 1, reasons
    assert [q["text"].split()[0] for q in quotes] == ["x0"], quotes
    vp = {"preethaji": np.array([1.0, 0.0]), "krishnaji": np.array([0.0, 1.0])}
    assert name_cluster(np.array([1.0, 0.0]), 50, vp, {"P": 0.55, "K": 0.55}) == "P"
    assert name_cluster(np.array([1.0, 0.0]), 3, vp, {"P": 0.55, "K": 0.55}) == "?"
    print("self-check ok")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--self-check", action="store_true")
    sub = p.add_subparsers(dest="cmd")
    e = sub.add_parser("embed")
    e.add_argument("--wav", required=True); e.add_argument("--out", required=True)
    e.add_argument("--hop", type=float, default=1.0)
    n = sub.add_parser("enroll")
    n.add_argument("--npz-dir", required=True); n.add_argument("--out", required=True)
    a = sub.add_parser("attribute")
    for k in ("--segments", "--wav", "--npz", "--voiceprints", "--out"):
        a.add_argument(k, required=True)
    s = sub.add_parser("sample")
    for k in ("--quotes-dir", "--out", "--key"):
        s.add_argument(k, required=True)
    s.add_argument("--n", type=int, default=299); s.add_argument("--seed", type=int, default=20260923)
    args = p.parse_args()
    if args.self_check:
        return _self_check()
    if args.cmd == "embed":
        t, emb = embed_windows(Path(args.wav), args.hop)
        np.savez(args.out, t=t, e=emb)
    elif args.cmd == "enroll":
        r = enroll(Path(args.npz_dir))
        np.savez(args.out, preethaji=r["vp"]["preethaji"], krishnaji=r["vp"]["krishnaji"],
                 thr_P=r["thr"]["P"], thr_K=r["thr"]["K"])
        print(json.dumps({"thr": r["thr"], "sessions": r["sessions"], "cohort": r["cohort"]}))
    elif args.cmd == "attribute":
        _cmd_attribute(args)
    elif args.cmd == "sample":
        _cmd_sample(args)
    else:
        p.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
