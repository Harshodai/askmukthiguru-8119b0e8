"""Regression guard: the semantic cache similarity floor must never drop below 0.92.

A false semantic-cache hit in this app serves one seeker's answer as doctrine in
response to a *different* seeker's question. Research consensus for factual/RAG
workloads is a floor of >= 0.92 (below 0.90 dissimilar queries start matching).

Three sources must all honor the floor:
  - ``app/config.py`` (Settings.semantic_cache_similarity) — the code default
  - ``docker-compose.yml`` (``SEMANTIC_CACHE_SIMILARITY:-<default>`` fallback) — the
    value any environment gets if it never sets the env var explicitly

This test covers both. See docs/plans/latency-at-scale-and-correctness-plan-2026-08-26.md,
acceptance criterion A2.1.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.config import settings

FLOOR = 0.92

_COMPOSE_PATH = Path(__file__).resolve().parents[1] / "docker-compose.yml"


def _compose_fallback_value() -> float:
    text = _COMPOSE_PATH.read_text()
    match = re.search(r"SEMANTIC_CACHE_SIMILARITY:-([0-9.]+)\}", text)
    assert match, "SEMANTIC_CACHE_SIMILARITY fallback not found in docker-compose.yml"
    return float(match.group(1))


def test_config_default_meets_floor():
    assert settings.semantic_cache_similarity >= FLOOR, (
        f"semantic_cache_similarity={settings.semantic_cache_similarity} is below the "
        f"{FLOOR} correctness floor — this is not a tuning knob, see A2.1"
    )


def test_compose_fallback_meets_floor():
    value = _compose_fallback_value()
    assert value >= FLOOR, (
        f"docker-compose.yml SEMANTIC_CACHE_SIMILARITY fallback={value} is below the "
        f"{FLOOR} correctness floor — any environment that doesn't set the env var "
        "explicitly would silently inherit an unsafe threshold"
    )


if __name__ == "__main__":
    import pytest as _pytest

    _pytest.main([__file__, "-v"])
