import csv,json
from pathlib import Path
root=Path('scripts/ingestion/reviews/correction_research_run')
rows=list(csv.DictReader(open(root/'correction_locations.csv',encoding='utf-8')))
manual=[r for r in rows if r['disposition'].startswith('manual_review')]
style=[r for r in rows if ('style_normalization' in r['disposition'] or 'spacing_normalization' in r['disposition'])]
fields=list(rows[0])
for name,data in [('manual_review_details.csv',manual),('style_normalization_details.csv',style)]:
 with open(root/name,'w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(data)
def counts(data):
 from collections import Counter
 return {'total':len(data),'by_disposition':dict(Counter(r['disposition'] for r in data)),'by_rule':dict(Counter(r['rule_id'] for r in data)),'by_pair':dict(Counter(r['matched_text']+' -> '+r['replacement'] for r in data))}
(root/'manual_style_views_summary.json').write_text(json.dumps({'manual_review':counts(manual),'style_normalization':counts(style)},indent=2,ensure_ascii=False)+'\n')
print(json.dumps({'manual_review':counts(manual),'style_normalization':counts(style)},ensure_ascii=False))
