"""One LLM budget table and one capacity line, logged at startup.

NEW-OPS-8 / NEW-LOAD-4 (SYS-014), NEW-LOAD-5, NEW-AI-3.

Each row reads its value from the single place that owns it:

- relevance scorer timeout: `Settings.first_person_relevance_timeout_s`
  (read by services/first_person_pipeline.py at call time)
- answerability gate timeout: `_ANSWERABILITY_TIMEOUT_S` in services/first_person_pipeline.py
- Jev timeout: `Settings.jev_timeout_s`, else `Settings.intent_router_jev_timeout_s`
- provider RPM limit: `Settings.openrouter_rpm_limit`

Nothing here changes behaviour. It only reports.
"""

from __future__ import annotations

import logging
import os
from typing import Any


def _answerability_timeout_s() -> float | None:
    try:
        from services import first_person_pipeline

        return float(first_person_pipeline._ANSWERABILITY_TIMEOUT_S)
    except (ImportError, AttributeError, TypeError, ValueError):
        return None


def llm_budget_table(settings: Any) -> list[dict[str, Any]]:
    """Rows of {name, value, source}: the scorer timeouts, RPM limit and cap headroom."""
    rows: list[dict[str, Any]] = [
        {
            "name": "relevance_scorer_timeout_s",
            "value": float(getattr(settings, "first_person_relevance_timeout_s", 25.0)),
            "source": "Settings.first_person_relevance_timeout_s (D-PG13 decided 2026-11-07: the graded run pins 12 s; this default stays)",
        }
    ]
    gate = _answerability_timeout_s()
    if gate is not None:
        rows.append(
            {
                "name": "answerability_gate_timeout_s",
                "value": gate,
                "source": "services/first_person_pipeline._ANSWERABILITY_TIMEOUT_S",
            }
        )
    jev = getattr(settings, "jev_timeout_s", None)
    if jev is None:
        jev = getattr(settings, "intent_router_jev_timeout_s", 2.0)
    rows.append(
        {
            "name": "jev_timeout_s",
            "value": float(jev),
            "source": "Settings.jev_timeout_s, else intent_router_jev_timeout_s",
        }
    )
    rows.append(
        {
            "name": "openrouter_rpm_limit",
            "value": int(getattr(settings, "openrouter_rpm_limit", 60)),
            "source": "Settings.openrouter_rpm_limit (per model, shared across workers)",
        }
    )
    # SYS-014: when usage.cost is not reported, each call keeps the flat reservation.
    daily = float(getattr(settings, "openrouter_daily_budget_usd", 10.0))
    reserve = float(getattr(settings, "openrouter_max_request_cost_usd", 0.03))
    calls = int(daily / reserve) if reserve > 0 else 0
    rows.append(
        {
            "name": "daily_cap_full_path_requests",
            "value": calls // 3,  # about 3 LLM calls per full-path request
            "source": (
                f"SYS-014: ${daily:g} daily cap / ${reserve:g} reservation = {calls} calls, "
                "about 3 per request, when the provider reports no usage.cost"
            ),
        }
    )
    return rows


def capacity_snapshot(settings: Any) -> dict[str, int]:
    """CPU count, executor sizes and chat admission cap (NEW-LOAD-5).

    `os.cpu_count()` reads the HOST core count inside a container, not the cgroup
    quota (L-DOCKER-9), so compare it with the plan's vCPU before trusting it.
    """
    cpu = os.cpu_count() or 1
    embed = int(getattr(settings, "embed_thread_workers", 0) or 0)
    return {
        "cpu_count": cpu,
        # asyncio's default ThreadPoolExecutor: min(32, cpu + 4).
        "default_executor_workers": min(32, cpu + 4),
        "embed_executor_workers": embed if embed > 0 else min(2, cpu // 2 or 1),
        "max_concurrent_chat": int(getattr(settings, "max_concurrent_chat", 0) or 0),
    }


def serving_gate_warnings(settings: Any) -> list[str]:
    """Question-level gates that are off while first-person chat is serving.

    Invariants 19 and 22 describe the YES/NO answerability gate as covering every
    served clip. It is a flag: with it off the harness records
    ``answerability="permissive"`` and the relevance scorer is the only
    question-level gate left. That may be a deliberate choice, so this reports it
    at startup instead of changing it (found off in the live env, 2026-11-13).
    """
    serving = bool(getattr(settings, "first_person_route_enabled", False)) and bool(
        getattr(settings, "first_person_chat_bridge_enabled", False)
    )
    if serving and not bool(getattr(settings, "first_person_answerability_check_enabled", True)):
        return [
            "FIRST_PERSON_ANSWERABILITY_CHECK_ENABLED=false while first-person chat serves: "
            "no YES/NO answerability gate runs (answers record answerability=permissive); "
            "the relevance scorer is the only question-level gate"
        ]
    return []


def log_runtime_budget(logger: logging.Logger, settings: Any) -> None:
    """Log the budget table and the capacity line. Never raises."""
    try:
        for warning in serving_gate_warnings(settings):
            logger.warning("Serving gate posture: %s", warning)
        table = " ".join(f"{row['name']}={row['value']}" for row in llm_budget_table(settings))
        logger.info("LLM budget table: %s", table)
        cap = capacity_snapshot(settings)
        logger.info("Capacity: %s", " ".join(f"{k}={v}" for k, v in cap.items()))
    except (
        TypeError,
        ValueError,
        KeyError,
        AttributeError,
    ):  # pragma: no cover - reporting must not stop startup
        logger.debug("runtime budget log failed", exc_info=True)
