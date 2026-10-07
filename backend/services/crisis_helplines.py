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
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Helpline:
    region: str
    name: str
    contact: str
    url: str | None = None
    hours: str | None = None
    languages: list[str] | None = None
    source_url: str | None = None
    last_verified: str | None = None
    last_checked_public_listing: str | None = None
    last_verified_by_call: str | None = None


_FALLBACK_HELPLINES: tuple[Helpline, ...] = (
    Helpline("India", "National Emergency Services", "112"),
    Helpline("India", "Tele-MANAS", "14416 / 1800-891-4416"),
    Helpline("India", "KIRAN", "1800-599-0019"),
    Helpline("India", "iCall", "9152987821"),
    Helpline("India", "Vandrevala Foundation", "+91 9999 666 555"),
    Helpline("United States", "988 Suicide & Crisis Lifeline", "988"),
    Helpline("International", "Crisis Text Line", "Text HOME to 741741"),
)

_FALLBACK_DOMESTIC_VIOLENCE_HELPLINES: tuple[Helpline, ...] = (
    Helpline("India", "National Emergency Helpline", "112"),
    Helpline("India", "Women Helpline (All India)", "181 / 1091"),
    Helpline(
        "United States",
        "National Domestic Violence Hotline",
        "1-800-799-SAFE (7233) or Text START to 88788",
    ),
    Helpline("United Kingdom", "National Domestic Abuse Helpline", "0808 2000 247"),
)


def _parse_helpline_entry(entry: dict) -> Helpline:
    """Parse one YAML helpline entry. Raises KeyError/TypeError on malformed input."""
    languages = entry.get("languages")
    last_verified_by_call = (
        str(entry["last_verified_by_call"])
        if entry.get("last_verified_by_call") is not None
        else None
    )
    last_checked_public_listing = (
        str(entry["last_checked_public_listing"])
        if entry.get("last_checked_public_listing") is not None
        else None
    )
    legacy_last_verified = (
        str(entry["last_verified"]) if entry.get("last_verified") is not None else None
    )
    effective_last_verified = last_verified_by_call or legacy_last_verified

    return Helpline(
        region=str(entry["region"]),
        name=str(entry["name"]),
        contact=str(entry["contact"]),
        url=str(entry["url"]) if entry.get("url") else None,
        hours=str(entry["hours"]) if entry.get("hours") else None,
        languages=[str(lang) for lang in languages] if languages else None,
        source_url=str(entry["source_url"]) if entry.get("source_url") else None,
        last_verified=effective_last_verified,
        last_checked_public_listing=last_checked_public_listing,
        last_verified_by_call=last_verified_by_call,
    )


def _resolve_config_path() -> Path:
    override = getattr(settings, "helplines_config_path", None)
    if override:
        candidate = Path(override).expanduser().resolve()
        if candidate.is_file():
            return candidate
    # Default: repo-root config/helplines.yaml (single source of truth for
    # crisis/DV helplines — see PLAN.md Phase A2). Moved here 2026-09-21 from
    # backend/config/router_routes.yaml; that file no longer carries helpline
    # data. See lessons.md for the migration note.
    return Path(__file__).resolve().parents[2] / "config" / "helplines.yaml"


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
        logger.warning("crisis_helplines: %s not found; using in-code fallback list.", path)
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

    if not isinstance(raw, dict):
        logger.warning(
            "crisis_helplines: %s did not parse to a mapping (got %s); using in-code fallback.",
            path,
            type(raw).__name__,
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
            parsed.append(_parse_helpline_entry(entry))
        except (KeyError, TypeError) as exc:
            logger.warning("crisis_helplines: skipping malformed entry %r: %s", entry, exc)
    if not parsed:
        return _FALLBACK_HELPLINES
    # Warn on ANY unverified entry, not only when all are: one verified call must not
    # silence the warning for the rest.
    unverified = [h.name for h in parsed if not h.last_verified_by_call]
    if unverified:
        logger.warning(
            "crisis_helplines: %d of %d entries in %s are unverified by call (%s). "
            "Do not treat these numbers as launch-ready.",
            len(unverified),
            len(parsed),
            path,
            ", ".join(unverified),
        )
    return tuple(parsed)


@lru_cache(maxsize=1)
def get_domestic_violence_helplines() -> tuple[Helpline, ...]:
    """Return the immutable tuple of domestic violence helplines configured via YAML."""
    path = _resolve_config_path()
    if not path.is_file():
        return _FALLBACK_DOMESTIC_VIOLENCE_HELPLINES

    try:
        with path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return _FALLBACK_DOMESTIC_VIOLENCE_HELPLINES

    if not isinstance(raw, dict):
        return _FALLBACK_DOMESTIC_VIOLENCE_HELPLINES

    entries = raw.get("domestic_violence_helplines") or []
    if not entries:
        return _FALLBACK_DOMESTIC_VIOLENCE_HELPLINES

    parsed: list[Helpline] = []
    for entry in entries:
        try:
            parsed.append(_parse_helpline_entry(entry))
        except (KeyError, TypeError):
            continue
    return tuple(parsed) or _FALLBACK_DOMESTIC_VIOLENCE_HELPLINES


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
            # Never mislabel a single-country number (e.g. a US-only "988")
            # as "International" — use its real region unless the entry is
            # actually region-agnostic.
            intl_label = "International" if intl.region.lower() == "international" else intl.region
            lines.append(f"• {intl_label}: {intl.name} {intl.contact}")
        return "\n".join(lines)

    # bullet (default)
    lines = []
    if intro:
        lines.append(intro)
    for h in helplines:
        url_suffix = f" ({h.url})" if h.url else ""
        lines.append(f"- {h.region} | {h.name}: {h.contact}{url_suffix}")
    return "\n".join(lines)


def format_support_line() -> str:
    """One short, deterministic support line, India first (2026-10-05).

    Appended to every answer that ends in the DISTRESS intent, so a seeker who
    is struggling but below the crisis pre-emption tier still sees a human
    number. Numbers come from helplines.yaml (Tele-MANAS, then 988 and
    Samaritans when configured); nothing is hard-coded here.
    """
    helplines = get_helplines()

    def _pick(region: str, name_part: str) -> Helpline | None:
        return next(
            (
                h
                for h in helplines
                if h.region.lower() == region and name_part.lower() in h.name.lower()
            ),
            None,
        )

    picks = [
        _pick("india", "tele-manas") or _pick("india", "kiran"),
        _pick("united states", "988"),
        _pick("united kingdom", "samaritans"),
    ]
    parts = [f"{h.region} {h.name.split(' (')[0]} {h.contact}" for h in picks if h]
    emergency = _pick("india", "emergency")
    tail = (
        f" In an emergency, call {emergency.contact} (India) or your local number."
        if emergency
        else ""
    )
    if not parts:
        return ""
    return (
        "If this feels heavy, you don't have to carry it alone. You can talk to someone now: "
        + " · ".join(parts)
        + "."
        + tail
    )


def ensure_support_line(answer: str) -> str:
    """``answer`` with the support line appended unless a helpline block is
    already there (the crisis pre-emption copy carries the full list)."""
    text = answer or ""
    line = format_support_line()
    if not line or line in text or "Tele-MANAS" in text or "14416" in text:
        return text
    return f"{text.rstrip()}\n\n{line}" if text.strip() else line


def format_domestic_violence_helplines_block(
    *,
    region: str | None = None,
    intro: str = "🛡️ Domestic Violence & Emergency Support Helplines:",
) -> str:
    """Render domestic violence helplines as a user-facing block."""
    helplines = _filter_by_region(get_domestic_violence_helplines(), region)
    if not helplines:
        return ""
    lines = []
    if intro:
        lines.append(intro)
    for h in helplines:
        url_suffix = f" ({h.url})" if h.url else ""
        lines.append(f"- {h.region} | {h.name}: {h.contact}{url_suffix}")
    return "\n".join(lines)
