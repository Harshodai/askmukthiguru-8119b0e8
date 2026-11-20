"""READ-ONLY: why the harness speaker gate rejects fp-context children. Scrolls Qdrant, writes nothing."""
import collections, json, sys
sys.path.insert(0, "/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend")
from qdrant_client import QdrantClient
from domain.speaker_provenance import speaker_write_violations

coll = sys.argv[1] if len(sys.argv) > 1 else "first_person_v12_shadow"
c = QdrantClient(url="http://localhost:6333", timeout=60)
reasons, by_video, role, scores, n = collections.Counter(), collections.defaultdict(collections.Counter), collections.Counter(), [], 0
offset = None
while True:
    pts, offset = c.scroll(coll, limit=512, offset=offset, with_payload=True, with_vectors=False,
                           scroll_filter={"must": [{"key": "record_type", "match": {"value": "retrieval_child"}}]})
    for p in pts:
        pl = p.payload or {}; n += 1
        r = str(pl.get("speaker_role")); role[r] += 1
        vid = pl.get("video_id")
        if r != "guru": why = f"role:{r}"
        elif not pl.get("speaker_verified"): why = "unverified:" + str(pl.get("speaker_verification_status") or pl.get("voice_verification_method") or "none")
        else:
            v = speaker_write_violations(pl, allow_legacy_centroid=True)
            why = ("violation:" + v[0].split(":")[0]) if v else "PASS"
        reasons[why] += 1; by_video[vid][why] += 1
        if isinstance(pl.get("voice_score"), (int, float)): scores.append((float(pl["voice_score"]), why, pl.get("voice_margin")))
    if offset is None: break
print(f"collection={coll} children={n}")
for k, v in reasons.most_common(): print(f"  {v:5d} {v/n:6.1%}  {k}")
fails = [(vid, sum(cnt.values()) - cnt["PASS"], sum(cnt.values())) for vid, cnt in by_video.items()]
fails.sort(key=lambda x: -x[1])
print("videos:", len(by_video), "with >=1 reject:", sum(1 for f in fails if f[1]), "fully rejected:", sum(1 for f in fails if f[1] == f[2]))
print("top rejecting videos:", fails[:12])
sc = sorted(s for s, w, _ in scores)
if sc:
    import statistics as st
    print("voice_score n", len(sc), "p10 %.3f p50 %.3f p90 %.3f" % (sc[len(sc)//10], st.median(sc), sc[9*len(sc)//10]))
    print("non-PASS unverified/violations by category:",
          collections.Counter(w for s, w, _ in scores if w != "PASS").most_common(6))
with open(sys.argv[2] if len(sys.argv) > 2 else "/dev/null", "w", encoding="utf-8") as fh:
    json.dump({"reasons": reasons, "videos": fails}, fh, default=list)
