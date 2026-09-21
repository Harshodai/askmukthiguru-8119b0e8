"""Kill switch — PLAN.md Phase A5.

A single flag (global or per-locale) that disables generation entirely and
serves a safe static response with helplines, no model call, no retrieval,
no cache read/write. Runs BEFORE every other stage, including cache, so a
tripped switch can never be bypassed by a cache hit computed before the
switch was flipped, and never depends on any other stage's state.

Default off. This exists for incident response (a bad deploy, a provider
producing unsafe output, a legal/compliance hold) — not a routine control.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from app.config import settings
from app.pipeline.result import PipelineResult
from app.pipeline.stages.base import Stage
from app.release_manifest import get_release_manifest
from services.crisis_helplines import format_helplines_block
from services.safety_telemetry import log_kill_switch_triggered

if TYPE_CHECKING:
    from app.pipeline.stages.context import PipelineContext

logger = logging.getLogger(__name__)

_STATIC_MESSAGE = (
    "AskMukthiGuru is temporarily unable to generate a response. "
    "This is not about you or your question — please try again shortly."
)


def _kill_switch_locales() -> set[str]:
    raw = getattr(settings, "generation_kill_switch_locales", "") or ""
    return {code.strip().lower() for code in raw.split(",") if code.strip()}


def is_generation_killed(locale: str | None) -> bool:
    """True if generation is disabled globally or for this specific locale.

    Exposed as a standalone function (not just the Stage) so non-pipeline
    callers — an admin status endpoint, a health check — can report the
    same answer without re-implementing the flag logic.
    """
    if getattr(settings, "generation_kill_switch_enabled", False):
        return True
    return (locale or "en").lower() in _kill_switch_locales()


class KillSwitchStage(Stage):
    """First stage in the pipeline. Short-circuits everything when tripped."""

    name = "kill_switch"

    async def run(self, ctx: PipelineContext) -> PipelineResult | None:
        if not is_generation_killed(ctx.preferred_lang):
            return None

        is_global = getattr(settings, "generation_kill_switch_enabled", False)
        logger.warning(
            "GENERATION_KILL_SWITCH_ACTIVE locale=%s global=%s",
            ctx.preferred_lang,
            is_global,
        )
        log_kill_switch_triggered(
            trace_id=getattr(ctx, "trace_id", ""),
            locale=ctx.preferred_lang,
            scope="global" if is_global else "locale",
        )

        resources = format_helplines_block(
            intro="If you need to talk to someone now, these are always available:",
        )
        response = f"{_STATIC_MESSAGE}\n\n{resources}"

        return PipelineResult(
            final_answer=response,
            intent="SYSTEM_KILL_SWITCH",
            trace_id=getattr(ctx, "trace_id", ""),
            latency_ms=int((time.time() - getattr(ctx, "start_time", time.time())) * 1000),
            model_used=None,
            model_provider=None,
            route_decision="kill_switch_active",
            route_metadata={
                "requested_variant": "kill_switch",
                "selected_variant": "kill_switch_active",
                "locale": ctx.preferred_lang,
            },
            verification={
                "passed": True,
                "method": "kill_switch_static_response",
                "citations_verified": False,
            },
            release_manifest=get_release_manifest().to_dict(),
        )


if __name__ == "__main__":
    # ponytail: quick self-check, no pipeline/container needed
    from app.config import settings as _settings

    assert is_generation_killed("en") is False, "kill switch must default off"
    _settings.generation_kill_switch_enabled = True
    assert is_generation_killed("en") is True
    _settings.generation_kill_switch_enabled = False
    _settings.generation_kill_switch_locales = "hi,te"
    assert is_generation_killed("hi") is True
    assert is_generation_killed("en") is False
    _settings.generation_kill_switch_locales = ""
    print("kill_switch_stage self-checks passed")
