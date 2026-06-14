import re
import sys

_SARVAM_REASONING_MARKERS = [
    "now, count words:",
    "we must check:",
    "we must ensure",
    "we must not",
    "we can write:",
    "let's draft:",
    "we have cited",
    "we have used",
    "we have not repeated",
    "that's within",
    "that's acceptable",
    "we must output",
    "now, we must",
    "we must keep it within",
    "count words:",
    "we are consistent",
    "we must check the token count",
    "initial scan of the context",
    "i'll quickly read through",
    "quickly read through the provided",
    "scan of the context",
    "let me quickly scan",
]

_COT_PATTERNS = [
    r"<think>.*?</think>",
    r"(?is)^\s*(we are given|we need to|we must|let me analyze|i need to analyze|analysis:|let's draft|now,?\s*count|we have used|we can write|we have cited|we must check|we must ensure|we must not|we must output).*?(?=\n\n|beloved|dear one|seeker|friend|the teaching|according to|$)",
    r"(?im)^\s*(step\s*\d+|reasoning|chain of thought|scratchpad)\s*[:.-].*$",
    r"(?im)^\s*(first,?\s*)?i(?:'| a)?ll analyze.*$",
    r"(?im)^\s*(?:Note|Checklist|Verification|Important):.*$",
    r"(?im)^\s*\d+[\s.)]+(?:\*\*)?(?:Analyze|Scan|Initial Scan|Formulate|Draft|Evaluate|Check|Verify|Review|Identify|Translate|Filter|Retrieve|Select|Generate|Output|Synthesize|Compare|Determine|Process|Resolve|Find|Cite|Locate|Deconstruct|Read|Parse|Extract|Consider|Assess)\b.*?(?=\n\s*\d+|\n\n(?![*\s])|\Z)",
]

def strip_cot(text: str) -> str:
    if not text:
        return text

    cleaned = text
    # 1. Apply regex pattern replacements
    for _ in range(4):
        prev = cleaned
        for pattern in _COT_PATTERNS:
            cleaned = re.sub(pattern, "", cleaned, flags=re.DOTALL).strip()
        if cleaned == prev:
            break

    # 2. Split into paragraphs and filter out any paragraph that starts with a reasoning marker
    paragraphs = cleaned.split("\n\n")
    filtered_paragraphs = []
    for para in paragraphs:
        para_strip = para.strip()
        if not para_strip:
            continue
        para_lower = para_strip.lower()
        normalized_para = re.sub(r"^[\s\d.*#_()\[\]-]+", "", para_lower)
        
        is_reasoning = False
        for marker in _SARVAM_REASONING_MARKERS:
            if normalized_para.startswith(marker):
                is_reasoning = True
                break
        
        if not is_reasoning:
            filtered_paragraphs.append(para_strip)
            
    cleaned = "\n\n".join(filtered_paragraphs)

    # 3. Handle markers appearing in the middle/end of text
    cleaned_lower = cleaned.lower()
    for marker in _SARVAM_REASONING_MARKERS:
        idx = cleaned_lower.find(marker)
        if idx != -1 and idx > 100:
            cleaned = cleaned[:idx].strip()
            cleaned_lower = cleaned.lower()

    for marker in ["Final answer:", "Answer:", "Mukthi Guru:"]:
        idx = cleaned.lower().find(marker.lower())
        if idx != -1:
            cleaned = cleaned[idx + len(marker) :].strip()

    if not cleaned:
        return "I apologize, but I am unable to formulate a complete response right now. Please allow me to share some relevant teachings from the sacred knowledge base instead."
    return cleaned

test_cases = [
    # Case 1: Standard leak from Q12
    "**Initial Scan of the Context:** We find Soul Sync meditation.\n\nSoul Sync meditation is a practice...",
    # Case 2: Numbered initial scan
    "1. **Initial Scan of the Context:** Scanning.\n2. **Draft Response:** Drafting.\n\nHere is the answer:\nSoul Sync is...",
    # Case 3: think tags
    "<think>Thinking...</think>Soul Sync is...",
    # Case 4: No leak
    "Soul Sync is a meditation practice designed to bring peace."
]

for i, tc in enumerate(test_cases, 1):
    print(f"\n--- Test Case {i} ---")
    print("Input:")
    print(repr(tc))
    out = strip_cot(tc)
    print("Output:")
    print(repr(out))
