import csv
import json
from collections import Counter
from pathlib import Path

base = Path('scripts/ingestion/reviews')
out = base / 'sanskrit_terms_audit'
rows = list(csv.DictReader(open(out / 'all_sanskrit_term_locations.csv', encoding='utf-8')))
prior = list(csv.DictReader(open(out.parent / 'sanskrit_mantra_audit/mantra_variant_locations.csv', encoding='utf-8')))
found = []

confirmed = {
    'ACOM': ('Ekam', 'confirmed_asr_correction', 'ACOM/ACAM are recurrent phonetic variants of the project term Ekam.'),
    'ACAM': ('Ekam', 'confirmed_asr_correction', 'ACOM/ACAM are recurrent phonetic variants of the project term Ekam.'),
    'Ham se': ('Humsah Soham Ekam', 'confirmed_mantra_correction', 'Primary-source Ekam recordings establish Humsah Soham Ekam.'),
    'sohameekam': ('Humsah Soham Ekam', 'confirmed_mantra_correction', 'Primary-source Ekam recordings establish Humsah Soham Ekam.'),
    'Soha Mikam': ('Humsah Soham Ekam', 'confirmed_mantra_correction', 'Primary-source Ekam recordings reject Soha Mikam as phonetic noise.'),
    'Suhami Kham': ('Humsah Soham Ekam', 'confirmed_mantra_correction', 'Primary-source Ekam recordings reject Suhami Kham as phonetic noise.'),
    'shantar': ('Shantir Bhavatu', 'confirmed_mantra_correction', 'Primary Peace Chant source uses Shantir Bhavatu.'),
    'sthita pradhna': ('Sthitaprajna / Sthita Prajna', 'confirmed_term_correction', 'Authoritative Sanskrit references use Sthitaprajña/Sthitaprajna.'),
    'prena mudra': ('Pranam Mudra', 'confirmed_source_term_correction', 'Primary Peace Ritual analysis identifies Pranam Mudra.'),
    'Adi Dhaivata': ('Aadhi Daivika', 'confirmed_source_term_correction', 'Primary Peace Ritual analysis uses Aadhi Daivika; standard form is Ādhidaivika.'),
    'eye consciousness': ('I-Consciousness', 'confirmed_project_style_correction', 'Project glossary maps Eye Consciousness to I-Consciousness.'),
    'Smaranadiksha': ('Smarana Deeksha', 'review', 'Compound boundary and project spelling require review; Deeksha is fixed.'),
}
manual = {
    'akam': ('Ekam', 'manual_review_context', 'Lowercase akam can be a legitimate Tamil/Sanskrit-derived word; do not auto-rewrite without context.'),
    'Hamsa': ('Humsah Soham Ekam', 'manual_transliteration', 'Hamsa is a valid alternative transliteration; official Ekam source recordings use Humsah.'),
    'hamsa': ('Humsah Soham Ekam', 'manual_transliteration', 'Hamsa is a valid alternative transliteration; official Ekam source recordings use Humsah.'),
    'Mukti': ('Mukthi', 'manual_transliteration', 'Mukti is supported by Sanskrit references; Mukthi is the project preference.'),
    'mukti': ('Mukthi', 'manual_transliteration', 'Mukti is supported by Sanskrit references; Mukthi is the project preference.'),
    'Kapola': ('Kapola / Kapala', 'manual_term_identity', 'Kapola is a valid Sanskrit word, but the intended chakra term is not uniquely established.'),
    'I consciousness': ('I-Consciousness', 'manual_project_style', 'Source usage supports I consciousness; hyphenation is a project style decision.'),
}
for r in rows:
    variant = r['matched_form']
    item = confirmed.get(variant) or manual.get(variant)
    if not item:
        continue
    proposed, disposition, reason = item
    found.append({
        'video_id': r['video_id'], 'artifact': r['artifact'], 'segment_id': r['segment_id'],
        'start': r['start'], 'end': r['end'], 'canonical_family': r['canonical_family'],
        'matched_form': variant, 'char_start': r['char_start'], 'char_end': r['char_end'],
        'proposed_form': proposed, 'disposition': disposition, 'reason': reason, 'context': r['context']
    })
# Add the exact Diksha locations from the previous all-variant scan.
for r in prior:
    if 'diksha' not in (r.get('matches') or '').lower():
        continue
    found.append({
        'video_id': r['video_id'], 'artifact': r['file'], 'segment_id': r['segment_id'],
        'start': r['start'], 'end': r['end'], 'canonical_family': 'Deeksha',
        'matched_form': r['matches'], 'char_start': '', 'char_end': '', 'proposed_form': 'Deeksha',
        'disposition': 'confirmed_project_spelling', 'reason': 'User-required project spelling, supported by official Oneness usage.', 'context': r['text'][:500]
    })
fields = ['video_id','artifact','segment_id','start','end','canonical_family','matched_form','char_start','char_end','proposed_form','disposition','reason','context']
with (out / 'classified_sanskrit_term_locations.csv').open('w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(found)
summary = {
    'candidate_rows': len(found),
    'videos': len(set(r['video_id'] for r in found)),
    'by_disposition': dict(Counter(r['disposition'] for r in found)),
    'by_matched_form': dict(Counter(r['matched_form'] for r in found)),
    'by_proposed_form': dict(Counter(r['proposed_form'] for r in found)),
}
(out / 'classified_sanskrit_term_summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n')
print(json.dumps(summary, ensure_ascii=False))
