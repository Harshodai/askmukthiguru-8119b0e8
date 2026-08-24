"""Doctrine exact-match cache for high-frequency spiritual queries.

Loads a curated question -> {answer, citations} map (JSON file or the
``doctrine_faqs`` Supabase table) and serves fuzzy/exact matches without
running the full RAG pipeline.

Every entry MUST carry non-empty structured ``citations`` — an entry without
them is skipped at load time rather than served. Before 2026-08-24 this cache
had an embedded ``DEFAULT_DOCTRINE`` fallback of hand-written answers with an
inline "[Source: X]" text label and no structured citation, and
DoctrineCacheStage returned those with ``citations=[]``: a config-drift
bypass around retrieval and verification (audit finding OH-P0-01). The
embedded fallback is gone; an unconfigured cache is simply empty (harmless
no-op), and lookup() itself refuses to return an entry with no citations, so
the stage can no longer short-circuit with an uncited answer regardless of
how the loader is wired up.
"""

from __future__ import annotations

import json
import logging
import os
import string
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DoctrineAnswer:
    """A cache hit: the canned text plus the structured citations backing it."""

    answer: str
    citations: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Levenshtein distance (iterative, O(n*m) but fast for short strings)
# ---------------------------------------------------------------------------
def _levenshtein(a: str, b: str) -> int:
    """Return the Levenshtein distance between two strings."""
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)

    previous_row = range(len(b) + 1)
    for i, c1 in enumerate(a):
        current_row = [i + 1]
        for j, c2 in enumerate(b):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------
def _normalize(text: str) -> str:
    """Lower-case, strip punctuation, collapse whitespace."""
    text = text.lower().strip()
    text = text.translate(str.maketrans("", "", string.punctuation))
    return " ".join(text.split())


# Minimum similarity threshold for fuzzy match (Levenshtein ratio)
_FUZZY_THRESHOLD = 0.85


def _coerce_entry(question: object, raw: object) -> tuple[str, DoctrineAnswer] | None:
    """Validate one loaded row/item; return None (and log) if it lacks citations."""
    if not isinstance(question, str) or not question.strip():
        return None
    if isinstance(raw, str):
        # Legacy flat-string format predates the citation requirement — it is
        # inherently uncitable, so it is skipped rather than served.
        logger.warning(
            "DoctrineCache: skipping %r — legacy string entry has no structured citations", question
        )
        return None
    if not isinstance(raw, dict):
        return None
    answer = raw.get("answer")
    citations = raw.get("citations")
    if not isinstance(answer, str) or not answer.strip():
        return None
    if not isinstance(citations, list) or not citations:
        logger.warning("DoctrineCache: skipping %r — no citations", question)
        return None
    return question, DoctrineAnswer(answer=answer, citations=citations)


class DoctrineCache:
    """Exact + fuzzy match cache for common doctrine queries.

    Loads a JSON file if provided, otherwise the ``doctrine_faqs`` Supabase
    table. Entries without non-empty structured ``citations`` are dropped at
    load time — there is no embedded fallback dataset, so an unconfigured
    cache is simply empty rather than serving fabricated answers.
    """

    def __init__(self, doctrine_file: str | None = None, supabase_client=None) -> None:
        self._map: dict[str, DoctrineAnswer] = {}
        self._raw: dict[str, DoctrineAnswer] = {}
        self._supabase = supabase_client

        # 1. Try explicit file
        if doctrine_file and os.path.exists(doctrine_file):
            self._load_json(doctrine_file)

        # 2. Try dynamic loading from Supabase
        if not self._raw and self._supabase is not None:
            self._load_from_supabase()

        # 3. Try default path relative to backend root
        if not self._raw:
            default_path = Path(__file__).resolve().parent.parent / "data" / "doctrine_faqs.json"
            if default_path.exists():
                self._load_json(str(default_path))

    def _load_json(self, path: str) -> None:
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                items = data.items()
            elif isinstance(data, list):
                items = (
                    (item.get("question"), item)
                    for item in data
                    if isinstance(item, dict) and "question" in item
                )
            else:
                raise ValueError("Expected dict or list")
            self._raw = dict(filter(None, (_coerce_entry(q, a) for q, a in items)))
            self._build_index()
            logger.info("Loaded doctrine cache from %s (%d usable entries)", path, len(self._raw))
        except Exception as e:
            logger.warning("Failed to load doctrine cache from %s: %s", path, e)
            self._raw = {}

    def _load_from_supabase(self) -> None:
        """Load doctrine FAQs from Supabase table ``doctrine_faqs``."""
        try:
            # supabase client is synchronous; wrap in to_thread if we ever need async,
            # but init runs in sync context during service construction.
            res = (
                self._supabase.table("doctrine_faqs")
                .select("question,answer,citations")
                .eq("is_active", True)
                .execute()
            )
            rows = getattr(res, "data", []) or []
            self._raw = dict(
                filter(
                    None,
                    (
                        _coerce_entry(row.get("question"), {k: row.get(k) for k in ("answer", "citations")})
                        for row in rows
                    ),
                )
            )
            self._build_index()
            logger.info("Loaded doctrine cache from Supabase (%d usable entries)", len(self._raw))
        except Exception as e:
            logger.warning("Failed to load doctrine cache from Supabase: %s", e)
            self._raw = {}

    def refresh(self) -> None:
        """Refresh the cache — useful for hot-reloading after admin edits."""
        self._raw = {}
        self._map = {}
        if self._supabase is not None:
            self._load_from_supabase()

    def _build_index(self) -> None:
        self._map = {_normalize(q): a for q, a in self._raw.items()}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def lookup(self, query: str) -> DoctrineAnswer | None:
        """Return a cited canned answer if the query is close enough to a known question.

        First tries exact normalized match, then fuzzy Levenshtein. Every
        entry in ``self._map`` already carries non-empty citations (enforced
        at load time), so a returned hit is always citable.
        """
        if not query or not query.strip():
            return None

        normalized = _normalize(query)

        # Exact match
        if normalized in self._map:
            logger.debug("DoctrineCache exact hit: %s", normalized)
            return self._map[normalized]

        # Fuzzy match (Levenshtein ratio > threshold)
        best_ratio = 0.0
        best_answer: DoctrineAnswer | None = None
        for known, answer in self._map.items():
            dist = _levenshtein(normalized, known)
            max_len = max(len(normalized), len(known))
            ratio = (max_len - dist) / max_len if max_len else 0.0
            if ratio > best_ratio:
                best_ratio = ratio
                best_answer = answer

        if best_ratio >= _FUZZY_THRESHOLD:
            logger.debug("DoctrineCache fuzzy hit (%.2f): %s", best_ratio, normalized)
            return best_answer

        return None
