import argparse,json,hashlib,re
from pathlib import Path
from collections import Counter

def load(p):
 try:return json.loads(p.read_text(encoding='utf-8'))
 except Exception as e:return {'__error__':str(e)}
def sha(p):
 h=hashlib.sha256();
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def audit(root,out):
 out.mkdir(parents=True,exist_ok=True); pkgs=sorted(p for p in root.iterdir() if p.is_dir()); rec=[]; issues=[]; counts=Counter(); states=Counter(); total_segments=0; total_words=0
 for p in pkgs:
  vid=p.name; required=['transcript.md','quality_report.json','canonical_segments.json','correction_ledger.json','artifact_manifest.json']; miss=[n for n in required if not (p/n).is_file()]
  if miss:
   for n in miss: issues.append({'video_id':vid,'severity':'critical','type':'missing_artifact','artifact':n})
   rec.append({'video_id':vid,'package_complete':False,'missing':miss}); counts['incomplete_package']+=1; continue
  q=load(p/'quality_report.json'); sv=load(p/'canonical_segments.json'); led=load(p/'correction_ledger.json'); man=load(p/'artifact_manifest.json'); t=(p/'transcript.md').read_text(encoding='utf-8',errors='replace'); ss=sv.get('segments',[]) if isinstance(sv,dict) else []; es=led if isinstance(led,list) else led.get('entries',[]) if isinstance(led,dict) else []
  local=[]; total_segments+=len(ss); total_words+=len(re.findall(r"\b\w+[’']?\w*\b",t.split('## Transcript',1)[-1]))
  for rel,e in (man.get('artifacts',{}).items() if isinstance(man,dict) and isinstance(man.get('artifacts',{}),dict) else []):
   fp=p/rel
   if not fp.is_file():local.append(('critical','manifest_missing_file',rel))
   elif isinstance(e,dict) and e.get('sha256') and sha(fp)!=e['sha256']:local.append(('critical','manifest_hash_mismatch',rel))
  ids=[str(s.get('segment_id','')) for s in ss]; by={str(s.get('segment_id')):s for s in ss}; prev=-1; duration=float(q.get('duration_seconds') or 0) if isinstance(q,dict) else 0
  for i,s in enumerate(ss):
   a=s.get('start'); b=s.get('end'); txt=str(s.get('text',''))
   if not isinstance(a,(int,float)) or not isinstance(b,(int,float)) or a<0 or b<a:local.append(('high','invalid_timestamp',str(i)))
   if isinstance(a,(int,float)) and a<prev:local.append(('high','non_monotonic_timestamp',str(i)))
   if isinstance(a,(int,float)):prev=a
   if not txt.strip() and not s.get('is_non_speech'):local.append(('medium','empty_spoken_segment',str(i)))
   if isinstance(b,(int,float)) and duration and b>duration+2:local.append(('medium','segment_exceeds_duration',str(i)))
  for i,e in enumerate(es):
   sid=str(e.get('segment_id','')); s=by.get(sid); orig=e.get('original_segment_text'); corr=e.get('corrected_segment_text'); a=e.get('char_start'); b=e.get('char_end'); mt=e.get('matched_text','')
   if not s:local.append(('high','ledger_segment_missing',str(i)));continue
   if not isinstance(a,int) or not isinstance(b,int) or b<a:local.append(('high','ledger_offset_invalid',str(i)))
   elif orig is not None and orig[a:b]!=mt:local.append(('high','ledger_original_span_mismatch',str(i)))
   if corr is not None and corr!=s.get('text'):local.append(('high','ledger_corrected_text_mismatch',str(i)))
  if isinstance(q,dict):
   states[str(q.get('quality_state'))]+=1
   if q.get('terminology_corrections_count')!=len(es):local.append(('medium','quality_ledger_count_mismatch',f"{q.get('terminology_corrections_count')}!={len(es)}"))
  if isinstance(man,dict):
   if man.get('video_id')!=vid:local.append(('critical','manifest_video_id_mismatch',str(man.get('video_id'))))
   if q.get('quality_state')!=man.get('final_quality_state'):local.append(('high','quality_state_manifest_mismatch',''))
  if '**Video ID:**' not in t or vid not in t:local.append(('medium','transcript_metadata_missing_video_id',''))
  if '## Transcript' not in t:local.append(('high','transcript_section_missing',''))
  body=t.split('## Transcript',1)[-1]; th=re.search(r'\*\*Transcript Hash:\*\* `([^`]+)`',t); bodytext=body.split('\n',1)[-1].strip() if '\n' in body else body.strip()
  if th and hashlib.sha256(bodytext.encode()).hexdigest()!=th.group(1):local.append(('high','transcript_hash_content_mismatch',''))
  for sev,typ,loc in local:issues.append({'video_id':vid,'severity':sev,'type':typ,'location':loc}); counts[typ]+=1
  rec.append({'video_id':vid,'package_complete':True,'quality_state':q.get('quality_state'),'quality_score':q.get('quality_score'),'segment_count':len(ss),'ledger_count':len(es),'issue_count':len(local),'manifest_hash':man.get('manifest_hash')})
 summary={'package_dirs':len(pkgs),'complete_packages':sum(r.get('package_complete') for r in rec),'incomplete_packages':sum(not r.get('package_complete') for r in rec),'transcript_files':sum((p/'transcript.md').is_file() for p in pkgs),'total_segments':total_segments,'total_ledger_entries':sum(r.get('ledger_count',0) for r in rec),'total_transcript_words_estimate':total_words,'quality_states':dict(states),'issue_counts':dict(counts),'issue_total':len(issues)}
 (out/'end_to_end_summary.json').write_text(json.dumps(summary,indent=2)+'\n');(out/'package_audit.json').write_text(json.dumps(rec,indent=2)+'\n');(out/'end_to_end_issues.json').write_text(json.dumps(issues,indent=2)+'\n');print(json.dumps(summary))
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--corpus',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();audit(a.corpus,a.out)
