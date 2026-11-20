import csv
import json
import os
import sys
import time
from pathlib import Path
import numpy as np
import soundfile as sf
import torch
from speechbrain.inference.speaker import EncoderClassifier

REPO = Path(__file__).resolve().parents[2]


def main():
    refs = np.load(str(REPO / '.work/speaker_2026-10-31/references_v2.npz'))
    ref_k = refs['krishnaji'] / np.linalg.norm(refs['krishnaji'])
    ref_p = refs['preethaji'] / np.linalg.norm(refs['preethaji'])

    print("Loading SpeechBrain ECAPA model...")
    enc = EncoderClassifier.from_hparams('speechbrain/spkrec-ecapa-voxceleb')
    wav_dir = str(Path.home() / 'mukthiguru_attribution_data' / 'audio_archive' / 'wavs')

    csv_path = str(REPO / 'audits/work/2026-11-19-serve-rate/speaker_label_sample.csv')
    with open(csv_path) as f:
        rows = list(csv.DictReader(f))

    print(f"Loaded {len(rows)} rows from {csv_path}. Running acoustic attribution...")
    t0 = time.time()
    results = []

    for idx, r in enumerate(rows):
        vid = r['video_id']
        s = float(r['start_s'])
        e = float(r['end_s'])
        gid = r['guru_id']
        wav_path = os.path.join(wav_dir, f"{vid}.wav")

        if not os.path.exists(wav_path):
            results.append({
                "row_number": idx + 1,
                "point_id": r['point_id'],
                "video_id": vid,
                "start_s": s,
                "end_s": e,
                "guru_id": gid,
                "error": "missing_wav"
            })
            continue

        info = sf.info(wav_path)
        sr = info.samplerate
        s_idx = max(0, int(s * sr))
        e_idx = min(info.frames, int(e * sr))

        if e_idx <= s_idx:
            results.append({
                "row_number": idx + 1,
                "point_id": r['point_id'],
                "video_id": vid,
                "start_s": s,
                "end_s": e,
                "guru_id": gid,
                "error": "invalid_bounds"
            })
            continue

        slice_x, _ = sf.read(wav_path, start=s_idx, stop=e_idx, dtype='float32')
        if slice_x.ndim > 1:
            slice_x = slice_x.mean(axis=1)

        rms = float(np.sqrt(np.mean(slice_x**2))) if len(slice_x) > 0 else 0.0

        # If slice longer than 25s, evaluate middle 20s
        if len(slice_x) > sr * 25:
            mid = len(slice_x) // 2
            slice_x = slice_x[mid - int(sr * 10) : mid + int(sr * 10)]

        with torch.no_grad():
            emb = enc.encode_batch(torch.from_numpy(slice_x).unsqueeze(0)).squeeze().cpu().numpy()
            norm = np.linalg.norm(emb)
            if norm > 1e-6:
                emb = emb / norm
            else:
                emb = np.zeros_like(emb)

        sim_k = float(np.dot(emb, ref_k))
        sim_p = float(np.dot(emb, ref_p))

        # Attribution decision based on anchors
        best_sim = max(sim_k, sim_p)
        best_guru = "krishnaji" if sim_k > sim_p else "preethaji"
        margin = abs(sim_k - sim_p)

        results.append({
            "row_number": idx + 1,
            "point_id": r['point_id'],
            "video_id": vid,
            "start_s": s,
            "end_s": e,
            "guru_id": gid,
            "sim_krishnaji": round(sim_k, 4),
            "sim_preethaji": round(sim_p, 4),
            "best_guru": best_guru,
            "margin": round(margin, 4),
            "rms": round(rms, 5),
            "duration_s": round(e - s, 2)
        })

        if (idx + 1) % 25 == 0:
            print(f"Processed {idx + 1}/{len(rows)} in {time.time()-t0:.1f}s")

    out_file = ".work/youtube_evidence/ecapa_full_results.json"
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Saved {len(results)} results to {out_file} in {time.time()-t0:.1f}s")

if __name__ == "__main__":
    main()
