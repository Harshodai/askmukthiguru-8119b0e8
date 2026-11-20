"""READ-ONLY: is a topic missing from ingestion, present but unservable, or servable but not retrieved?"""
import collections, re, sys
from pathlib import Path
from qdrant_client import QdrantClient
TOPICS = {"four sacred secrets": r"(four|4) sacred secrets?", "serene mind": r"serene mind", "soul sync": r"soul sync",
          "surrender": r"\bsurrender", "death/dying": r"\b(death|dying|die)\b"}
tx = Path("/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/transcripts")
c = QdrantClient(url="http://localhost:6333", timeout=60)
rows, offset = [], None
while True:
    pts, offset = c.scroll(sys.argv[1], limit=512, offset=offset, with_vectors=False,
        with_payload=["record_type", "video_id", "verbatim_text", "speaker_verified", "completeness_status", "boundary_status"])
    rows += [p.payload for p in pts]
    if offset is None: break
kids = [r for r in rows if r.get("record_type") == "retrieval_child"]
vids = {r.get("video_id") for r in kids}
for name, pat in TOPICS.items():
    rx = re.compile(pat, re.I)
    tfiles = [f.stem for f in tx.glob("*.md") if rx.search(f.read_text(errors="ignore"))]
    hit = [r for r in kids if rx.search(r.get("verbatim_text") or "")]
    serv = [r for r in hit if r.get("speaker_verified") and str(r.get("completeness_status")) not in ("fragment", "incomplete")]
    print(f"{name:20} transcripts={len(tfiles):3d} (indexed videos among them={len(set(tfiles) & vids):3d}) "
          f"children_with_term={len(hit):3d} speaker_ok&complete={len(serv):3d} "
          f"status={dict(collections.Counter(str(r.get('completeness_status')) for r in hit))}")
