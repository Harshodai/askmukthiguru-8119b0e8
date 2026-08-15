# scripts/assemble_as_locale.py
# -*- coding: utf-8 -*-
"""
Master Assamese (অসমীয়া) Locale Assembler.
Combines translations from Part 1, Part 2, and Part 3 to build src/locales/as.json.
Guarantees 100% key parity with src/locales/en.json (1,077 keys, 0 missing).
Validates placeholder variable matching and valid JSON syntax.
"""

import json
import re
import sys
from scripts.as_translations_part1 import get_part1_translations
from scripts.as_translations_part2 import get_part2_translations
from scripts.as_translations_part3 import get_part3_translations

def flatten(d, prefix=''):
    res = {}
    for k, v in d.items():
        curr = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            res.update(flatten(v, curr))
        else:
            res[curr] = v
    return res

def unflatten(flat_dict, schema_ref):
    """
    Reconstruct nested dictionary matching the exact schema structure of schema_ref.
    """
    res = {}
    for k, v in schema_ref.items():
        if isinstance(v, dict):
            sub_flat = {}
            prefix = k + "."
            for fk, fv in flat_dict.items():
                if fk.startswith(prefix):
                    sub_flat[fk[len(prefix):]] = fv
            res[k] = unflatten(sub_flat, v)
        else:
            if k in flat_dict:
                res[k] = flat_dict[k]
            else:
                raise KeyError(f"Key {k} missing from flat dictionary")
    return res

def main():
    with open('src/locales/en.json', 'r', encoding='utf-8') as f:
        en = json.load(f)

    en_flat = flatten(en)
    total_en_keys = len(en_flat)
    print(f"Total keys in en.json: {total_en_keys}")

    p1 = get_part1_translations()
    p2 = get_part2_translations()
    p3 = get_part3_translations()

    print(f"Part 1 keys: {len(p1)}")
    print(f"Part 2 keys: {len(p2)}")
    print(f"Part 3 keys: {len(p3)}")

    all_translations = {}
    all_translations.update(p1)
    all_translations.update(p2)
    all_translations.update(p3)

    print(f"Total translations assembled: {len(all_translations)}")

    missing = set(en_flat.keys()) - set(all_translations.keys())
    extra = set(all_translations.keys()) - set(en_flat.keys())

    print(f"Missing keys ({len(missing)}):")
    for k in sorted(missing):
        print(f"  MISSING: {k} (EN: {en_flat[k]})")

    print(f"Extra keys ({len(extra)}):")
    for k in sorted(extra):
        print(f"  EXTRA: {k}")

    if missing or extra:
        print("ERROR: Parity mismatch! Halting.")
        sys.exit(1)

    # Validate placeholder variables
    placeholder_mismatches = []
    for k in en_flat:
        en_val = en_flat[k]
        as_val = all_translations[k]
        if isinstance(en_val, str) and isinstance(as_val, str):
            en_vars = set(re.findall(r'\{\{[^}]+\}\}', en_val))
            as_vars = set(re.findall(r'\{\{[^}]+\}\}', as_val))
            if en_vars != as_vars:
                placeholder_mismatches.append((k, en_vars, as_vars, en_val, as_val))
        elif isinstance(en_val, list) and isinstance(as_val, list):
            if len(en_val) != len(as_val):
                placeholder_mismatches.append((k, f"len {len(en_val)}", f"len {len(as_val)}", en_val, as_val))

    print(f"Placeholder variable / array length mismatches: {len(placeholder_mismatches)}")
    for k, ev, av, en_v, as_v in placeholder_mismatches:
        print(f"  MISMATCH in {k}:")
        print(f"    EN ({ev}): {en_v}")
        print(f"    AS ({av}): {as_v}")

    if placeholder_mismatches:
        print("ERROR: Placeholder mismatches found! Halting.")
        sys.exit(1)

    print("\nAll checks passed with 100% accuracy!")
    print("Unflattening to nested JSON schema matching en.json...")

    as_nested = unflatten(all_translations, en)

    with open('src/locales/as.json', 'w', encoding='utf-8') as f:
        json.dump(as_nested, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("Successfully wrote src/locales/as.json!")

    # Verify written file
    with open('src/locales/as.json', 'r', encoding='utf-8') as f:
        as_loaded = json.load(f)

    as_loaded_flat = flatten(as_loaded)
    print(f"Verified loaded as.json: {len(as_loaded_flat)} keys.")
    assert len(as_loaded_flat) == total_en_keys == 1077
    print("Verification complete: 1,077 keys, 0 missing, 100% key parity!")

if __name__ == '__main__':
    main()
