#!/usr/bin/env python3
import argparse, csv, json, statistics
from collections import Counter
from pathlib import Path

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('audit_json', type=Path); ap.add_argument('--out', type=Path, required=True); args=ap.parse_args()
    data=json.loads(args.audit_json.read_text()); rows=data['packages']; summary=data['summary']
    scores=[r['quality_score'] for r in rows if isinstance(r.get('quality_score'),(int,float))]
    cov=[r['coverage_ratio'] for r in rows if isinstance(r.get('coverage_ratio'),(int,float))]
    paras=[r['paragraph_median_chars'] for r in rows if isinstance(r.get('paragraph_median_chars'),(int,float))]
    def pct(n,d): return round(100*n/d,2) if d else 0
    issue_rows=[r for r in rows if r.get('issues')]
    warning_rows=[r for r in rows if r.get('warnings')]
    out={
      'package_count':len(rows),
      'nonempty_package_count':sum('transcript_chars' in r for r in rows),
      'empty_or_incomplete_count':sum('transcript_chars' not in r for r in rows),
      'package_ok_count':sum(r.get('package_ok') for r in rows),
      'issue_package_count':len(issue_rows), 'warning_package_count':len(warning_rows),
      'quality_state_counts':dict(Counter(r.get('quality_state') for r in rows if r.get('quality_state'))),
      'quality_score':{'min':min(scores),'median':statistics.median(scores),'mean':round(statistics.mean(scores),4),'max':max(scores),'counts':dict(Counter(scores))} if scores else {},
      'coverage_ratio':{'min':min(cov),'median':statistics.median(cov),'mean':round(statistics.mean(cov),4),'max':max(cov)} if cov else {},
      'paragraph_median_chars':{'min':min(paras),'median':statistics.median(paras),'mean':round(statistics.mean(paras),2),'max':max(paras)} if paras else {},
      'manifest_artifact_hash_mismatch_packages':sum((r.get('manifest_hash_mismatches') or 0)>0 for r in rows),
      'manifest_raw_hash_mismatch_packages':sum((r.get('manifest_raw_hash_mismatches') or 0)>0 for r in rows),
      'low_token_overlap_packages':sum('transcript_segment_low_token_overlap' in r.get('warnings',[]) for r in rows),
      'timestamp_like_transcript_packages':sum('timestamp_like_text_in_transcript_body' in r.get('warnings',[]) for r in rows),
      'paragraph_target_warning_packages':sum('most_paragraphs_outside_300_500_chars' in r.get('warnings',[]) for r in rows),
      'correction_count_total':sum(r.get('correction_count',0) or 0 for r in rows),
      'correction_warning_packages':sum(any(w.startswith('correction_') for w in r.get('warnings',[])) for r in rows),
      'top_issue_counts':summary.get('issue_counts',{}), 'top_warning_counts':summary.get('warning_counts',{}),
      'highest_risk_packages':sorted([{'video_id':r['video_id'],'quality_score':r.get('quality_score'),'quality_state':r.get('quality_state'),'issues':r.get('issues',[]),'warnings':r.get('warnings',[]),'coverage_ratio':r.get('coverage_ratio'),'segment_count':r.get('segment_count')} for r in rows if r.get('issues') or r.get('warnings')], key=lambda x:(len(x['issues'])>0, -len(x['issues']), x['quality_score'] if isinstance(x['quality_score'],(int,float)) else 99))[:50]
    }
    args.out.write_text(json.dumps(out, indent=2, ensure_ascii=False)); print(json.dumps(out, indent=2))
if __name__=='__main__': main()
