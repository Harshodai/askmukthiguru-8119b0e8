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

_DEFAULT = (
    {
        "id": "preethaji",
        "label": "Sri Preethaji",
        "aliases": [r"(?:sri\s+)?preeth(?:a|i)ji", "preetha"],
    },
    {"id": "krishnaji", "label": "Sri Krishnaji", "aliases": [r"(?:sri\s+)?krishnaji"]},
)
_CONFIG = Path(__file__).resolve().parents[1] / "config" / "gurus.yaml"


@dataclass(frozen=True)
class Guru:
    id: str
    label: str
    pattern: re.Pattern


@lru_cache(maxsize=1)
def get_gurus() -> tuple[Guru, ...]:
    raw: list[dict] = list(_DEFAULT)
    try:
        data = yaml.safe_load(_CONFIG.read_text(encoding="utf-8")) or {}
        raw = list(data.get("gurus") or raw)
    except (OSError, yaml.YAMLError):
        logger.warning("guru_registry: %s unreadable; using built-in defaults", _CONFIG)
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


def requested_gurus(query: str) -> list[str]:
    """Ids of every guru named in ``query`` (registry order). Empty = none named."""
    text = unicodedata.normalize("NFKC", query or "")
    return [g.id for g in get_gurus() if g.pattern.search(text)]


if __name__ == "__main__":
    assert requested_gurus("What does Sri Preethaji say?") == ["preethaji"]
    assert requested_gurus("Preethaji and Krishnaji on love") == ["preethaji", "krishnaji"]
    print("guru_registry ok", sorted(allowed_speaker_labels()))
