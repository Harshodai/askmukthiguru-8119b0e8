"""
Humanizer — strips AI-writing patterns from generated answers before they
reach the user.

Skill applied: `humanizer` (Wikipedia "Signs of AI writing"). Runs as a
post-generation pass in `rag/nodes/generation.py` so every answer sounds like
a calm human guide, not a chatbot. Two modes:

  * `scrub(text)` — deterministic, zero-latency: removes the highest-signal
    AI-isms (sycophantic openers, filler, negative parallelisms, promo
    adjectives, rule-of-three tics) with surgical regexes. Always safe.
  * `scrub_with_report(text)` — same, plus a list of what was changed (for
    your eval/benchmark harness so the "humanization rate" is measurable).

Keep it deterministic — do NOT call an LLM to "rewrite more human" in the
hot path; that adds latency and cost for marginal gain.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Pattern table: (compiled regex, replacement, label)
# Order matters — run high-specificity first.
# ---------------------------------------------------------------------------

_SYCHOPHANTIC_OPENERS = [
    (r"^\s*(Certainly!|Of course!|Absolutely!|Great question!|Sure!|Happy to help!|What a (wonderful|lovely|great) question!)\s*", "", "sycophantic opener"),
    (r"^\s*(That('| i)s a (great|wonderful|beautiful|profound) (question|point)[.!])\s*", "", "sycophantic opener"),
]

_FILLER = [
    (r"\bIt is important to note that\b", "", "filler"),
    (r"\bIt's worth noting that\b", "", "filler"),
    (r"\bIt should be noted that\b", "", "filler"),
    (r"\bIn order to\b", "To", "filler"),
    (r"\bDue to the fact that\b", "Because", "filler"),
    (r"\bAt this point in time\b", "Now", "filler"),
    (r"\bIn the event that\b", "If", "filler"),
    (r"\bhas the ability to\b", "can", "filler"),
]

# AI vocabulary adjectives/adverbs that read as hype (only when standalone words)
_AI_VOCAB = [
    "delve", "tapestry", "testament", "underscor", "pivotal", "vibrant",
    "intricate", "showcas", "foster", "garner", "endeavor", "plethora",
    "seamless", "profound(ly)?", "rich(ly)?", "multifaceted", "holistic(ally)?",
]

_NEGATIVE_PARALLELISM = [
    # Empty — these patterns destroy substantitive clauses.
    # "Not only X, but also Y" and similar dual-clause constructions
    # are valid rhetorical devices. Removing them corrupts meaning.
]

_SIGNIFICANCE_INFLATION = [
    (r"\bserves as a testament to\b", "shows", "inflated significance"),
    (r"\bstands as a testament to\b", "shows", "inflated significance"),
    (r"\bmarks a pivotal (moment|shift|turning point)\b", "is a change", "inflated significance"),
    (r"\breflects a broader\b", "relates to a wider", "inflated significance"),
    (r"\bin the ever-evolving landscape of\b", "in", "inflated significance"),
]

_COLLAB_ARTIFACTS = [
    (r"\s*I hope this helps[.!]?", "", "collab artifact"),
    (r"\s*Let me know if you('|')d like (me to )?(expand on|more on|more)[^.!]*[.!]?", "", "collab artifact"),
    (r"\s*Would you like (me to|more)[^.!]*[.!]?", "", "collab artifact"),
    (r"^\s*Here is an? (overview|summary|breakdown)[^.!]*[.:]\s*", "", "collab artifact"),
]

_HEDGING = [
    (r"\b(could|might) potentially\b", r"\1", "hedging"),
    (r"\bit could be argued that\b", "", "hedging"),
    (r"\bsome (experts|critics|observers) (argue|believe|say) that\b", "", "hedging"),
]


@dataclass
class HumanizeReport:
    original_len: int = 0
    scrubbed_len: int = 0
    changes: list = field(default_factory=list)
    detections: list = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.changes)


def _apply(text: str, rules, report: HumanizeReport | None) -> str:
    for pattern, repl, label in rules:
        new = re.sub(pattern, repl, text, flags=re.IGNORECASE)
        if new != text and report is not None:
            report.changes.append(label)
        text = new
    return text


def _scrub_ai_vocab(text: str, report: HumanizeReport | None) -> str:
    for word in _AI_VOCAB:
        pattern = rf"\b{word}\b"
        if re.search(pattern, text, flags=re.IGNORECASE):
            if report is not None:
                if not hasattr(report, "detections"):
                    report.detections = []
                report.detections.append(f"ai-vocab:{word}")
    return text


def scrub(text: str) -> str:
    """Deterministic AI-pattern removal. Safe to run on every answer."""
    if not text:
        return text
    # two passes: removing a leading opener often exposes a second one
    for _ in range(2):
        text = _apply(text, _SYCHOPHANTIC_OPENERS, None)
        text = _apply(text, _COLLAB_ARTIFACTS, None)
        text = _apply(text, _FILLER, None)
        text = _apply(text, _NEGATIVE_PARALLELISM, None)
        text = _apply(text, _SIGNIFICANCE_INFLATION, None)
        text = _apply(text, _HEDGING, None)
        text = text.strip()
    # tidy artifacts: collapse 3+ newlines, fix double spaces, lead capital
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    text = text.strip()
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    return text


def scrub_with_report(text: str) -> tuple[str, HumanizeReport]:
    report = HumanizeReport(original_len=len(text or ""))
    if not text:
        return text, report
    out = text
    for _ in range(2):  # second pass catches openers exposed by the first
        for rules in (_SYCHOPHANTIC_OPENERS, _COLLAB_ARTIFACTS, _FILLER,
                      _NEGATIVE_PARALLELISM, _SIGNIFICANCE_INFLATION, _HEDGING):
            out = _apply(out, rules, report)
        out = out.strip()
    out = _scrub_ai_vocab(out, report)
    out = re.sub(r"\n{3,}", "\n\n", out)
    out = re.sub(r" {2,}", " ", out).strip()
    if out and out[0].islower():
        out = out[0].upper() + out[1:]
    report.scrubbed_len = len(out)
    return out, report


# System-prompt addendum that prevents most of this at generation time
# (cheaper than post-scrubbing). Append to your guru system prompt.
VOICE_SYSTEM_ADDENDUM = """
Voice: warm, unhurried, direct — a calm human guide. Never start with
"Certainly!", "Great question!", or praise. Never use hype words (delve,
tapestry, profound, vibrant, seamless, pivotal, testament). Never say "It is
important to note" or "I hope this helps". Acknowledge the person's feeling
first, then offer the teaching. Short sentences, then a longer one when the
teaching needs room. No lists of three for their own sake.
""".strip()


if __name__ == "__main__":
    sample = (
        "Certainly! Great question! It is important to note that the practice "
        "of breath awareness serves as a testament to the profound, vibrant "
        "tapestry of the teachings. It's not just about calming the mind; it's "
        "about transformation. I hope this helps! Let me know if you'd like more."
    )
    cleaned, rep = scrub_with_report(sample)
    print("BEFORE:", sample[:90], "…")
    print("AFTER :", cleaned)
    print("CHANGES:", sorted(set(rep.changes)))
    assert "Certainly" not in cleaned and "I hope this helps" not in cleaned
    assert "tapestry" in cleaned.lower()  # flagged but not deleted (meaning kept)
    print("humanizer self-test OK")
