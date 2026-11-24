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

import hashlib
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
    warnings: list[str] = []
    serving = bool(getattr(settings, "first_person_route_enabled", False)) and bool(
        getattr(settings, "first_person_chat_bridge_enabled", False)
    )
    if serving and not bool(getattr(settings, "first_person_answerability_check_enabled", True)):
        warnings.append(
            "FIRST_PERSON_ANSWERABILITY_CHECK_ENABLED=false while first-person chat serves: "
            "no YES/NO answerability gate runs (answers record answerability=permissive); "
            "the relevance scorer is the only question-level gate"
        )
    # A-32: in production an undeclared posture is allowed but named, so a deployment
    # that lost its harness variables is visible as "serving the legacy lane".
    if getattr(settings, "is_production", False) is True and not getattr(
        settings, "first_person_serving_posture", ""
    ):
        v10 = bool(getattr(settings, "first_person_context_harness_enabled", False)) and (
            getattr(settings, "first_person_context_terminal_enabled", False) is True
        )
        lane = "v10-only context harness" if v10 else "legacy clip store"
        warnings.append(
            "FIRST_PERSON_SERVING_POSTURE is undeclared: the resolved flags serve the "
            f"{lane} (collection "
            f"{getattr(settings, 'first_person_collection', '')!r}); set it to v10_only, "
            "v12_shadow, v13_shadow, or v8_bridge so a mismatch stops startup"
        )
    return warnings


# The project alerts at 70% of a cap in production; locally there was no signal at all, so a
# plain compose stack refused every model call with a provider-style message and nothing said
# whose limit it was (T-E2, 2026-11-14).
HEADROOM_WARN_FRACTION = 0.70


def budget_cap_warnings(
    settings: Any, spent_day: float | None, spent_month: float | None
) -> list[str]:
    """Report a spend cap that is at or near its limit *before* a user asks a question.

    Pure: the caller reads the ledger. ``None`` means the ledger could not be read, which is
    not a cap breach and must not be reported as one (an unreachable ledger already has its
    own fail-closed behaviour in `app/openrouter_budget.py`).
    """
    if not bool(getattr(settings, "openrouter_budget_guard_enabled", False)):
        return []
    daily = float(getattr(settings, "openrouter_daily_budget_usd", 0.0) or 0.0)
    monthly = float(getattr(settings, "openrouter_monthly_budget_usd", 0.0) or 0.0)
    warnings: list[str] = []
    for label, spent, cap, setting in (
        ("day", spent_day, daily, "OPENROUTER_DAILY_BUDGET_USD"),
        ("month", spent_month, monthly, "OPENROUTER_MONTHLY_BUDGET_USD"),
    ):
        if spent is None or cap <= 0:
            continue
        if spent >= cap:
            warnings.append(
                f"model budget cap reached: {label} ledger ${spent:.2f} >= cap ${cap:.2f} "
                f"({setting}). Every LLM call is refused by our own guard "
                "(app/openrouter_budget.py) until the cap is raised or the ledger rolls over — "
                "this is not a provider balance problem"
            )
        elif spent >= cap * HEADROOM_WARN_FRACTION:
            warnings.append(
                f"model budget {label} ledger ${spent:.2f} is at "
                f"{spent / cap:.0%} of the ${cap:.2f} cap ({setting}); at 100% every LLM call "
                "is refused by our own guard"
            )
    return warnings


def _ledger_read_errors() -> tuple[type[BaseException], ...]:
    """The exceptions a ledger read may raise, named rather than swallowed with `Exception`.

    Redis raises `redis.exceptions.RedisError`, which does not subclass `OSError`, so a narrow
    `OSError` catch would miss a dead Redis. The repo's exception ratchet is shrink-only, so this
    stays an enumerated tuple instead of a blanket catch.
    """
    errors: tuple[type[BaseException], ...] = (
        ImportError,
        OSError,
        ValueError,
        TypeError,
        AttributeError,
        TimeoutError,
    )
    try:
        from redis.exceptions import RedisError

        return errors + (RedisError,)
    except ImportError:  # redis absent in a docs-only environment
        return errors


_LEDGER_READ_ERRORS = _ledger_read_errors()


async def read_spend_ledger(settings: Any) -> tuple[float | None, float | None]:
    """Read today's and this month's OpenRouter spend. Best-effort: `(None, None)` when unknown.

    Uses the guard's own key derivation (`OpenRouterBudgetGuard._keys`) so the reader and the
    writer can never disagree about where the ledger lives.
    """
    if not bool(getattr(settings, "openrouter_budget_guard_enabled", False)):
        return None, None
    try:
        import redis.asyncio as aioredis

        from app.openrouter_budget import OpenRouterBudgetGuard

        day_key, month_key, _, _ = OpenRouterBudgetGuard._keys()
        # Bounded: a startup report must never hold the app on an unreachable Redis
        # (`socket_connect_timeout=None` is the client default, i.e. OS-timeout only).
        client = aioredis.from_url(
            str(settings.redis_url),
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        try:
            day, month = await client.mget(day_key, month_key)
        finally:
            await client.aclose()
        return float(day or 0.0), float(month or 0.0)
    except _LEDGER_READ_ERRORS:  # reporting must never stop startup
        return None, None


async def log_budget_headroom(logger: logging.Logger, settings: Any) -> None:
    """Say the cap state once at startup. Never raises, never spends."""
    try:
        spent_day, spent_month = await read_spend_ledger(settings)
        for warning in budget_cap_warnings(settings, spent_day, spent_month):
            logger.warning("Model budget posture: %s", warning)
        if spent_day is not None and spent_month is not None:
            logger.info(
                "Model budget ledger: day=$%.2f of $%.2f, month=$%.2f of $%.2f",
                spent_day,
                float(getattr(settings, "openrouter_daily_budget_usd", 0.0) or 0.0),
                spent_month,
                float(getattr(settings, "openrouter_monthly_budget_usd", 0.0) or 0.0),
            )
    except (
        TypeError,
        ValueError,
        KeyError,
        AttributeError,
    ):  # pragma: no cover - reporting must not stop startup
        logger.debug("budget headroom log failed", exc_info=True)


#: Additive retrieval expansions and the posture the repository documents for them
#: (AGENTS.md first-person serving invariant 3, the `app/config.py` comments and
#: `backend/.env.example`). Reported, never changed: the 2026-11-22 follow-up plan
#: requires the effective posture to be named and fingerprinted before any quality
#: measurement, because the code defaults and `.env` currently disagree with the docs.
_EXPANSION_POSTURE: tuple[tuple[str, str], ...] = (
    ("first_person_enrichment_window_enabled", "FIRST_PERSON_ENRICHMENT_WINDOW_ENABLED"),
    ("first_person_graph_expansion_enabled", "FIRST_PERSON_GRAPH_EXPANSION_ENABLED"),
    ("first_person_okf_expansion_enabled", "FIRST_PERSON_OKF_EXPANSION_ENABLED"),
    ("first_person_cross_video_diversity_enabled", "FIRST_PERSON_CROSS_VIDEO_DIVERSITY_ENABLED"),
    ("first_person_teaching_unit_graph_enabled", "FIRST_PERSON_TEACHING_UNIT_GRAPH_ENABLED"),
)


def expansion_posture(settings: Any) -> list[dict[str, Any]]:
    """Effective value of each additive expansion flag, with the documented default.

    The documented default is ``False`` for every row: the config comments, `.env.example`
    and serving invariant 3 all describe these as off until measured. A row whose
    ``effective`` differs is a posture the owner has to name, not something this reports
    as an error.
    """
    return [
        {
            "name": name,
            "env": env,
            "effective": bool(getattr(settings, name, False)),
            "documented_default": False,
        }
        for name, env in _EXPANSION_POSTURE
    ]


def expansion_posture_fingerprint(settings: Any) -> str:
    """Bounded digest of the effective expansion posture, for recording next to a run."""
    pairs = sorted(f"{row['name']}={int(row['effective'])}" for row in expansion_posture(settings))
    return hashlib.sha256("|".join(pairs).encode("utf-8")).hexdigest()[:12]


_RUNTIME_CONFIG_FINGERPRINT_FIELDS: tuple[str, ...] = (
    "llm_provider",
    "anthropic_gateway_enabled",
    "anthropic_gateway_model",
    "first_person_serving_posture",
    "first_person_mode",
    "first_person_collection",
    "first_person_context_collection",
    "first_person_context_harness_enabled",
    "first_person_context_terminal_enabled",
    "first_person_llm_fallback_enabled",
    "first_person_answerability_check_enabled",
    "first_person_relevance_min_score",
    "first_person_relevance_model",
    "first_person_context_use_sparse",
    "first_person_hyde_enabled",
    "first_person_comparative_judge_enabled",
    "first_person_enrichment_window_enabled",
    "first_person_graph_expansion_enabled",
    "first_person_okf_expansion_enabled",
    "first_person_cross_video_diversity_enabled",
    "first_person_teaching_unit_graph_enabled",
    "first_person_multipart_enabled",
    "first_person_abstain_related_clips_enabled",
)


def runtime_config_fingerprint(settings: Any) -> str:
    """Deterministic SHA-256 prefix over effective serving, provider, and retrieval flags."""
    pairs = [
        f"{name}={getattr(settings, name, None)!r}"
        for name in sorted(_RUNTIME_CONFIG_FINGERPRINT_FIELDS)
    ]
    return hashlib.sha256("|".join(pairs).encode("utf-8")).hexdigest()[:16]


def expansion_posture_warnings(settings: Any) -> list[str]:
    """One warning per expansion flag that is ON while the repository documents it off."""
    return [
        f"{row['env']}=true but AGENTS.md serving invariant 3 and the config comment document "
        f"it as off until measured ({row['name']}); record the owner decision and fingerprint "
        "the posture before measuring follow-up quality"
        for row in expansion_posture(settings)
        if row["effective"]
    ]


def log_runtime_budget(logger: logging.Logger, settings: Any) -> None:
    """Log the budget table and the capacity line. Never raises."""
    try:
        for warning in serving_gate_warnings(settings):
            logger.warning("Serving gate posture: %s", warning)
        for warning in expansion_posture_warnings(settings):
            logger.warning("Context expansion posture: %s", warning)
        table = " ".join(f"{row['name']}={row['value']}" for row in llm_budget_table(settings))
        logger.info("LLM budget table: %s", table)
        cap = capacity_snapshot(settings)
        logger.info("Capacity: %s", " ".join(f"{k}={v}" for k, v in cap.items()))
        posture = " ".join(
            f"{row['name']}={'on' if row['effective'] else 'off'}"
            for row in expansion_posture(settings)
        )
        logger.info(
            "Context expansion posture: %s fingerprint=%s",
            posture,
            expansion_posture_fingerprint(settings),
        )
    except (
        TypeError,
        ValueError,
        KeyError,
        AttributeError,
    ):  # pragma: no cover - reporting must not stop startup
        logger.debug("runtime budget log failed", exc_info=True)
