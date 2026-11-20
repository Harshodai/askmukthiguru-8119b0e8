"""READ-ONLY: near-floor rejects (candidate false rejects) + a stratified labelling sample CSV."""
import csv, random, sys
from qdrant_client import QdrantClient
c = QdrantClient(url="http://localhost:6333", timeout=60)
rows, offset = [], None
while True:
    pts, offset = c.scroll(sys.argv[1], limit=512, offset=offset, with_vectors=False,
        with_payload=["speaker_verified", "voice_score", "voice_margin", "voice_threshold_applied", "guru_id", "video_id", "start_ms", "end_ms", "verbatim_text"],
        scroll_filter={"must": [{"key": "record_type", "match": {"value": "retrieval_child"}}]})
    rows += [dict(p.payload, point_id=str(p.id)) for p in pts]
    if offset is None: break
bad = [r for r in rows if not r.get("speaker_verified") and isinstance(r.get("voice_score"), (int, float))]
def floor(r): return float((r.get("voice_threshold_applied") or {}).get("cosine_floor") or 0.4929868455061912)
near = [r for r in bad if floor(r) - 0.10 <= r["voice_score"] < floor(r) and (r.get("voice_margin") or 0) >= 0.15]
far = [r for r in bad if r["voice_score"] < floor(r) - 0.20 or (r.get("voice_margin") or 0) < 0.05]
near_pct = (len(near) / len(bad)) if bad else 0.0
far_pct = (len(far) / len(bad)) if bad else 0.0
print(f"rejected={len(bad)} near-floor & margin>=0.15 (candidate false rejects)={len(near)} ({near_pct:.0%}) "
      f"clear rejects (score << floor or margin<0.05)={len(far)} ({far_pct:.0%})")
print("videos touched by near-floor:", len({r['video_id'] for r in near}))
random.seed(7)
sample = random.sample(near, min(150, len(near))) + random.sample(far, min(50, len(far)))
with open(sys.argv[2], "w", newline="") as f:
    w = csv.writer(f); w.writerow(["point_id", "video_id", "start_s", "end_s", "guru_id", "score", "margin", "floor", "band", "text_head", "LABEL(teacher_correct? y/n)"])
    for r in sample:
        w.writerow([r["point_id"], r["video_id"], (r.get("start_ms") or 0)/1000, (r.get("end_ms") or 0)/1000, r.get("guru_id"),
                    round(r["voice_score"], 3), round(r.get("voice_margin") or 0, 3), round(floor(r), 3),
                    "near" if r in near else "clear", (r.get("verbatim_text") or "")[:80].replace("\n", " "), ""])
print("sample ->", sys.argv[2], len(sample))
