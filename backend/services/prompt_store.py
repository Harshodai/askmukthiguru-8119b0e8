"""
Unit 22 — Prompt Versioning

Tracks, versions, and serves prompt templates with full history.
Provides rollback capability and A/B testing integration.

Design:
  - SQLite-backed store (no additional infrastructure required)
  - ``PromptStore``: CRUD operations with semantic versioning
  - ``PromptVersion``: immutable versioned snapshot (content + metadata)
  - Active version per prompt name (easily overridable per A/B experiment)
  - Auto-imports existing prompts from rag/prompts.py on first run

Store location: ``backend/data/prompt_store.db`` (gitignored)

Schema:
  prompts(id, name, version, content, description, author, created_at, is_active)

Usage::

    from services.prompt_store import PromptStore, get_prompt_store

    store = get_prompt_store()
    # Get active version of a prompt
    prompt = store.get_active("GENERATION_PROMPT")
    # Save a new version
    store.save("GENERATION_PROMPT", new_content, description="Improved clarity")
    # Rollback
    store.rollback("GENERATION_PROMPT", version="1.0.0")
"""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DB_PATH = Path("data/prompt_store.db")
_SCHEMA = """
CREATE TABLE IF NOT EXISTS prompts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    version     TEXT    NOT NULL,
    content     TEXT    NOT NULL,
    description TEXT    DEFAULT '',
    author      TEXT    DEFAULT 'system',
    created_at  REAL    NOT NULL,
    is_active   INTEGER DEFAULT 0,  -- 1 = active version for this name
    UNIQUE(name, version)
);
CREATE INDEX IF NOT EXISTS idx_prompts_name ON prompts(name);
CREATE INDEX IF NOT EXISTS idx_prompts_active ON prompts(name, is_active);
"""


@dataclass
class PromptVersion:
    """An immutable versioned snapshot of a prompt template."""

    id: int
    name: str
    version: str
    content: str
    description: str
    author: str
    created_at: float
    is_active: bool

    @property
    def created_iso(self) -> str:
        """Return created_at as ISO-8601 string."""
        from datetime import datetime, timezone
        return datetime.fromtimestamp(self.created_at, tz=timezone.utc).isoformat()


class PromptStore:
    """SQLite-backed prompt versioning store.

    Thread-safe: SQLite WAL mode + connection-per-operation.
    """

    def __init__(self, db_path: Path = _DB_PATH) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    # ---- Version management ----

    def _next_version(self, name: str) -> str:
        """Generate the next semantic version for a prompt name."""
        existing = self.list_versions(name)
        if not existing:
            return "1.0.0"
        # Parse the latest version and increment patch
        latest = existing[0].version
        try:
            major, minor, patch = (int(x) for x in latest.split("."))
            return f"{major}.{minor}.{patch + 1}"
        except (ValueError, AttributeError):
            return f"1.0.{len(existing)}"

    def save(
        self,
        name: str,
        content: str,
        description: str = "",
        author: str = "system",
        activate: bool = True,
        version: Optional[str] = None,
    ) -> PromptVersion:
        """Save a new version of a prompt.

        Args:
            name: Prompt name (e.g., "GENERATION_PROMPT").
            content: Full prompt text.
            description: Human-readable change description.
            author: Who made the change (email or system).
            activate: If True, make this the active version immediately.
            version: Override the auto-generated version string.

        Returns:
            The newly created PromptVersion.
        """
        ver = version or self._next_version(name)
        now = time.time()

        with self._conn() as conn:
            if activate:
                # Deactivate all existing versions for this name
                conn.execute(
                    "UPDATE prompts SET is_active = 0 WHERE name = ?", (name,)
                )
            conn.execute(
                """
                INSERT INTO prompts (name, version, content, description, author, created_at, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name, version) DO UPDATE SET
                    content = excluded.content,
                    description = excluded.description,
                    is_active = excluded.is_active
                """,
                (name, ver, content, description, author, now, 1 if activate else 0),
            )
            row = conn.execute(
                "SELECT * FROM prompts WHERE name = ? AND version = ?", (name, ver)
            ).fetchone()

        pv = PromptVersion(
            id=row["id"],
            name=row["name"],
            version=row["version"],
            content=row["content"],
            description=row["description"],
            author=row["author"],
            created_at=row["created_at"],
            is_active=bool(row["is_active"]),
        )
        logger.info(
            f"PromptStore: saved '{name}' v{ver} "
            f"({'active' if activate else 'inactive'}, len={len(content)})"
        )
        return pv

    def get_active(self, name: str) -> Optional[PromptVersion]:
        """Return the currently active version of a prompt, or None."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM prompts WHERE name = ? AND is_active = 1", (name,)
            ).fetchone()
        if row is None:
            return None
        return PromptVersion(
            id=row["id"], name=row["name"], version=row["version"],
            content=row["content"], description=row["description"],
            author=row["author"], created_at=row["created_at"], is_active=True,
        )

    def get_version(self, name: str, version: str) -> Optional[PromptVersion]:
        """Return a specific version of a prompt."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM prompts WHERE name = ? AND version = ?", (name, version)
            ).fetchone()
        if row is None:
            return None
        return PromptVersion(
            id=row["id"], name=row["name"], version=row["version"],
            content=row["content"], description=row["description"],
            author=row["author"], created_at=row["created_at"],
            is_active=bool(row["is_active"]),
        )

    def list_versions(self, name: str) -> list[PromptVersion]:
        """Return all versions of a prompt, newest first."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM prompts WHERE name = ? ORDER BY created_at DESC", (name,)
            ).fetchall()
        return [
            PromptVersion(
                id=r["id"], name=r["name"], version=r["version"],
                content=r["content"], description=r["description"],
                author=r["author"], created_at=r["created_at"],
                is_active=bool(r["is_active"]),
            )
            for r in rows
        ]

    def list_prompt_names(self) -> list[str]:
        """Return all unique prompt names in the store."""
        with self._conn() as conn:
            rows = conn.execute("SELECT DISTINCT name FROM prompts ORDER BY name").fetchall()
        return [r["name"] for r in rows]

    def rollback(self, name: str, version: str) -> Optional[PromptVersion]:
        """Activate a specific older version (rollback).

        Returns the newly-activated PromptVersion, or None if not found.
        """
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM prompts WHERE name = ? AND version = ?", (name, version)
            ).fetchone()
            if row is None:
                logger.warning(f"PromptStore: rollback failed — '{name}' v{version} not found")
                return None
            conn.execute("UPDATE prompts SET is_active = 0 WHERE name = ?", (name,))
            conn.execute(
                "UPDATE prompts SET is_active = 1 WHERE name = ? AND version = ?",
                (name, version),
            )
        logger.info(f"PromptStore: rolled back '{name}' to v{version}")
        return self.get_active(name)

    def seed_from_module(self, module_name: str = "rag.prompts") -> int:
        """Seed the store with prompt constants from a Python module.

        Looks for all-caps string constants (e.g., GENERATION_PROMPT = "...").
        Skips prompts already in the store.

        Returns:
            Number of prompts seeded.
        """
        import importlib
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            logger.warning(f"PromptStore.seed_from_module: cannot import {module_name}: {exc}")
            return 0

        seeded = 0
        for attr_name in dir(module):
            if not attr_name.isupper():
                continue
            value = getattr(module, attr_name)
            if not isinstance(value, str) or len(value) < 20:
                continue
            existing = self.list_versions(attr_name)
            if existing:
                continue  # Already tracked
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


# -----------------------------------------------------------------------
# Singleton
# -----------------------------------------------------------------------
_store: Optional[PromptStore] = None


def get_prompt_store() -> PromptStore:
    """Return the global PromptStore singleton, auto-seeding from rag.prompts."""
    global _store
    if _store is None:
        _store = PromptStore()
        # Lazy seed on first use — non-blocking, errors are logged
        try:
            _store.seed_from_module("rag.prompts")
        except Exception as exc:
            logger.warning(f"PromptStore: auto-seed failed: {exc}")
    return _store
