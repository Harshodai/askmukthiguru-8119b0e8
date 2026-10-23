"""Pure, side-effect-free routing predicates shared across pipeline stages."""

from __future__ import annotations

import re

GREETING_RE = re.compile(
    r"^\s*(hi|hello|hey|namaste|pranam|namaskar|namasthe|greetings|"
    r"good\s*(morning|afternoon|evening|night)|howdy|yo|hola|\U0001f64f)[\s!.?]*$",
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
    rf"\s+(?:{_GREETING_VOCATIVES})[\s.!]*$",
    re.IGNORECASE,
)

# Two or three greeting tokens in a row ("Namaste! Good morning.") are still a pure greeting.
# Live run 2026-10-23: that message missed both patterns above, went to the LLM casual handler
# and took 3.5 s. Every part is a token from the same closed vocabularies, so nothing outside
# them (a crisis phrase, a question) can ride along.
_GREETING_TOKENS = (
    r"(?:hi|hello|hey|namaste|pranam|namaskar|namasthe|greetings|"
    r"good\s*(?:morning|afternoon|evening|night)|howdy|yo|hola|\U0001f64f)"
)
# One separator class and one trailing class only: adjacent overlapping whitespace quantifiers
# made CodeQL flag the first draft as polynomial (py/polynomial-redos).
GREETING_SEQUENCE_RE = re.compile(
    rf"^\s*{_GREETING_TOKENS}(?:[\s,.!]+(?:{_GREETING_TOKENS}|{_GREETING_VOCATIVES})){{1,3}}[\s.!?]*$",
    re.IGNORECASE,
)
# Real greetings are a few words; refuse to run any greeting regex on a long message.
_MAX_GREETING_CHARS = 80


def is_deterministic_greeting(text: str | None) -> bool:
    """Return true only for a pure or short vocative greeting."""
    value = str(text or "")
    if len(value) > _MAX_GREETING_CHARS:
        return False
    return bool(
        GREETING_RE.match(value)
        or GREETING_VOCATIVE_RE.match(value)
        or GREETING_SEQUENCE_RE.match(value)
    )
