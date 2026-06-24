"""
Mukthi Guru — Lightweight Hyper-Extract Adapter

A zero-dependency heuristic port of ideas from the Hyper-Extract project:
https://github.com/yifanfeng97/hyper-extract

Hyper-Extract is an LLM-powered knowledge-extraction framework that turns
unstructured documents into structured Knowledge Abstracts (lists, models,
knowledge graphs, hypergraphs, spatio-temporal graphs, etc.). It uses Pydantic
schemas, structured LLM output, and external stores such as OMem and SemHash.

This adapter keeps the *concepts* that improve retrieval quality — document
structure parsing, atomic fact extraction, and entity-relationship linking —
without introducing heavy packages or extra LLM calls. It runs entirely on the
Python standard library plus patterns that are safe for noisy transcripts and
spiritual content.

Design Patterns:
  - Pure functions: every helper returns new objects; inputs are never mutated.
  - Fail-soft: the caller decides whether to abort or continue on errors.
  - Domain-aware: a curated list of spiritual entities guides extraction so that
    transcripts about Sri Preethaji & Sri Krishnaji are interpreted correctly.
"""

from __future__ import annotations

import dataclasses
import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Maximum number of characters the adapter will process in one pass.
DEFAULT_MAX_TEXT_LENGTH = 50_000

# Minimum text length for meaningful enrichment.
DEFAULT_MIN_TEXT_LENGTH = 200


# =============================================================================
# Domain knowledge: known spiritual entities and stopwords
# =============================================================================

_KNOWN_SPIRITUAL_ENTITIES: frozenset[str] = frozenset(
    {
        "Sri Preethaji",
        "Sri Krishnaji",
        "Preethaji",
        "Krishnaji",
        "Ekam",
        "The Oneness Movement",
        "Beautiful State",
        "Serene Mind",
        "Mukthi",
        "Liberation",
        "Enlightenment",
        "Consciousness",
        "Meditation",
        "Breath",
        "Ego",
        "Suffering",
        "Joy",
        "Peace",
        "Observation",
        "Witnessing",
        "Intention",
        "Grace",
        "Oneness",
        "One Source",
        "Divine",
        "Cosmos",
        "Existence",
        "Awareness",
        "Stillness",
        "Compassion",
        "Love",
        "Dukkha",
        "Samadhi",
        "Satsang",
        "Dharma",
    }
)

_STOPWORDS: frozenset[str] = frozenset(
    {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "shall",
        "can",
        "need",
        "dare",
        "ought",
        "used",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "as",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "between",
        "under",
        "and",
        "but",
        "or",
        "yet",
        "so",
        "if",
        "because",
        "although",
        "though",
        "while",
        "where",
        "when",
        "that",
        "which",
        "who",
        "whom",
        "whose",
        "what",
        "this",
        "these",
        "those",
        "i",
        "me",
        "my",
        "mine",
        "we",
        "us",
        "our",
        "ours",
        "you",
        "your",
        "yours",
        "he",
        "him",
        "his",
        "she",
        "her",
        "hers",
        "it",
        "its",
        "they",
        "them",
        "their",
        "theirs",
        "myself",
        "yourself",
        "himself",
        "herself",
        "itself",
        "ourselves",
        "yourselves",
        "themselves",
        "here",
        "there",
        "where",
        "everywhere",
        "anywhere",
        "somewhere",
        "now",
        "then",
        "today",
        "tomorrow",
        "yesterday",
        "soon",
        "later",
        "already",
        "still",
        "once",
        "twice",
        "sometimes",
        "always",
        "never",
        "often",
        "rarely",
        "usually",
        "also",
        "too",
        "very",
        "quite",
        "rather",
        "just",
        "only",
        "even",
        "back",
        "again",
        "however",
        "therefore",
        "thus",
        "moreover",
        "furthermore",
        "nevertheless",
        "otherwise",
        "instead",
        "meanwhile",
        "besides",
        "accordingly",
    }
)


# =============================================================================
# Regular expressions
# =============================================================================

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")

_TIMESTAMP_RE = re.compile(
    r"^\s*(?:\[\d{1,2}:\d{2}(?::\d{2})?\]|\d{1,2}:\d{2}(?::\d{2})?)\s*[:\-]?\s*"
)

_SECTION_HEADER_RE = re.compile(
    r"^[\s]*(?:"
    r"\d+[.)\s]+\s*[A-Z][A-Za-z\s]{2,60}"
    r"|[A-Z][A-Z\s\-]{3,50}[:\-]?"
    r"|[A-Z][A-Za-z\s\-]{2,60}[:\-]\s*$"
    r"|\[\s*[A-Z][A-Za-z\s\-]{2,60}\s*\]"
    r")\s*$"
)

_PROPER_NOUN_RE = re.compile(r"\b([A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*){0,2})\b")

_RELATION_VERBS = [
    "teaches",
    "teach",
    "guides",
    "guide",
    "leads to",
    "leads",
    "creates",
    "create",
    "helps",
    "help",
    "brings",
    "bring",
    "is",
    "are",
    "was",
    "were",
    "reveals",
    "reveal",
    "shows",
    "show",
    "manifests",
    "manifest",
    "transforms",
    "transform",
    "awakens",
    "awaken",
    "connects",
    "connect",
    "opens",
    "open",
    "clears",
    "clear",
    "dissolves",
    "dissolve",
    "frees",
    "free",
    "expands",
    "expand",
    "deepens",
    "deepen",
    "restores",
    "restore",
]

_RELATION_RE = re.compile(
    r"\b("
    + "|".join(map(re.escape, sorted(_RELATION_VERBS, key=len, reverse=True)))
    + r")\b",
    re.IGNORECASE,
)


# =============================================================================
# Public data structures
# =============================================================================

@dataclass(frozen=True)
class Section:
    """A contiguous region of text that shares a detected heading/topic."""

    title: str
    start_index: int
    end_index: int
    text: str


def enrich_text(
    text: str,
    max_text_length: int = DEFAULT_MAX_TEXT_LENGTH,
    min_text_length: int = DEFAULT_MIN_TEXT_LENGTH,
) -> dict:
    """
    Parse raw transcript/document text and return structured knowledge.

    Returns:
        {
            "sections":       [{"title": str, "start_index": int,
                                "end_index": int, "text": str}],
            "atomic_facts":   [str],
            "entities":       [str],
            "relationships":  [(str, str, str)],
        }

    The function is safe on short, noisy, or spiritual texts. It returns empty
    lists for empty input and avoids expensive operations when text is below the
    configured minimum length.
    """
    if not text or not text.strip():
        return _empty_result()

    normalized = _preprocess(text)
    if len(normalized) < min_text_length:
        return _empty_result()

    normalized = _truncate(normalized, max_text_length)

    sections = _detect_sections(normalized)
    atomic_facts = _extract_atomic_facts(normalized)
    entities = _extract_entities(normalized)
    relationships = _extract_relationships(atomic_facts, entities)

    return {
        "sections": [dataclasses.asdict(section) for section in sections],
        "atomic_facts": atomic_facts,
        "entities": entities,
        "relationships": relationships,
    }


def is_eligible(text: str, min_length: int = DEFAULT_MIN_TEXT_LENGTH) -> bool:
    """Check whether a text is long enough to benefit from enrichment."""
    return bool(text and len(text.strip()) >= min_length)


# =============================================================================
# Internal helpers
# =============================================================================


def _empty_result() -> dict:
    return {
        "sections": [],
        "atomic_facts": [],
        "entities": [],
        "relationships": [],
    }


def _preprocess(text: str) -> str:
    """Collapse whitespace while preserving paragraph boundaries."""
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _truncate(text: str, max_length: int) -> str:
    """Trim text to a safe maximum length at a sentence boundary if possible."""
    if len(text) <= max_length:
        return text
    cutoff = text.rfind(". ", 0, max_length)
    if cutoff == -1:
        cutoff = max_length
    return text[:cutoff].strip()


def _detect_sections(text: str) -> list[Section]:
    """
    Segment text into sections using paragraph breaks and header heuristics.

    Timestamps such as "[00:12]" or "01:23" are treated as implicit section
    markers because transcripts often shift topic at those boundaries.
    """
    paragraphs = [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]
    if not paragraphs:
        return [Section(title="Body", start_index=0, end_index=len(text), text=text)]

    sections: list[Section] = []
    current_title = "Introduction"
    current_start = 0
    current_parts: list[str] = []
    offset = 0

    for paragraph in paragraphs:
        para_start = text.find(paragraph, offset)
        para_end = para_start + len(paragraph)

        if _is_section_boundary(paragraph):
            if current_parts:
                sections.append(
                    Section(
                        title=current_title,
                        start_index=current_start,
                        end_index=para_start,
                        text=" ".join(current_parts),
                    )
                )
            current_title = _sanitize_title(paragraph)
            current_start = para_start
            current_parts = []
        else:
            current_parts.append(paragraph)

        offset = para_end

    if current_parts or not sections:
        body_text = " ".join(current_parts) if current_parts else text[current_start:]
        sections.append(
            Section(
                title=current_title,
                start_index=current_start,
                end_index=len(text),
                text=body_text,
            )
        )

    return sections


def _is_section_boundary(line: str) -> bool:
    """Detect a line that looks like a section header or timestamp marker."""
    stripped = line.strip()
    if not stripped:
        return False
    if _TIMESTAMP_RE.match(stripped):
        return True
    if _SECTION_HEADER_RE.match(stripped):
        return True
    return _looks_like_title(stripped)


def _looks_like_title(line: str) -> bool:
    """Detect a short, title-case heading without sentence punctuation."""
    if len(line) > 60 or len(line) < 4:
        return False
    if line[-1] in ".?!,;":
        return False
    words = line.split()
    if len(words) < 2:
        return False
    capitalized = sum(1 for word in words if word and word[0].isupper())
    return words[0][0].isupper() and capitalized >= max(2, len(words) // 2 + 1)


def _sanitize_title(line: str) -> str:
    """Derive a clean title from a boundary line."""
    cleaned = re.sub(r"^\[|\]$", "", line.strip())
    cleaned = re.sub(r"^\d+[.)\s]+", "", cleaned)
    cleaned = re.sub(r"^(The|A|An)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip(" :-").title()
    return cleaned or "Section"


def _extract_atomic_facts(text: str) -> list[str]:
    """
    Split text into self-contained factual statements.

    Fragments, questions, and rhetorical exclamations are filtered out.
    Multi-sentence chunks are re-split on period boundaries.
    """
    raw = [candidate.strip() for candidate in _SENTENCE_RE.split(text) if candidate.strip()]
    facts: list[str] = []
    for candidate in raw:
        if _is_poor_fact(candidate):
            continue
        if candidate.count(". ") > 1:
            sub_facts = [part.strip() for part in candidate.split(". ") if len(part.strip()) >= 20]
            facts.extend(sub_facts)
        else:
            facts.append(candidate.rstrip("."))
    return _decontextualize_facts(facts)


def _is_poor_fact(candidate: str) -> bool:
    """Filter out fragments, questions, and exclamations."""
    if len(candidate) < 20:
        return True
    if candidate[-1] in "?!":
        return True
    return False


def _decontextualize_facts(facts: list[str]) -> list[str]:
    """
    Perform minimal pronoun resolution so that isolated facts remain readable.

    Only the most common subject pronouns are replaced, using the last explicit
    subject found in the stream. This is intentionally lightweight and safe for
    spiritual transcripts where pronouns usually refer to the most recent teaching
    or teacher.
    """
    if not facts:
        return []

    resolved: list[str] = []
    last_subject = ""
    subject_pronouns = {"he", "she", "it", "they"}

    for fact in facts:
        words = fact.split()
        if words and words[0].lower() in subject_pronouns and last_subject:
            words[0] = last_subject
            fact = " ".join(words)
        resolved.append(fact)

        new_subject = _guess_subject(fact)
        if new_subject:
            last_subject = new_subject

    return resolved


def _guess_subject(sentence: str) -> str:
    """Find a likely subject for pronoun resolution."""
    lower_sentence = sentence.lower()
    for entity in sorted(_KNOWN_SPIRITUAL_ENTITIES, key=len, reverse=True):
        if entity.lower() in lower_sentence:
            return entity
    match = re.search(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b", sentence)
    if match:
        candidate = match.group(1)
        if candidate.lower() not in _STOPWORDS:
            return candidate
    return ""


def _extract_entities(text: str) -> list[str]:
    """
    Extract unique entities from the text.

    First matches a curated list of spiritual terms (case-insensitive), then
    applies a conservative proper-noun heuristic. Duplicates are removed by
    lower-cased key, keeping the longest canonical form when available.
    """
    found: dict[str, str] = {}
    lower_text = text.lower()

    for entity in _KNOWN_SPIRITUAL_ENTITIES:
        key = entity.lower()
        if key in lower_text:
            if key not in found or len(entity) > len(found[key]):
                found[key] = entity

    for match in _PROPER_NOUN_RE.finditer(text):
        candidate = match.group(1).strip()
        key = candidate.lower()
        if key in _STOPWORDS or len(candidate) < 3:
            continue
        if key not in found:
            found[key] = candidate

    return list(found.values())


def _extract_relationships(
    facts: list[str], entities: list[str]
) -> list[tuple[str, str, str]]:
    """
    Build simple entity co-occurrence relationships from atomic facts.

    For each fact containing two or more entities, an edge is created between
    every entity pair using the strongest relation verb detected in the fact.
    This mimics the binary edge extraction in GraphRAG/LightRAG but uses
    deterministic heuristics instead of an LLM.
    """
    if len(entities) < 2:
        return []

    relationships: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    for fact in facts:
        present = [entity for entity in entities if entity.lower() in fact.lower()]
        if len(present) < 2:
            continue

        relation = _infer_relation(fact)
        for index, source in enumerate(present):
            for target in present[index + 1 :]:
                key = (source.lower(), relation.lower(), target.lower())
                if key not in seen:
                    seen.add(key)
                    relationships.append((source, relation, target))

    return relationships


def _infer_relation(sentence: str) -> str:
    """Pick a canonical relation verb from a sentence."""
    match = _RELATION_RE.search(sentence)
    if match:
        return match.group(1).lower()
    return "related_to"
