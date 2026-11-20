"""Eval set v2 = frozen v1 (unchanged, hash-checked) + multilingual items forced into the holdout split.

Usage: build_eval_set_v2.py V1.json OUT.json. Added 2026-11-20 on coordinator request, before any v2 run.
"""
import hashlib
import json
import sys

V1_SHA = "b7ee2c38dd2fded503769bba1704844703a600b22e4acdf5d807f4ce03a2eb1b"
ML = [
    ("telugu", "answer", "నా మనసు ప్రశాంతంగా ఉండాలంటే ఏమి చేయాలి?"),
    ("telugu", "answer", "బాధ ఎందుకు కలుగుతుంది?"),
    ("telugu", "answer", "నన్ను బాధపెట్టిన వ్యక్తిని ఎలా క్షమించాలి?"),
    ("hindi", "answer", "मुझे भविष्य की चिंता सताती है, क्या करूँ?"),
    ("hindi", "answer", "दुख का कारण क्या है?"),
    ("hindi", "answer", "किसी को माफ़ कैसे करें जिसने मुझे चोट पहुँचाई?"),
    ("kannada", "answer", "ಕೋಪವನ್ನು ಹೇಗೆ ನಿಯಂತ್ರಿಸುವುದು?"),
    ("kannada", "answer", "ಮನಸ್ಸಿನ ಶಾಂತಿ ಹೇಗೆ ಪಡೆಯುವುದು?"),
    ("kannada", "answer", "ಸುಂದರ ಸ್ಥಿತಿ ಎಂದರೇನು?"),
    ("tamil", "answer", "கோபத்தை எப்படி கட்டுப்படுத்துவது?"),
    ("tamil", "answer", "தனிமையாக உணர்கிறேன், என்ன செய்வது?"),
    ("tamil", "answer", "தியானத்தின் நோக்கம் என்ன?"),
]

if __name__ == "__main__":
    raw = open(sys.argv[1]).read()
    assert hashlib.sha256(raw.encode()).hexdigest() == V1_SHA, "v1 changed"
    items = json.loads(raw)
    for i, (cat, exp, q) in enumerate(ML):
        items.append({"id": f"ml_{i:02d}", "src": "new_v2", "cat": cat, "turns": [q], "expect": [exp],
                      "split": "holdout"})
    blob = json.dumps(items, ensure_ascii=False, indent=1, sort_keys=True)
    open(sys.argv[2], "w").write(blob)
    print(f"items={len(items)} sha256={hashlib.sha256(blob.encode()).hexdigest()}")
