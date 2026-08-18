import hashlib
import json
from pathlib import Path

corpus=Path('scripts/ingestion/corpus')
patch=Path('scripts/ingestion/reviews/confirmed_patch')
apply=json.load(open(patch/'apply_result.json',encoding='utf-8'))
changed=[]
for item in apply['packages']:
    vid=item['video_id']; pkg=corpus/vid
    segdata=json.load(open(pkg/'canonical_segments.json',encoding='utf-8'))
    segs={str(s.get('segment_id')):str(s.get('text','')) for s in segdata.get('segments',[])}
    ledpath=pkg/'correction_ledger.json'; ledger=json.load(open(ledpath,encoding='utf-8'))
    touched=False
    for e in ledger:
        sid=str(e.get('segment_id',''))
        if sid in segs:
            corr=segs[sid]
            if e.get('corrected_segment_text') != corr or e.get('corrected_segment_hash') != hashlib.sha256(corr.encode()).hexdigest():
                e['corrected_segment_text']=corr; e['corrected_segment_hash']=hashlib.sha256(corr.encode()).hexdigest(); touched=True
    if touched:
        ledpath.write_text(json.dumps(ledger,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        manpath=pkg/'artifact_manifest.json'; man=json.load(open(manpath,encoding='utf-8')); man['artifacts']['correction_ledger.json']['byte_size']=ledpath.stat().st_size; man['artifacts']['correction_ledger.json']['sha256']=hashlib.sha256(ledpath.read_bytes()).hexdigest(); manpath.write_text(json.dumps(man,indent=2,ensure_ascii=False)+'\n',encoding='utf-8'); changed.append(vid)
print(json.dumps({'packages_repaired':len(changed),'video_ids':changed}))
