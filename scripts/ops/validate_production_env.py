#!/usr/bin/env python3
"""Fail-closed, secret-redacting preflight for a production deployment."""

from __future__ import annotations

import ast
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PreflightResult:
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


def _backend_config_path() -> Path | None:
    """Locate ``backend/app/config.py`` from either twin path.

    The root copy lives at ``scripts/ops/`` and the backend copy at
    ``backend/scripts/ops/`` (byte-identical by ``test_repo_layout``). The tree
    next to this file wins, then the sibling ``backend/`` directory.
    """
    here = Path(__file__).resolve().parents[2]
    for candidate in (here, here / "backend"):
        config_path = candidate / "app" / "config.py"
        if config_path.is_file():
            return config_path
    return None


def _read_first_person_modes() -> tuple[str, ...] | None:
    """Read ``FIRST_PERSON_MODES`` from app/config.py without building Settings.

    Importing ``app.config`` constructs ``Settings()``, which raises on an
    incomplete or invalid environment; that failure belongs to the other checks,
    not to this one. The constant is a module-level literal tuple, so parsing the
    source keeps the check dependency-free. ``test_production_env_preflight``
    asserts this parse equals ``app.config.FIRST_PERSON_MODES``.
    """
    config_path = _backend_config_path()
    if config_path is None:
        return None
    try:
        content = config_path.read_text(encoding="utf-8")
        for node in ast.parse(content).body:
            if isinstance(node, ast.AnnAssign):
                if (
                    getattr(node.target, "id", None) == "FIRST_PERSON_MODES"
                    and node.value is not None
                ):
                    return tuple(ast.literal_eval(node.value))
            elif isinstance(node, ast.Assign):
                if any(
                    getattr(target, "id", None) == "FIRST_PERSON_MODES" for target in node.targets
                ):
                    return tuple(ast.literal_eval(node.value))
    except (OSError, SyntaxError, ValueError):
        return None
    return None


def validate_environment(env: Mapping[str, str] | None = None) -> PreflightResult:
    values = env if env is not None else os.environ
    errors: list[str] = []
    warnings: list[str] = []

    def required(name: str) -> None:
        if not str(values.get(name, "") or "").strip():
            errors.append(f"{name} is required")

    if str(values.get("IS_PRODUCTION", "")).lower() not in {"1", "true", "yes"}:
        errors.append("IS_PRODUCTION must be true")
    for name in (
        "SUPABASE_URL",
        "SUPABASE_KEY",
        "REDIS_URL",
        "ANON_SESSION_HMAC_SECRET",
        "FORWARDED_ALLOW_IPS",
    ):
        required(name)

    forwarded = str(values.get("FORWARDED_ALLOW_IPS", "") or "").strip()
    if forwarded == "*":
        errors.append("FORWARDED_ALLOW_IPS must not be '*'")
    if str(values.get("ENABLE_TEST_AUTH", "")).lower() in {"1", "true", "yes"}:
        errors.append("ENABLE_TEST_AUTH must be false in production")

    provider = str(values.get("LLM_PROVIDER", "sarvam_cloud")).lower().strip()
    provider_key = {
        "sarvam_cloud": "SARVAM_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "nim": "NIM_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "krutrim": "KRUTRIM_API_KEY",
        "emergent": "EMERGENT_LLM_KEY",
    }.get(provider)
    if provider_key:
        required(provider_key)
    else:
        warnings.append(f"LLM_PROVIDER={provider!r} has no preflight key mapping")

    # Mirrors Settings.validate_production_restrictions (backend/app/config.py).
    # Settings treats any non-empty string as "set" (no strip). A bool field
    # takes its default only when the variable is absent; pydantic does not
    # strip, so " " or "maybe" stops the app at import and must fail here too.
    def is_set(name: str) -> bool:
        return bool(str(values.get(name, "") or ""))

    def flag(name: str, default: bool) -> bool:
        if name not in values:
            return default
        raw = str(values[name]).lower()
        if raw in {"1", "true", "yes", "on", "t", "y"}:
            return True
        if raw in {"0", "false", "no", "off", "f", "n"}:
            return False
        errors.append(f"{name} is not a valid boolean")
        return default

    # Read every flag once, up front: a short-circuited `and` would skip the
    # parse check for a flag whose value Settings still rejects.
    faculty_gate_disabled = flag("FACULTY_GATE_DISABLED", False)
    budget_guard = flag("OPENROUTER_BUDGET_GUARD_ENABLED", True)
    budget_fail_closed = flag("OPENROUTER_BUDGET_FAIL_CLOSED", True)
    allow_uncapped = flag("ALLOW_UNCAPPED_LLM_SPEND", False)

    if not is_set("BRAIN_KEK"):
        errors.append("BRAIN_KEK is required")
    if not is_set("FACULTY_ACCESS_CODE") and not faculty_gate_disabled:
        errors.append(
            "FACULTY_ACCESS_CODE is required (or FACULTY_GATE_DISABLED=true as a recorded decision)"
        )
    budget_guarded = budget_guard and budget_fail_closed
    if not allow_uncapped and not budget_guarded:
        errors.append(
            "OPENROUTER_BUDGET_GUARD_ENABLED and OPENROUTER_BUDGET_FAIL_CLOSED must both be true "
            "(or ALLOW_UNCAPPED_LLM_SPEND=true as a recorded decision)"
        )

    first_person_mode = str(values.get("FIRST_PERSON_MODE", "") or "").lower().strip()
    if first_person_mode:
        # 2026-10-20: allowed values live in app.config (single source of truth)
        # and are read from source so an incomplete environment cannot fail this
        # check with an unrelated pydantic ValidationError.
        modes = _read_first_person_modes()
        if modes is None:
            errors.append("cannot read FIRST_PERSON_MODES from app/config.py")
        elif first_person_mode not in modes:
            errors.append(f"FIRST_PERSON_MODE must be one of {modes}")

    redis_url = str(values.get("REDIS_URL", "") or "").lower()
    if "localhost" in redis_url or "127.0.0.1" in redis_url:
        warnings.append("REDIS_URL points at loopback; confirm this is intentional")
    return PreflightResult(tuple(errors), tuple(warnings))


def main() -> int:
    result = validate_environment()
    for warning in result.warnings:
        print(f"WARN: {warning}")
    if result.errors:
        for error in result.errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Production environment preflight passed (secrets not printed).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
