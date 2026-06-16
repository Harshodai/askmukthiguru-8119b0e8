"""Crisis helpline registry — single source of truth.

The helplines used by the distress / safety paths previously lived in three
different files as hardcoded strings:

  - backend/guardrails/lightweight_handler.py
  - backend/services/serene_mind_engine.py
  - backend/rag/meditation.py

Changing a number (or adding a region) meant editing three files and praying.
This module consolidates them into ONE Python registry whose data comes
exclusively from `backend/config/router_routes.yaml`. Callers should consume
`get_helplines()` and `format_helplines_block()` instead of inlining strings.

Design intent:
  * **Data over code.** All helpline data lives in YAML. Adding a region
    means one YAML edit, no code change.
  * **Cached and immutable.** The registry is loaded once on first access,
    cached, and never mutated. Callers receive a read-only view.
  * **Region-aware formatting.** A region filter (e.g. "India") lets the
    distress handler localize the helpline block to the user's region while
    the global block remains the safe default.
  * **Defensive fallback.** If the YAML is unreadable or empty, the registry
    returns a small in-code fallback so the safety path never breaks.
    The fallback is loud-logged so an operator notices the misconfiguration.

Schema in YAML:
    crisis_helplines:
      - region: "India"
        name: "iCall"
        contact: "9152987821"
        url: "icall.in"        # optional
      - region: "United States"
        ...
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import yaml

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Helpline:
    region: str
    name: str
    contact: str
    url: str | None = None


_FALLBACK_HELPLINES: tuple[Helpline, ...] = (
    Helpline("India", "iCall", "9152987821"),
    Helpline("India", "Vandrevala Foundation", "1860-2662-345"),
    Helpline("United States", "988 Suicide & Crisis Lifeline", "988"),
    Helpline("International", "Crisis Text Line", "Text HOME to 741741"),
)


def _resolve_config_path() -> Path:
    override = getattr(settings, "router_config_path", None)
    if override:
        candidate = Path(override).expanduser().resolve()
        if candidate.is_file():
            return candidate
    # Default: bundled YAML beside the package.
    return Path(__file__).resolve().parents[1] / "config" / "router_routes.yaml"


@lru_cache(maxsize=1)
def get_helplines() -> tuple[Helpline, ...]:
    """Return the immutable tuple of helplines configured via YAML.

    The result is cached for the process lifetime. If you edit the YAML at
    runtime, call ``get_helplines.cache_clear()``.

    If the YAML is missing, malformed, or empty, the function falls back to a
    small in-code defaults tuple AND logs a loud WARNING so the operator
    knows the helpline data is degraded. The safety path must never depend on
    YAML being correct — but it should complain loudly when it is not.
    """
    path = _resolve_config_path()
    if not path.is_file():
        logger.warning(
            "crisis_helplines: %s not found; using in-code fallback list.", path
        )
        return _FALLBACK_HELPLINES

    try:
        with path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning(
            "crisis_helplines: failed to read %s (%s); using in-code fallback.",
            path,
            exc,
        )
        return _FALLBACK_HELPLINES

    entries = raw.get("crisis_helplines") or []
    if not entries:
        logger.warning(
            "crisis_helplines: %s has no `crisis_helplines:` entries; using fallback.",
            path,
        )
        return _FALLBACK_HELPLINES

    parsed: list[Helpline] = []
    for entry in entries:
        try:
            parsed.append(
                Helpline(
                    region=str(entry["region"]),
                    name=str(entry["name"]),
                    contact=str(entry["contact"]),
                    url=str(entry["url"]) if entry.get("url") else None,
                )
            )
        except (KeyError, TypeError) as exc:
            logger.warning(
                "crisis_helplines: skipping malformed entry %r: %s", entry, exc
            )
    if not parsed:
        return _FALLBACK_HELPLINES
    return tuple(parsed)


def _filter_by_region(helplines: Iterable[Helpline], region: str | None) -> tuple[Helpline, ...]:
    """Return helplines matching the requested region (case-insensitive).

    If `region` is None or no helplines match, returns the input unchanged so
    the caller still has a non-empty list.
    """
    if not region:
        return tuple(helplines)
    region_l = region.lower().strip()
    matched = tuple(h for h in helplines if h.region.lower() == region_l)
    return matched or tuple(helplines)


def format_helplines_block(
    *,
    region: str | None = None,
    style: str = "bullet",
    intro: str = "🆘 If you're in immediate crisis, please reach out:",
) -> str:
    """Render the helplines as a user-facing block.

    Args:
        region: Optional region filter ("India", "United States", ...).
                When None, all configured helplines are shown.
        style:  "bullet" (default) | "inline" | "compact_two_line"
                * bullet: full multi-line block. Use in distress responses.
                * inline: "India: iCall 9152987821 | US: 988"
                * compact_two_line: 2-line maximum, India + International.
        intro:  Heading line. Pass "" to omit.
    """
    helplines = _filter_by_region(get_helplines(), region)
    if not helplines:
        return ""

    if style == "inline":
        joined = " | ".join(f"{h.region}: {h.name} {h.contact}" for h in helplines)
        return f"{intro} {joined}".strip() if intro else joined

    if style == "compact_two_line":
        # Pick the first India helpline and the first international helpline.
        india = next((h for h in helplines if h.region.lower() == "india"), None)
        intl = next((h for h in helplines if h.region.lower() != "india"), None)
        lines = []
        if intro:
            lines.append(intro)
        if india:
            lines.append(f"• India: {india.name} {india.contact}")
        if intl:
            lines.append(f"• International: {intl.name} {intl.contact}")
        return "\n".join(lines)

    # bullet (default)
    lines = []
    if intro:
        lines.append(intro)
    for h in helplines:
        url_suffix = f" ({h.url})" if h.url else ""
        lines.append(f"- {h.region} | {h.name}: {h.contact}{url_suffix}")
    return "\n".join(lines)
