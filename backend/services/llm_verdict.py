"""Typed parsing of LLM verdicts.

Every provider used to parse its own verdicts with substring tests:

- ``"yes" in content.lower().split("-")[0]`` (ollama) treats *yesterday* as yes,
- ``"faithful" in result.lower()`` accepts "not faithful",
- three separate copies of the CRAG ``"1: yes - reason"`` line parser drifted,
- the answerability gate compared an exact token but logged nothing usable.

Substring matching on free-form model output is not a contract. This module
defines one: model noise (CoT blocks, Markdown fences, prose) is stripped, then
a verdict must be an explicit token or a JSON field. Anything else is
``indeterminate`` — never a guess, never an implicit yes.

The functions are pure and synchronous; they never call a provider.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

_VERDICT_VERSION = "llm_verdict_v1"

_THINK_RE = re.compile(r"<think(?:ing)?>.*?</think(?:ing)?>", re.IGNORECASE | re.DOTALL)
_FENCE_RE = re.compile(r"```[a-zA-Z0-9_-]*\s*\n?(.*?)```", re.DOTALL)

_YES = frozenset({"yes", "true", "y", "1", "relevant", "answerable", "supported"})
_NO = frozenset({"no", "false", "n", "0", "irrelevant", "not_relevant", "unanswerable"})

# Keys a provider may use for a boolean verdict.
_VERDICT_KEYS = ("verdict", "answer", "answerable", "relevant", "result", "is_relevant")

# Provider graceful-degradation / refusal strings are not verdicts.
_DEGRADATION_MARKERS = (
    "temporary connection issue",
    "experiencing a temporary",
    "unable to grade",
    "i cannot grade",
    "cannot evaluate",
)

# CRAG line formats seen in the wild: ``1: yes - reason``, ``1. no``,
# ``1 - yes (reason)``, ``**1:** yes``. Index is captured, verdict is strict.
_NUMBERED_RE = re.compile(
    r"^\s*\**\s*(?P<idx>\d{1,3})\s*\**\s*[:.)\-]\s*\**\s*"
    r"(?P<verdict>yes|no|true|false|relevant|irrelevant)\b"
    r"(?P<rest>.*)$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class Verdict:
    """Parsed verdict: ``value`` is None when the output was not a verdict."""

    value: bool | None
    source: str  # "json" | "token" | "unparseable" | "degraded" | "empty"
    raw_length: int = 0
    version: str = _VERDICT_VERSION

    @property
    def indeterminate(self) -> bool:
        return self.value is None

    def reason(self) -> str:
        if self.value is True:
            return "verdict_yes"
        if self.value is False:
            return "verdict_no"
        return f"verdict_{self.source}"


def strip_model_noise(raw: Any) -> str:
    """Remove CoT blocks and Markdown fences; keep prose for token matching."""
    text = "" if raw is None else str(raw)
    text = _THINK_RE.sub(" ", text)
    text = _FENCE_RE.sub(lambda m: m.group(1), text)
    return text.strip()


def is_degradation(text: str) -> bool:
    lowered = text.casefold()
    return any(marker in lowered for marker in _DEGRADATION_MARKERS)


def parse_verdict(raw: Any) -> Verdict:
    """Parse a single yes/no verdict from model output.

    Order: JSON object/array field → exact leading token → unparseable.
    """
    text = strip_model_noise(raw)
    length = len(text)
    if not text:
        return Verdict(value=None, source="empty", raw_length=0)
    if is_degradation(text):
        return Verdict(value=None, source="degraded", raw_length=length)

    from_json = _verdict_from_json(text)
    if from_json is not None:
        return Verdict(value=from_json, source="json", raw_length=length)

    token = _verdict_from_token(text)
    if token is not None:
        return Verdict(value=token, source="token", raw_length=length)
    return Verdict(value=None, source="unparseable", raw_length=length)


def _verdict_from_json(text: str) -> bool | None:
    start = text.find("{")
    end = text.rfind("}")
    candidate = text[start : end + 1] if start != -1 and end > start else text
    try:
        payload = json.loads(candidate)
    except (ValueError, TypeError):
        return None
    if isinstance(payload, list):
        payload = payload[0] if payload else None
    if not isinstance(payload, dict):
        return None
    for key in _VERDICT_KEYS:
        if key not in payload:
            continue
        value = payload[key]
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().casefold()
            if normalized in _YES:
                return True
            if normalized in _NO:
                return False
    return None


def _verdict_from_token(text: str) -> bool | None:
    # Only the first token counts: "yes, because..." is yes; "not sure, yes"
    # is not a verdict and must stay indeterminate.
    first = re.split(r"[\s,.;:!?]+", text.strip(), maxsplit=1)[0].strip().casefold()
    if first in _YES:
        return True
    if first in _NO:
        return False
    return None


def parse_numbered_verdicts(raw: Any) -> dict[int, tuple[bool, str]]:
    """Parse CRAG-style numbered verdicts: ``{index0: (relevant, reason)}``.

    Returns only the lines that carried a real verdict; callers decide what an
    empty result means (the existing contract keeps the top document and says
    the grader output was unparseable).
    """
    text = strip_model_noise(raw)
    parsed: dict[int, tuple[bool, str]] = {}
    if not text:
        return parsed

    json_verdicts = _numbered_from_json(text)
    if json_verdicts:
        return json_verdicts

    for line in text.splitlines():
        match = _NUMBERED_RE.match(line)
        if not match:
            continue
        try:
            index = int(match.group("idx")) - 1
        except (TypeError, ValueError):
            continue
        if index < 0:
            continue
        verdict = match.group("verdict").casefold() in _YES
        reason = _reason_from_rest(match.group("rest"), verdict)
        parsed[index] = (verdict, reason)
    return parsed


def _reason_from_rest(rest: str, verdict: bool) -> str:
    cleaned = rest.strip().lstrip("-–—:(),").strip()
    if cleaned:
        return cleaned[:500]
    return "Relevant teaching" if verdict else "Irrelevant content"


def _numbered_from_json(text: str) -> dict[int, tuple[bool, str]]:
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end <= start:
        return {}
    try:
        payload = json.loads(text[start : end + 1])
    except (ValueError, TypeError):
        return {}
    if not isinstance(payload, list):
        return {}
    parsed: dict[int, tuple[bool, str]] = {}
    for position, item in enumerate(payload):
        if not isinstance(item, dict):
            continue
        index = item.get("index", item.get("document", position + 1))
        value = item.get("relevant", item.get("verdict"))
        if isinstance(value, bool):
            verdict = value
        elif isinstance(value, str):
            normalized = value.strip().casefold()
            if normalized in _YES:
                verdict = True
            elif normalized in _NO:
                verdict = False
            else:
                continue
        else:
            continue
        try:
            index0 = int(index) - 1
        except (TypeError, ValueError):
            index0 = position
        if index0 < 0:
            continue
        reason = str(item.get("reason") or "").strip() or _reason_from_rest("", verdict)
        parsed[index0] = (verdict, reason[:500])
    return parsed


def grade_documents(raw: Any, n_documents: int) -> list[dict]:
    """CRAG grading result for ``n_documents`` from one grader reply.

    Shared by every provider so the three copies cannot drift. The
    unparseable-reply contract is unchanged (keep the top document) but now
    carries ``indeterminate: True`` so a real "yes" is distinguishable from a
    grader failure.
    """
    results: list[dict] = [
        {"relevant": False, "reason": "No response from LLM"} for _ in range(max(0, n_documents))
    ]
    parsed = parse_numbered_verdicts(raw)
    for index, (verdict, reason) in parsed.items():
        if 0 <= index < len(results):
            results[index] = {"relevant": verdict, "reason": reason}
    if not parsed and results:
        results[0] = {
            "relevant": True,
            "indeterminate": True,
            "reason": "Grader output unparseable: kept top retrieval result.",
        }
    return results


def parse_faithfulness(raw: Any) -> bool | None:
    """True = faithful, False = not faithful, None = not a verdict.

    Negation is checked before affirmation: "not faithful" and "unfaithful"
    both contain "faithful" as a substring, which is exactly the bug that made
    the old ``"faithful" in result.lower()`` check always true.
    """
    text = strip_model_noise(raw)
    if not text:
        return None
    if is_degradation(text):
        return None
    json_verdict = _verdict_from_json(text)
    if json_verdict is not None:
        return json_verdict
    token = _verdict_from_token(text)
    if token is not None and len(text.split()) == 1:
        return token
    lowered = text.casefold()
    if re.search(r"\b(?:not|un)\s*faithful\b|\bunfaithful\b|\bnot\s+supported\b", lowered):
        return False
    if re.search(r"\bfaithful\b|\bfully\s+supported\b", lowered):
        return True
    return None


if __name__ == "__main__":
    assert parse_verdict("yes").value is True
    assert parse_verdict("Yes.").value is True
    assert parse_verdict("no").value is False
    assert parse_verdict("yes, because the clip names it").value is True
    # Not a verdict: a substring is not an answer.
    assert parse_verdict("yesterday it rained").value is None
    assert parse_verdict("not sure, yes maybe").value is None
    assert parse_verdict("").value is None
    assert parse_verdict(None).value is None
    assert parse_verdict("I'm currently experiencing a temporary connection issue").value is None
    assert parse_verdict("```json\n{\"verdict\": \"no\"}\n```").value is False
    assert parse_verdict("<think>maybe</think>yes").value is True

    _v = parse_numbered_verdicts("1: yes - on topic\n2: no - off topic")
    assert _v == {0: (True, "on topic"), 1: (False, "off topic")}
    assert parse_numbered_verdicts("1. no") == {0: (False, "Irrelevant content")}
    assert parse_numbered_verdicts("I cannot grade these documents.") == {}

    assert parse_faithfulness("Faithful") is True
    assert parse_faithfulness("Not faithful: the second claim is unsupported") is False
    assert parse_faithfulness("unfaithful") is False
    assert parse_faithfulness("no idea") is None
    print("llm_verdict self-check passed")
