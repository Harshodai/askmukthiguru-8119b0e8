import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

CORPUS = Path('scripts/ingestion/corpus')
OUT = Path('scripts/ingestion/reviews/sanskrit_terms_audit')
OUT.mkdir(parents=True, exist_ok=True)

# Curated project glossary plus Sanskrit-derived terms observed in the corpus.
TERMS = {
    'Ekam': ['Acam','Akam','Akham','Ecom','Ecoms','Acom','Acoms','ECAM','Eikam','acome'],
    'Sri Preethaji': ['Sri Pretty Ji','Sri Preeti Ji','Pretaji','Pritaji','Preetha ji','Pretty Ji','Preeti Ji'],
    'Sri Krishnaji': ['Sri Krishna Ji','Krishna Ji','Krishna G'],
    'Deeksha': ['Diksha','diksha','dikshaa'],
    'Soul Sync': ['Soulsync','SoulSync','soul sink'],
    'Mukthi': ['Mukti','mukti'],
    'I-Consciousness': ['Eye Consciousness','I Consciousness','I consciousness'],
    'Dhyana': ['Dhyan','Dhyanam','dhyana','dhyāna'],
    'Pranayama': ['Pranayam','Prana Yama','pranayama'],
    'Kundalini': ['Cunda Lini','kundalini'],
    'Samskara': ['Samskaras','Samscara','samskara','samskaras'],
    'Sadhana': ['Saadhana','sadhana'],
    'Samadhi': ['Soma thee','samadhi'],
    'Moksha': ['Mokesha','moksha'],
    'Ahamkara': ['Ahamkar','ahamkara'],
    'Dheera': ['Dhira','dhira','Adira','Deerah'],
    'Sanyasi': ['Samyasi','Sanyassee','sanyasi'],
    'Darshan': ['Darshana','darshan'],
    'Namaste': ['No must stay','namaste'],
    'Bhakti': ['Bacti','bhakti'],
    'Chakra': ['Chakras','chakras','chakra'],
    'Mantra': ['mantra','mantram'],
    'Shanti': ['shanti','śānti','shantih','shantihi','shantir','shantar'],
    'Soham': ['soham','sohum','sohameekam','soha mikam','suhami kham'],
    'Hamsa/Humsah': ['hamsa','humsah','ham se'],
    'Namah': ['namah','namaha'],
    'Gayatri': ['gayatri','gāyatr'],
    'Pashupataye': ['pashupataye'],
    'Om/Aum': ['aum','om'],
    'Adi Daivika': ['Adi Dhaivata','Adi Daivika','Aadhi Daivika','adi dhaivata'],
    'Adi Bhautika': ['Adi Bhautika','Aadhi Bhauthika','adi bhautika'],
    'Adhyatmika': ['Adhyatmika','Aadhyaatmika','adhyatmika'],
    'Mudra': ['mudra','mudrā'],
    'Pranam': ['prana mudra','pranam mudra','prena mudra'],
    'Maha': ['maha','mahā'],
    'Saraswati': ['Saraswati','Saraswathi'],
    'Lakshmi': ['Lakshmi','Lakshmis','Lakṣmī'],
    'Vishwamitra': ['Vishwamitra','Viśvāmitra'],
    'Sanskrit': ['Sanskrit'],
    'Rishi': ['Rishi','ṛṣi'],
    'Guru': ['guru','Gurus'],
    'Dharma': ['Dharma','dharma'],
    'Karma': ['Karma','karma'],
    'Maya': ['Maya','māyā'],
    'Veda': ['Veda','Vedas','Vedic'],
    'Upanishad': ['Upanishad','Upanishads'],
    'Yoga': ['Yoga','yoga'],
    'Kapal(a)': ['Kapola','Kapal'],
    'Anahata': ['Anahata'],
    'Sthita Prajna': ['sthita pradhna','sthita prajna','sthita pradhna'],
    'Hiranyagarbha': ['Hiranyagarbha'],
    'Smarana': ['Smaranadikisha','Smaranadiksha'],
}

compiled = []
for canonical, variants in TERMS.items():
    seen = set()
    for variant in variants:
        key = variant.lower()
        if key in seen:
            continue
        seen.add(key)
        compiled.append((canonical, variant, re.compile(r'(?<!\w)' + re.escape(variant) + r'(?!\w)', re.I)))

rows = []
for package in sorted(p for p in CORPUS.iterdir() if p.is_dir()):
    segfile = package / 'canonical_segments.json'
    if segfile.is_file():
        try:
            segments = json.loads(segfile.read_text(encoding='utf-8')).get('segments', [])
        except Exception:
            segments = []
        for seg in segments:
            text = str(seg.get('text',''))
            for canonical, variant, rx in compiled:
                for match in rx.finditer(text):
                    rows.append({'video_id': package.name, 'artifact': 'canonical_segments.json', 'segment_id': seg.get('segment_id',''), 'start': seg.get('start',''), 'end': seg.get('end',''), 'canonical_family': canonical, 'matched_form': match.group(0), 'char_start': match.start(), 'char_end': match.end(), 'context': text[max(0,match.start()-100):min(len(text),match.end()+140)]})
    transcript = package / 'transcript.md'
    if transcript.is_file():
        text = transcript.read_text(encoding='utf-8', errors='replace').split('## Transcript', 1)[-1]
        for canonical, variant, rx in compiled:
            for match in rx.finditer(text):
                rows.append({'video_id': package.name, 'artifact': 'transcript.md', 'segment_id': 'transcript', 'start': '', 'end': '', 'canonical_family': canonical, 'matched_form': match.group(0), 'char_start': match.start(), 'char_end': match.end(), 'context': text[max(0,match.start()-100):min(len(text),match.end()+140)].replace('\n',' ')})

fields = ['video_id','artifact','segment_id','start','end','canonical_family','matched_form','char_start','char_end','context']
with (OUT/'all_sanskrit_term_locations.csv').open('w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
counts = Counter((r['canonical_family'], r['matched_form']) for r in rows)
video_counts = Counter(r['video_id'] for r in rows)
summary = {'rows': len(rows), 'videos': len(video_counts), 'families': len(set(r['canonical_family'] for r in rows)), 'family_counts': dict(Counter(r['canonical_family'] for r in rows)), 'matched_form_counts': {f'{k[0]} :: {k[1]}': v for k,v in counts.items()}, 'video_counts_top': dict(video_counts.most_common(30))}
(OUT/'sanskrit_term_inventory_summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False)+'\n')
print(json.dumps({'rows':len(rows),'videos':len(video_counts),'families':len(set(r['canonical_family'] for r in rows))}, ensure_ascii=False))
