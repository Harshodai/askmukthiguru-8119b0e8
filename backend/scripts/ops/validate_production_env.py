#!/usr/bin/env python3
"""Fail-closed, secret-redacting preflight for a production deployment."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class PreflightResult:
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


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
