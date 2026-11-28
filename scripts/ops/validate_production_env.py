#!/usr/bin/env python3
"""Fail-closed, secret-redacting preflight for a production deployment."""

from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
import os
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


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


# 2026-11-19 never-again guards: a local .env copied onto Railway overwrote BRAIN_KEK
# (vault rows unreadable) and carried dev hosts. Values are never echoed.
_HOST_VARS = re.compile(r"(_URL|_URI|_HOST|_DSN)$")
# Loopback, Docker-for-Mac, and bare compose service names (no dot = not a real host).
_DEV_HOST_RE = re.compile(
    r"^(localhost|127\.\d+\.\d+\.\d+|0\.0\.0\.0|\[?::1\]?|host\.docker\.internal|[a-z0-9_-]+)$",
    re.IGNORECASE,
)
# Secrets that protect data already stored: changing one on a live service makes that
# data unreadable (BRAIN_KEK) or invalidates every session (JWT secrets). Rotate via the
# documented path (BRAIN_KEK_NEXT + scripts/ops/rotate_brain_kek.py), never by overwrite.
PROTECTED_SECRETS = (
    "BRAIN_KEK",
    "JWT_SECRET",
    "SUPABASE_JWT_SECRET",
    "SUPABASE_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "ANON_SESSION_HMAC_SECRET",
)


def _host_of(value: str) -> str:
    if "://" in value:
        try:
            return urlsplit(value).hostname or ""
        except ValueError:
            return ""
    rest = value.split("/", 1)[0].rsplit("@", 1)[-1]
    if rest.startswith("["):
        return rest.split("]", 1)[0] + "]"
    return rest.rsplit(":", 1)[0] if rest.count(":") == 1 else rest


def _jwt_issuer(token: str) -> str:
    parts = token.split(".")
    if len(parts) != 3:
        return ""
    try:
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
    except (ValueError, json.JSONDecodeError):
        return ""
    return str(payload.get("iss", "")) if isinstance(payload, dict) else ""


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _guard_errors(values: Mapping[str, str], current: Mapping[str, str] | None) -> list[str]:
    errors: list[str] = []
    for name, raw in values.items():
        value = str(raw or "").strip()
        if value and _HOST_VARS.search(name) and ("://" in value or name.endswith("_HOST")):
            if _DEV_HOST_RE.match(_host_of(value)):
                errors.append(f"{name} points at a development host (loopback/docker/service name)")
    for name in ("SUPABASE_KEY", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY"):
        if _jwt_issuer(str(values.get(name, "") or "")) == "supabase-demo":
            errors.append(f"{name} is the local Supabase demo key")
    for name in PROTECTED_SECRETS:
        old = str((current or {}).get(name, "") or "")
        new = str(values.get(name, "") or "")
        if old and new and _digest(old) != _digest(new):
            errors.append(
                f"{name} would overwrite a secret that protects stored data; rotate it, never overwrite"
            )
    return errors


def validate_environment(
    env: Mapping[str, str] | None = None, current: Mapping[str, str] | None = None
) -> PreflightResult:
    """``current``: the variables the target service holds now (None = not checked)."""
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
    budget_guard = flag("OPENROUTER_BUDGET_GUARD_ENABLED", True)
    budget_fail_closed = flag("OPENROUTER_BUDGET_FAIL_CLOSED", True)
    allow_uncapped = flag("ALLOW_UNCAPPED_LLM_SPEND", False)

    if not is_set("BRAIN_KEK"):
        errors.append("BRAIN_KEK is required")
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

    # Serving posture: v10-only needs both flags, the v8 rollback needs neither.
    # Exactly one on would silently serve the legacy clip store (A-32).
    harness = flag("FIRST_PERSON_CONTEXT_HARNESS_ENABLED", False)
    terminal = flag("FIRST_PERSON_CONTEXT_TERMINAL_ENABLED", False)
    if harness != terminal:
        errors.append(
            "FIRST_PERSON_CONTEXT_HARNESS_ENABLED and FIRST_PERSON_CONTEXT_TERMINAL_ENABLED "
            "must both be true (v10-only) or both be false (v8 rollback)"
        )
    # Mirrors services/first_person_serving_contract._check_declared_posture and the
    # slot resolver Settings.resolve_first_person_active_collection (A-32).
    posture = str(values.get("FIRST_PERSON_SERVING_POSTURE", "") or "")
    active = str(values.get("FIRST_PERSON_ACTIVE_COLLECTION", "first_person_v10") or "").strip()
    legacy_slot = str(values.get("FIRST_PERSON_COLLECTION", "") or "").strip() or (
        active if harness and terminal else "first_person_v8"
    )
    context_slot = str(values.get("FIRST_PERSON_CONTEXT_COLLECTION", "") or "").strip() or active
    if posture == "v10_only":
        if not (harness and terminal and legacy_slot == context_slot == "first_person_v10"):
            errors.append(
                "FIRST_PERSON_SERVING_POSTURE=v10_only needs FIRST_PERSON_CONTEXT_HARNESS_ENABLED "
                "and FIRST_PERSON_CONTEXT_TERMINAL_ENABLED true and both collection slots "
                "on first_person_v10"
            )
    elif posture == "v8_bridge":
        if harness or terminal:
            errors.append(
                "FIRST_PERSON_SERVING_POSTURE=v8_bridge needs FIRST_PERSON_CONTEXT_HARNESS_ENABLED "
                "and FIRST_PERSON_CONTEXT_TERMINAL_ENABLED false"
            )
    elif posture:
        errors.append("FIRST_PERSON_SERVING_POSTURE must be v10_only, v8_bridge or empty")
    else:
        lane = "v10-only context harness" if harness and terminal else "legacy clip store"
        warnings.append(f"FIRST_PERSON_SERVING_POSTURE is undeclared; the flags serve the {lane}")

    errors.extend(_guard_errors(values, current))
    # e94c3ff2: a QUANTIZED_ONLY image does not bake all-MiniLM-L6-v2, but the on-device
    # intent encoder defaults to on, so the first request tries an online download.
    quantized_only = flag("QUANTIZED_ONLY", False)
    on_device_intent = flag("ON_DEVICE_INTENT_ENCODER_ENABLED", True)
    if quantized_only and on_device_intent:
        warnings.append(
            "QUANTIZED_ONLY image without all-MiniLM-L6-v2 but ON_DEVICE_INTENT_ENCODER_ENABLED "
            "is on: the first request tries an online model download (owner decision: set it "
            "false, or bake the model)"
        )
    return PreflightResult(tuple(errors), tuple(warnings))


def _read_env_file(path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            val = val.strip()
            if len(val) >= 2 and val[0] in "'\"":
                quote = val[0]
                close_idx = -1
                i = 1
                while i < len(val):
                    if val[i] == "\\" and quote == '"' and i + 1 < len(val):
                        i += 2
                        continue
                    if val[i] == quote:
                        close_idx = i
                        break
                    i += 1
                if close_idx != -1:
                    val = val[1:close_idx]
                else:
                    val = val.split(" #", 1)[0].strip()
            else:
                val = val.split(" #", 1)[0].strip()  # an unquoted value drops an inline comment
            out[key.strip().removeprefix("export ").strip()] = val
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", help="proposed variables (default: this process env)")
    parser.add_argument(
        "--current-env-file", help="variables the target service holds now (overwrite guard)"
    )
    args = parser.parse_args(argv)
    proposed = _read_env_file(args.env_file) if args.env_file else None
    current = _read_env_file(args.current_env_file) if args.current_env_file else None
    result = validate_environment(proposed, current=current)
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
