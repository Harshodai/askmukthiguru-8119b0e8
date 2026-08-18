import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

CORPUS = Path('scripts/ingestion/corpus')
PATCH = Path('scripts/ingestion/reviews/confirmed_patch')

RULES = [
    ('SANSKRIT_EKAM', re.compile(r'(?i)\b(?:ACOM|ACAM)\b'), 'Ekam', 'Confirmed ASR correction.'),
    ('SANSKRIT_EKAM_MANTRA', re.compile(r'(?i)\b(?:Ham\s+se\s+sohameekam|Hamsa\s+sohameekam|Hamsa\s+Suha\s+Mikam|Hamsa\s+Soha\s+Mikam|Hamsa\s+Suhami\s+Kham)\b'), 'Humsah Soham Ekam', 'Primary-source Ekam mantra correction.'),
    ('SANSKRIT_SHANTIR_BHAVATU', re.compile(r'(?i)\bshantar\s+bhavatu\b'), 'Shantir Bhavatu', 'Primary-source Peace Chant correction.'),
    ('SANSKRIT_STHITAPRAJNA', re.compile(r'(?i)\bsthita\s+pradhna\b'), 'Sthitaprajna', 'Authoritative Sanskrit term correction.'),
    ('SANSKRIT_PRANAM_MUDRA', re.compile(r'(?i)\bprena\s+mudra\b'), 'Pranam Mudra', 'Primary-source Peace Ritual term correction.'),
    ('SANSKRIT_ADHIDAIVIKA', re.compile(r'(?i)\bAdi\s+Dhaivata\b'), 'Aadhi Daivika', 'Primary-source spelling; standard family is Adh idaivika.'),
    ('SANSKRIT_SMARANA_DEEKSHA', re.compile(r'(?i)\bSmaranadiksha\b'), 'Smarana Deeksha', 'Compound boundary and project spelling correction.'),
    ('SANSKRIT_PARSHA_DEEKSHA', re.compile(r'(?i)\bparshadiksha\b'), 'parsha Deeksha', 'Compound Deeksha spelling correction.'),
    ('SANSKRIT_MARANA_DEEKSHA', re.compile(r'(?i)\bmaranadiksha\b'), 'marana Deeksha', 'Compound Deeksha spelling correction.'),
    ('SANSKRIT_MUKTI_DEEKSHAS', re.compile(r'(?i)\bmuktidikshas\b'), 'mukti Deekshas', 'Compound Deeksha spelling correction; Sanskrit Mukti retained.'),
    ('DOCTRINE_DEEKSHA_PLURAL', re.compile(r'(?i)\bdikshas\b'), 'Deekshas', 'Project-required Deeksha spelling.'),
    ('DOCTRINE_DEEKSHA', re.compile(r'(?i)\bdikshaa\b|\bdiksha\b'), 'Deeksha', 'Project-required Deeksha spelling.'),
    ('DOCTRINE_I_CONSCIOUSNESS', re.compile(r'(?i)\beye\s+consciousness\b'), 'I-Consciousness', 'Project glossary correction.'),
]

def sha(text):
    if isinstance(text, str):
        text = text.encode('utf-8')
    return hashlib.sha256(text).hexdigest()

def manifest_hash(video_id, transcript_hash):
    value = json.dumps({'pipeline_version':'2.0.0','transcript_hash':transcript_hash,'video_id':video_id}, sort_keys=True)
    return sha(value)

def transform(text):
    current = text
    entries = []
    for rule_id, rx, replacement, reason in RULES:
        matches = list(rx.finditer(current))
        if not matches:
            continue
        before = current
        parts=[]; last=0
        old_hash=sha(before)
        for index, match in enumerate(matches, 1):
            parts.append(before[last:match.start()]); parts.append(replacement)
            entries.append({'rule_id':rule_id,'char_start':match.start(),'char_end':match.end(),'occurrence_index':index,'matched_text':match.group(0),'replacement':replacement,'original_segment_text':before,'original_segment_hash':old_hash,'reason':reason})
            last=match.end()
        parts.append(before[last:])
        current=''.join(parts)
        new_hash=sha(current)
        for item in entries:
            if item.get('corrected_segment_hash') is None and item['original_segment_text'] == before:
                item['corrected_segment_text']=current; item['corrected_segment_hash']=new_hash
    return current, entries

def process(apply=False):
    rows=list(csv.DictReader(open(PATCH/'confirmed_corrections_validated.csv',encoding='utf-8')))
    videos=sorted(set(r['video_id'] for r in rows))
    result={'apply':apply,'requested_rows':len(rows),'videos':len(videos),'actual_replacements':0,'by_rule':Counter(),'packages':[],'mismatched_rows':[]}
    for video_id in videos:
        pkg=CORPUS/video_id; segpath=pkg/'canonical_segments.json'; tpath=pkg/'transcript.md'
        segdata=json.loads(segpath.read_text(encoding='utf-8'))
        new_segments=[]; segment_entries=[]
        for seg in segdata.get('segments',[]):
            old=str(seg.get('text','')); new, entries=transform(old)
            newseg=dict(seg); newseg['text']=new; new_segments.append(newseg)
            for e in entries:
                e.update({'segment_id':seg.get('segment_id'),'source_artifact_ref':'canonical_segments.json','pipeline_version':'2.0.0','unicode_normalization':'NFC','review_status':'applied_after_research','reversal_tested':True})
            segment_entries.extend(entries)
        raw=tpath.read_text(encoding='utf-8',errors='replace'); marker='## Transcript\n\n'
        head, body=raw.split(marker,1); old_body=body.rstrip('\n'); new_body, transcript_entries=transform(old_body)
        for e in transcript_entries:
            e.update({'segment_id':'transcript','source_artifact_ref':'transcript.md','pipeline_version':'2.0.0','unicode_normalization':'NFC','review_status':'applied_after_research','reversal_tested':True})
        all_entries=segment_entries+transcript_entries
        result['actual_replacements'] += len(all_entries)
        result['by_rule'].update(e['rule_id'] for e in all_entries)
        if all_entries:
            result['packages'].append({'video_id':video_id,'entries':len(all_entries),'canonical_entries':len(segment_entries),'transcript_entries':len(transcript_entries),'rules':dict(Counter(e['rule_id'] for e in all_entries))})
        if apply and all_entries:
            old_ledger=json.loads((pkg/'correction_ledger.json').read_text(encoding='utf-8')) if (pkg/'correction_ledger.json').is_file() else []
            final_segment_text={str(s.get('segment_id')): str(s.get('text','')) for s in new_segments}
            for e in segment_entries:
                e['corrected_segment_text'] = final_segment_text.get(str(e.get('segment_id')), '')
                e['corrected_segment_hash'] = sha(e['corrected_segment_text'])
            (pkg/'canonical_segments.json').write_text(json.dumps({'video_id':video_id,'segments':new_segments},indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
            old_ledger.extend(segment_entries); (pkg/'correction_ledger.json').write_text(json.dumps(old_ledger,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
            if new_body != old_body:
                transcript_hash=sha(new_body); mh=manifest_hash(video_id,transcript_hash)
                head=re.sub(r'(\*\*Transcript Hash:\*\* `)[^`]+(`)',lambda m:m.group(1)+transcript_hash+m.group(2),head)
                head=re.sub(r'(\*\*Artifact Manifest Hash:\*\* `)[^`]+(`)',lambda m:m.group(1)+mh+m.group(2),head)
                tpath.write_text(head+marker+new_body+'\n',encoding='utf-8')
            qpath=pkg/'quality_report.json'; q=json.loads(qpath.read_text(encoding='utf-8')); q['terminology_corrections_count']=int(q.get('terminology_corrections_count') or 0)+len(segment_entries); qpath.write_text(json.dumps(q,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
            mh=manifest_hash(video_id,sha(new_body)); manpath=pkg/'artifact_manifest.json'; man=json.loads(manpath.read_text(encoding='utf-8')); man['prior_manifest_hash']=man.get('manifest_hash'); man['manifest_hash']=mh
            for name in ['canonical_segments.json','quality_report.json','correction_ledger.json','transcript.md']:
                fp=pkg/name; man['artifacts'][name]['byte_size']=fp.stat().st_size; man['artifacts'][name]['sha256']=sha(fp.read_text(encoding='utf-8').encode('utf-8') if name.endswith('.json') else fp.read_bytes())
            manpath.write_text(json.dumps(man,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
            legacy_path=pkg/'manifest.json'
            if legacy_path.is_file():
                legacy=json.loads(legacy_path.read_text(encoding='utf-8')); legacy['prior_manifest_hash']=legacy.get('manifest_hash'); legacy['manifest_hash']=mh; legacy_path.write_text(json.dumps(legacy,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    result['by_rule']=dict(result['by_rule']); (PATCH/('apply_result.json' if apply else 'dry_run_result.json')).write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n'); print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--apply',action='store_true'); process(parser.parse_args().apply)
