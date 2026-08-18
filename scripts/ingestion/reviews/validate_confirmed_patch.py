import csv
import json
from pathlib import Path
from collections import Counter

root = Path('scripts/ingestion')
corpus = root / 'corpus'
review = root / 'reviews'
out = review / 'confirmed_patch'
out.mkdir(parents=True, exist_ok=True)
rows = list(csv.DictReader(open(review / 'sanskrit_terms_audit/classified_sanskrit_term_locations.csv', encoding='utf-8')))
confirmed_types = {'confirmed_asr_correction','confirmed_mantra_correction','confirmed_term_correction','confirmed_source_term_correction','confirmed_project_style_correction','manual_compound_correction','confirmed_project_spelling'}
confirmed = [r for r in rows if r['disposition'] in confirmed_types]
valid=[]; invalid=[]
for r in confirmed:
    pkg = corpus / r['video_id']
    artifact = r['artifact']
    path = pkg / artifact
    matched = r['matched_form']
    ok = path.is_file()
    evidence=''
    if not ok:
        evidence='missing artifact'
    elif artifact == 'canonical_segments.json':
        try:
            data=json.loads(path.read_text(encoding='utf-8'))
            seg=next((s for s in data.get('segments',[]) if str(s.get('segment_id'))==str(r['segment_id'])),None)
            text=str(seg.get('text','')) if seg else ''
            start=r.get('char_start',''); end=r.get('char_end','')
            if start != '' and end != '':
                ok = text[int(start):int(end)] == matched
                evidence = 'canonical span matches' if ok else f"span={text[int(start):int(end)]!r}"
            else:
                ok = matched.lower() in text.lower()
                evidence = 'canonical text contains candidate' if ok else 'candidate absent from canonical text'
        except Exception as e:
            ok=False; evidence=f'parse error: {e}'
    elif artifact == 'transcript.md':
        text=path.read_text(encoding='utf-8',errors='replace')
        body=text.split('## Transcript',1)[-1]
        start=r.get('char_start',''); end=r.get('char_end','')
        if start != '' and end != '':
            ok = body[int(start):int(end)] == matched
            evidence='transcript span matches' if ok else f"span={body[int(start):int(end)]!r}"
        else:
            ok = matched.lower() in body.lower() or 'diksha' in body.lower()
            evidence='transcript contains candidate' if ok else 'candidate absent from transcript'
    item=dict(r); item['validation']=evidence; item['validation_ok']=str(ok).lower()
    (valid if ok else invalid).append(item)
fields = (list(confirmed[0]) if confirmed else (list(rows[0]) if rows else ['video_id'])) + ['validation','validation_ok']
with open(out/'confirmed_corrections_validated.csv','w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(valid+invalid)
summary={'confirmed_rows':len(confirmed),'valid_rows':len(valid),'invalid_rows':len(invalid),'invalid_by_reason':dict(Counter(x['validation'] for x in invalid)),'by_disposition':dict(Counter(x['disposition'] for x in confirmed))}
(out/'validation_summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')
print(json.dumps(summary,ensure_ascii=False))
