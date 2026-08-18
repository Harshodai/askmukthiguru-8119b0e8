import argparse,json,re,csv
from pathlib import Path
PAT=re.compile(r'(?i)\b(mantra|mantram|chant|shanti|santi|aum|om|gayatri|gāyatr|mahamrity|mrityunjaya|mrityu|soham|so-ham|namah|namaha|deeksha|diksha|mukti|mukthi|samskara|samskaras|chakra|chakras|dhyana|dhyāna|pranayama|kundalini|sadhana|samadhi|moksha|bhakti|darshan|sanyasi|dheera|ekam)\b|ॐ')
def load(p):
 try:return json.loads(p.read_text(encoding='utf-8'))
 except:return None
ap=argparse.ArgumentParser();ap.add_argument('--corpus',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True); rows=[]
for p in sorted(x for x in a.corpus.iterdir() if x.is_dir()):
 sv=load(p/'canonical_segments.json') if (p/'canonical_segments.json').is_file() else {}; ss=sv.get('segments',[]) if isinstance(sv,dict) else []
 for i,s in enumerate(ss):
  if not isinstance(s,dict):continue
  txt=str(s.get('text',''))
  if PAT.search(txt):
   rows.append({'video_id':p.name,'segment_index':i,'segment_id':s.get('segment_id'),'start':s.get('start'),'end':s.get('end'),'text':txt,'source_tier':s.get('source_tier'),'matches':';'.join(sorted(set(m.group(0) for m in PAT.finditer(txt)),key=str.lower))})
 t=p/'transcript.md'
 if t.is_file():
  body=t.read_text(encoding='utf-8',errors='replace')
  if re.search(r'(?i)mantra|chant|shanti|gayatri|aum|om ',body):
   rows.append({'video_id':p.name,'segment_index':'transcript','segment_id':'transcript','start':'','end':'','text':body.split('## Transcript',1)[-1].strip(),'source_tier':'transcript','matches':'transcript_hit'})
with (a.out/'mantra_candidates.csv').open('w',newline='',encoding='utf-8') as f:
 w=csv.DictWriter(f,fieldnames=['video_id','segment_index','segment_id','start','end','text','source_tier','matches']);w.writeheader();w.writerows(rows)
from collections import Counter
print(json.dumps({'candidate_rows':len(rows),'video_ids':len(set(r['video_id'] for r in rows)),'match_counts':dict(Counter(m for r in rows for m in r['matches'].split(';')))},ensure_ascii=False))
