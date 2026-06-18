import re
import logging

logger = logging.getLogger(__name__)


class PIIScanner:
    EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
    PHONE_REGEX = re.compile(r"(\+\d{1,3}[\s-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")
    AADHAAR_REGEX = re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b")
    SSN_REGEX = re.compile(r"\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b")
    IP_REGEX = re.compile(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b")

    @classmethod
    def scan(cls, text: str) -> dict:
        if not text:
            return {"has_pii": False, "types": [], "locations": []}
        findings = []
        for name, pattern in [
            ("email", cls.EMAIL_REGEX),
            ("phone", cls.PHONE_REGEX),
            ("aadhaar", cls.AADHAAR_REGEX),
            ("ssn", cls.SSN_REGEX),
            ("ip_address", cls.IP_REGEX),
        ]:
            for match in pattern.finditer(text):
                findings.append({
                    "type": name,
                    "start": match.start(),
                    "end": match.end(),
                    "value": match.group(),
                })
        return {
            "has_pii": len(findings) > 0,
            "types": list({f["type"] for f in findings}),
            "details": findings,
        }

    @classmethod
    def redact(cls, text: str) -> str:
        text = cls.EMAIL_REGEX.sub("[REDACTED_EMAIL]", text)
        text = cls.PHONE_REGEX.sub("[REDACTED_PHONE]", text)
        text = cls.AADHAAR_REGEX.sub("[REDACTED_ID]", text)
        text = cls.SSN_REGEX.sub("[REDACTED_SSN]", text)
        text = cls.IP_REGEX.sub("[REDACTED_IP]", text)
        return text
