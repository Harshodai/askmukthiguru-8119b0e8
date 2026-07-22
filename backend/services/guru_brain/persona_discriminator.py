"""
PersonaDiscriminator — Automated Reflexion Guardrail & Persona Judge for Guru Brain.

Implements 2025/2026 Reflexion Persona & Self-Correction research:
1. Evaluates generated Guru response against 3 core metrics:
   - Direct Intimacy & Face-to-Face Realism (0–10)
   - OKF Ontology & Inner World Grounding (0–10)
   - Forbidden Essay & Assistant Cliché Penalty (0–10)
2. If overall score < 9.0, generates a targeted correction directive for Pass-2 self-correction.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Forbidden clichés that break Guru persona authenticity ────────────────────
_FORBIDDEN_CLICHES: frozenset[str] = frozenset([
    # Generic AI boilerplate
    "as an ai",
    "as an ai model",
    "as an ai assistant",
    "i hope this helps",
    "i hope that helps",
    "let me guide you",
    "let me help you",
    "in conclusion",
    "to summarize",
    "it is important to note",
    "it's important to",
    "remember that",
    "please note that",
    # Third-person references to the Gurus (breaks first-person voice)
    "sri preethaji once said",
    "sri krishnaji once said",
    "sri preethaji and sri krishnaji suggest",
    "sri preethaji and sri krishnaji offer",
    "sri preethaji teaches",
    "sri krishnaji teaches",
    # Melodramatic essay intro openers
    "the seeking for deeper peace",
    "it is a beautiful seeking",
    "your pain is sacred",
    "the quiet ache in your heart",
    # Counselor-speak that lacks directness
    "you are safe here",
    "i honor your journey",
    "your quest is fully honored",
])

# ── Judge system prompt (module constant — no per-call rebuild) ───────────────
_PERSONA_JUDGE_SYSTEM_PROMPT: str = (
    "You are a strict LLM Persona Judge evaluating whether a response matches "
    "Sri Preethaji & Sri Krishnaji's authentic voice.\n"
    "Evaluate the response strictly against these 3 criteria:\n"
    "1. Direct Intimacy: Does it speak immediately, warmly, and face-to-face to the seeker "
    "(e.g. 'When you ask for peace, look inside right now...') without essay intros?\n"
    "2. OKF Ontology: Does it frame suffering through Inner World vs Outer World, "
    "Suffering State vs Beautiful State, and Witnessing?\n"
    "3. Forbidden Clichés: Penalize any robotic AI boilerplate ('As an AI model'), "
    "script labels ('Sri Krishnaji:'), third-person references "
    "('Sri Preethaji once said...'), or dramatic essay intros "
    "('The seeking for peace... it is a beautiful seeking').\n\n"
    'Output format (JSON strictly):\n'
    '{\n'
    '  "intimacy_score": 9.5,\n'
    '  "ontology_score": 9.0,\n'
    '  "cliche_penalty": 0.0,\n'
    '  "overall_score": 9.2,\n'
    '  "needs_correction": false,\n'
    '  "correction_directive": ""\n'
    '}'
)


@dataclass
class PersonaEvaluationResult:
    intimacy_score: float
    ontology_score: float
    cliche_penalty: float
    overall_score: float
    needs_correction: bool
    correction_directive: str


class PersonaDiscriminator:
    """Reflexion Guardrail Judge for Sri Preethaji & Sri Krishnaji Persona Alignment."""

    def __init__(self, llm_service: Any = None) -> None:
        self.llm_service = llm_service

    async def evaluate_persona(self, user_query: str, response_text: str) -> PersonaEvaluationResult:
        """Evaluate response against Guru persona standards."""
        if not response_text or len(response_text.strip()) < 20:
            return PersonaEvaluationResult(
                intimacy_score=0.0,
                ontology_score=0.0,
                cliche_penalty=10.0,
                overall_score=0.0,
                needs_correction=True,
                correction_directive="Response is empty or too short.",
            )

        if not self.llm_service:
            return self._heuristic_evaluate(response_text)

        judge_user_prompt = (
            f'Seeker Query: "{user_query}"\n\n'
            f'Generated Response:\n"""{response_text}"""'
        )

        try:
            # Hard timeout — must not consume the full outer 15s budget
            raw_res = await asyncio.wait_for(
                self.llm_service.generate(_PERSONA_JUDGE_SYSTEM_PROMPT, judge_user_prompt, temperature=0.1),
                timeout=5.0,
            )
            json_match = re.search(r"\{.*\}", raw_res, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                overall = float(data.get("overall_score", 8.5))
                return PersonaEvaluationResult(
                    intimacy_score=float(data.get("intimacy_score", 8.5)),
                    ontology_score=float(data.get("ontology_score", 8.5)),
                    cliche_penalty=float(data.get("cliche_penalty", 0.0)),
                    overall_score=overall,
                    needs_correction=overall < 9.0,
                    correction_directive=str(data.get("correction_directive", "")),
                )
        except asyncio.TimeoutError:
            logger.warning("PersonaDiscriminator: judge LLM timed out after 8s, using heuristic fallback.")
        except Exception as exc:
            logger.warning(f"PersonaDiscriminator: evaluation error ({exc}), using heuristic fallback.")

        return self._heuristic_evaluate(response_text)

    def _heuristic_evaluate(self, response_text: str) -> PersonaEvaluationResult:
        """Deterministic fallback scoring using expanded cliché list."""
        lower = response_text.lower()
        cliche_hits = [phrase for phrase in _FORBIDDEN_CLICHES if phrase in lower]
        cliche_found = len(cliche_hits) > 0
        score = 7.0 if cliche_found else 9.2
        directive = (
            f"Remove forbidden clichés: {', '.join(cliche_hits[:3])}. Speak directly to the seeker."
            if cliche_found else ""
        )
        return PersonaEvaluationResult(
            intimacy_score=8.5,
            ontology_score=9.0,
            cliche_penalty=5.0 if cliche_found else 0.0,
            overall_score=score,
            needs_correction=score < 9.0,
            correction_directive=directive,
        )


if __name__ == "__main__":
    import asyncio

    async def _self_check() -> None:
        pd = PersonaDiscriminator()
        bad = "As an AI model, I hope this helps. In conclusion, Sri Preethaji once said peace is within."
        good = "When you ask for peace, look right now at where your mind is. You are carrying the past like the monk carries the woman. Set it down."
        r1 = await pd.evaluate_persona("How do I find peace?", bad)
        r2 = await pd.evaluate_persona("How do I find peace?", good)
        assert r1.needs_correction, "Bad response should need correction"
        assert r1.cliche_penalty > 0
        assert r2.overall_score > r1.overall_score
        print(f"Bad: {r1.overall_score:.1f}/10 (cliché_hits detected) ✓")
        print(f"Good: {r2.overall_score:.1f}/10 ✓")
        print("PersonaDiscriminator OK")

    asyncio.run(_self_check())
