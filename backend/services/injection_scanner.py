import re
import logging

logger = logging.getLogger(__name__)


class InjectionScanner:
    INJECTION_PATTERNS = [
        (r"\bignore\s+(all\s+)?(previous|above|prior)\s+(instructions|commands|directions|prompts)\b", "instruction_override"),
        (r"\b(feign|pretend|act\s+as|you\s+are\s+now)\s+", "role_play"),
        (r"\bSYSTEM\s*:", "system_override"),
        (r"\b<\|im_start\|>", "token_injection"),
        (r"\boverride\s+(mode|system|safety|guardrails)\b", "override_attempt"),
        (r"\\u200b|\\u200c|\\u200d|\\ufeff|\\u00a0", "unicode_hidden"),
        (r"\[REDACTED_", "pii_redacted"),
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
