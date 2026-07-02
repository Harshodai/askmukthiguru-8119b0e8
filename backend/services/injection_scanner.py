import re
import logging

logger = logging.getLogger(__name__)


class InjectionScanner:
    INJECTION_PATTERNS = [
        # — adversarial injection (user-submitted attacks) —
        (r"\bignore\s+(all\s+)?(previous|above|prior)\s+(instructions|commands|directions|prompts)\b", "instruction_override"),
        (r"\b(feign|pretend|act\s+as|you\s+are\s+now)\s+", "role_play"),
        (r"\bSYSTEM\s*:", "system_override"),
        (r"\b<\|im_start\|>", "token_injection"),
        (r"\boverride\s+(mode|system|safety|guardrails)\b", "override_attempt"),
        (r"\\u200b|\\u200c|\\u200d|\\ufeff|\\u00a0", "unicode_hidden"),
        (r"\[REDACTED_", "pii_redacted"),
        # — LLM prompt self-leakage (LLM echoes its own system prompt on empty input) —
        (r"You are a Text Correction Expert", "prompt_leak_corrector"),
        (r"Your task is to fix transcription errors", "prompt_leak_corrector"),
        (r"DO NOT retain the original meaning", "prompt_leak_corrector"),
        (r"Important Terms to Correct", "prompt_leak_corrector"),
        (r"You are a Data Quality Auditor", "prompt_leak_auditor"),
        (r"The instruction is to not retain", "prompt_leak_raptor"),
        (r"I need to summarize the given text passages", "prompt_leak_raptor"),
        (r"However, I notice that the text passages", "prompt_leak_raptor"),
    ]

    @classmethod
    def scan_chunk(cls, text: str) -> dict:
        if not text:
            return {"injection_detected": False, "patterns": [], "severity": "none"}
        matches = []
        for pattern, name in cls.INJECTION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                matches.append(name)
        severity = "none"
        if matches:
            severity = "high" if any(m in matches for m in ["instruction_override", "system_override", "token_injection"]) else "low"
        return {
            "injection_detected": len(matches) > 0,
            "patterns": matches,
            "severity": severity,
        }


def scan_chunks_for_injection(chunks: list[str]) -> tuple[list[str], list[tuple[int, str, str]]]:
    if not chunks:
        return [], []
    clean = []
    risky = []
    for i, chunk in enumerate(chunks):
        result = InjectionScanner.scan_chunk(chunk)
        if not result["injection_detected"]:
            clean.append(chunk)
        else:
            risky.append((i, chunk[:80], result["severity"]))
    return clean, risky
