"""Fast intake safety kernel with deterministic zero-I/O crisis preemption.

Adheres to Invariant X38: Deterministic crisis and acute self-harm safety
decisions must execute before any database lookups, crypto operations, or LLM stages.
Resolves M1/M2 audit defects (question-phrased crisis queries like
"how do i stop wanting to die", "ways to end it all", "is life worth living").
"""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional


@dataclass(frozen=True)
class SafetyVerdict:
    """Deterministic verdict emitted by FastSafetyKernel."""

    is_crisis: bool
    reason: Optional[str] = None
    matched_pattern: Optional[str] = None
    helpline_response: Optional[str] = None
    disposition: Optional[str] = None
    is_injection: bool = False
    refusal_response: Optional[str] = None


class _AhoCorasickNode:
    __slots__ = ("children", "fail", "output")

    def __init__(self) -> None:
        self.children: dict[str, _AhoCorasickNode] = {}
        self.fail: _AhoCorasickNode | None = None
        self.output: list[str] = []


class _AhoCorasickAutomaton:
    """Pure-Python high-performance Aho-Corasick automaton."""

    def __init__(self, patterns: list[str]) -> None:
        self.root = _AhoCorasickNode()
        for p in patterns:
            self._insert(p)
        self._build_transitions()

    def _insert(self, pattern: str) -> None:
        curr = self.root
        for ch in pattern:
            curr = curr.children.setdefault(ch, _AhoCorasickNode())
        curr.output.append(pattern)

    def _build_transitions(self) -> None:
        queue: deque[_AhoCorasickNode] = deque()
        for child in self.root.children.values():
            child.fail = self.root
            queue.append(child)

        while queue:
            curr = queue.popleft()
            for ch, child in curr.children.items():
                fail_node = curr.fail
                while fail_node and ch not in fail_node.children:
                    fail_node = fail_node.fail
                child.fail = fail_node.children[ch] if fail_node else self.root
                child.output.extend(child.fail.output)
                queue.append(child)

    def search_first(self, text: str) -> Optional[str]:
        """Return the first matched pattern or None."""
        curr = self.root
        for ch in text:
            while curr and ch not in curr.children:
                curr = curr.fail
            if not curr:
                curr = self.root
                continue
            curr = curr.children[ch]
            if curr.output:
                return curr.output[0]
        return None


# Standard acute crisis phrases and question-phrased queries (M1/M2)
_CRISIS_PATTERNS = [
    "suicide",
    "suicidal",
    "kill myself",
    "end my life",
    "take my life",
    "take my own life",
    "want to die",
    "wanting to die",
    "hang myself",
    "overdose",
    "overdosed",
    "overdosing",
    "overdoses",
    "suicides",
    "not worth living",
    "stop wanting to die",
    "better off dead",
    "cutting myself",
    "slit my wrists",
    "slit my wrist",
    "slit wrists",
    "slit wrist",
    "commit suicide",
    "end it all",
    "ending it all",
    "ending everything",
    "ways to end it all",
    "how do i stop wanting to die",
    "how to stop wanting to die",
    "is life worth living",
    "how to kill myself",
    "how to end my life",
    "how to commit suicide",
    "ways to commit suicide",
    "i want to die",
    "i want to kill myself",
    "i want to end my life",
    "i want to end it all",
    "suicide is my only option",
    "harm myself",
    "harming myself",
    "jump off a bridge",
    "jump off bridge",
    "jump off the bridge",
    "jump off a cliff",
    "jump off cliff",
    "standing on the ledge",
    "standing on a ledge",
    "standing on ledge",
    # implicit lethal means (SEC-01 / ua70)
    "bottle of sleeping pills",
    "bottle of pills",
    "pills next to me",
    "staring at pills",
    "handful of sleeping pills",
    "overdose on sleeping pills",
    "swallow sleeping pills",
    "swallowed all my sleeping pills",
    "swallowed my sleeping pills",
    "took all my sleeping pills",
    "taking all my sleeping pills",
    "stockpiling my sleeping pills",
    "how many sleeping pills",
    "rat poison",
    # third-party and adolescent self-harm (SEC-01 / ua71)
    "cutting her arm",
    "cutting his arm",
    "cutting their arm",
    "cutting my arm",
    "cutting her wrist",
    "cutting his wrist",
    "cutting their wrist",
    "cutting my wrist",
    "cutting her body",
    "cutting his body",
    "cutting their body",
    "cutting my body",
    "cutting her arms",
    "cutting his arms",
    "cutting their arms",
    "cutting my arms",
    "cutting herself",
    "cutting himself",
    "cutting themselves",
    "teen cutting",
    "daughter cutting",
    "son cutting",
    # inflections and common acute phrasings that the exact phrases above miss
    "killing myself",
    "ending my life",
    "ending my own life",
    "taking my life",
    "taking my own life",
    "end my own life",
    "dont want to live",
    "don t want to live",
    "do not want to live",
    "no reason to live",
    "wish i was dead",
    "wish i were dead",
    "self harm",
    "self harming",
]

# Obfuscation-resistant condensed needles (matched against de-spaced strings)
_DESPACED_CRISIS_NEEDLES = [
    "suicide",
    "suicidal",
    "killmyself",
    "endmylife",
    "takemylife",
    "takemyownlife",
    "wanttodie",
    "wantingtodie",
    "hangmyself",
    "overdose",
    "notworthliving",
    "stopwantingtodie",
    "betteroffdead",
    "cuttingmyself",
    "slitmywrists",
    "slitmywrist",
    "slitwrists",
    "commitsuicide",
    "enditall",
    "waystoenditall",
    "howdoistopwantingtodie",
    "howtokillmyself",
    "howtoendmylife",
    "howtocommitsuicide",
    "suicideismyonlyoption",
    "harmmyself",
    "harmingmyself",
    "sleepingpills",
    "bottleofsleepingpills",
    "bottleofpills",
    "ratpoison",
    "cuttingherarm",
    "cuttinghisarm",
    "cuttingtheirarm",
    "cuttingmyarm",
    "cuttingherself",
    "cuttinghimself",
    "cuttingthemselves",
]

_HELPLINE_MESSAGE = (
    "Please connect directly with verified, confidential crisis support:\n"
    "• Tele-MANAS (India): 14416 / 1800 891 4416 (24/7 Toll-Free Mental Health Helpline)\n"
    "• Emergency Services: 112 (India) or your local emergency number\n"
    "• Vandrevala Foundation (India): +91 9999 666 555 (24/7 Free & Confidential Counseling)\n\n"
    "Support is available and trained professionals are ready to help. You do not have to "
    "face this alone. If you or someone nearby is in immediate danger, please contact "
    "emergency services immediately."
)

_INJECTION_REFUSAL_MESSAGE = (
    "I am an AI assistant designed to explore teachings from Sri Preethaji and Sri Krishnaji. "
    "I cannot alter my core instructions, disclose system prompts, or adopt external personas. "
    "How may I assist you with teachings today?"
)

_PROMPT_INJECTION_PATTERNS = [
    r"\b(ignore|disregard|forget)\b.*\b(previous|above|prior|all)\b.*\b(instructions?|rules?|prompts?)\b",
    r"\b(you\s+are\s+now|act\s+as|pretend\s+to\s+be|roleplay\s+as)\b",
    r"\b(system\s+prompt|reveal\s+your|show\s+me\s+your)\b.*\b(instructions?|prompt|rules?)\b",
    r"\bdan\s+mode\b",
    r"\bjailbreak\b",
    r"\bdo\s+anything\s+now\b",
    r"\bdeveloper\s*mode\b|डेवलपर\s*मोड|డెవలపర్\s*మోడ్",
    r"प्रतिबंध\s*हटा",
    r"\byou\s+are\s+(?:now\s+)?no\s+longer\s+(?:an?\s+)?(?:ai|guru|assistant|bot)\b",
    r"(?:तुम|आप)\s*अब\s*(?:कोई\s*)?ai\s*नहीं",
    r"\bSYSTEM\s*:\s*.+\b(override|guardrails?|safety|instructions?|rules?)\b",
    r"\boverride\s+(mode|system|safety|guardrails?|instructions?)\b",
    r"(?:सिस्टम|సిస్టమ్|சிஸ்டம்)\s*(?:प्रॉम्प्ट|प्रांप्ट|ప్రాంప్ట్|ப்ராம்ப்ட்)",
    r"(?:पिछ(?:ली|ले)|पहले\s+के|मागील|మునుపటి|முந்தைய)\s*(?:सारे\s+|सभी\s+)?(?:निर्देश|सूचना\w*|సూచన\w*|அறிவுறுத்தல்\w*)",
    r"\bpichh?le\b.{0,25}\binstructions?\b.{0,25}\b(?:ignore|bhool|bhul)\w*",
    r"\b(?:ignore|bhool|bhul)\w*\b.{0,30}\b(?:pichh?le|pehle|previous)\b.{0,25}\binstructions?\b",
    r"स्वतंत्र\s*(?:AI|एआई|ए\s*आई)",
    r"सुरक्षा\s*(?:नियम|नीति)\s*(?:के\s+)?बिना",
    r"(?:सभी|सारे)\s+(?:नियम|प्रतिबंध)\s*(?:तोड़|हटा|बदल)\w*",
    r"बिना\s+(?:किसी\s+)?(?:सीमा|प्रतिबंध|नियम)\s+के\s+(?:जवाब|बता|बोल)\w*",
    r"(?:భద్రత|రక్షణ)\s*(?:నియమాలు|నీతి)\s*(?:లేకుండా|తొలగించు)",
    r"స్వతంత్ర\s*(?:AI|ఏఐ)",
]
_PROMPT_INJECTION_RES = [re.compile(p, re.IGNORECASE) for p in _PROMPT_INJECTION_PATTERNS]


_SINGLE_CHAR_RUN_RE = re.compile(r"(?:^| )[a-z0-9](?: [a-z0-9]){2,}(?: |$)")


class FastSafetyKernel:
    """Pre-compiled zero-IO Aho-Corasick safety preemption engine.

    Guarantees deterministic <2ms response time for acute self-harm
    and crisis triggers before entering the RAG pipeline.
    """

    def __init__(self) -> None:
        # Whole-word matching: " end it all " must not fire inside "send it all".
        self._automaton = _AhoCorasickAutomaton([f" {p} " for p in _CRISIS_PATTERNS])
        self._despaced_automaton = _AhoCorasickAutomaton(_DESPACED_CRISIS_NEEDLES)
        self._injection_regexes = _PROMPT_INJECTION_RES

    def evaluate(self, text: str) -> SafetyVerdict:
        """Scan input query for acute crisis or prompt-injection indicators in <2ms."""
        if not text or not isinstance(text, str):
            return SafetyVerdict(is_crisis=False, disposition="ordinary_hardship")

        raw = text.strip()
        if not raw:
            return SafetyVerdict(is_crisis=False, disposition="ordinary_hardship")

        # 0. Deterministic fast prompt-injection refusal before retrieval (<0.1ms)
        for pat in self._injection_regexes:
            if pat.search(raw):
                return SafetyVerdict(
                    is_crisis=False,
                    is_injection=True,
                    disposition="elevated_safety_support",
                    reason="prompt_injection",
                    matched_pattern=pat.pattern,
                    refusal_response=_INJECTION_REFUSAL_MESSAGE,
                )

        lower = raw.lower()

        # 1. Normalized space-delimited check
        # Replaces punctuation with single spaces and collapses whitespace
        normalized = re.sub(r"[^a-z0-9]+", " ", lower).strip()
        matched = self._automaton.search_first(f" {normalized} ")
        if matched:
            matched = matched.strip()
            return SafetyVerdict(
                is_crisis=True,
                disposition="acute_crisis",
                reason="acute_self_harm_preemption",
                matched_pattern=matched,
                helpline_response=_HELPLINE_MESSAGE,
            )

        # 2. De-spaced check for obfuscation ("s u i c i d e", "k-i-l-l-m-y-s-e-l-f").
        # Only when the text carries a run of 3+ single-character tokens: de-spacing ordinary
        # prose glues words together ("send it all to me" -> "enditall", "I want to diet" ->
        # "wanttodie") and flagged benign messages.
        if not _SINGLE_CHAR_RUN_RE.search(normalized):
            return SafetyVerdict(is_crisis=False, disposition="ordinary_hardship")
        despaced = re.sub(r"[^a-z0-9]", "", lower)
        matched_despaced = self._despaced_automaton.search_first(despaced)
        if matched_despaced:
            return SafetyVerdict(
                is_crisis=True,
                disposition="acute_crisis",
                reason="obfuscated_self_harm_preemption",
                matched_pattern=matched_despaced,
                helpline_response=_HELPLINE_MESSAGE,
            )

        return SafetyVerdict(is_crisis=False, disposition="ordinary_hardship")


@lru_cache(maxsize=1)
def get_safety_kernel() -> FastSafetyKernel:
    """Process-wide kernel: the two automata are built once, not per request."""
    return FastSafetyKernel()
