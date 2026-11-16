"""Pure, side-effect-free routing predicates shared across pipeline stages.

Fable 5.2 Refactoring:
Replaced 4 overlapping regular expressions (GREETING_RE, GREETING_VOCATIVE_RE,
GREETING_SEQUENCE_RE, CONVERSATIONAL_OPENER_RE — flagged in CodeQL #1975 for
polynomial backtracking on repeated Unicode prayer emojis and tabs) with a
zero-regex, linear-time O(N) lexical token-stream state machine while preserving
the closed-vocabulary crisis-preemption invariant.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

_MAX_GREETING_CHARS = 80

_SINGLE_GREETING_WORDS = frozenset(
    {
        "hi",
        "hello",
        "hey",
        "namaste",
        "pranam",
        "namaskar",
        "namasthe",
        "greetings",
        "howdy",
        "yo",
        "hola",
        "\U0001f64f",
    }
)
_GOOD_TIME_WORDS = frozenset({"morning", "afternoon", "evening", "night"})
_VOCATIVE_WORDS = frozenset(
    {
        "guruji",
        "gurujee",
        "guru",
        "ji",
        "swami",
        "swamiji",
        "master",
        "acharya",
        "teacher",
        "teacherji",
        "seeker",
        "seekerji",
        "friend",
        "sadhak",
        "sadhaka",
        "devotee",
        "brother",
        "sister",
        "everyone",
        "all",
        "there",
        "folks",
        "sir",
        "madam",
        "ma'am",
    }
)
_CONVERSATIONAL_OPENERS = frozenset(
    {
        ("what's", "up"),
        ("whats", "up"),
        ("what's", "happening"),
        ("whats", "happening"),
        ("what's", "new"),
        ("whats", "new"),
        ("how", "are", "you"),
        ("how", "are", "you", "doing"),
        ("how", "is", "it", "going"),
        ("how", "are", "things"),
        ("how", "goes", "it"),
    }
)
_ALLOWED_GREETING_PUNCT = frozenset({" ", "\t", "\n", "\r", ".", ",", "!", "?"})


def _tokenize_greeting(value: str) -> list[str] | None:
    if not value or len(value) > _MAX_GREETING_CHARS:
        return None

    normalized_chars: list[str] = []
    for ch in value:
        if ch == "\U0001f64f":
            normalized_chars.append(" \U0001f64f ")
        elif ch in _ALLOWED_GREETING_PUNCT:
            normalized_chars.append(" ")
        elif ch.isalnum() or ch == "'":
            normalized_chars.append(ch.lower())
        else:
            return None

    tokens = "".join(normalized_chars).split()
    if not tokens or len(tokens) > 8:
        return None
    return tokens


def is_deterministic_greeting(text: str | None) -> bool:
    """Return true only for a pure or short vocative greeting in O(N) time."""
    tokens = _tokenize_greeting(str(text or ""))
    if tokens is None:
        return False

    if tuple(tokens) in _CONVERSATIONAL_OPENERS:
        return True

    units: list[str] = []
    i = 0
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        if tok == "good" and i + 1 < n and tokens[i + 1] in _GOOD_TIME_WORDS:
            units.append("GREETING")
            i += 2
        elif tok in _SINGLE_GREETING_WORDS:
            units.append("GREETING")
            i += 1
        elif tok in _VOCATIVE_WORDS:
            units.append("VOCATIVE")
            i += 1
        else:
            return False

    if not units or units[0] != "GREETING" or len(units) > 4:
        return False

    return True


class _MatchResult:
    def __init__(self, matched_text: str):
        self._text = matched_text

    def group(self, *args: Any) -> str:
        return self._text

    def __bool__(self) -> bool:
        return True


class _LinearGreetingMatcher:
    """Zero-regex linear matcher adapter preserving interface compatibility without ReDoS."""

    def __init__(self, predicate: Callable[[list[str]], bool]):
        self._predicate = predicate

    def match(self, text: str | None) -> _MatchResult | None:
        tokens = _tokenize_greeting(str(text or ""))
        if tokens is None:
            return None
        if self._predicate(tokens):
            return _MatchResult(str(text or ""))
        return None


def _is_single_greeting_tokens(tokens: list[str]) -> bool:
    if tokens[0] == "good" and len(tokens) == 2 and tokens[1] in _GOOD_TIME_WORDS:
        return True
    return len(tokens) == 1 and tokens[0] in _SINGLE_GREETING_WORDS


def _is_vocative_greeting_tokens(tokens: list[str]) -> bool:
    if tokens[0] == "good" and len(tokens) == 3 and tokens[1] in _GOOD_TIME_WORDS:
        return tokens[2] in _VOCATIVE_WORDS
    if len(tokens) == 2 and tokens[0] in _SINGLE_GREETING_WORDS:
        return tokens[1] in _VOCATIVE_WORDS
    return False


def _is_sequence_greeting_tokens(tokens: list[str]) -> bool:
    if len(tokens) < 2 or tuple(tokens) in _CONVERSATIONAL_OPENERS:
        return False
    units: list[str] = []
    i = 0
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        if tok == "good" and i + 1 < n and tokens[i + 1] in _GOOD_TIME_WORDS:
            units.append("GREETING")
            i += 2
        elif tok in _SINGLE_GREETING_WORDS:
            units.append("GREETING")
            i += 1
        elif tok in _VOCATIVE_WORDS:
            units.append("VOCATIVE")
            i += 1
        else:
            return False
    return bool(units and units[0] == "GREETING" and len(units) <= 4)


def _is_conversational_opener_tokens(tokens: list[str]) -> bool:
    return tuple(tokens) in _CONVERSATIONAL_OPENERS


GREETING_RE = _LinearGreetingMatcher(_is_single_greeting_tokens)
GREETING_VOCATIVE_RE = _LinearGreetingMatcher(_is_vocative_greeting_tokens)
GREETING_SEQUENCE_RE = _LinearGreetingMatcher(_is_sequence_greeting_tokens)
CONVERSATIONAL_OPENER_RE = _LinearGreetingMatcher(_is_conversational_opener_tokens)
