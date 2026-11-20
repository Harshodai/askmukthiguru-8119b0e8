"""READ-ONLY: score/margin distribution of passing vs failing children and the thresholds applied."""
import collections, sys
from qdrant_client import QdrantClient
c = QdrantClient(url="http://localhost:6333", timeout=60)
rows, offset, th = [], None, collections.Counter()
keys = ["speaker_verified", "speaker_verification_status", "voice_score", "voice_margin", "voice_threshold_applied",
        "voice_verification_method", "voice_calibration_id", "guru_id", "video_id", "start_ms", "end_ms", "speaker_verification_reason"]
while True:
    pts, offset = c.scroll(sys.argv[1], limit=512, offset=offset, with_payload=keys, with_vectors=False,
                           scroll_filter={"must": [{"key": "record_type", "match": {"value": "retrieval_child"}}]})
    rows += [p.payload for p in pts]
    if offset is None: break
for r in rows: th[str(r.get("voice_threshold_applied"))[:120]] += 1
print("thresholds applied:", th.most_common(4))
print("methods:", collections.Counter(r.get("voice_verification_method") for r in rows).most_common(4))
print("fail reasons:", collections.Counter(str(r.get("speaker_verification_reason"))[:60] for r in rows if not r.get("speaker_verified")).most_common(8))
def band(rs, f):
    b = collections.Counter()
    for r in rs:
        v = r.get(f)
        if isinstance(v, (int, float)): b[round(v * 20) / 20] += 1
    return dict(sorted(b.items()))
ok = [r for r in rows if r.get("speaker_verified")]; bad = [r for r in rows if not r.get("speaker_verified")]
print("PASS score bands", band(ok, "voice_score")); print("FAIL score bands", band(bad, "voice_score"))
print("PASS margin bands", band(ok, "voice_margin")); print("FAIL margin bands", band(bad, "voice_margin"))
dur = lambda r: ((r.get("end_ms") or 0) - (r.get("start_ms") or 0)) / 1000
for name, rs in (("PASS", ok), ("FAIL", bad)):
    d = sorted(dur(r) for r in rs)
    if d:
        p10 = d[len(d) // 10]
        p50 = d[len(d) // 2]
        p90 = d[min(9 * len(d) // 10, len(d) - 1)]
        print(name, "duration s p10/p50/p90", p10, p50, p90)
    else:
        print(name, "duration s p10/p50/p90: empty")
print("FAIL by guru:", collections.Counter(r.get("guru_id") for r in bad), "PASS by guru:", collections.Counter(r.get("guru_id") for r in ok))
