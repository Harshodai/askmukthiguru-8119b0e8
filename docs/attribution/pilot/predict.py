"""Blind speaker prediction for each labelling-sheet row: P / K / N (neither = host, narrator, other)."""
import csv, sys, pathlib, numpy as np
from enroll import voiceprints

THR, MARGIN = 0.35, 0.10  # below THR = not a teacher; P/K gap under MARGIN = abstain ("?")

def predict(video: str) -> list[dict]:
    here = pathlib.Path(__file__).parent
    z = np.load(here / "itv" / f"{video}.npz"); e, t = z["e"], z["t"]
    vp = voiceprints()
    rows = list(csv.DictReader(open(here / f"label_{video}.csv")))
    for r in rows:
        a, b = float(r["start_s"]), float(r["end_s"])
        c = t + 1.0  # window centre
        m = (c >= a) & (c <= b)
        if m.sum() == 0 and len(c):
            m = np.abs(c - (a + b) / 2) == np.min(np.abs(c - (a + b) / 2))
            if np.min(np.abs(c - (a + b) / 2)) > 1.5: m[:] = False
        if m.sum() == 0:
            r.update(pred="?", sP="", sK=""); continue
        v = e[m].mean(0); v /= np.linalg.norm(v)
        sp, sk = float(v @ vp["preethaji"]), float(v @ vp["krishnaji"])
        if max(sp, sk) < THR: pred = "N"
        elif abs(sp - sk) < MARGIN: pred = "?"
        else: pred = "P" if sp > sk else "K"
        r.update(pred=pred, sP=f"{sp:.2f}", sK=f"{sk:.2f}")
    return rows

if __name__ == "__main__":
    video = sys.argv[1] if len(sys.argv) > 1 else "UlOt31lBhLY"
    rows = predict(video)
    out = pathlib.Path(__file__).parent / f"pred_{video}.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    from collections import Counter
    print(Counter(r["pred"] for r in rows))
    for r in rows[::7]:
        print(f'{float(r["start_s"]):7.1f} {r["pred"]} P={r["sP"]} K={r["sK"]} | {r["text"][:80]}')
