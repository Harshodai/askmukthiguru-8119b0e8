"""OKF (Open Knowledge Format) store — read, validate, and query markdown entries.

Implements Google Cloud's Open Knowledge Format v0.1 (June 2026), which formalizes
Karpathy's LLM-wiki pattern: a bundle is a directory of markdown files, each carrying
YAML frontmatter with exactly one required field, ``type``. ``index.md`` and ``log.md``
are reserved filenames and carry no frontmatter.
  spec: https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md

This bundle is a *doctrine* bundle: it holds only Sri Preethaji & Sri Krishnaji's
teachings. OKF lets a producer define its own types; ours are ``DOCTRINE_TYPES``.
Anything else — engineering runbooks, RAG notes, config lessons — must live outside
``memory/okf/`` (see ``docs/engineering-notes/``), because every entry here is
embedded and injected verbatim into answers by ``rag/nodes/retrieval.py:_okf_match``.

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

from services.okf_quality_filter import OKFQualityFilter

logger = logging.getLogger(__name__)

_base_path = Path(__file__).resolve().parent
while _base_path.name and _base_path.name != "backend":
    _base_path = _base_path.parent
_OKF_DIR = (_base_path.parent / "memory" / "okf") if _base_path.name else Path("/app/memory/okf")

# The one correct resolver. compiler.py and scripts/extract_okf_from_stores.py each
# hand-rolled their own and both broke inside the image (backend/ IS /app there, so
# `.parent` lands on `/`). Import these instead of deriving them again.
OKF_DIR = _OKF_DIR
STAGING_DIR = _OKF_DIR / "staging"

# OKF v0.1 reserved filenames — no frontmatter, not concept documents.
RESERVED_FILENAMES = frozenset({"index.md", "log.md"})

# The producer-defined type vocabulary for this bundle. OKF says consumers must
# tolerate unknown types "gracefully"; for a zero-hallucination doctrine layer,
# graceful means *excluded from the answer path*, not silently injected.
DOCTRINE_TYPES = frozenset({"teaching", "practice", "glossary", "qa", "reflection"})


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

    @property
    def teacher(self) -> str:
        return self.meta.get("teacher", "both")

    @property
    def description(self) -> str:
        """OKF-recommended one-sentence summary; derived from the body when absent.

        The compiler embeds ``title + description``. Embedding the bare title meant
        a seeker's question was matched against strings like "The Beautiful State".
        """
        explicit = str(self.meta.get("description", "")).strip()
        if explicit:
            return explicit
        for line in self.body.splitlines():
            line = line.strip()
            if not line or line.startswith(("#", ">", "-", "*", "|", "`")):
                continue
            sentence = re.split(r"(?<=[.!?])\s", line)[0].strip()
            return sentence[:300]
        return ""

    @property
    def embed_text(self) -> str:
        """What the compiler embeds for semantic match."""
        desc = self.description
        return f"{self.title}. {desc}" if desc else self.title


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
        # **/*.md recurses into sri-preethaji/, sri-krishnaji/, shared/.
        # Exclude staging/ (unreviewed LLM output) and _scripts/ (tooling).
        _excluded_parts = frozenset({"staging", "_scripts"})
        for p in sorted(self.dir.rglob("*.md")):
            if any(part in p.parts for part in _excluded_parts):
                continue
            if p.name in RESERVED_FILENAMES:
                continue  # OKF v0.1: index.md / log.md are not concept documents
            try:
                text = p.read_text(encoding="utf-8")
                meta, body = _parse_frontmatter(text)
                if "type" not in meta:
                    logger.warning("Skipping OKF entry without 'type': %s", p)
                    continue

                entry_type = str(meta.get("type", "")).strip().lower()
                if entry_type not in DOCTRINE_TYPES:
                    # Everything in this bundle is embedded and injected verbatim into
                    # answers. A runbook or engineering note reaching _okf_match would
                    # be cited to the seeker as a teaching of the gurus.
                    logger.warning(
                        "Skipping non-doctrine OKF entry (type=%r, allowed=%s): %s",
                        entry_type, sorted(DOCTRINE_TYPES), p,
                    )
                    continue

                ok, reason = OKFQualityFilter.validate_entry(
                    {
                        "type": entry_type,
                        "title": str(meta.get("title", "")),
                        "body": body,
                        "source": meta.get("source", ""),
                    }
                )
                if not ok:
                    logger.warning("Skipping malformed OKF entry (%s): %s", reason, p)
                    continue

                entries.append(OKFEntry(path=p, meta=meta, body=body))
            except Exception as e:
                logger.warning("Failed to read OKF entry %s: %s", p, e)
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
