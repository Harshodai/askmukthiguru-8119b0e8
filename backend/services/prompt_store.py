"""
Unit 22 — Prompt Versioning

Tracks, versions, and serves prompt templates with full history.
Provides rollback capability and A/B testing integration.

Design:
  - Supabase-backed store (single operational DB — no more SQLite data loss)
  - PromptStore: CRUD operations with semantic versioning
  - PromptVersion: immutable versioned snapshot (content + metadata)
  - Active version per prompt name (easily overridable per A/B experiment)
  - Auto-imports existing prompts from rag/prompts.py on first run

Store: Supabase public.prompt_versions table

Schema:
  prompt_versions(id, name, version, content, description, author, active, created_at)

Usage:
    from services.prompt_store import PromptStore, get_prompt_store

    store = get_prompt_store()
    prompt = store.get_active("GENERATION_PROMPT")
    store.save("GENERATION_PROMPT", new_content, description="Improved clarity")
    store.rollback("GENERATION_PROMPT", version="1.0.0")
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

UTC = timezone.utc


# Default teacher personality fragments (Phase E5 stub).
# Overridable via settings.teacher_personalities (JSON string).
DEFAULT_TEACHER_PERSONALITIES: dict[str, str] = {
    "sadhguru": "Speak with the direct, earthy, and pragmatic tone of a yogi.",
    "preethaji": "Speak with warmth, stillness, and a focus on the Beautiful State.",
    "krishnaji": "Speak with clarity, pointing to ego observation and presence.",
    "amma_bhagavan": "Speak with the inclusive voice of the Oneness Movement.",
    "iskcon": "Speak with devotional warmth rooted in Bhakti Yoga and Lord Krishna.",
}


def get_teacher_personality(teacher_id: Optional[str]) -> str:
    """Return the personality prompt fragment for ``teacher_id``.

    Config-driven: ``settings.teacher_personalities`` (JSON string) overrides
    the built-in defaults. Returns "" when no teacher is specified or no
    personality is configured.
    """
    if not teacher_id:
        return ""
    personalities = dict(DEFAULT_TEACHER_PERSONALITIES)
    raw = getattr(settings, "teacher_personalities", "") or ""
    if raw:
        try:
            personalities.update(json.loads(raw))
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning(f"get_teacher_personality: bad teacher_personalities JSON: {exc}")
    return personalities.get(teacher_id, "")


def build_teacher_prompt(teacher_id: Optional[str], base_prompt: str) -> str:
    """Prepend a teacher-specific voice instruction to ``base_prompt``.

    If no personality is configured for ``teacher_id``, ``base_prompt`` is
    returned unchanged. This is the stub used by generation nodes to support
    multi-teacher voice without changing prompt schemas.
    """
    personality = get_teacher_personality(teacher_id)
    if not personality:
        return base_prompt
    return f"[Teacher voice] {personality}\n\n{base_prompt}"


def _get_client():
    from app.telemetry_db import _get_client as _supa_client
    return _supa_client()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_pv(row: dict) -> PromptVersion:
    return PromptVersion(
        id=row["id"],
        name=row["name"],
        version=row["version"],
        content=row.get("content", row.get("body", "")),
        description=row.get("description", ""),
        author=row.get("author", "system"),
        created_at=row.get("created_at", _now_iso()),
        is_active=bool(row.get("active", False)),
    )


@dataclass
class PromptVersion:
    """An immutable versioned snapshot of a prompt template."""

    id: str
    name: str
    version: str
    content: str
    description: str
    author: str
    created_at: str
    is_active: bool

    @property
    def created_iso(self) -> str:
        return self.created_at if isinstance(self.created_at, str) else str(self.created_at)


def _next_version(existing: list[PromptVersion]) -> str:
    if not existing:
        return "1.0.0"
    latest = existing[0].version
    try:
        major, minor, patch = (int(x) for x in latest.split("."))
        return f"{major}.{minor}.{patch + 1}"
    except (ValueError, AttributeError):
        return f"1.0.{len(existing)}"


class PromptStore:
    """Supabase-backed prompt versioning store."""

    # ---- Version management ----

    def save(
        self,
        name: str,
        content: str,
        description: str = "",
        author: str = "system",
        activate: bool = True,
        version: Optional[str] = None,
    ) -> PromptVersion:
        ver = version or _next_version(self.list_versions(name))
        client = _get_client()
        if not client:
            raise RuntimeError("Supabase client unavailable for PromptStore")

        if activate:
            try:
                client.table("prompt_versions").update({"active": False}).eq("name", name).execute()
            except Exception as e:
                logger.warning(f"PromptStore: deactivate failed: {e}")

        payload = {
            "name": name,
            "version": ver,
            "content": content,
            "description": description,
            "author": author,
            "active": activate,
        }
        try:
            res = client.table("prompt_versions").insert(payload).execute()
            data = res.data
            if not data:
                raise RuntimeError("Insert returned empty data")
            row = data[0]
        except Exception as e:
            logger.error(f"PromptStore: save failed for '{name}' v{ver}: {e}")
            raise

        pv = _row_to_pv(row)
        logger.info(
            f"PromptStore: saved '{name}' v{ver} "
            f"({'active' if activate else 'inactive'}, len={len(content)})"
        )
        return pv

    def get_active(self, name: str) -> Optional[PromptVersion]:
        client = _get_client()
        if not client:
            return None
        try:
            res = (
                client.table("prompt_versions")
                .select("*")
                .eq("name", name)
                .eq("active", True)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if not res.data:
                return None
            return _row_to_pv(res.data[0])
        except Exception as e:
            logger.error(f"PromptStore: get_active failed for '{name}': {e}")
            return None

    def get_version(self, name: str, version: str) -> Optional[PromptVersion]:
        client = _get_client()
        if not client:
            return None
        try:
            res = (
                client.table("prompt_versions")
                .select("*")
                .eq("name", name)
                .eq("version", version)
                .limit(1)
                .execute()
            )
            if not res.data:
                return None
            return _row_to_pv(res.data[0])
        except Exception as e:
            logger.error(f"PromptStore: get_version failed for '{name}' v{version}: {e}")
            return None

    def list_versions(self, name: str) -> list[PromptVersion]:
        client = _get_client()
        if not client:
            return []
        try:
            res = (
                client.table("prompt_versions")
                .select("*")
                .eq("name", name)
                .order("created_at", desc=True)
                .execute()
            )
            return [_row_to_pv(r) for r in (res.data or [])]
        except Exception as e:
            logger.error(f"PromptStore: list_versions failed for '{name}': {e}")
            return []

    def list_prompt_names(self) -> list[str]:
        client = _get_client()
        if not client:
            return []
        try:
            res = (
                client.table("prompt_versions")
                .select("name")
                .execute()
            )
            seen: set[str] = set()
            names: list[str] = []
            for r in (res.data or []):
                n = r.get("name")
                if n and n not in seen:
                    seen.add(n)
                    names.append(n)
            return sorted(names)
        except Exception as e:
            logger.error(f"PromptStore: list_prompt_names failed: {e}")
            return []

    def rollback(self, name: str, version: str) -> Optional[PromptVersion]:
        client = _get_client()
        if not client:
            return None
        try:
            res = (
                client.table("prompt_versions")
                .select("*")
                .eq("name", name)
                .eq("version", version)
                .limit(1)
                .execute()
            )
            if not res.data:
                logger.warning(f"PromptStore: rollback failed — '{name}' v{version} not found")
                return None

            client.table("prompt_versions").update({"active": False}).eq("name", name).execute()
            client.table("prompt_versions").update({"active": True}).eq("name", name).eq("version", version).execute()

            logger.info(f"PromptStore: rolled back '{name}' to v{version}")
            return self.get_active(name)
        except Exception as e:
            logger.error(f"PromptStore: rollback failed: {e}")
            return None

    def seed_from_module(self, module_name: str = "rag.prompts") -> int:
        import importlib
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            logger.warning(f"PromptStore.seed_from_module: cannot import {module_name}: {exc}")
            return 0

        seeded = 0
        existing_names = set(self.list_prompt_names())
        for attr_name in dir(module):
            if not attr_name.isupper():
                continue
            value = getattr(module, attr_name)
            if not isinstance(value, str) or len(value) < 20:
                continue
            if attr_name in existing_names:
                continue
            self.save(
                name=attr_name,
                content=value,
                description=f"Auto-seeded from {module_name}",
                author="system",
                activate=True,
            )
            seeded += 1

        logger.info(f"PromptStore: seeded {seeded} prompts from {module_name}")
        return seeded


# Singleton
_store: Optional[PromptStore] = None


def get_prompt_store() -> PromptStore:
    global _store
    if _store is None:
        _store = PromptStore()
        try:
            _store.seed_from_module("rag.prompts")
        except Exception as exc:
            logger.warning(f"PromptStore: auto-seed failed: {exc}")
    return _store


if __name__ == "__main__":
    # Self-check: teacher personality wiring.
    assert get_teacher_personality(None) == ""
    assert get_teacher_personality("unknown_teacher") == ""
    sadhguru = get_teacher_personality("sadhguru")
    assert sadhguru and "yogi" in sadhguru.lower()
    out = build_teacher_prompt("sadhguru", "Answer the question.")
    assert out.startswith("[Teacher voice]") and "Answer the question." in out
    assert build_teacher_prompt(None, "x") == "x"
    print("ok")
