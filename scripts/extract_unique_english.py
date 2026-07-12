import json
from pathlib import Path

def main():
    langs = ["hi", "te", "kn", "ta", "mr"]
    unique_en_strings = set()
    
    for lang in langs:
        p = Path(f"scripts/keys_to_translate_{lang}.json")
        if not p.exists():
            continue
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        for k, (reason, en_val) in data.items():
            unique_en_strings.add(en_val)
            
    print(f"Total unique English strings needing translation: {len(unique_en_strings)}")
    with open("scripts/unique_english_strings.json", "w", encoding="utf-8") as f:
        json.dump(sorted(list(unique_en_strings)), f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    main()
