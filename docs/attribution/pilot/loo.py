"""Leave-one-video-out check: is each solo video's speech closer to its own teacher's voiceprint?"""
import numpy as np, pathlib
D = pathlib.Path(__file__).parent / "audio"
LABEL = {"XzS56RqIxeE": "preethaji", "Ejcq9mNGJk0": "preethaji", "TqxxCYnAxo8": "preethaji",
         "w2qbJB6ie9Y": "krishnaji", "rGcNJ_Nsuy8": "krishnaji", "btbKcsb9Dzw": "krishnaji", "hUmlujE6SN0": "krishnaji"}
E = {v: np.load(D / f"{v}.npz")["e"] for v in LABEL}

def centroid(embs: np.ndarray) -> np.ndarray:
    c = embs.mean(0); c /= np.linalg.norm(c)
    keep = embs @ c >= np.percentile(embs @ c, 30)  # drop intros/music/other voices before re-averaging
    c = embs[keep].mean(0); return c / np.linalg.norm(c)

for held in LABEL:
    cents = {t: centroid(np.concatenate([E[v] for v in LABEL if LABEL[v] == t and v != held])) for t in ("preethaji", "krishnaji")}
    s = {t: E[held] @ c for t, c in cents.items()}
    own, other = s[LABEL[held]], s["krishnaji" if LABEL[held] == "preethaji" else "preethaji"]
    margin = own - other
    print(f"{held} {LABEL[held]:9s} n={len(margin):4d} correct={np.mean(margin>0):.3f} "
          f"margin>0.15={np.mean(margin>0.15):.3f} wrong&confident(margin<-0.15)={np.mean(margin<-0.15):.4f} "
          f"own_sim_med={np.median(own):.2f} other_sim_med={np.median(other):.2f}")
