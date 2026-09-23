"""Cache ECAPA speaker embeddings on sliding windows for each wav."""
import sys, pathlib, numpy as np, soundfile as sf, torch
from speechbrain.inference.speaker import EncoderClassifier

import os
WIN, HOP, SR = 2.0, float(os.environ.get("HOP", "1.0")), 16000
enc = EncoderClassifier.from_hparams("speechbrain/spkrec-ecapa-voxceleb", savedir=str(pathlib.Path(__file__).parent / "ecapa"))

def embed(wav_path: pathlib.Path) -> None:
    out = wav_path.with_suffix(".npz")
    if out.exists():
        return
    x, sr = sf.read(wav_path, dtype="float32")
    assert sr == SR, sr
    w, h = int(WIN * SR), int(HOP * SR)
    starts = np.arange(0, max(len(x) - w, 1), h)
    rms = np.array([np.sqrt(np.mean(x[s:s + w] ** 2)) for s in starts])
    keep = rms > 0.01  # ponytail: absolute floor only; a relative floor dropped ~97% of evenly-loud audio. Real VAD if music beds matter
    starts = starts[keep]
    embs = []
    for i in range(0, len(starts), 64):
        batch = torch.stack([torch.from_numpy(x[s:s + w]) for s in starts[i:i + 64]])
        embs.append(enc.encode_batch(batch).squeeze(1).numpy())
    e = np.concatenate(embs)
    e /= np.linalg.norm(e, axis=1, keepdims=True)
    np.savez(out, t=starts / SR, e=e)
    print(wav_path.name, len(starts), "windows")

for p in sys.argv[1:]:
    embed(pathlib.Path(p))
