# -*- coding: utf-8 -*-
"""
Master script to assemble, validate, and write src/locales/ml.json.
"""
import json
import re
import sys
from ml_locales_part1 import get_part1
from ml_locales_part2 import get_part2
from ml_locales_chat import get_chat

def flatten(d, prefix=''):
    items = []
    for k, v in d.items():
        new_key = f'{prefix}.{k}' if prefix else k
        if isinstance(v, dict):
            items.extend(flatten(v, new_key).items())
        else:
            items.append((new_key, v))
    return dict(items)

def main():
    part1 = get_part1()
    part2 = get_part2()
    chat = get_chat()

    # Assemble in exact order of en.json
    ml = {
        "distressIndicator": part1["distressIndicator"],
        "common": part1["common"],
        "crisisDialog": part1["crisisDialog"],
        "nav": part1["nav"],
        "landing": part1["landing"],
        "mood": part1["mood"],
        "chat": chat,
        "notFound": part1["notFound"],
        "privacy": part1["privacy"],
        "terms": part1["terms"],
        "auth": part1["auth"],
        "admin": part1["admin"],
        "meditation": part1["meditation"],
        "error": part1["error"],
        "onboarding": part1["onboarding"],
        "kg": part1["kg"],
        "layout": part1["layout"],
        "desktopSidebar": part1["desktopSidebar"],
        "notes": part2["notes"],
        "memory": part2["memory"],
        "practices": part2["practices"],
        "seo": part2["seo"],
        "cancelFlow": part2["cancelFlow"],
        "language": part2["language"],
        "brain": part2["brain"],
        "profileStatTiles": part2["profileStatTiles"],
        "profile": part2["profile"]
    }

    with open('src/locales/en.json', 'r', encoding='utf-8') as f:
        en = json.load(f)

    en_flat = flatten(en)
    ml_flat = flatten(ml)

    print(f"EN total flat keys: {len(en_flat)}")
    print(f"ML total flat keys: {len(ml_flat)}")

    missing_in_ml = set(en_flat.keys()) - set(ml_flat.keys())
    extra_in_ml = set(ml_flat.keys()) - set(en_flat.keys())

    if missing_in_ml:
        print(f"ERROR: {len(missing_in_ml)} keys missing in ML:")
        for k in sorted(missing_in_ml):
            print(f"  MISSING: {k} -> EN: {en_flat[k]}")
        sys.exit(1)

    if extra_in_ml:
        print(f"ERROR: {len(extra_in_ml)} extra keys in ML:")
        for k in sorted(extra_in_ml):
            print(f"  EXTRA: {k}")
        sys.exit(1)

    print("SUCCESS: Exact key parity (1,077 keys, 0 missing, 0 extra)!")

    # Check placeholder tags: {{...}}
    placeholder_re = re.compile(r'\{\{([^}]+)\}\}')
    mismatched_placeholders = []
    for k in en_flat:
        en_val = str(en_flat[k])
        ml_val = str(ml_flat[k])
        en_tags = sorted(placeholder_re.findall(en_val))
        ml_tags = sorted(placeholder_re.findall(ml_val))
        if en_tags != ml_tags:
            mismatched_placeholders.append((k, en_tags, ml_tags, en_val, ml_val))

    if mismatched_placeholders:
        print(f"ERROR: {len(mismatched_placeholders)} placeholder mismatches found:")
        for k, en_tags, ml_tags, en_val, ml_val in mismatched_placeholders:
            print(f"  KEY: {k}\n    EN ({en_tags}): {en_val}\n    ML ({ml_tags}): {ml_val}")
        sys.exit(1)
    else:
        print("SUCCESS: All interpolation placeholders match perfectly!")

    # Write output to src/locales/ml.json
    with open('src/locales/ml.json', 'w', encoding='utf-8') as f:
        json.dump(ml, f, indent=2, ensure_ascii=False)
        f.write('\n')

    print("Wrote src/locales/ml.json successfully!")

if __name__ == '__main__':
    main()
