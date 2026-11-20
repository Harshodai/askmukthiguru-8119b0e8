"""Torch-free: turn asnorm_compute checkpoints into scores.jsonl, SUMMARY.md, label_sheet.csv.
Distribution comparisons only; no floor is chosen here (see fit_floor.py, which needs human labels)."""
from __future__ import annotations
import argparse, collections, csv, json, sys
from pathlib import Path
import numpy as np

REPO = Path(__file__).resolve().parents[4]
REFS = REPO / "backend/config/ecapa_guru_references.npz"
OLD_SHEET = REPO / "audits/work/2026-11-19-serve-rate/speaker_label_sample.csv"
K_TARGET = 40
EXTRA_ROWS = 100  # extra rejected spans appended after the owner's original 200


def asnorm(emb, ref, cohort, k):
    """Symmetric AS-norm; cohort is (N,192) unit vectors. Returns (raw, asnorm, K used)."""
    k = min(k, len(cohort))
    def stat(v):
        top = np.sort(cohort @ v)[-k:]
        return float(top.mean()), max(float(top.std()), 1e-6)
    s = float(emb @ ref)
    mu_t, sd_t = stat(emb)
    mu_e, sd_e = stat(ref)
    return s, 0.5 * ((s - mu_e) / sd_e + (s - mu_t) / sd_t), k


def pct(v, q):
    return float(np.percentile(v, q))


def hist(vals_by_group, lo, hi, bins=14):
    edges = np.linspace(lo, hi, bins + 1)
    lines = []
    cnt = {g: np.histogram(np.clip(v, lo, hi - 1e-9), edges)[0] for g, v in vals_by_group.items()}
    for i in range(bins):
        cells = "  ".join(f"{g}:{'#' * int(round(40 * cnt[g][i] / max(1, cnt[g].sum())))}{cnt[g][i]:>4}" for g in cnt)
        lines.append(f"{edges[i]:7.2f}..{edges[i+1]:5.2f} | {cells}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True, help="compute dir (population.jsonl, ckpt/, cohort/)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    work, out = Path(a.work), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    refs = {k: v.astype(np.float32) for k, v in np.load(REFS).items()}
    pop = {r["point_id"]: r for r in map(json.loads, (work / "population.jsonl").open())}
    cohort = np.array([c["emb"] for c in json.loads((work / "cohort/cohort.json").read_text())], dtype=np.float32)
    run = json.loads((work / "run.json").read_text())
    recs = {}
    for f in (work / "ckpt").glob("*.json"):
        if f.name.endswith(".validate.json"):
            continue
        for r in json.loads(f.read_text()):
            recs[r["point_id"]] = r

    rows, missing, unscored = [], [], []
    for pid, p in pop.items():
        r = recs.get(pid)
        if r is None:
            unscored.append(pid); continue
        if "emb" not in r:
            missing.append((pid, p["video_id"], r["audio_err"])); continue
        g, other = p["guru_id"], ("preethaji" if p["guru_id"] == "krishnaji" else "krishnaji")
        if g not in refs:
            unscored.append(pid); continue
        emb = np.array(r["emb"], dtype=np.float32)
        coh = np.vstack([cohort, refs[other][None, :]])  # impostors + the other teacher's reference
        raw, an, k = asnorm(emb, refs[g], coh, K_TARGET)
        wc = np.array(r["win_cos"], dtype=float)
        rows.append({"point_id": pid, "group": p["group"], "video_id": p["video_id"], "guru_id": g,
                     "start_ms": p["start_ms"], "end_ms": p["end_ms"], "raw": round(raw, 4),
                     "margin": round(raw - float(emb @ refs[other]), 4), "asnorm": round(an, 4),
                     "stored_voice_score": p.get("voice_score"), "stored_voice_margin": p.get("voice_margin"),
                     "n_windows": r["n_windows"], "win_cos_min": round(float(wc.min()), 4),
                     "win_cos_mean": round(float(wc.mean()), 4), "win_cos_median": round(float(np.median(wc)), 4),
                     "windows_failing": r["win_stats"]["windows_failing"], "windowed_verdict": r["win_verdict"], "K": k})
    with (out / "scores.jsonl").open("w") as fh:
        fh.writelines(json.dumps(x) + "\n" for x in rows)

    P = [x for x in rows if x["group"] == "pass"]; R = [x for x in rows if x["group"] == "reject"]
    pa = np.array([x["asnorm"] for x in P]); pr = np.array([x["raw"] for x in P])
    th = {q: pct(pa, q) for q in (5, 10)}; thr = {q: pct(pr, q) for q in (5, 10)}
    ver = lambda x: x["windowed_verdict"] == "verified"
    def cnt(sub, f): return sum(1 for x in sub if f(x))
    L = []
    L.append("# Speaker AS-norm: distribution comparison (offline, label-free)\n")
    L.append("**These are distribution comparisons between rejected spans and a passing-span sample. They are NOT a validated floor, "
             "and no human labels were used. The passing sample is itself the output of the existing gate, so it is only an "
             "in-distribution reference, not ground truth. A floor needs owner labels: see `fit_floor.py`.**\n")
    L.append(f"- Collection `first_person_v12_shadow`, retrieval_child. Compute: CPU, torch threads={run['threads']}, wall {run['wall_s']} s, "
             f"capped={run['capped']}.")
    L.append(f"- Population: rejected {sum(1 for p in pop.values() if p['group']=='reject')}, passing sample {sum(1 for p in pop.values() if p['group']=='pass')}.")
    L.append(f"- Scored: rejected {len(R)}, passing {len(P)}. Audio missing/unreadable: {len(missing)}. Not reached (cap or no ref): {len(unscored)}.")
    L.append(f"- AS-norm cohort: {len(cohort)} host/other (diarization `O` runs, `build_impostor_slices`) + 1 other-teacher reference per claim; K={min(K_TARGET, len(cohort)+1)}.")
    L.append(f"- Passing AS-norm p5={th[5]:.3f} p10={th[10]:.3f}; passing raw cosine p5={thr[5]:.3f} p10={thr[10]:.3f}.")
    L.append(f"- Existing calibrated windowed verdict (pre-existing calibration, reported not re-tuned): passing sample verified {cnt(P, ver)}/{len(P)}.\n")
    L.append("## Rejected set vs passing reference\n")
    L.append("| measure | count | of |\n|---|---|---|")
    for q in (5, 10):
        L.append(f"| AS-norm >= passing p{q} ({th[q]:.3f}) | {cnt(R, lambda x: x['asnorm'] >= th[q])} | {len(R)} |")
        L.append(f"| raw cosine >= passing p{q} ({thr[q]:.3f}) | {cnt(R, lambda x: x['raw'] >= thr[q])} | {len(R)} |")
    L.append(f"| windowed calibrated verdict = verified | {cnt(R, ver)} | {len(R)} |")
    L.append(f"| windowed verified AND AS-norm >= p5 | {cnt(R, lambda x: ver(x) and x['asnorm'] >= th[5])} | {len(R)} |\n")
    L.append("### Agreement (rejected set): AS-norm >= passing p5 vs windowed verified\n")
    L.append("| | windowed verified | windowed refused |\n|---|---|---|")
    for nm, f in (("AS-norm >= p5", lambda x: x["asnorm"] >= th[5]), ("AS-norm < p5", lambda x: x["asnorm"] < th[5])):
        L.append(f"| {nm} | {cnt(R, lambda x: f(x) and ver(x))} | {cnt(R, lambda x: f(x) and not ver(x))} |")
    L.append("\n### Per video (rejected spans)\n")
    L.append("| video | n | AS>=p5 | AS>=p10 | windowed verified |\n|---|---|---|---|---|")
    byv = collections.defaultdict(list)
    for x in R: byv[x["video_id"]].append(x)
    for v, xs in sorted(byv.items(), key=lambda kv: -len(kv[1])):
        L.append(f"| {v} | {len(xs)} | {cnt(xs, lambda x: x['asnorm']>=th[5])} | {cnt(xs, lambda x: x['asnorm']>=th[10])} | {cnt(xs, ver)} |")
    L.append("\n## Histograms (counts; bars normalised within group)\n")
    L.append("### Raw whole-span cosine (pass vs reject)\n```\n" + hist({"pass": pr, "rej ": np.array([x['raw'] for x in R])}, 0.0, 0.84) + "\n```")
    L.append("### AS-norm (pass vs reject)\n```\n" + hist({"pass": pa, "rej ": np.array([x['asnorm'] for x in R])}, -2.0, 6.0) + "\n```")
    if missing:
        L.append("\n## Spans with missing/unreadable audio\n")
        L += [f"- {pid} ({vid}): {err}" for pid, vid, err in missing[:200]]
    (out / "SUMMARY.md").write_text("\n".join(L) + "\n")

    # label sheet: owner's 200 rows first (re-ordered), then top extra rejected spans; LABEL stays empty
    by = {x["point_id"]: x for x in rows}
    srt = np.sort(pr); sra = np.sort(pa)
    sd_pass = float(pa.std()) or 1.0
    def prio(x):
        d = abs(np.searchsorted(srt, x["raw"]) / len(srt) - np.searchsorted(sra, x["asnorm"]) / len(sra))
        dis = d + (1.0 if (ver(x) != (x["asnorm"] >= th[5])) else 0.0)
        close = min(abs(x["asnorm"] - th[5]), abs(x["asnorm"] - th[10])) / sd_pass
        return dis - 0.5 * min(1.0, close)
    with open(OLD_SHEET, "r", encoding="utf-8", newline="") as fh:
        old = list(csv.reader(fh))
    if not old or not old[0]:
        raise ValueError(f"Empty or invalid sheet in {OLD_SHEET}")
    hdr, old_rows = old[0], old[1:]
    required_cols = {"point_id", "video_id", "start_s", "end_s", "guru_id"}
    missing_cols = required_cols - set(hdr)
    if missing_cols:
        raise ValueError(f"Missing required columns {missing_cols} in {OLD_SHEET}")

    out_rows, seen = [], set()
    for r in old_rows:
        x = by.get(r[0]); seen.add(r[0])
        out_rows.append((prio(x) if x else -99, r, x, "y"))
    extras = sorted((x for x in R if x["point_id"] not in seen), key=prio, reverse=True)[:EXTRA_ROWS]
    label_col = next((c for c in hdr if c.strip().upper().startswith("LABEL")), None)
    for x in extras:
        val_map = {
            "point_id": x["point_id"],
            "video_id": x["video_id"],
            "start_s": x["start_ms"] / 1000,
            "end_s": x["end_ms"] / 1000,
            "guru_id": x["guru_id"],
            "score": x.get("stored_voice_score"),
            "margin": x.get("stored_voice_margin"),
            "floor": 0.493,
            "band": "extra",
        }
        if label_col:
            val_map[label_col] = ""
        r = [val_map.get(col, "") for col in hdr]
        out_rows.append((prio(x), r, x, "n"))
    out_rows.sort(key=lambda t: -t[0])  # old rows with no score fall to the bottom
    with (out / "label_sheet.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(hdr + ["raw_cos", "asnorm", "windowed_verdict", "win_cos_min", "priority", "in_original_sheet"])
        for pr_, r, x, was in out_rows:
            w.writerow(r + ([x["raw"], x["asnorm"], x["windowed_verdict"], x["win_cos_min"], round(pr_, 4)] if x else ["", "", "", "", ""]) + [was])
    print(f"scored R={len(R)} P={len(P)} missing={len(missing)} unscored={len(unscored)} thresholds={th}")


if __name__ == "__main__":
    main()
