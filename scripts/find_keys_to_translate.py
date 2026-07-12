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
            items[new_key] = str(v) if v is not None else ""
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

def is_corrupted_hi(val: str) -> bool:
    return "स्रा" in val

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
    en_path = locales_dir / "en.json"
    
    with open(en_path, "r", encoding="utf-8") as f:
        en_data = json.load(f)
    en_flat = flatten_json(en_data)
    
    langs = ["hi", "te", "kn", "ta", "mr"]
    
    for lang in langs:
        lang_file = locales_dir / f"{lang}.json"
        if not lang_file.exists():
            print(f"{lang}.json does not exist")
            continue
            
        with open(lang_file, "r", encoding="utf-8") as f:
            tgt_data = json.load(f)
        tgt_flat = flatten_json(tgt_data)
        
        # Keys to translate
        to_translate = {}
        
        # 1. Missing keys
        missing = set(en_flat.keys()) - set(tgt_flat.keys())
        for k in missing:
            to_translate[k] = ("missing", en_flat[k])
            
        # 2. English fallback, corrupted, or validation failed
        for k, tgt_val in tgt_flat.items():
            if k not in en_flat:
                continue
            en_val = en_flat[k]
            
            # Check validation
            valid = validate_placeholders_and_citations(en_val, tgt_val)
            
            if not valid:
                to_translate[k] = ("validation_failed", en_val)
            elif is_english_fallback(en_val, tgt_val):
                to_translate[k] = ("fallback", en_val)
            elif lang == "kn" and is_corrupted_kn(tgt_val):
                to_translate[k] = ("corrupted_kn", en_val)
            elif lang == "hi" and is_corrupted_hi(tgt_val):
                to_translate[k] = ("corrupted_hi", en_val)
                
        print(f"Language: {lang} - Needs {len(to_translate)} translations")
        # Save to temporary file
        out_path = Path(f"scripts/keys_to_translate_{lang}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(to_translate, f, indent=2, ensure_ascii=False)
        print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
