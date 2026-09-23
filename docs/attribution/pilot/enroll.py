"""Voiceprints anchored on human-confirmed moments (user confirmed 2026-09-23)."""
import numpy as np, pathlib
from sklearn.cluster import AgglomerativeClustering

D = pathlib.Path(__file__).parent / "audio"
ANCHORS = {"preethaji": ("hUmlujE6SN0", 563.0), "krishnaji": ("rGcNJ_Nsuy8", 386.0)}

def voice_clusters(e: np.ndarray) -> np.ndarray:
    return AgglomerativeClustering(n_clusters=None, distance_threshold=0.6, metric="cosine", linkage="average").fit_predict(e)

def anchored_centroid(video: str, t_anchor: float) -> np.ndarray:
    z = np.load(D / f"{video}.npz"); e, t = z["e"], z["t"]
    lab = voice_clusters(e)
    c_id = lab[np.argmin(np.abs(t - t_anchor))]  # the cluster the confirmed moment belongs to
    c = e[lab == c_id].mean(0)
    print(f"  anchor {video}@{t_anchor:.0f}s -> cluster of {int((lab == c_id).sum())}/{len(lab)} windows")
    return c / np.linalg.norm(c)

def voiceprints() -> dict[str, np.ndarray]:
    return {k: anchored_centroid(*v) for k, v in ANCHORS.items()}

if __name__ == "__main__":
    vp = voiceprints()
    print("P-K voiceprint cosine:", round(float(vp["preethaji"] @ vp["krishnaji"]), 3))
    for v in ["XzS56RqIxeE", "TqxxCYnAxo8", "btbKcsb9Dzw", "Ejcq9mNGJk0", "w2qbJB6ie9Y"]:
        e = np.load(D / f"{v}.npz")["e"]; sp, sk = e @ vp["preethaji"], e @ vp["krishnaji"]
        best = np.maximum(sp, sk)
        print(f"{v}: P={np.mean((sp>sk)&(best>=0.45)):.2f} K={np.mean((sk>sp)&(best>=0.45)):.2f} "
              f"neither={np.mean(best<0.45):.2f}  (share of speech windows, threshold 0.45)")
