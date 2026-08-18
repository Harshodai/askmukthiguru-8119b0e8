import csv,json,statistics,collections,subprocess,hashlib,datetime
from pathlib import Path
base=Path('scripts/ingestion/reviews'); out=base/'status_and_corrections'; out.mkdir(parents=True,exist_ok=True)
rows=list(csv.DictReader(open(base/'sanskrit_mantra_audit/mantra_correction_locations.csv',encoding='utf-8')))
packs=json.load(open(base/'end_to_end_audit/package_audit.json',encoding='utf-8')); complete=[p for p in packs if p.get('package_complete')]
scores=[float(p['quality_score']) for p in complete]; states=collections.Counter(p.get('quality_state') for p in complete); dist=collections.Counter(f'{x:.2f}' for x in scores)
# exact row-level CSV copy with a stable report name
fields=list(rows[0])
with open(out/'sanskrit_mantra_corrections_all_locations.csv','w',newline='',encoding='utf-8') as f:
 w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
summary={'audited_complete_packages':len(complete),'quality_score_count':len(scores),'quality_score_min':min(scores),'quality_score_max':max(scores),'quality_score_mean':round(statistics.mean(scores),6),'quality_score_median':statistics.median(scores),'quality_score_distribution':dict(dist),'trust_states':dict(states),'correction_rows':len(rows),'correction_videos':len(set(r['video_id'] for r in rows)),'correction_application_status':'proposals_only_corpus_unchanged'}
(out/'quality_score_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
md=['# Sanskrit Corrections and 657-Package Quality Summary','','## Correction application status','','**The corrections have not been applied.** The 47 rows below are evidence-backed proposals only. The immutable transcript, canonical-segment, ledger, and manifest files remain unchanged.','','## Sanskrit correction locations','',f"The review identified **{len(rows)} rows across {len(set(r['video_id'] for r in rows))} videos**. The attached CSV contains the complete exact row-level data.",'']
for vid in sorted(set(r['video_id'] for r in rows)):
 md += [f'### `{vid}`','', '| Artifact | Segment | Timestamp (s) | Detected form | Proposed form | Type |','|---|---|---:|---|---|---|']
 for r in [x for x in rows if x['video_id']==vid]:
  loc=f"{r['start']}–{r['end']}" if r['start'] else 'transcript body'
  md.append(f"| `{r['artifact']}` | `{r['segment_id']}` | {loc} | `{r['matched_variants']}` | **{r['proposed_form']}** | {r['correction_type']} |")
 md.append('')
md += ['## Quality scores and trust states for all 657 audited packages','','| Metric | Result |','|---|---:|',f'| Complete audited packages | {len(complete)} |',f'| Minimum quality score | {min(scores):.2f} |',f'| Maximum quality score | {max(scores):.2f} |',f'| Mean quality score | {statistics.mean(scores):.4f} |',f'| Median quality score | {statistics.median(scores):.2f} |','', '| Quality score | Packages |','|---:|---:|']
for k in sorted(dist,key=float): md.append(f'| {k} | {dist[k]} |')
md += ['','| Trust/quality state | Packages | Interpretation |','|---|---:|---|',f"| `needs_review` | {states.get('needs_review',0)} | Requires human/audio review before trusted promotion. |",f"| `sound_only` | {states.get('sound_only',0)} | Sound-only source; do not treat as trusted transcript text. |",'| `trusted` | 0 | No audited package is currently marked trusted. |','','## Conclusion','','The deterministic correction discovery and evidence review are complete for the identified Sanskrit-mantra and Deeksha candidates, but the corrections themselves are **not done/applied**. They remain reversible proposals. Applying them requires a separate write operation with updated transcript/canonical-segment files, correction ledgers, and cryptographic manifests, followed by a new integrity audit.']
(out/'status_and_corrections_report.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
names=['status_and_corrections_report.md','sanskrit_mantra_corrections_all_locations.csv','quality_score_summary.json']
manifest={'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'corpus_modified':False,'correction_application_status':'not_applied','output_hashes':{n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in names}}
(out/'status_report_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(summary,ensure_ascii=False))
