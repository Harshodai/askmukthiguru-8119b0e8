"""Config-driven teacher and shared-corpus registry.

Runtime routing, speaker allowlists, and ingestion attribution must not maintain
parallel hardcoded teacher lists. backend/config/gurus.yaml is authoritative.
If it cannot be loaded, teacher-specific attribution fails closed.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)
_CONFIG = Path(__file__).resolve().parents[1] / "config" / "gurus.yaml"


@lru_cache(maxsize=1)
def _registry_document() -> dict[str, Any]:
    try:
        data = yaml.safe_load(_CONFIG.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict) or not isinstance(data.get("gurus"), list):
            raise ValueError("gurus.yaml must contain a 'gurus' list")
        return data
    except (OSError, yaml.YAMLError, ValueError) as exc:
        logger.error(
            "guru_registry unavailable; registered-teacher attribution is disabled (%s)",
            type(exc).__name__,
        )
        return {}


@dataclass(frozen=True)
class Guru:
    id: str
    label: str
    pattern: re.Pattern
    attribution_tag: str


@lru_cache(maxsize=1)
def get_gurus() -> tuple[Guru, ...]:
    data = _registry_document()
    raw = data.get("gurus") or []
    gurus: list[Guru] = []
    for entry in raw:
        if not isinstance(entry, dict) or not entry.get("id") or not entry.get("label"):
            logger.warning("Ignoring invalid teacher entry in gurus.yaml")
            continue
        aliases = entry.get("aliases") or []
        if not isinstance(aliases, list) or any(not isinstance(alias, str) for alias in aliases):
            logger.warning("Ignoring invalid aliases for a teacher entry in gurus.yaml")
            continue
        try:
            pat = "|".join(f"(?:{alias})" for alias in aliases) or re.escape(str(entry["label"]))
            gurus.append(
                Guru(
                    id=str(entry["id"]).strip().lower(),
                    label=str(entry["label"]).strip(),
                    pattern=re.compile(rf"\b(?:{pat})\b", re.I),
                    attribution_tag=str(entry.get("attribution_tag") or f"teacher:{entry['id']}"),
                )
            )
        except re.error:
            logger.exception("Ignoring invalid alias regex for a teacher entry in gurus.yaml")
    return tuple(gurus)


def allowed_speaker_labels() -> frozenset[str]:
    return frozenset(g.label for g in get_gurus())


def label_for(guru_id: str | None) -> str | None:
    gid = (guru_id or "").strip().lower()
    return next((g.label for g in get_gurus() if g.id == gid), None)


def attribution_tag_for(guru_id: str) -> str | None:
    gid = (guru_id or "").strip().lower()
    return next((g.attribution_tag for g in get_gurus() if g.id == gid), None)


def voice_teacher_labels() -> dict[str, str]:
    """Teacher IDs and shared-corpus IDs to display labels, derived from this registry."""
    teachers = {guru.id: guru.label for guru in get_gurus()}
    primary, shared_ids = shared_attribution()
    if shared_ids:
        shared_label = " and ".join(teachers[item] for item in shared_ids if item in teachers)
        if shared_label:
            teachers["_".join(shared_ids)] = shared_label
            if primary:
                teachers[primary] = shared_label
    for organization in _registry_document().get("organizations") or []:
        if not isinstance(organization, dict) or not organization.get("id"):
            continue
        org_id = str(organization["id"]).strip().lower()
        related = organization.get("attributed_teacher_ids") or []
        if isinstance(related, list):
            names = [teachers[str(item).lower()] for item in related if str(item).lower() in teachers]
        else:
            names = []
        teachers[org_id] = " and ".join(dict.fromkeys(names)) or str(
            organization.get("label") or org_id
        )
    return teachers


def neutral_voice_id() -> str:
    """Configured shared teacher scope used when no single speaker is established."""
    primary, shared_ids = shared_attribution()
    if primary:
        return primary
    return "_".join(shared_ids) if shared_ids else "shared"


def requested_gurus(query: str) -> list[str]:
    """Ids of configured teachers named in text, in registry order."""
    text = unicodedata.normalize("NFKC", query or "")
    return [g.id for g in get_gurus() if g.pattern.search(text)]


def resolve_guru_id(value: str | None) -> str | None:
    """Resolve a configured teacher ID, label, or registered alias to its ID.

    Canonical IDs come from gurus.yaml. Unknown values deliberately return
    None so callers cannot treat an unregistered teacher filter as no filter.
    """
    candidate = unicodedata.normalize("NFKC", value or "").strip().lower()
    if not candidate:
        return None
    for guru in get_gurus():
        slug_values = {
            guru.id.lower(),
            re.sub(r"[^a-z0-9]+", "-", guru.id.lower()).strip("-"),
            re.sub(r"[^a-z0-9]+", "-", guru.label.lower()).strip("-"),
            guru.label.lower(),
        }
        if candidate in slug_values:
            return guru.id
    normalized_alias = re.sub(r"[-_]+", " ", candidate)
    requested = requested_gurus(normalized_alias)
    if len(requested) == 1:
        return requested[0]
    for organization in _registry_document().get("organizations") or []:
        if not isinstance(organization, dict):
            continue
        org_id = str(organization.get("id") or "").strip().lower()
        org_label = str(organization.get("label") or "").strip().lower()
        org_aliases = organization.get("aliases") or []
        if candidate == org_id or candidate == org_label:
            return org_id or None
        if isinstance(org_aliases, list):
            try:
                if any(re.search(str(alias), normalized_alias, re.I) for alias in org_aliases):
                    return org_id or None
            except re.error:
                continue
    return None


def shared_attribution() -> tuple[str | None, list[str]]:
    """Configured primary ID and allowed related IDs for the shared corpus."""
    data = _registry_document()
    known = {guru.id for guru in get_gurus()}
    ids = data.get("shared_attribution_ids") or []
    if not isinstance(ids, list) or not ids or any(str(item).lower() not in known for item in ids):
        return None, []
    primary = str(data.get("shared_primary_teacher_id") or "").strip().lower()
    if not primary:
        return None, [str(item).lower() for item in ids]
    return primary, [str(item).lower() for item in ids]


def match_organization(context: str) -> dict[str, Any] | None:
    """Resolve a registered organization/channel alias in source metadata only."""
    for organization in _registry_document().get("organizations") or []:
        if not isinstance(organization, dict) or not organization.get("id"):
            continue
        aliases = organization.get("aliases") or []
        if not isinstance(aliases, list):
            continue
        try:
            pattern = re.compile("|".join(f"(?:{alias})" for alias in aliases), re.I)
        except re.error:
            logger.warning("Ignoring invalid organization alias pattern")
            continue
        if pattern.search(unicodedata.normalize("NFKC", context or "")):
            return organization
    return None


def is_shared_guru_scope(value: str | None) -> bool:
    candidate = (value or "").strip().lower()
    if candidate in {"both", "all", "shared"}:
        return True
    primary, _ = shared_attribution()
    if primary and candidate == primary:
        return True
    return False


if __name__ == "__main__":
    assert requested_gurus("What does Sri Preethaji say?") == ["preethaji"]
    assert requested_gurus("Preethaji and Krishnaji on love") == ["preethaji", "krishnaji"]
    assert resolve_guru_id("sri-preethaji") == "preethaji"
    print("guru_registry ok", sorted(allowed_speaker_labels()))
