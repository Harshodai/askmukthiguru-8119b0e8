import csv
import hashlib
import json
import re
from pathlib import Path

root=Path('scripts/ingestion'); corpus=root/'corpus'; out=root/'reviews/source_first_audit'; out.mkdir(parents=True,exist_ok=True)
rows=[]
for pkg in sorted(p for p in corpus.iterdir() if p.is_dir()):
    required=['transcript.md','quality_report.json','canonical_segments.json','correction_ledger.json','artifact_manifest.json']
    if not all((pkg/n).is_file() for n in required):
        continue
    t=(pkg/'transcript.md').read_text(encoding='utf-8',errors='replace')
    url_re=r'https?://(?:www\.)?(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)[A-Za-z0-9?=_&%-]+'
    m=re.search(r'\*\*URL:\*\*\s*('+url_re+')',t)
    if m:
        url=m.group(1).rstrip('.,)')
        status='queued'
    else:
        m=re.search(url_re,t)
        url=m.group(0).rstrip('.,)') if m else ''
        status='queued' if m else 'missing_url'
    q=json.loads((pkg/'quality_report.json').read_text(encoding='utf-8'))
    seg=json.loads((pkg/'canonical_segments.json').read_text(encoding='utf-8'))
    rows.append({'video_id':pkg.name,'url':url,'quality_score':q.get('quality_score'),'quality_state':q.get('quality_state'),'segment_count':len(seg.get('segments',[])),'transcript_sha256':hashlib.sha256((pkg/'transcript.md').read_bytes()).hexdigest(),'canonical_sha256':hashlib.sha256((pkg/'canonical_segments.json').read_bytes()).hexdigest(),'ledger_sha256':hashlib.sha256((pkg/'correction_ledger.json').read_bytes()).hexdigest(),'manifest_sha256':hashlib.sha256((pkg/'artifact_manifest.json').read_bytes()).hexdigest(),'analysis_status':status})
fields=list(rows[0]) if rows else []
with (out/'source_analysis_queue.csv').open('w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
(out/'source_analysis_queue.json').write_text(json.dumps(rows,indent=2,ensure_ascii=False)+'\n')
(out/'baseline_summary.json').write_text(json.dumps({'complete_packages':len(rows),'unique_urls':len(set(r['url'] for r in rows)),'queue_status':'queued','corpus_write_performed':False},indent=2)+'\n')
print(json.dumps({'complete_packages':len(rows),'unique_urls':len(set(r['url'] for r in rows)),'queue_csv':str(out/'source_analysis_queue.csv')}))
