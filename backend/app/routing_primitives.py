"""Pure, side-effect-free routing predicates shared across pipeline stages."""

from __future__ import annotations

import re

GREETING_RE = re.compile(
    r"^\s*(hi|hello|hey|namaste|pranam|namaskar|namasthe|greetings|"
    r"good\s*(morning|afternoon|evening|night)|howdy|yo|hola|\U0001f64f)\s*[!.?]*\s*$",
    re.IGNORECASE,
)

# A short vocative greeting is deterministic when it starts with a known
# greeting token and is followed by exactly one KNOWN vocative. The tail has to
# be a closed vocabulary: "greeting token + any one word" also matched
# "hello kms" / "namaste suicide", which the pipeline answers from the canned
# greeting before the input guardrail and distress stages ever run.
_GREETING_VOCATIVES = (
    r"guruji|gurujee|guru|ji|swami|swamiji|master|acharya|teacher|teacherji|"
    r"seeker|seekerji|friend|sadhak|sadhaka|devotee|brother|sister|"
    r"everyone|all|there|folks|sir|madam|ma'am"
)
GREETING_VOCATIVE_RE = re.compile(
    r"^\s*(hi|hello|hey|namaste|pranam|namaskar|namasthe|greetings|"
    r"good\s*(morning|afternoon|evening|night)|howdy|yo|hola|\U0001f64f)"
    rf"\s+(?:{_GREETING_VOCATIVES})\s*[.!]*\s*$",
    re.IGNORECASE,
)


def is_deterministic_greeting(text: str | None) -> bool:
    """Return true only for a pure or short vocative greeting."""
    value = str(text or "")
    return bool(GREETING_RE.match(value) or GREETING_VOCATIVE_RE.match(value))
