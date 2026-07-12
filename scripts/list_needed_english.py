import json
import re
from pathlib import Path

def flatten_json(data, parent_key="", sep="."):
    items = {}
    for k, v in data.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.update(flatten_json(v, new_key, sep=sep))
        else:
            items[new_key] = v
    return items

def is_english_fallback(en_val: str, tgt_val: str) -> bool:
    if en_val != tgt_val:
        return False
    cleaned = re.sub(r'\{\{[^}]+\}\}', '', en_val)
    cleaned = re.sub(r'\[[^\]]+\]', '', cleaned)
    cleaned = re.sub(r'\d+', '', cleaned)
    cleaned = re.sub(r'[^\w\s]', '', cleaned).strip()
    return len(cleaned) > 0

def is_corrupted_kn(val: str) -> bool:
    return any('\u0900' <= char <= '\u097F' for char in val)

def validate_placeholders_and_citations(en_val: str, tgt_val: str) -> bool:
    en_placeholders = set(re.findall(r'\{\{[^}]+\}\}', en_val))
    tgt_placeholders = set(re.findall(r'\{\{[^}]+\}\}', tgt_val))
    if en_placeholders - tgt_placeholders:
        return False
    en_citations = set(re.findall(r'\[[a-zA-Z0-9]+\]', en_val))
    tgt_citations = set(re.findall(r'\[[a-zA-Z0-9]+\]', tgt_val))
    if en_citations - tgt_citations:
        return False
    return True

def main():
    locales_dir = Path("src/locales")
    en_data = json.load(open(locales_dir / "en.json", "r", encoding="utf-8"))
    en_flat = flatten_json(en_data)
    
    needed = {"kn": {}, "ta": {}, "mr": {}}
    
    for lang in ["kn", "ta", "mr"]:
        lang_file = locales_dir / f"{lang}.json"
        if not lang_file.exists():
            continue
        tgt_data = json.load(open(lang_file, "r", encoding="utf-8"))
        tgt_flat = flatten_json(tgt_data)
        
        # Superfluous
        superfluous = set(tgt_flat.keys()) - set(en_flat.keys())
        
        # Missing or fallback
        for k, en_val in en_flat.items():
            if k not in tgt_flat:
                needed[lang][k] = en_val
            else:
                tgt_val = tgt_flat[k]
                if is_english_fallback(str(en_val), str(tgt_val)) or (lang == "kn" and is_corrupted_kn(str(tgt_val))) or not validate_placeholders_and_citations(str(en_val), str(tgt_val)):
                    needed[lang][k] = en_val
                    
    with open("scripts/needed_translations.json", "w", encoding="utf-8") as f:
        json.dump(needed, f, indent=2, ensure_ascii=False)
        
    print(f"Kannada: {len(needed['kn'])} needed")
    print(f"Tamil: {len(needed['ta'])} needed")
    print(f"Marathi: {len(needed['mr'])} needed")

if __name__ == "__main__":
    main()
