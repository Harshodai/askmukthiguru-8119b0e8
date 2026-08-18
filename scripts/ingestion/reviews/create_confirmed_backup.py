import csv
import json
import hashlib
import shutil
from pathlib import Path

root = Path('scripts/ingestion')
corpus = root / 'corpus'
review = root / 'reviews'
out = review / 'confirmed_patch'
backup = out / 'backup_before_apply'
backup.mkdir(parents=True, exist_ok=True)
rows = list(csv.DictReader(open(out / 'confirmed_corrections_validated.csv', encoding='utf-8')))
packages = sorted(set(r['video_id'] for r in rows))
manifest = {'packages': {}, 'rows': len(rows), 'package_count': len(packages), 'backup_path': str(backup)}
for vid in packages:
    src = corpus / vid
    dst = backup / vid
    if dst.exists():
        raise SystemExit(f'backup already exists: {dst}')
    shutil.copytree(src, dst)
    files = {}
    for p in sorted(dst.rglob('*')):
        if p.is_file():
            files[str(p.relative_to(dst))] = hashlib.sha256(p.read_bytes()).hexdigest()
    manifest['packages'][vid] = files
(out / 'backup_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({'rows': len(rows), 'packages': len(packages), 'backup': str(backup)}))
