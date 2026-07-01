"""MeditationGen stage — teachings-infused custom meditation reflections.

Runs AFTER GraphStage, BEFORE ResultAssemblyStage.
Only fires when proactive Serene Mind is triggered AND teachings context
is available. On any failure, returns None (non-fatal) — Serene Mind
always remains the default fallback.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

from app.pipeline.stages.base import Stage

if TYPE_CHECKING:
    from app.pipeline.stages.context import PipelineContext

logger = logging.getLogger(__name__)

# Serene Mind GUIDED_STEPS structure — step IDs that MUST be preserved.
# ponytail: hard-coded IDs mirror src/components/meditation/meditationSteps.ts
_GUIDED_STEP_IDS = [
    "arrive",
    "observe-body",
    "observe-breath",
    "observe-sound",
    "compassion",
    "complete",
]

_GUIDED_STEPS_TEMPLATE = """## Serene Mind Structure (PRESERVE EXACTLY)

| ID | Title | Duration (seconds) | Breath Pattern |
|---|---|---|---|
| arrive | Arrive | 20 | none |
| observe-body | Observe the Body | 45 | none |
| observe-breath | Observe the Breath | 60 | inhale:4, hold:0, exhale:6 |
| observe-sound | Observe the Sound | 45 | none |
| compassion | Be with Compassion | 45 | none |
| complete | Carry the Stillness | 10 | none |

Total duration: ~225 seconds (~3.75 min)."""


class MeditationGenStage(Stage):
    """Generate teachings-infused meditation instruction text.

    Rewrites ONLY the ``instruction`` field of each Serene Mind step,
    infusing it with teachings relevant to the user's emotional signals.
    Step IDs, titles, durations, and breath patterns are preserved.
    """

    name = "meditation_gen"

    async def run(self, ctx: "PipelineContext") -> "PipelineResult | None":
        import rag.prompts as prompts

        # Guard 1: only fire when proactive Serene Mind is triggered
        proactive = ctx.proactive_data
        if not proactive or not proactive.get("triggered"):
            return None

        # Guard 2: require teachings context — never generate without grounding
        citations = ctx.citations or []
        if not citations:
            logger.info("MeditationGen skipped — no teachings citations available")
            return None

        # Guard 3: crisis-level queries never get any meditation
        from services.serene_mind_engine import DistressLevel
        if proactive.get("level") == DistressLevel.CRISIS.name or proactive.get("level") == DistressLevel.SEVERE.name:
            logger.info("MeditationGen skipped — %s level, helplines only", proactive.get("level"))
            return None

        try:
            # Extract teachings context from top citations (~2000 chars)
            teachings_context = self._extract_teachings(citations, max_chars=2000)
            if not teachings_context:
                return None

            # Extract detected emotional signals
            signals = proactive.get("signals", [])
            signals_text = ", ".join(signals) if signals else "emotional distress"

            # Build prompts
            system_prompt = getattr(prompts, "MEDITATION_INFUSION_PROMPT", "")
            user_prompt = self._build_user_prompt(signals_text, teachings_context)

            # Call LLM with JSON mode (structured output)
            llm = getattr(ctx.container, "ollama", None)
            if not llm:
                logger.warning("MeditationGen skipped — no LLM service available")
                return None

            raw = await llm.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                timeout=getattr(llm, "_config", {}).get("timeout", 60) if hasattr(llm, "_config") else 60,
            )

            # Parse JSON response
            parsed = self._parse_json(raw)
            if not parsed:
                return None

            # Guard 4: verify step IDs match GUIDED_STEPS
            if not self._validate_steps(parsed):
                logger.warning("MeditationGen generated steps don't match Serene Mind structure — discarding")
                return None

            custom_meditation = {
                "source_teaching": parsed.get("source_teaching", ""),
                "steps": parsed["steps"],
            }

            # Attach to proactive Serene Mind state
            state = ctx.state
            if "proactive_serene_mind" not in state:
                state["proactive_serene_mind"] = {}
            state["proactive_serene_mind"]["custom_meditation"] = custom_meditation

            logger.info(
                "MeditationGen generated custom meditation — source: %s, signals: %s",
                parsed.get("source_teaching")[:80],
                signals_text,
            )

        except Exception as e:
            logger.warning("MeditationGen failed (non-fatal): %s", e)

        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_teachings(self, citations: list, max_chars: int = 2000) -> str:
        """Extract teachings text from top citations."""
        chunks: list[str] = []
        total = 0
        for c in citations[:3]:
            if isinstance(c, dict):
                text = c.get("text") or c.get("content") or c.get("document") or ""
            elif isinstance(c, str):
                text = c
            else:
                continue
            if not text:
                continue
            remaining = max_chars - total
            if remaining <= 0:
                break
            if len(text) > remaining:
                text = text[:remaining] + "…"
            chunks.append(text)
            total += len(text)
        return "\n\n---\n\n".join(chunks)

    def _build_user_prompt(self, signals_text: str, teachings_context: str) -> str:
        """Build the user prompt for meditation infusion."""
        return f"""## Detected Emotional Signals
{signals_text}

## Retrieved Teachings Context
{teachings_context}

{_GUIDED_STEPS_TEMPLATE}

## Task
Rewrite ONLY the `instruction` field of each step above. Infuse each instruction
with wisdom from the provided teachings that speaks to someone experiencing
{signals_text}. Preserve step IDs, titles, durations, and breath patterns EXACTLY.

Return a JSON object with:
- `source_teaching`: which teaching/chapter the reflections draw from (cite it)
- `steps`: array of 6 step objects, each with `id`, `title`, `instruction`, `durationSeconds`, and `breathPattern` (only for observe-breath)"""

    _JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\"steps\"[\s\S]*\}", re.MULTILINE)

    def _parse_json(self, raw: str) -> dict | None:
        """Extract and parse JSON from LLM output."""
        # Try direct parse first
        try:
            return json.loads(raw.strip())
        except json.JSONDecodeError:
            pass

        # Try extracting JSON block from markdown/code fences
        # Remove ```json fences
        cleaned = re.sub(r"```(?:json)?\s*", "", raw)
        cleaned = re.sub(r"```\s*$", "", cleaned)

        try:
            return json.loads(cleaned.strip())
        except json.JSONDecodeError:
            pass

        # Last resort: find the first { that starts the JSON
        match = self._JSON_BLOCK_RE.search(raw)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        logger.warning("MeditationGen could not parse LLM JSON output")
        return None

    def _validate_steps(self, parsed: dict) -> bool:
        """Verify step IDs match GUIDED_STEPS structure."""
        steps = parsed.get("steps", [])
        if not isinstance(steps, list) or len(steps) != len(_GUIDED_STEP_IDS):
            return False

        actual_ids = [s.get("id") if isinstance(s, dict) else None for s in steps]
        return actual_ids == _GUIDED_STEP_IDS


# ponytail: self-check — verifies stage name and step validation
if __name__ == "__main__":
    s = MeditationGenStage()
    assert s.name == "meditation_gen", f"Expected 'meditation_gen', got {s.name}"

    # Validate good steps pass
    good = {
        "source_teaching": "Four Sacred Secrets, Ch. 4",
        "steps": [
            {"id": "arrive", "title": "Arrive", "instruction": "...", "durationSeconds": 20},
            {"id": "observe-body", "title": "Observe the Body", "instruction": "...", "durationSeconds": 45},
            {"id": "observe-breath", "title": "Observe the Breath", "instruction": "...", "durationSeconds": 60, "breathPattern": {"inhale": 4, "hold": 0, "exhale": 6}},
            {"id": "observe-sound", "title": "Observe the Sound", "instruction": "...", "durationSeconds": 45},
            {"id": "compassion", "title": "Be with Compassion", "instruction": "...", "durationSeconds": 45},
            {"id": "complete", "title": "Carry the Stillness", "instruction": "...", "durationSeconds": 10},
        ],
    }
    assert s._validate_steps(good), "Valid steps should pass validation"

    # Bad steps (wrong IDs) should fail
    bad = {
        "source_teaching": "test",
        "steps": [
            {"id": "settle", "title": "Settle", "instruction": "...", "durationSeconds": 20},
        ],
    }
    assert not s._validate_steps(bad), "Invalid steps should fail validation"

    print("✓ MeditationGenStage self-check passed")