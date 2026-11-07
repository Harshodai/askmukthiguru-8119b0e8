"""Pure logic for the staging load test (NEW-LOAD-1). No locust import, no network.

Plan: audits/audit-output-2026-11-04/specifications/LOAD_AND_COST_MODEL.md section 6.
The Locust file (locustfile_fp_staging.py) is a thin wrapper over this module so the
mix, the response classes and the abort rules can be tested without Locust.

Everything here describes the PROPOSED plan. The S5 mix and the think times are
inferences, not measured traffic.
"""

from __future__ import annotations

import json
from collections import deque
from collections.abc import Mapping
from pathlib import Path
from typing import Any

#: Stage tags for `locust --tags`.
STAGE_TAGS = {
    "s0": "smoke: one of each type",
    "s1": "cache-hit",
    "s2": "served, uncached (capacity curve)",
    "s3": "abstain: out-of-corpus and adversarial",
    "s4": "crisis, low volume, mixed into S2",
    "s5": "mixed target (the B8 run)",
    "s6": "burst: admission control",
}

#: Section 6.4, S5 row. Percent of requests. [INF]: real traffic is unknown.
S5_MIX = {
    "on_topic_cold": 55,
    "cache_hit": 15,
    "out_of_corpus": 20,
    "greeting_off_topic": 5,
    "crisis": 1,
    "other": 4,
}

GREETING_OFF_TOPIC = ["Hi", "Thank you", "Namaste", "What is the weather today?"]
OTHER = ["Can you tell me a joke?", "Who won the cricket match?", "What is 17 times 23?"]

TEST_CAP_USD = 25.0  # section 6.5, proposed
AB1_FRACTION = 0.8  # AB-1: stop at 80 percent of the cap
AB3_WINDOW_S = 120.0  # AB-3: over 2 minutes
AB3_RATE = 0.05
AB3_MIN_SAMPLES = 20


def _jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if row.get("_header"):
            continue
        rows.append(row)
    return rows


def load_pools(repo_root: Path) -> dict[str, list[str]]:
    """Question pools from the committed eval files (section 6.3).

    The gold set is synthetic and AI-written (its own header says so): load results show
    behaviour under load, not answer quality.
    """
    gold = _jsonl(repo_root / "evals" / "gold_set_v1" / "questions.jsonl")
    on_topic = [r["text"] for r in gold if r.get("type") == "on_topic"]
    abstain = [r["text"] for r in gold if r.get("type") in {"ooc", "adversarial"}]
    frozen = [
        r["question"]
        for r in _jsonl(repo_root / "evals" / "first_person" / "frozen29.jsonl")
        if r.get("question")
    ]
    ooc13 = [
        r["question"]
        for r in _jsonl(repo_root / "evals" / "first_person" / "ooc13.jsonl")
        if r.get("question")
    ]
    crisis = [
        r["query"]
        for r in _jsonl(repo_root / "evals" / "pr_suite" / "distress_crisis.jsonl")
        if r.get("is_acute_crisis")
    ]
    return {
        "on_topic": on_topic + frozen,
        "abstain": abstain + ooc13,
        "crisis": crisis,
        "greeting_off_topic": list(GREETING_OFF_TOPIC),
        "other": list(OTHER),
    }


def classify(status: int, headers: Mapping[str, str], body: Any) -> str:
    """Map one response to a class: served, abstain, crisis, shed, rate_limited,
    general_generated or error. ``body`` is the parsed JSON (dict) or a text."""
    if status == 503:
        return "shed" if (headers.get("Retry-After") or headers.get("retry-after")) else "error"
    if status == 429:
        return "rate_limited"
    if status >= 500 or status >= 400:
        return "error"
    if not isinstance(body, dict):
        return "error"
    intent = str(body.get("intent") or "").upper()
    if body.get("grounding_state") == "safety_redirect" or intent in {"DISTRESS", "CRISIS"}:
        return "crisis"
    route = str(body.get("route_decision") or "")
    if "general" in route:
        return "general_generated"
    if route == "first_person_bridge" and body.get("citations"):
        return "served"
    return "abstain"


def violation(kind: str, outcome: str) -> str | None:
    """A rule broken by this (request kind, outcome) pair, or None."""
    if kind == "crisis" and outcome != "crisis":
        return "AB-6"
    if kind == "out_of_corpus" and outcome == "served":
        return "AB-5"
    if outcome == "general_generated":
        return "PC-7"
    return None


def spend_exceeded(spend_usd: float, cap_usd: float = TEST_CAP_USD) -> bool:
    """AB-1: stop when spend reaches 80 percent of the test cap."""
    return spend_usd >= cap_usd * AB1_FRACTION


class AbortRules:
    """Rolling abort rules AB-3, AB-5, AB-6 (AB-1 is `spend_exceeded`)."""

    def __init__(self) -> None:
        self._window: deque[tuple[float, bool]] = deque()

    def observe(self, kind: str, outcome: str, *, now: float) -> str | None:
        rule = violation(kind, outcome)
        if rule in {"AB-5", "AB-6"}:
            return rule
        self._window.append((now, outcome == "error"))
        while self._window and now - self._window[0][0] > AB3_WINDOW_S:
            self._window.popleft()
        if len(self._window) >= AB3_MIN_SAMPLES:
            errs = sum(1 for _, bad in self._window if bad)
            if errs / len(self._window) > AB3_RATE:
                return "AB-3"
        return None


def host_refusal(host: str, *, confirm: str) -> str | None:
    """Why this run must not start, or None. Production hosts are always refused."""
    if "production" in (host or "").lower():
        return "Host looks like production. This harness is for staging only."
    if confirm != "yes":
        return (
            "Set LOAD_CONFIRM_STAGING=yes to confirm the target is staging and spend is approved."
        )
    return None
