"""Config-driven registry of the gurus whose recordings may be served verbatim.

L-GURU-REGISTRY-1 (2026-10-08): speaker names were hardcoded in four places. The registry
(config/gurus.yaml) is now the one list: serve-time allowlist, ingest allowlist, and the
"which guru did the seeker ask for" detector all read it.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# No hardcoded teacher fallback: config/gurus.yaml is the single source of truth.
# If it cannot be loaded, teacher-specific attribution must fail closed.
_DEFAULT: tuple[dict, ...] = ()
_CONFIG = Path(__file__).resolve().parents[1] / "config" / "gurus.yaml"


@dataclass(frozen=True)
class Guru:
    id: str
    label: str
    pattern: re.Pattern


@lru_cache(maxsize=1)
def get_gurus() -> tuple[Guru, ...]:
    raw: list[dict] = []
    try:
        data = yaml.safe_load(_CONFIG.read_text(encoding="utf-8")) or {}
        entries = data.get("gurus") or []
        if not isinstance(entries, list):
            raise ValueError("gurus.yaml must contain a 'gurus' list")
        raw = [entry for entry in entries if isinstance(entry, dict) and entry.get("id") and entry.get("label")]
    except (OSError, yaml.YAMLError, ValueError) as exc:
        logger.error(
            "guru_registry unavailable; registered-teacher attribution is disabled (%s)",
            type(exc).__name__,
        )
        return ()
    gurus = []
    for g in raw:
        aliases = g.get("aliases") or []
        pat = "|".join(f"(?:{a})" for a in aliases) or re.escape(g["label"])
        gurus.append(
            Guru(str(g["id"]).lower(), str(g["label"]), re.compile(rf"\b(?:{pat})\b", re.I))
        )
    return tuple(gurus)


def allowed_speaker_labels() -> frozenset[str]:
    return frozenset(g.label for g in get_gurus())


def label_for(guru_id: str | None) -> str | None:
    gid = (guru_id or "").lower()
    return next((g.label for g in get_gurus() if g.id == gid), None)


def resolve_guru_id(value: str | None) -> str | None:
    """Resolve a configured teacher ID, label, or registered alias to its ID.

    Canonical IDs come from gurus.yaml. Unknown values deliberately return
    None so callers cannot treat an unregistered teacher filter as no filter.
    """
    candidate = unicodedata.normalize("NFKC", value or "").strip().lower()
    if not candidate or candidate in {"both", "all", "shared"}:
        return None
    for guru in get_gurus():
        slug_values = {
            guru.id.lower(),
            re.sub(r"[^a-z0-9]+", "-", guru.id.lower()).strip("-"),
            re.sub(r"[^a-z0-9]+", "-", guru.label.lower()).strip("-"),
        }
        if candidate in slug_values or candidate == guru.label.lower():
            return guru.id
    normalized_alias = re.sub(r"[-_]+", " ", candidate)
    requested = requested_gurus(normalized_alias)
    return requested[0] if len(requested) == 1 else None


def requested_gurus(query: str) -> list[str]:
    """Ids of every guru named in ``query`` (registry order). Empty = none named."""
    text = unicodedata.normalize("NFKC", query or "")
    return [g.id for g in get_gurus() if g.pattern.search(text)]


if __name__ == "__main__":
    assert requested_gurus("What does Sri Preethaji say?") == ["preethaji"]
    assert requested_gurus("Preethaji and Krishnaji on love") == ["preethaji", "krishnaji"]
    print("guru_registry ok", sorted(allowed_speaker_labels()))
