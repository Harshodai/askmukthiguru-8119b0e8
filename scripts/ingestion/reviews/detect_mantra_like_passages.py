import csv
import json
import re
from collections import Counter
from pathlib import Path

corpus=Path('scripts/ingestion/corpus'); out=Path('scripts/ingestion/reviews/mantra_audit'); out.mkdir(parents=True,exist_ok=True)
# High-recall triggers. They are candidates, not automatic corrections.
triggers={
 'om_prefix': re.compile(r'(?i)(?<!\w)(?:om|aum)(?:\s+|[-–—])'),
 'om_symbol': re.compile(r'ॐ|ओम्|ॐ'),
 'mantra_word': re.compile(r'(?i)\bmantra(?:s|m)?\b'),
 'sanskrit_script': re.compile(r'[\u0900-\u097F]'),
 'ritual_invocation': re.compile(r'(?i)\b(?:namah|namaha|shanti|shantihi|shantir|soham|hamsa|humsah|gayatri|pashupataye|bhava|ekapad|dvipad|tripad|catus|panch|shatpad|saptapad|svaha|swaha|namo|jaya|jai)\b'),
 'chant_context': re.compile(r'(?i)\b(?:chant|recite|invoke|invocation|prayer|peace chant|sacred verse|sacred words|repeat after me|say together|ritual)\b'),
}
rows=[]
def add(vid,artifact,sid,start,end,text):
    matched=[k for k,rx in triggers.items() if rx.search(text)]
    if not matched: return
    rows.append({'video_id':vid,'artifact':artifact,'segment_id':sid,'start':start,'end':end,'trigger_types':';'.join(matched),'text':text,'context':text[:900]})
for pkg in sorted(p for p in corpus.iterdir() if p.is_dir()):
    segpath=pkg/'canonical_segments.json'
    if segpath.is_file():
        try: data=json.loads(segpath.read_text(encoding='utf-8'))
        except Exception: data={'segments':[]}
        for s in data.get('segments',[]): add(pkg.name,'canonical_segments.json',s.get('segment_id',''),s.get('start',''),s.get('end',''),str(s.get('text','')))
    tpath=pkg/'transcript.md'
    if tpath.is_file():
        body=tpath.read_text(encoding='utf-8',errors='replace').split('## Transcript',1)[-1]
        # Keep paragraph granularity so the full mantra context is preserved.
        for i,para in enumerate(re.split(r'\n\s*\n',body)):
            para=para.strip()
            if para: add(pkg.name,'transcript.md',f'paragraph_{i+1}','','',para)
fields=['video_id','artifact','segment_id','start','end','trigger_types','text','context']
with (out/'mantra_like_locations.csv').open('w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
summary={'candidate_rows':len(rows),'videos':len(set(r['video_id'] for r in rows)),'trigger_counts':dict(Counter(t for r in rows for t in r['trigger_types'].split(';'))),'artifact_counts':dict(Counter(r['artifact'] for r in rows)),'video_counts':dict(Counter(r['video_id'] for r in rows).most_common())}
(out/'mantra_like_summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({'candidate_rows':len(rows),'videos':len(set(r['video_id'] for r in rows)),'trigger_counts':summary['trigger_counts']},ensure_ascii=False))
