"""Humanizer: Removes AI-generated writing patterns from spiritual responses.

Based on Wikipedia's 'Signs of AI writing' guide, adapted for spiritual content.
Preserves doctrinal accuracy while making responses feel more human and present.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, Optional


# ---------------------------------------------------------------------------
# Prometheus counter — graceful fallback if metrics module unavailable.
# ---------------------------------------------------------------------------
try:
    from app.metrics import Counter as _PromCounter  # type: ignore

    humanizer_pattern_hits_total = _PromCounter(
        "guru_humanizer_pattern_hits_total",
        "Humanizer pattern-rule hits by rule and intent",
        ["rule", "intent"],
    )

    def _inc_pattern_hit(rule: str, intent: str, count: int) -> None:
        try:
            humanizer_pattern_hits_total.labels(rule=rule, intent=intent).inc(count)
        except Exception:
            pass
except Exception:  # pragma: no cover — import guard
    humanizer_pattern_hits_total = None  # type: ignore[assignment]

    def _inc_pattern_hit(rule: str, intent: str, count: int) -> None:
        return None


@dataclass
class PatternRule:
    """A single pattern detection and replacement rule."""

    name: str
    pattern: re.Pattern
    replacement: str | Callable[[re.Match], str]
    description: str


class SpiritualHumanizer:
    """Removes AI writing patterns from spiritual AI responses.

    Key principles:
      1. Preserve all doctrinal references and citations.
      2. Maintain spiritual depth — don't oversimplify.
      3. Add genuine presence — the sense of a real guide speaking.
      4. Vary rhythm — mix short and long sentences.
      5. Remove mechanical patterns that signal AI generation.
    """

    _MAX_STATISTICS: int = 1000

    def __init__(self) -> None:
        self.rules: list[PatternRule] = self._build_rules()
        self.statistics: list[dict] = []

    def _build_rules(self) -> list[PatternRule]:
        """Build all pattern detection rules."""
        return [
            # === AI VOCABULARY PATTERNS ===
            PatternRule(
                name="inflated_significance",
                pattern=re.compile(
                    r"\b(serves as|serving as|stands as|marks|represents) "
                    r"(a testament to|a reminder of|"
                    r"a pivotal moment|a significant step|a crucial turning point|"
                    r"an enduring legacy|a vital contribution)\b",
                    re.IGNORECASE,
                ),
                replacement=self._replace_inflated_significance,
                description="Remove inflated significance language",
            ),
            PatternRule(
                name="ai_filler_words",
                pattern=re.compile(
                    r"\b(Additionally|Moreover|Furthermore|Importantly|Notably|"
                    r"Significantly|Interestingly|Undoubtedly|Clearly|Obviously)\b",
                    re.IGNORECASE,
                ),
                replacement=self._replace_filler_word,
                description="Remove AI filler transition words",
            ),
            PatternRule(
                name="superficial_ing",
                pattern=re.compile(
                    r"(?:,\s*|\s+and\s+)(highlighting|underscoring|emphasizing|ensuring|reflecting|"
                    r"symbolizing|contributing to|cultivating|fostering|showcasing|"
                    r"encompassing|demonstrating|illustrating) [^,\[]+",
                    re.IGNORECASE,
                ),
                replacement="",
                description="Remove superficial -ing participial phrases",
            ),
            PatternRule(
                name="promotional_language",
                pattern=re.compile(
                    r"\b(nestled|breathtaking|stunning|vibrant|rich cultural heritage|"
                    r"natural beauty|groundbreaking|renowned|must-visit|profound)\b",
                    re.IGNORECASE,
                ),
                replacement=self._replace_promotional,
                description="Remove promotional adjectives",
            ),
            PatternRule(
                name="rule_of_three",
                pattern=re.compile(
                    r"(\w+), (\w+), and (\w+)"
                    r"\s+(?:that|which)?\s*"
                    r"(?:will|can|is|are|provide|offer|create|enable|help|guide)\b",
                    re.IGNORECASE,
                ),
                replacement=self._break_rule_of_three,
                description="Break rule-of-three patterns",
            ),
            # Note: rule_of_three is bounded by the \b word boundary on both
            # sides so it will not match across [Source: ...] markers. The
            # trailing \b prevents continuation into a bracket.
            PatternRule(
                name="negative_parallelism",
                pattern=re.compile(
                    r"It's not (just|only|merely|simply) [^.\[]+;?\s*it's [^.\[]+\."
                ),
                replacement=self._replace_negative_parallelism,
                description="Remove 'Not X, it's Y' constructions",
            ),
            PatternRule(
                name="em_dash_overuse",
                pattern=re.compile(r" — "),
                replacement=lambda m: self._replace_em_dash(),
                description="Replace em dashes with commas or periods",
            ),
            PatternRule(
                name="vague_attribution",
                pattern=re.compile(
                    r"\b(Experts|Researchers|Studies|Many|Some) (believe|argue|suggest|"
                    r"indicate|show|have found|have shown) that\b",
                    re.IGNORECASE,
                ),
                replacement=self._replace_vague_attribution,
                description="Remove vague attributions",
            ),
            PatternRule(
                name="collaborative_communication",
                pattern=re.compile(
                    r"\b(I hope this helps|Let me know|Feel free to|I'm here to help|"
                    r"I'd be happy to|Of course!|Certainly!|You're welcome)\b[.!]?",
                    re.IGNORECASE,
                ),
                replacement="",
                description="Remove chatbot-style closings",
            ),
            PatternRule(
                name="generic_positive_conclusion",
                pattern=re.compile(
                    r"\b(The future looks bright|Exciting times lie ahead|"
                    r"This is a major step|This represents a significant advancement)\b[^.]*\."
                ),
                replacement="",
                description="Remove generic positive conclusions",
            ),
            PatternRule(
                name="filler_phrases",
                pattern=re.compile(
                    r"\b(In order to|Due to the fact that|At this point in time|"
                    r"In the event that|It is important to note that|"
                    r"It should be noted that)\b",
                    re.IGNORECASE,
                ),
                replacement=self._replace_filler_phrase,
                description="Remove filler phrases",
            ),
            PatternRule(
                name="excessive_hedging",
                pattern=re.compile(
                    r"\b(could potentially|might possibly|may perhaps|"
                    r"it could be argued that|one might consider that)\b",
                    re.IGNORECASE,
                ),
                replacement=self._replace_hedging,
                description="Remove excessive hedging",
            ),
            # === SPIRITUAL-SPECIFIC PATTERNS ===
            PatternRule(
                name="spiritual_cliche",
                pattern=re.compile(
                    r"\b(Remember, |Always remember that |It is important to remember that )"
                    r"(the journey|the path|the divine|your true nature|the universe|"
                    r"consciousness|awareness)\b",
                    re.IGNORECASE,
                ),
                replacement=self._replace_spiritual_cliche,
                description="Remove spiritual cliches",
            ),
            PatternRule(
                name="mechanical_structure",
                pattern=re.compile(
                    r"^(First[,.]|To begin with|Let us start)\s+[^.\[]+\.\s+"
                    r"(Second[,.]|Next|Then)\s+[^.\[]+\.\s+"
                    r"(Finally[,.]|Lastly|In conclusion)\s+[^.\[]+\."
                ),
                replacement=self._replace_mechanical_structure,
                description="Break mechanical first/second/finally structures",
            ),
            PatternRule(
                name="doctrinal_footer",
                pattern=re.compile(
                    r"\*\*Note: Based on what I found[\s\S]*?\*\*"),
                replacement="",
                description="Remove canned doctrinal footer",
            ),
            PatternRule(
                name="meditation_closing",
                pattern=re.compile(
                    r"(May you find peace|May this guide you|May you be blessed|"
                    r"Peace be with you|Om shanti)[.!]?\s*$",
                    re.IGNORECASE,
                ),
                replacement=self._replace_meditation_closing,
                description="Vary meditation closings",
            ),
        ]

    # === REPLACEMENT METHODS ===

    def _replace_inflated_significance(self, match: re.Match) -> str:
        """Replace inflated significance with simple statement."""
        return ""

    def _replace_filler_word(self, match: re.Match) -> str:
        """Replace AI filler words with natural transitions or nothing."""
        fillers = {
            "additionally": "",
            "moreover": "",
            "furthermore": "",
            "importantly": "",
            "notably": "",
            "significantly": "",
            "interestingly": "",
            "undoubtedly": "",
            "clearly": "",
            "obviously": "",
        }
        original = match.group(0)
        lower = original.lower()
        return fillers.get(lower, "")

    def _replace_promotional(self, match: re.Match) -> str:
        """Replace promotional adjectives with neutral alternatives."""
        replacements = {
            "nestled": "located in",
            "breathtaking": "beautiful",
            "stunning": "striking",
            "vibrant": "active",
            "groundbreaking": "new",
            "renowned": "known",
            "must-visit": "worth visiting",
            "profound": "deep",
        }
        return replacements.get(match.group(0).lower(), match.group(0))

    def _break_rule_of_three(self, match: re.Match) -> str:
        """Break rule of three into varied structure."""
        return f"{match.group(1)} and {match.group(2)}. {match.group(3).capitalize()}"

    def _replace_negative_parallelism(self, match: re.Match) -> str:
        """Replace 'Not X, it's Y' with direct statement.
        Handles both forms: with optional semicolon (; it's ...) or
        without ( ... it's ...).
        """
        parts = re.split(r";?\s*it's\s*", match.group(0), maxsplit=1)
        return parts[-1].strip().rstrip(".") + "." if len(parts) > 1 else ""

    def _replace_em_dash(self) -> str:
        """Replace em dash based on context."""
        return random.choice([", ", ". "])

    def _replace_vague_attribution(self, match: re.Match) -> str:
        """Replace vague attributions with direct statements."""
        return ""

    def _replace_filler_phrase(self, match: re.Match) -> str:
        """Replace filler phrases with concise alternatives."""
        fillers = {
            "in order to": "to",
            "due to the fact that": "because",
            "at this point in time": "now",
            "in the event that": "if",
            "it is important to note that": "",
            "it should be noted that": "",
        }
        return fillers.get(match.group(0).lower(), "")

    def _replace_hedging(self, match: re.Match) -> str:
        """Replace hedging with direct statement."""
        return ""

    def _replace_spiritual_cliche(self, match: re.Match) -> str:
        """Replace spiritual cliches with fresh phrasing."""
        intros = [
            "Consider",
            "Reflect on",
            "Notice",
            "Observe",
            "In your experience, see if",
        ]
        return random.choice(intros)

    def _replace_mechanical_structure(self, match: re.Match) -> str:
        """Break mechanical first/second/finally structure."""
        text = match.group(0)
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
        cleaned: list[str] = []
        for s in sentences:
            s = re.sub(
                r"^(First[,.]|Second[,.]|Next[,.]|Then[,.]|Finally[,.]|Lastly[,.]|"
                r"In conclusion[,.]|To begin with[,.]|Let us start[,.])\s*",
                "",
                s,
                flags=re.IGNORECASE,
            )
            if s:
                cleaned.append(s)
        return " ".join(cleaned)

    def _replace_meditation_closing(self, match: re.Match) -> str:
        """Vary meditation closings."""
        closings = [
            "Rest in this awareness.",
            "Remain with this feeling.",
            "Simply be.",
            "Let this settle.",
            "Stay here as long as you wish.",
        ]
        return random.choice(closings)

    # === PUBLIC API ===

    def humanize(self, text: str, intent: str = "general") -> str:
        """Remove AI patterns from spiritual response text.

        Args:
            text: The AI-generated response.
            intent: The intent type (general, meditation, teaching, distress, greeting).

        Returns:
            Humanized text with AI patterns removed.
        """
        original = text
        changes: list[dict] = []

        for rule in self.rules:
            # Skip meditation-specific rules for non-meditation intents
            if intent != "meditation" and rule.name in ("meditation_closing",):
                continue

            new_text, count = rule.pattern.subn(rule.replacement, text)
            if count > 0:
                changes.append({
                    "rule": rule.name,
                    "count": count,
                    "description": rule.description,
                })
                text = new_text
                _inc_pattern_hit(rule.name, intent, count)

        # Clean up artifacts
        text = self._cleanup(text)

        # Add rhythm variation
        text = self._vary_rhythm(text)

        self.statistics.append({
            "original_length": len(original),
            "final_length": len(text),
            "changes": changes,
            "total_changes": sum(c["count"] for c in changes),
        })
        # Bounded retention: evict oldest when limit exceeded.
        if len(self.statistics) > self._MAX_STATISTICS:
            self.statistics = self.statistics[-self._MAX_STATISTICS:]

        return text.strip()

    def _cleanup(self, text: str) -> str:
        """Clean up artifacts from replacements."""
        # Remove double spaces
        text = re.sub(r"  +", " ", text)
        # Remove empty lines
        text = re.sub(r"\n\n\n+", "\n\n", text)
        # Fix punctuation spacing
        text = re.sub(r" ([.,;!?])", r"\1", text)
        # Strip leading punctuation at sentence beginnings (from removed filler words).
        text = re.sub(r"^[,\s;:]+", "", text, flags=re.MULTILINE)
        # Capitalize first character of each sentence if it's lowercase.
        text = re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)
        # Remove leading/trailing whitespace per paragraph
        text = "\n".join(line.strip() for line in text.split("\n"))
        return text

    def _vary_rhythm(self, text: str) -> str:
        """Add rhythm variation to sentence structure."""
        sentences = re.split(r"(?<=[.!?])\s+", text)

        # If all sentences are similar length, vary them
        lengths = [len(s.split()) for s in sentences if s.strip()]
        if len(lengths) < 3:
            return text

        avg_length = sum(lengths) / len(lengths)
        if max(lengths) - min(lengths) <= 3:
            # Sentences are too uniform — add a short one
            for i, s in enumerate(sentences):
                if len(s.split()) > avg_length + 2:
                    # Split a long sentence and capitalize the fragment
                    parts = s.split(", ", 1)
                    if len(parts) == 2:
                        sentences[i] = parts[0] + ".\n" + parts[1][0].upper() + parts[1][1:]
                        break

        return " ".join(sentences)

    def get_statistics(self) -> list[dict]:
        """Get statistics from recent humanize calls."""
        return self.statistics


# === INTEGRATION WITH RESPONSE PIPELINE ===

@lru_cache(maxsize=1)
def _get_humanizer() -> SpiritualHumanizer:
    """Cached humanizer instance (Ponytail: simple caching, no state-tracking)."""
    return SpiritualHumanizer()


def apply_humanizer_to_response(response_text: str, intent: str = "general") -> str:
    """Apply humanizer to a generated response before sending to user.

    Usage in pipeline:
        final_answer = apply_humanizer_to_response(
            raw_llm_response,
            intent=detected_intent,
        )
    """
    humanizer = _get_humanizer()

    # Don't humanize if response is too short (likely a simple answer)
    if len(response_text) < 100:
        return response_text

    # Don't humanize if response contains citations that must be preserved
    if "Based on" in response_text and "teaching" in response_text.lower():
        # Be more careful with doctrinal responses
        return humanizer.humanize(response_text, intent="teaching")

    return humanizer.humanize(response_text, intent=intent)


# === TEST EXAMPLES ===

TEST_CASES = [
    {
        "name": "Inflated significance",
        "input": (
            "This meditation technique stands as a testament to the ancient wisdom of "
            "our teachers, serving as a pivotal moment in your spiritual journey and "
            "contributing to the evolving landscape of consciousness."
        ),
        "expected_contains": ["meditation technique", "ancient wisdom"],
        "expected_not_contains": [
            "stands as a testament", "pivotal moment", "evolving landscape",
        ],
    },
    {
        "name": "AI filler words",
        "input": (
            "Additionally, it is important to remember that the path of meditation is "
            "profoundly personal. Moreover, your journey is uniquely yours."
        ),
        "expected_contains": ["meditation", "personal"],
        "expected_not_contains": [
            "Additionally", "Moreover", "it is important to remember",
        ],
    },
    {
        "name": "Rule of three",
        "input": (
            "This practice offers clarity, peace, and transformation that will guide "
            "you on your journey."
        ),
        "expected_not_contains": ["clarity, peace, and transformation"],
    },
    {
        "name": "Doctrinal footer",
        "input": (
            "The teaching of breath awareness comes from the Upanishads. **Note: Based "
            "on what I found in our teachings library, this information is provided for "
            "your spiritual growth.**"
        ),
        "expected_contains": ["breath awareness", "Upanishads"],
        "expected_not_contains": ["Note: Based on what I found"],
    },
]


def _run_test_cases() -> int:
    """Run the 4 embedded TEST_CASES. Returns number of failures."""
    failures = 0
    humanizer = SpiritualHumanizer()
    for case in TEST_CASES:
        out = humanizer.humanize(case["input"], intent="general")
        ok = True
        for needle in case.get("expected_contains", []):
            if needle not in out:
                ok = False
                print(f"FAIL [{case['name']}] expected contains '{needle}' missing")
                print(f"  output: {out!r}")
        for needle in case.get("expected_not_contains", []):
            if needle in out:
                ok = False
                print(f"FAIL [{case['name']}] expected not contains '{needle}' present")
                print(f"  output: {out!r}")
        if ok:
            print(f"PASS [{case['name']}]")
        else:
            failures += 1
    return failures


if __name__ == "__main__":
    _f = _run_test_cases()
    if _f == 0:
        print("A3 OK")
    raise SystemExit(0 if _f == 0 else 1)