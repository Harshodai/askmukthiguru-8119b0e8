"""Per-video speaker census against the two human-confirmed voiceprints.

Cluster-level call: centroid cosine >= MATCH to a voiceprint and beating the other by MARGIN.
Thresholds come from the pilot: same speaker across videos scored 0.63-0.80, different speakers <= 0.40.
"""
import csv, sys, pathlib, numpy as np
from enroll import voiceprints, voice_clusters

MATCH, MARGIN, MIN_SHARE = 0.55, 0.15, 0.03
HERE = pathlib.Path(__file__).parent

def census(npz: pathlib.Path, vp: dict) -> tuple[dict, list]:
    e = np.load(npz)["e"]; lab = voice_clusters(e)
    share = {"P": 0.0, "K": 0.0, "other": 0.0}; clusters = []
    for c in np.unique(lab):
        m = lab == c; frac = m.mean()
        cen = e[m].mean(0); cen /= np.linalg.norm(cen)
        sp, sk = float(cen @ vp["preethaji"]), float(cen @ vp["krishnaji"])
        who = "P" if sp >= MATCH and sp - sk >= MARGIN else "K" if sk >= MATCH and sk - sp >= MARGIN else "other"
        share[who] += frac
        if frac >= MIN_SHARE: clusters.append((round(frac, 2), who, round(sp, 2), round(sk, 2)))
    return share, sorted(clusters, reverse=True)

def verdict(label: str, s: dict) -> str:
    p, k = s["P"] >= 0.10, s["K"] >= 0.10
    heard = "preethaji_krishnaji" if p and k else "preethaji" if p else "krishnaji" if k else "none"
    if label == "ekam": return f"org label; heard {heard}"
    return "MATCH" if heard == label else f"MISMATCH (heard {heard})"

if __name__ == "__main__":
    vp = voiceprints()
    rows = [l.rstrip("\n").split("\t") for l in open(HERE / "top14" / "list.tsv")]
    out = []
    for vid, label, n, title in rows:
        f = HERE / "top14" / f"{vid}.npz"
        if not f.exists(): print(vid, "MISSING"); continue
        s, cl = census(f, vp)
        v = verdict(label, s)
        out.append(dict(video_id=vid, corpus_label=label, chunks=n, P=round(s["P"], 2), K=round(s["K"], 2),
                        other=round(s["other"], 2), verdict=v, clusters=cl, title=title))
        print(f"{vid} {label:20s} P={s['P']:.2f} K={s['K']:.2f} other={s['other']:.2f}  {v}\n    clusters(share,who,simP,simK): {cl[:5]}")
    with open(HERE / "top14" / "census.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
