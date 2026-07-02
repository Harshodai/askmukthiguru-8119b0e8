"""Doctrine exact-match cache for high-frequency spiritual queries.

Uses a pre-seeded JSON map of normalized question → canned response.
Fuzzy match via Levenshtein distance allows slight paraphrasing.
"""

from __future__ import annotations

import json
import logging
import os
import re
import string
from pathlib import Path

logger = logging.getLogger(__name__)


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


# ---------------------------------------------------------------------------
# Default doctrine dataset (embedded so the cache works out of the box)
# ---------------------------------------------------------------------------
DEFAULT_DOCTRINE: dict[str, str] = {
    "what is the beautiful state": (
        "The Beautiful State is a state of calm, joy, and inner connection taught by "
        "Sri Preethaji and Sri Krishnaji. It is not dependent on external circumstances, "
        "but is a direct experience of peace that arises when we move beyond the "
        "conditioned mind. It is the foundation of the Ekam teachings and the goal "
        "of the spiritual journey. [Source: Beautiful State Teachings]"
    ),
    "who is sri preethaji": (
        "Sri Preethaji is a spiritual teacher and the co-founder of Ekam, along with "
        "Sri Krishnaji. She is known for her mystical experiences and teachings on the "
        "Beautiful State, Deeksha, and the Four Sacred Secrets. [Source: Sri Preethaji Bio]"
    ),
    "who is sri krishnaji": (
        "Sri Krishnaji is a spiritual teacher and the co-founder of Ekam, along with "
        "Sri Preethaji. He is known for his teachings on consciousness, the Beautiful State, "
        "and the science of mysticism. [Source: Sri Krishnaji Bio]"
    ),
    "what is soul sync": (
        "Soul Sync is a powerful 7-minute meditation practice created by Sri Preethaji "
        "and Sri Krishnaji. It uses specific breathing and visualization techniques to help "
        "you connect with your soul and enter a state of inner peace and beauty. [Source: Soul Sync]"
    ),
    "what is deeksha": (
        "Deeksha (or Deeksha) is a sacred transmission of energy that awakens the "
        "Beautiful State within you. It is given through the touch or intention of an "
        "awakened being and is a central practice in the Ekam tradition. [Source: Deeksha Teachings]"
    ),
    "what are the four sacred secrets": (
        "The Four Sacred Secrets are the core teachings of Sri Preethaji and Sri Krishnaji: "
        "1. The Secret of the Beautiful State, 2. The Secret of a Powerful Consciousness, "
        "3. The Secret of a Calm Mind, and 4. The Secret of a Compassionate Heart. "
        "[Source: Four Sacred Secrets]"
    ),
    "what is ekam": (
        "Ekam is the oneness and higher consciousness field founded by Sri Preethaji "
        "and Sri Krishnaji. It is a spiritual movement and a science of mysticism that "
        "offers teachings, Deeksha, and practices like Soul Sync to awaken the Beautiful State. "
        "[Source: Ekam Overview]"
    ),
    "what is oneness": (
        "Oneness is the experience of being one with all life, free from separation. "
        "In the Ekam teachings, Oneness is the natural state when the Beautiful State is "
        "fully awakened. It is the end of conflict within and the beginning of true compassion. "
        "[Source: Oneness Teachings]"
    ),
    "what is moksha": (
        "Moksha is liberation from the cycle of suffering and the conditioned mind. "
        "In the Ekam tradition, Moksha is not a future destination but a present possibility "
        "through Deeksha and the Beautiful State. [Source: Moksha Teachings]"
    ),
    "what is the beautiful state meditation": (
        "The Beautiful State Meditation is a guided practice by Sri Preethaji and Sri Krishnaji "
        "that helps you move from stress and anxiety to a state of calm, joy, and connection. "
        "It is the foundation of all Ekam practices. [Source: Beautiful State Meditation]"
    ),
    "how do i meditate": (
        "Start with Soul Sync, a 7-minute guided meditation by Sri Preethaji and Sri Krishnaji. "
        "Find a quiet place, sit comfortably, and follow the guided instructions. Consistency "
        "is more important than duration. [Source: Beginner Meditation Guide]"
    ),
    "what is the meaning of life": (
        "According to the Ekam teachings, the meaning of life is to awaken the Beautiful State "
        "within you and help others do the same. This is achieved through Deeksha, meditation, "
        "and living from a place of oneness and compassion. [Source: Life Purpose Teachings]"
    ),
}

# Minimum similarity threshold for fuzzy match (Levenshtein ratio)
_FUZZY_THRESHOLD = 0.85


class DoctrineCache:
    """Exact + fuzzy match cache for common doctrine queries.

    Loads a JSON file if provided, otherwise falls back to the built-in
    ``DEFAULT_DOCTRINE`` map.  Answers include pre-written citations so
    that a cache hit is indistinguishable from a generated answer.
    """

    def __init__(self, doctrine_file: str | None = None, supabase_client=None) -> None:
        self._map: dict[str, str] = {}
        self._raw: dict[str, str] = {}
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

        # 4. Fall back to embedded defaults
        if not self._raw:
            self._raw = DEFAULT_DOCTRINE.copy()
            self._build_index()

    def _load_json(self, path: str) -> None:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            # Accept both flat dict and list-of-dict formats
            if isinstance(data, dict):
                self._raw = data
            elif isinstance(data, list):
                self._raw = {item["question"]: item["answer"] for item in data if "question" in item and "answer" in item}
            else:
                raise ValueError("Expected dict or list")
            self._build_index()
            logger.info("Loaded doctrine cache from %s (%d entries)", path, len(self._raw))
        except Exception as e:
            logger.warning("Failed to load doctrine cache from %s: %s", path, e)
            self._raw = {}

    def _load_from_supabase(self) -> None:
        """Load doctrine FAQs from Supabase table ``doctrine_faqs``."""
        try:
            import asyncio
            # supabase client is synchronous; wrap in to_thread if we ever need async,
            # but init runs in sync context during service construction.
            res = self._supabase.table("doctrine_faqs").select("question,answer").execute()
            rows = getattr(res, "data", []) or []
            if rows:
                self._raw = {row["question"]: row["answer"] for row in rows if "question" in row and "answer" in row}
                self._build_index()
                logger.info("Loaded doctrine cache from Supabase (%d entries)", len(self._raw))
        except Exception as e:
            logger.warning("Failed to load doctrine cache from Supabase: %s", e)
            self._raw = {}

    def refresh(self) -> None:
        """Refresh the cache — useful for hot-reloading after admin edits."""
        self._raw = {}
        self._map = {}
        if self._supabase is not None:
            self._load_from_supabase()
        if not self._raw:
            self._raw = DEFAULT_DOCTRINE.copy()
            self._build_index()

    def _build_index(self) -> None:
        self._map = {_normalize(q): a for q, a in self._raw.items()}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def lookup(self, query: str) -> str | None:
        """Return a canned answer if the query is close enough to a known question.

        First tries exact normalized match, then fuzzy Levenshtein.
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
        best_answer: str | None = None
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