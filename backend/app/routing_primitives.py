"""Pure, side-effect-free routing predicates shared across pipeline stages."""
from __future__ import annotations

import re


GREETING_RE = re.compile(
    r"^\s*(hi|hello|hey|namaste|pranam|namaskar|namasthe|greetings|"
    r"good\s*(morning|afternoon|evening|night)|howdy|yo|hola|\U0001f64f)\s*[!.?]*\s*$",
    re.IGNORECASE,
)

# A short vocative greeting is deterministic when it starts with a known
# greeting token, contains exactly one additional word-like token, and has no question
# punctuation. It is deliberately structural, not query-specific.
GREETING_VOCATIVE_RE = re.compile(
    r"^\s*(hi|hello|hey|namaste|pranam|namaskar|namasthe|greetings|"
    r"good\s*(morning|afternoon|evening|night)|howdy|yo|hola|\U0001f64f)"
    r"(?:\s+[\w'-]+){1,1}\s*[.!]*\s*$",
    re.IGNORECASE,
)


def is_deterministic_greeting(text: str | None) -> bool:
    """Return true only for a pure or short vocative greeting."""
    value = str(text or "")
    return bool(GREETING_RE.match(value) or GREETING_VOCATIVE_RE.match(value))
