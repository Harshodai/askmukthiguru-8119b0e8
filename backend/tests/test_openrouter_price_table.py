"""NEW-AI-4: every allowed OpenRouter model has a fallback price, or is listed.

`_OPENROUTER_FALLBACK_RATES_PER_MILLION` is used only when the provider reports no
`usage.cost`. A model without an entry is costed at 0 by the fallback, which
under-reports spend (SYS-014 is the opposite failure: the flat reservation
over-counts). This test finds models that are allowed by the repo's own settings,
presets and compose files and have no price.

Rules:
- `KNOWN_MISSING_PRICE` may only shrink. A model that gains a price must be
  removed from the set (the test fails if it is still listed), and a new model
  without a price fails the test.
- Prices are never invented here. Add a price from OpenRouter's model page, with
  the date you read it, in `services/openrouter_service.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.config import Settings
from services.openrouter_service import _OPENROUTER_FALLBACK_RATES_PER_MILLION

BACKEND = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND.parent

# Allowed by repo configuration, no price in the fallback table. Shrink only.
# D-16 (2026-11-07): anthropic/claude-haiku-5.5 gained a dated price and left the set.
KNOWN_MISSING_PRICE: frozenset[str] = frozenset()


def _compose_models() -> set[str]:
    found: set[str] = set()
    for path in (
        BACKEND / "docker-compose.yml",
        BACKEND / "docker-compose.graded.yml",
        BACKEND / "docker-compose.dev.yml",
        REPO_ROOT / "docker-compose.prod.yml",
    ):
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            if line.lstrip().startswith("#"):
                continue
            m = re.search(
                r"(?:FIRST_PERSON_RELEVANCE_MODEL|OPENROUTER_EXTRA_ALLOWED_MODELS)"
                r"\s*[:=]\s*[\"']?([A-Za-z0-9_.\-/,]+)",
                line,
            )
            if m and not m.group(1).startswith("$"):
                found.update(x for x in m.group(1).split(",") if "/" in x)
    return found


def _allowed_models() -> set[str]:
    defaults = {
        Settings.model_fields[name].default
        for name in (
            "openrouter_generation_model",
            "openrouter_generation_model_fallback",
            "openrouter_fast_model",
            "openrouter_classify_model",
        )
    }
    presets = {
        model for preset in Settings.OPENROUTER_PRESETS.values() for model in preset.values()
    }
    return {m for m in defaults | presets | _compose_models() if m}


def test_every_allowed_model_has_a_price_or_is_listed():
    missing = {m for m in _allowed_models() if m not in _OPENROUTER_FALLBACK_RATES_PER_MILLION}
    print("OpenRouter models without a fallback price:", sorted(missing))
    unexpected = missing - KNOWN_MISSING_PRICE
    assert not unexpected, (
        f"No fallback price for {sorted(unexpected)}. Add a dated price from OpenRouter's "
        "model page to services/openrouter_service.py. Do not invent one."
    )


def test_known_missing_set_only_shrinks():
    missing = {m for m in _allowed_models() if m not in _OPENROUTER_FALLBACK_RATES_PER_MILLION}
    stale = KNOWN_MISSING_PRICE - missing
    assert not stale, (
        f"{sorted(stale)} now has a price or is no longer allowed: remove it from "
        "KNOWN_MISSING_PRICE so the set shrinks."
    )


def test_prices_are_positive_pairs():
    for model, (inp, out) in _OPENROUTER_FALLBACK_RATES_PER_MILLION.items():
        assert inp > 0 and out > 0, model
