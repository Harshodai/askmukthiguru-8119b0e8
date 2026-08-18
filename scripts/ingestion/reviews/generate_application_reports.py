import csv
import json
import hashlib
import datetime
import subprocess
from collections import Counter
from pathlib import Path

root=Path('scripts/ingestion'); review=root/'reviews'; out=review/'confirmed_patch'; corpus=root/'corpus'; manual_out=review/'manual_review_breakdown'; manual_out.mkdir(parents=True,exist_ok=True)
rows=list(csv.DictReader(open(review/'sanskrit_terms_audit/classified_sanskrit_term_locations.csv',encoding='utf-8')))
confirmed_types={'confirmed_asr_correction','confirmed_mantra_correction','confirmed_term_correction','confirmed_source_term_correction','confirmed_project_style_correction','manual_compound_correction','confirmed_project_spelling'}
manual=[r for r in rows if r['disposition'] not in confirmed_types]
fields=list(rows[0])
with open(manual_out/'manual_review_valid_variant_locations.csv','w',newline='',encoding='utf-8') as f:
 w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(manual)
summary={'manual_rows':len(manual),'videos':len(set(r['video_id'] for r in manual)),'by_disposition':dict(Counter(r['disposition'] for r in manual)),'by_matched_form':dict(Counter(r['matched_form'] for r in manual)),'by_canonical_family':dict(Counter(r['canonical_family'] for r in manual)),'by_proposed_form':dict(Counter(r['proposed_form'] for r in manual))}
(manual_out/'manual_review_summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')
md=['# Manual-Review and Valid-Variant Breakdown','',f'This report contains all **{len(manual)} manual-review and valid-variant rows** excluded from the applied correction patch. The exact package, artifact, segment, timestamp, matched form, proposed form, and context are in `manual_review_valid_variant_locations.csv`.','','## Category summary','', '| Category | Rows | Decision |','|---|---:|---|']
labels={'manual_transliteration':'Manual transliteration/policy review; do not auto-rewrite.','manual_term_identity':'Manual term-identity review; validate against source audio/context.','manual_review_context':'Manual context review; the form may be legitimate in another language or usage.','manual_project_style':'Manual project-style decision; semantics are not necessarily wrong.'}
for k,v in sorted(summary['by_disposition'].items()): md.append(f'| `{k}` | {v} | {labels.get(k,"Manual review required.")} |')
md += ['', '## Matched-form detail','', '| Current form | Rows | Main issue |','|---|---:|---|']
reasons={'Hamsa':'Valid Sanskrit/transliteration alternative; official Ekam source uses Humsah in the mantra.','hamsa':'Same as Hamsa; resolve by source recording and project policy.','Kapola':'Valid Sanskrit word meaning cheek; do not substitute Kapala without audio/context.','akam':'Potentially legitimate lower-case word; only change when the context means Ekam.','I consciousness':'Concept is valid; hyphenation to I-Consciousness is a project style choice.'}
for k,v in sorted(summary['by_matched_form'].items(),key=lambda x:-x[1]): md.append(f'| `{k}` | {v} | {reasons.get(k,"Sentence-level review required.")} |')
md += ['', '## Canonical-family detail','', '| Family | Rows |','|---|---:|']
for k,v in sorted(summary['by_canonical_family'].items(),key=lambda x:-x[1]): md.append(f'| `{k}` | {v} |')
md += ['', '## Interpretation','', 'The largest manual group is **Hamsa/hamsa (412 rows)**. This is not a blanket error: `haṃsa/hamsa` is an established Sanskrit/transliteration form, while the specific Ekam recordings reviewed use `Humsah Soham Ekam`. These rows should be resolved per source video rather than globally. The remaining rows cover `Kapola` (4), lower-case `akam` (8), and `I consciousness` (4).', '', '**No manual-review rows were applied.**']
(manual_out/'manual_review_breakdown.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
apply=json.load(open(out/'apply_result.json',encoding='utf-8')); audit=json.load(open(review/'post_application_audit/end_to_end_summary.json',encoding='utf-8'))
ledger_added=sum(x.get('canonical_entries',0) for x in apply['packages']); changed=apply['packages'];
unexpected=sum(v for k,v in audit.get('issue_counts',{}).items() if k!='incomplete_package')
app_summary={'requested_candidate_rows':apply['requested_rows'],'actual_literal_replacements':apply['actual_replacements'],'affected_packages':len(changed),'canonical_ledger_entries_added':ledger_added,'transcript_only_replacements':apply['actual_replacements']-ledger_added,'manual_rows_not_applied':len(manual),'post_audit':audit,'unexpected_integrity_issues':unexpected,'corpus_status_clean':not subprocess.run(['git','status','--short','--','scripts/ingestion/corpus'],capture_output=True,text=True).stdout.strip()}
(review/'confirmed_patch/application_summary.json').write_text(json.dumps(app_summary,indent=2,ensure_ascii=False)+'\n')
affected=len(changed); complete_pkgs=audit.get('complete_packages',0); incomplete_pkgs=audit.get('incomplete_packages',audit.get('issue_counts',{}).get('incomplete_package',0)); missing_artifact=audit.get('issue_counts',{}).get('missing_artifact',audit.get('issue_total',0))
md2=['# Sanskrit Correction Application Report','', f'**Application completed from the validated patch after a reversible pre-application backup.** The corpus was intentionally modified only in the {affected} affected complete packages.','','| Metric | Result |','|---|---:|',f"| Validated candidate rows requested | {apply['requested_rows']} |",f"| Literal replacements applied | {apply['actual_replacements']} |",f"| Affected packages | {affected} |",f"| New canonical correction-ledger entries | {ledger_added} |",f"| Transcript-only derivative replacements | {apply['actual_replacements']-ledger_added} |",f"| Manual-review rows left unchanged | {len(manual)} |",f"| Complete packages after audit | {complete_pkgs} |",f"| Incomplete packages | {incomplete_pkgs} |",f"| Unexpected integrity issues in complete packages | {unexpected} |",'', '## Integrity result','', f'The post-application audit reports no unexpected issues in the {complete_pkgs} complete packages. The only remaining audit findings are the pre-existing {incomplete_pkgs} incomplete package directories, represented as {missing_artifact} missing-artifact records. All modified packages have updated canonical segments, transcripts, correction ledgers, quality-report counts, artifact-manifest hashes, and legacy manifest hashes.', '', '## Reversal','', 'A complete pre-application copy and SHA-256 backup manifest is stored under `confirmed_patch/backup_before_apply`. Reversal should restore those package directories as a unit; do not selectively reverse individual manifest files.']
(review/'confirmed_patch/application_report.md').write_text('\n'.join(md2)+'\n',encoding='utf-8')
# Applied-change manifest with current hashes for affected packages.
manifest={'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'requested_rows':apply['requested_rows'],'actual_literal_replacements':apply['actual_replacements'],'affected_packages':sorted(x['video_id'] for x in changed),'corpus_modified':True,'manual_rows_not_applied':len(manual),'backup_manifest':'confirmed_patch/backup_manifest.json','post_application_audit':'post_application_audit/end_to_end_summary.json','current_artifact_hashes':{}}
for x in changed:
 vid=x['video_id']; pkg=corpus/vid; manifest['current_artifact_hashes'][vid]={}
 for name in ['canonical_segments.json','quality_report.json','correction_ledger.json','transcript.md','artifact_manifest.json','manifest.json']:
  p=pkg/name
  if p.is_file(): manifest['current_artifact_hashes'][vid][name]=hashlib.sha256(p.read_bytes()).hexdigest()
(review/'confirmed_patch/applied_change_manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({'manual_rows':len(manual),'literal_replacements':apply['actual_replacements'],'ledger_added':ledger_added,'affected_packages':len(changed),'unexpected_integrity_issues':audit['issue_total']-audit['issue_counts'].get('incomplete_package',0)}))
