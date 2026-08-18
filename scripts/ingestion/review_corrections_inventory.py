import argparse,json,hashlib,sys
from json import JSONDecodeError
from pathlib import Path
from collections import Counter
R=['transcript.md','quality_report.json','canonical_segments.json','correction_ledger.json','artifact_manifest.json']
def load(p):
 try:return json.loads(p.read_text())
 except FileNotFoundError:return None
 except (OSError,JSONDecodeError) as e:
  print(f'warning: failed to load {p}: {e}',file=sys.stderr);return None
def digest(p):
 h=hashlib.sha256(); h.update(p.read_bytes()); return h.hexdigest()
def main(corpus,out):
 out.mkdir(parents=True,exist_ok=True); pkgs=sorted(x for x in corpus.iterdir() if x.is_dir()); rec=[]; cand=[]; qc=Counter(); issues=Counter()
 for p in pkgs:
  vid=p.name; miss=[x for x in R if not (p/x).is_file()]; q=load(p/'quality_report.json') if (p/'quality_report.json').is_file() else {}; state=q.get('quality_state') if isinstance(q,dict) else None; qc[str(state)]+=1; integ=[]; m=load(p/'artifact_manifest.json') if (p/'artifact_manifest.json').is_file() else {}; arts=m.get('artifacts',{}) if isinstance(m,dict) else {}
  for rel,e in arts.items() if isinstance(arts,dict) else []:
   z=p/rel
   if not z.is_file(): integ.append(rel)
   elif isinstance(e,dict) and e.get('sha256') and digest(z)!=e['sha256']: integ.append(rel+'#hash')
  if miss:issues['missing_required']+=1
  if integ:issues['integrity_failure']+=1
  sv=load(p/'canonical_segments.json') if (p/'canonical_segments.json').is_file() else {}; ss=sv.get('segments',[]) if isinstance(sv,dict) else []; by={str(x.get('segment_id')):x for x in ss if isinstance(x,dict)}; lv=load(p/'correction_ledger.json') if (p/'correction_ledger.json').is_file() else []; es=lv if isinstance(lv,list) else lv.get('entries',[]) if isinstance(lv,dict) else []
  for i,e in enumerate(es):
   sid=str(e.get('segment_id','')); s=by.get(sid); a=e.get('char_start'); b=e.get('char_end'); mt=e.get('matched_text',''); li=[]
   if not isinstance(a,int) or not isinstance(b,int):li+=['invalid_offsets']
   if isinstance(a,int) and isinstance(b,int) and (a<0 or b<a):li+=['invalid_range']
   if not s:li+=['segment_not_found']
   else:
    txt=str(e.get('original_segment_text') or s.get('text',''))
    if isinstance(a,int) and isinstance(b,int) and mt and txt[a:b]!=mt:li+=['matched_text_mismatch']
    if e.get('corrected_segment_text') and e['corrected_segment_text']!=s.get('text',''):li+=['corrected_segment_text_mismatch']
   if li:issues['ledger_local_validation_failure']+=1
   cand.append({'candidate_id':vid+':'+str(i),'video_id':vid,'package_path':str(p),'ledger_index':i,'rule_id':e.get('rule_id'),'segment_id':sid,'char_start':a,'char_end':b,'start_seconds':s.get('start') if s else None,'end_seconds':s.get('end') if s else None,'matched_text':mt,'replacement':e.get('replacement'),'reason':e.get('reason'),'local_issues':li,'segment_text':s.get('text') if s else None,'original_segment_text':e.get('original_segment_text'),'quality_state':state})
  rec.append({'video_id':vid,'missing_required':miss,'integrity':integ,'segment_count':len(ss),'quality_state':state,'quality_score':q.get('quality_score') if isinstance(q,dict) else None,'ledger_count':len(es)})
 s={'package_count':len(pkgs),'packages_with_ledgers':sum(x['ledger_count']>0 for x in rec),'candidate_count':len(cand),'quality_state_counts':dict(qc),'issue_counts':dict(issues)}
 (out/'inventory_summary.json').write_text(json.dumps(s,indent=2),encoding='utf-8');(out/'package_inventory.json').write_text(json.dumps(rec,indent=2),encoding='utf-8');(out/'correction_candidates.json').write_text(json.dumps(cand,indent=2,ensure_ascii=False),encoding='utf-8');print(json.dumps(s))
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--corpus',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);x=ap.parse_args();main(x.corpus,x.out)
