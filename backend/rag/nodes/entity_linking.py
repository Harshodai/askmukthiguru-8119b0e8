"""R6 entity-linking pre-pass: doctrine terms in a query -> OKF tags/teachers.

Research hook: ``docs/OKF_WIRING_RESEARCH_2026-10-04.md`` R6 — link query
entities (doctrine terms, teacher names) to the OKF tag/teacher vocabulary
*before* dense search, so term-mismatch queries ("diksha", "soul-sync",
"shri preethaji") still resolve to the curated vocabulary. Expected gain:
recall up on the term-heavy slice only.

Design constraints (binding):
- Pure function of the query string. No LLM calls, no I/O, no Qdrant/Neo4j.
  The lexicon proper nouns + ``DOCTRINE_SYNONYMS`` + codebase-attested
  teacher variants below are the whole vocabulary (0 LLM calls by construction).
- Precision-first: single-token aliases link ONLY when doctrine-distinctive
  (``_DISTINCTIVE_SINGLES``). Generic English glosses from the synonym lists
  ("awareness", "unity", "grace", "now", "seeker", "master") deliberately do
  NOT link — they fire on ordinary chit-chat and would widen every filter.
- ``teachers`` contains ONLY the two licensed OKF ids consumed by
  ``retrieval._okf_match`` (``sri-preethaji`` | ``sri-krishnaji``). Other
  recognized teachers (Sadhguru, Amma Bhagavan, ...) link as ``terms``.
- Bare "krishna" is NOT a teacher mention (deity ambiguity — "Stories of
  Krishna" must not route to Sri Krishnaji). Only ji-bearing / full variants.
- Downstream ``knowledge_tags`` is a hard Qdrant ``MatchAny`` filter
  (``services/qdrant/utils.py:build_tag_conditions`` — chunk must match >= 1
  tag), so the integration may only ever UNION tags, never replace.

Activation gate (per R6 row): per-class recall delta on the term-heavy slice
only, plus a lexicon-edit audit trail. Until that passes, the retrieval hook
runs with ``enabled=False`` (``getattr`` fallback, no config change): inputs
pass through unchanged and only the trace is recorded.
"""

from __future__ import annotations

import re

from domain.spiritual_ontology import CANONICAL_ENTITY_ALIASES

# OKF teacher ids — the exact values ``retrieval._okf_match(teacher=...)``
# filters on (see memory/AGENTS.md "Teacher Routing").
OKF_TEACHER_PREETHAJI = "sri-preethaji"
OKF_TEACHER_KRISHNAJI = "sri-krishnaji"

# Teacher-name variants attested in the codebase (not invented):
# - DOCTRINE_SYNONYMS "sri preethaji"/"sri krishnaji" entries
#   (backend/rag/nodes/utils.py)
# - lightrag_service TEACHER map: shri/sree/sri-sri/sreepreethaji fused forms,
#   "preetha", "krishna ji", acharya- forms
# Bare "krishna"/"preetha"-as-first-name risk is handled by excluding bare
# "krishna" (deity ambiguity); bare "preetha" is kept (codebase-attested) but
# matched on strict word boundaries.
_TEACHER_VARIANTS: dict[str, list[str]] = {
    OKF_TEACHER_PREETHAJI: [
        "sri preethaji",
        "sri sri preethaji",
        "shri preethaji",
        "sree preethaji",
        "acharya preethaji",
        "preethaji",
        "preetha ji",
        "preetha",
        "sreepreethaji",
    ],
    OKF_TEACHER_KRISHNAJI: [
        "sri krishnaji",
        "sri sri krishnaji",
        "shri krishnaji",
        "sree krishnaji",
        "acharya krishnaji",
        "krishnaji",
        "krishna ji",
        "sreekrishnaji",
    ],
}

# Extra alias -> canonical-term entries for doctrine vocabulary present in
# DOCTRINE_SYNONYMS (backend/rag/nodes/utils.py) but absent from
# CANONICAL_ENTITY_ALIASES, plus lexicon proper-noun singles
# (backend/data/doctrine_lexicon.json "proper_nouns": ojas/humsa/sohum/turiya/
# lokaa) and blessing-transliteration variants from the verification regex
# (backend/rag/nodes/verification.py: diksha/deeksha/aashirvaad/aashirvad).
# Generic English glosses are deliberately omitted (see module docstring).
# Canonicals use the ontology Title-Case style; tags are canonical.lower().
_R6_EXTRA_ALIASES: dict[str, str] = {
    "meditation": "Meditation",
    "dhyana": "Meditation",
    "dhyan": "Meditation",
    "mindfulness practice": "Meditation",
    "karma": "Karma",
    "karmic": "Karma",
    "dharma": "Dharma",
    "moksha": "Moksha",
    "atma": "Atma",
    "atman": "Atma",
    "brahman": "Brahman",
    "saguna brahman": "Divine Manifest",
    "nirguna brahman": "Divine Unmanifest",
    "samsara": "Samsara",
    "mantra": "Mantra",
    "bhakti": "Bhakti",
    "jnana": "Jnana",
    "kriya": "Kriya",
    "vairagya": "Vairagya",
    "satsang": "Satsang",
    "satsang meditation": "Satsang",
    "sankalpa": "Sankalpa",
    "sadhna": "Sadhna",
    "sadhana": "Sadhna",
    "spiritual sadhana": "Sadhna",
    "sadhak": "Sadhak",
    "mahavakya": "Mahavakya",
    "paramatma": "Paramatma",
    "paramatman": "Paramatma",
    "prarabdha": "Prarabdha",
    "prarabdha karma": "Prarabdha",
    "jeevan mukta": "Jeevan Mukta",
    "jeevanmukta": "Jeevan Mukta",
    "dharma prabhu": "Dharma Prabhu",
    "mayic force": "Mayic Force",
    "universal intelligence": "Universal Intelligence",
    "divine field": "Universal Intelligence",
    "cosmic consciousness": "Universal Intelligence",
    "divine intelligence": "Universal Intelligence",
    "universal consciousness field": "Universal Intelligence",
    "inner stillness": "Inner Stillness",
    "inner quiet": "Inner Stillness",
    "quiet presence": "Inner Stillness",
    "inner calm": "Inner Stillness",
    "warring self": "Warring Self",
    "divided self": "Warring Self",
    "conflicted self": "Warring Self",
    "inner conflict": "Warring Self",
    "self-centric thinking": "Self-Centric Thinking",
    "self-centered thinking": "Self-Centric Thinking",
    "self-preoccupation": "Self-Centric Thinking",
    "ego-centric thinking": "Self-Centric Thinking",
    "heart awakening": "Heart Awakening",
    "heart opening": "Heart Awakening",
    "open heart": "Heart Awakening",
    "awakening of the heart": "Heart Awakening",
    "heart center opening": "Heart Awakening",
    "heart explosion": "Heart Explosion",
    "explosion of the heart": "Heart Explosion",
    "compassion": "Compassion",
    "karuna": "Compassion",
    "intuition": "Intuition",
    "intuitive knowing": "Intuition",
    "inner knowing": "Intuition",
    "heart knowledge": "Intuition",
    "awakening": "Awakening",
    "spiritual awakening": "Awakening",
    "inner awakening": "Awakening",
    "divine grace": "Grace",
    "anugraha": "Grace",
    "being present": "Presence",
    "present moment": "Presence",
    "non-duality": "Oneness",
    "non-dual": "Oneness",
    "advaita": "Oneness",
    "higher consciousness": "Consciousness",
    "divine consciousness": "Consciousness",
    "universal consciousness": "Consciousness",
    "witness awareness": "Witness Awareness",
    "witness consciousness": "Witness Awareness",
    "observing awareness": "Witness Awareness",
    "sakshi bhava": "Witness Awareness",
    "sākṣī bhāva": "Witness Awareness",
    "साक्षी भाव": "Witness Awareness",
    "inner truth": "Inner Truth",
    "truth within": "Inner Truth",
    "deep truth": "Inner Truth",
    "essential truth": "Inner Truth",
    "core truth": "Inner Truth",
    "collective meditation": "Collective Meditation",
    "group meditation": "Collective Meditation",
    "community meditation": "Collective Meditation",
    "divine manifest": "Divine Manifest",
    "manifest divine": "Divine Manifest",
    "creator manifest": "Divine Manifest",
    "god with form": "Divine Manifest",
    "divine unmanifest": "Divine Unmanifest",
    "unmanifest divine": "Divine Unmanifest",
    "formless divine": "Divine Unmanifest",
    "god without form": "Divine Unmanifest",
    "synchronicity": "Synchronicity",
    "divine timing": "Synchronicity",
    "cosmic alignment": "Synchronicity",
    "karmic clearing": "Karmic Clearing",
    "karma clearing": "Karmic Clearing",
    "karmic release": "Karmic Clearing",
    "karmic debt clearing": "Karmic Clearing",
    "purification of karma": "Karmic Clearing",
    "spiritual vision": "Spiritual Vision",
    "divine vision": "Spiritual Vision",
    "higher vision": "Spiritual Vision",
    "sacred vision": "Spiritual Vision",
    "science of purification": "Science of Purification",
    "purification process": "Science of Purification",
    "inner purification": "Science of Purification",
    "cleansing practice": "Science of Purification",
    "truth of suffering": "Truth of Suffering",
    "seeing suffering": "Truth of Suffering",
    "nature of suffering": "Truth of Suffering",
    "dissolving into the beautiful state": "Dissolving into the Beautiful State",
    "dissolving into": "Dissolving into the Beautiful State",
    "merging with the beautiful state": "Dissolving into the Beautiful State",
    "dissolving suffering": "Dissolving into the Beautiful State",
    "three questions": "Three Questions",
    "three question meditation": "Three Questions",
    "total surrender": "Surrender",
    "sadhguru": "Sadhguru",
    "jaggi vasudev": "Sadhguru",
    "isha foundation": "Sadhguru",
    "sri amma bhagavan": "Amma Bhagavan",
    "kalki": "Amma Bhagavan",
    "oneness movement": "Amma Bhagavan",
    "iskcon": "ISKCON",
    "hare krishna": "ISKCON",
    "prabhupada": "ISKCON",
    "oo academy": "O&O Academy",
    "o and o academy": "O&O Academy",
    "o&o academy": "O&O Academy",
    "oando academy": "O&O Academy",
    "mukthi guru": "Mukthi Guru",
    "mukthiguru": "Mukthi Guru",
    # Lexicon proper-noun singles (doctrine entities, not ordinary English).
    "ojas": "Ojas",
    "humsa": "Humsa",
    "sohum": "Sohum",
    "turiya": "Turiya",
    "lokaa": "Lokaa",
    # Blessing-transliteration variants (verification.py fraud regex).
    "aashirvaad": "Deeksha",
    "aashirvad": "Deeksha",
}

# Single-token aliases link ONLY when doctrine-distinctive. Everything else
# (awareness, unity, grace, now, seeker, master, surrender, soul, ...) stays
# unlinked even when it appears in the alias tables — that is the precision
# guard: generic English must not link on its own.
_DISTINCTIVE_SINGLES = frozenset(
    {
        "ekam",
        "deeksha",
        "diksha",
        "ojas",
        "humsa",
        "sohum",
        "turiya",
        "lokaa",
        "aham",
        "ahamkara",
        "ahamkar",
        "moksha",
        "karma",
        "karmic",
        "dharma",
        "mantra",
        "bhakti",
        "jnana",
        "kriya",
        "vairagya",
        "satsang",
        "sankalpa",
        "sadhna",
        "sadhana",
        "sadhak",
        "atma",
        "atman",
        "brahman",
        "samsara",
        "mahavakya",
        "paramatma",
        "paramatman",
        "prarabdha",
        "jeevanmukta",
        "japa",
        "gita",
        "patanjali",
        "dhyana",
        "dhyan",
        "advaita",
        "karuna",
        "anugraha",
        "aashirvaad",
        "aashirvad",
        "meditation",
        "synchronicity",
        "compassion",
        "intuition",
        "awakening",
        "sadhguru",
        "kalki",
        "iskcon",
        "prabhupada",
        "mukthiguru",
    }
)


def _normalize(text: str) -> str:
    """Lowercase + separator folding. Preserves Devanagari/diacritics intact.

    Only ASCII separators are folded — combining marks (Devanagari matras,
    virama) are NOT word characters, so a ``[^\\w]`` strip would corrupt
    "साक्षी भाव". Folding is therefore allowlist-based, never strip-based.
    """
    text = (text or "").casefold()
    text = re.sub(r"[-_–—/]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# Ontology aliases that name the two licensed teachers route through
# ``teachers`` (with full variant coverage), never through ``terms``.
_LICENSED_TEACHER_ALIASES = frozenset({"preethaji", "krishnaji", "sri preethaji", "sri krishnaji"})

# alias -> canonical term, longest-first for deterministic overlap handling.
_ALIAS_INDEX: list[tuple[str, str]] = sorted(
    (
        (alias, CANONICAL_ENTITY_ALIASES[alias])
        for alias in CANONICAL_ENTITY_ALIASES
        if alias not in _LICENSED_TEACHER_ALIASES
    ),
    key=lambda item: -len(item[0]),
) + sorted(_R6_EXTRA_ALIASES.items(), key=lambda item: -len(item[0]))

_ALIAS_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b" + re.escape(_normalize(alias)) + r"\b"), canonical)
    for alias, canonical in _ALIAS_INDEX
    if " " in _normalize(alias).strip() or _normalize(alias) in _DISTINCTIVE_SINGLES
]

_TEACHER_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b" + re.escape(_normalize(variant)) + r"\b"), teacher)
    for teacher, variants in _TEACHER_VARIANTS.items()
    for variant in variants
]


def link_entities(query: str) -> dict[str, list[str]]:
    """Link doctrine entities in ``query`` to the OKF tag/teacher vocabulary.

    Returns ``{"teachers": [...], "terms": [...], "tags": [...]}`` where
    ``teachers`` are OKF teacher ids, ``terms`` are Title-Case canonicals,
    and ``tags`` are the lowercase knowledge-tag forms. Ordering is by first
    mention in the query (deterministic). Empty query -> all empty.
    """
    normalized = _normalize(query)
    teachers: list[str] = []
    for pattern, teacher in sorted(_TEACHER_PATTERNS, key=lambda p: -len(p[0].pattern)):
        if pattern.search(normalized) and teacher not in teachers:
            teachers.append(teacher)
    # Deterministic id order regardless of mention order.
    teachers.sort()

    hits: list[tuple[int, str]] = []
    seen: set[str] = set()
    for pattern, canonical in _ALIAS_PATTERNS:
        match = pattern.search(normalized)
        if match and canonical not in seen:
            seen.add(canonical)
            hits.append((match.start(), canonical))
    hits.sort(key=lambda h: (h[0], h[1]))
    terms = [canonical for _, canonical in hits]
    return {
        "teachers": teachers,
        "terms": terms,
        "tags": [term.lower() for term in terms],
    }


# Max tags the enabled path may ADD (union cap — never replace existing tags).
_ENTITY_TAG_BUDGET = 5


def resolve_entity_links(
    question: str,
    knowledge_tags: list[str] | tuple[str, ...] | None = (),
    teacher_id: str | None = None,
    enabled: bool = False,
) -> tuple[dict[str, list[str]], list[str], str | None]:
    """Retrieval integration point for the R6 pre-pass.

    ``enabled=False`` (default): pure trace — returns the links plus the
    inputs UNCHANGED, so live ranking is provably unaffected.
    ``enabled=True`` (future, gated): additive-only — union links' tags into
    ``knowledge_tags`` (capped at ``+_ENTITY_TAG_BUDGET``) and fill
    ``teacher_id`` ONLY when unset and exactly one teacher linked.
    """
    links = link_entities(question)
    base_tags = list(knowledge_tags or [])
    if not enabled:
        return links, base_tags, teacher_id
    merged = list(base_tags)
    for tag in links["tags"]:
        if len(merged) - len(base_tags) >= _ENTITY_TAG_BUDGET:
            break
        if tag not in merged:
            merged.append(tag)
    eff_teacher = teacher_id
    if eff_teacher is None and len(links["teachers"]) == 1:
        eff_teacher = links["teachers"][0]
    return links, merged, eff_teacher
