"""OKF (Open Knowledge Format) store — read, validate, and query markdown entries.

Each OKF entry is a markdown file with YAML frontmatter. One required field:
  type: teaching | practice | glossary

The store reads from disk; the compiler (compiler.py) builds a compiled index.
"""

from __future__ import annotations

import glob
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

try:
    import frontmatter  # type: ignore
except ImportError:  # pragma: no cover
    frontmatter = None  # type: ignore

logger = logging.getLogger(__name__)

_OKF_DIR = Path(__file__).resolve().parents[3] / "memory" / "okf"


@dataclass(frozen=True)
class OKFEntry:
    path: Path
    meta: dict[str, Any]
    body: str

    @property
    def type(self) -> str:
        return self.meta.get("type", "unknown")

    @property
    def title(self) -> str:
        return self.meta.get("title", self.path.stem.replace("_", " ").title())

    @property
    def tags(self) -> list[str]:
        t = self.meta.get("tags", [])
        return t if isinstance(t, list) else [t] if t else []

    @property
    def source(self) -> str:
        return self.meta.get("source", "")


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Minimal YAML frontmatter parser (no external dep)."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            raw_yaml = parts[1].strip()
            body = parts[2].strip()
            import yaml
            try:
                meta = yaml.safe_load(raw_yaml) or {}
            except Exception:
                meta = {}
            return meta, body
    return {}, text


class OKFStore:
    """Read and validate OKF markdown entries from disk."""

    def __init__(self, directory: Optional[Path] = None) -> None:
        self.dir = directory or _OKF_DIR

    def list_entries(self) -> list[OKFEntry]:
        """Return all valid OKF entries in the directory."""
        entries: list[OKFEntry] = []
        if not self.dir.exists():
            logger.warning("OKF directory not found: %s", self.dir)
            return entries
        for p in sorted(self.dir.glob("*.md")):
            try:
                text = p.read_text(encoding="utf-8")
                meta, body = _parse_frontmatter(text)
                if "type" not in meta:
                    logger.warning("Skipping OKF entry without 'type': %s", p)
                    continue
                entries.append(OKFEntry(path=p, meta=meta, body=body))
            except Exception as e:
                logger.warning("Failed to read OKF entry %s: %e", p, e)
        return entries

    def by_type(self, type_name: str) -> list[OKFEntry]:
        return [e for e in self.list_entries() if e.type == type_name]

    def search(self, term: str, limit: int = 20) -> list[OKFEntry]:
        """Case-insensitive substring search across titles and bodies."""
        term_lower = term.lower()
        results: list[OKFEntry] = []
        for e in self.list_entries():
            if term_lower in e.title.lower() or term_lower in e.body.lower():
                results.append(e)
                if len(results) >= limit:
                    break
        return results


if __name__ == "__main__":  # ponytail: runnable self-check
    store = OKFStore()
    entries = store.list_entries()
    print(f"OKF entries: {len(entries)}")
    for e in entries:
        print(f"  {e.type}: {e.title}")
    assert len(entries) >= 1
    teaching = store.by_type("teaching")
    print(f"  teaching count: {len(teaching)}")
    results = store.search("beautiful")
    print(f"  search 'beautiful': {len(results)} results")
    print("okf_store OK")
