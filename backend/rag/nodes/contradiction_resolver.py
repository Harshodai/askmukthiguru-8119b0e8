"""
Contradiction Resolution & Authority Engine (Phase 3 Task 3).

Metadata-driven conflict detection and authority-weighted resolution between
dense passage evidence (vector chunks) and graph knowledge entities, referencing
patterns from ConflictRAG and Enterprise Trust RAG.
"""

from __future__ import annotations

from enum import IntEnum
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class AuthorityRank(IntEnum):
    """
    Source authority ranking:
      Rank 1 (Weight 1.0): Canonical published core books, direct discourse transcripts, scripture
      Rank 2 (Weight 0.7): Q&A sessions, podcasts, video transcripts
      Rank 3 (Weight 0.4): Community summaries, staging OKF, secondary notes
    """
    CANONICAL = 1
    DISCOURSE_MEDIA = 2
    COMMUNITY_SECONDARY = 3


AUTHORITY_WEIGHTS: dict[int, float] = {
    AuthorityRank.CANONICAL.value: 1.0,
    AuthorityRank.DISCOURSE_MEDIA.value: 0.7,
    AuthorityRank.COMMUNITY_SECONDARY.value: 0.4,
}

# Source types mapped to Rank 1 (Weight 1.0)
RANK_1_TYPES: set[str] = {
    "canonical_book",
    "primary_discourse",
    "scripture",
    "core_book",
    "book",
    "published_book",
    "canonical",
    "doctrine",
    "direct_discourse",
}

# Source types mapped to Rank 2 (Weight 0.7)
RANK_2_TYPES: set[str] = {
    "qa",
    "qa_session",
    "podcast",
    "video_transcript",
    "youtube",
    "video",
    "discourse_video",
    "interview",
    "audio_transcript",
}

# Source types mapped to Rank 3 (Weight 0.4)
RANK_3_TYPES: set[str] = {
    "community_summary",
    "staging_okf",
    "secondary_notes",
    "notes",
    "summary",
    "secondary",
    "staging",
    "web",
    "forum",
    "blog",
    "unverified",
    "draft",
    "unknown",
}

# Canonical opposite relations in spiritual ontology
OPPOSITE_RELATIONS: dict[str, set[str]] = {
    "leads_to": {"prevents", "causes_opposite_of", "blocks", "hinders"},
    "causes": {"prevents", "blocks", "hinders"},
    "prevents": {"leads_to", "causes", "facilitates", "promotes"},
    "is_opposite_of": {"is_similar_to", "is_same_as", "equals"},
    "is_similar_to": {"is_opposite_of", "contradicts"},
    "precedes": {"follows", "succeeds"},
    "follows": {"precedes"},
    "is_a": {"is_not_a"},
}

# Domain-specific antonym pairs for polarity conflict detection
DOMAIN_ANTONYMS: list[tuple[set[str], set[str]]] = [
    ({"peace", "peaceful", "serene", "calm", "tranquil", "stillness"},
     {"agitation", "agitated", "anxiety", "anxious", "conflict", "distress", "restless", "suffering"}),
    ({"effective", "potent", "beneficial", "sacred", "transformative", "genuine"},
     {"ineffective", "harmful", "detrimental", "fake", "fabricated", "useless", "myth", "placebo"}),
    ({"liberation", "mukthi", "freedom", "enlightenment", "awakening"},
     {"bondage", "illusion", "maya", "ignorance", "entanglement"}),
    ({"truth", "true", "authentic", "canonical"},
     {"false", "untrue", "fake", "fabricated", "myth", "distorted"}),
]

# Negation prefixes and adverbs
NEGATION_PATTERNS = re.compile(
    r"\b(not|never|no|cannot|can't|does\s+not|doesn't|did\s+not|didn't|is\s+not|isn't|"
    r"are\s+not|aren't|would\s+not|should\s+not|fails?\s+to|prevents?|blocks?|rejects?)\b",
    re.IGNORECASE,
)

# Number words to digits for factual count conflict detection
NUMBER_WORDS: dict[str, int] = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

# Known core spiritual entities for fallback detection
_KNOWN_CORE_ENTITIES = (
    "four sacred secrets",
    "soul sync",
    "serene mind",
    "deeksha",
    "aham",
    "ananda",
    "oneness blessing",
    "spiritual vision",
    "universal intelligence",
    "inner truth",
    "spiritual right action",
    "beautiful state",
    "suffering state",
    "breath awareness",
)


def _normalize_entity(val: str) -> str:
    """Normalize entity identifier to lowercase alphanumeric string with spaces."""
    if not val or not isinstance(val, str):
        return ""
    cleaned = re.sub(r"[^\w\s-]", "", val.strip().lower())
    return re.sub(r"[\s_-]+", " ", cleaned).strip()


def get_source_authority(item: dict[str, Any]) -> tuple[int, float]:
    """
    Determine source authority rank (1, 2, 3) and weight (1.0, 0.7, 0.4) for a chunk or graph entity.

    Returns:
        (authority_rank: int, authority_weight: float)
    """
    if not isinstance(item, dict):
        return AuthorityRank.COMMUNITY_SECONDARY.value, 0.4

    # 1. Direct explicit authority_rank (int or numeric str)
    raw_rank = item.get("authority_rank")
    if raw_rank is None and isinstance(item.get("metadata"), dict):
        raw_rank = item["metadata"].get("authority_rank")
    if raw_rank is not None:
        try:
            rank_val = int(raw_rank)
            if rank_val in (1, 2, 3):
                return rank_val, AUTHORITY_WEIGHTS.get(rank_val, 0.4)
        except (ValueError, TypeError):
            pass

    # 2. Match source_type
    meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    prov = item.get("provenance") if isinstance(item.get("provenance"), dict) else {}

    raw_source_type = (
        item.get("source_type")
        or meta.get("source_type")
        or prov.get("source_type")
        or item.get("type")
        or ""
    )
    if isinstance(raw_source_type, str) and raw_source_type.strip():
        norm_type = raw_source_type.strip().lower().replace("-", "_").replace(" ", "_")
        if norm_type in RANK_1_TYPES:
            return AuthorityRank.CANONICAL.value, 1.0
        if norm_type in RANK_2_TYPES:
            return AuthorityRank.DISCOURSE_MEDIA.value, 0.7
        if norm_type in RANK_3_TYPES:
            return AuthorityRank.COMMUNITY_SECONDARY.value, 0.4

    # 3. Inspect URL, title, or channel heuristics
    url = str(item.get("source_url") or meta.get("source_url") or prov.get("source") or "").lower()
    title = str(item.get("title") or meta.get("title") or "").lower()
    channel = str(item.get("channel") or "").lower()

    if any(k in url or k in title for k in ("canonical_book", "four sacred secrets", "scripture", "canonical")):
        return AuthorityRank.CANONICAL.value, 1.0
    if "youtube.com" in url or "youtu.be" in url or "video" in channel or "podcast" in url:
        return AuthorityRank.DISCOURSE_MEDIA.value, 0.7
    if any(k in url or k in title for k in ("community", "staging", "notes", "wiki", "forum", "secondary")):
        return AuthorityRank.COMMUNITY_SECONDARY.value, 0.4

    # Default to Rank 3 (Community / Secondary)
    return AuthorityRank.COMMUNITY_SECONDARY.value, 0.4


def _get_source_id(item: dict[str, Any]) -> str:
    """Return a descriptive source identifier for an item."""
    if not isinstance(item, dict):
        return "unknown"
    return str(
        item.get("source_url")
        or item.get("source_id")
        or item.get("title")
        or item.get("name")
        or (item.get("metadata", {}).get("source_url") if isinstance(item.get("metadata"), dict) else None)
        or (item.get("metadata", {}).get("title") if isinstance(item.get("metadata"), dict) else None)
        or (item.get("provenance", {}).get("source") if isinstance(item.get("provenance"), dict) else None)
        or "unknown_source"
    )


def extract_entity_keys(item: dict[str, Any]) -> set[str]:
    """Extract normalized entity keys from chunk or graph entity."""
    keys: set[str] = set()
    if not isinstance(item, dict):
        return keys

    # Check direct entity fields
    for field in ("entity_ids", "entities", "entity_id", "entity", "name", "concept", "subject", "title"):
        val = item.get(field)
        if isinstance(val, str) and val.strip():
            norm = _normalize_entity(val)
            if norm:
                keys.add(norm)
        elif isinstance(val, (list, set, tuple)):
            for sub in val:
                if isinstance(sub, str) and sub.strip():
                    norm = _normalize_entity(sub)
                    if norm:
                        keys.add(norm)
                elif isinstance(sub, dict) and "name" in sub:
                    norm = _normalize_entity(str(sub["name"]))
                    if norm:
                        keys.add(norm)

    # Check metadata or provenance
    meta = item.get("metadata")
    if isinstance(meta, dict):
        for field in ("entity_ids", "entities", "entity_id", "concept"):
            val = meta.get(field)
            if isinstance(val, str) and val.strip():
                norm = _normalize_entity(val)
                if norm:
                    keys.add(norm)
            elif isinstance(val, (list, set, tuple)):
                for sub in val:
                    if isinstance(sub, str) and sub.strip():
                        norm = _normalize_entity(sub)
                        if norm:
                            keys.add(norm)

    prov = item.get("provenance")
    if isinstance(prov, dict):
        val = prov.get("entity_ids")
        if isinstance(val, (list, tuple)):
            for sub in val:
                norm = _normalize_entity(str(sub))
                if norm:
                    keys.add(norm)

    # If no structured entity keys found, scan text for known core entities
    text = (item.get("text") or item.get("content") or item.get("description") or "")
    if text:
        text_lower = text.lower()
        for known in _KNOWN_CORE_ENTITIES:
            if known in text_lower:
                keys.add(_normalize_entity(known))

    return keys


def detect_conflict(item_a: dict[str, Any], item_b: dict[str, Any]) -> tuple[bool, str]:
    """
    Detect if item_a and item_b have conflicting factual claims about a shared entity.
    Returns (has_conflict: bool, reason: str).
    """
    if not isinstance(item_a, dict) or not isinstance(item_b, dict):
        return False, ""

    src_a = _get_source_id(item_a)
    src_b = _get_source_id(item_b)
    if src_a == src_b and src_a != "unknown_source":
        # Same source does not conflict with itself
        return False, ""

    # Check explicit conflict markers
    conflicts_a = item_a.get("conflicts") or item_a.get("contradicts") or []
    if isinstance(conflicts_a, str):
        conflicts_a = [conflicts_a]
    if any(c in src_b or src_b in c for c in conflicts_a):
        return True, f"Explicit conflict flag in {src_a} against {src_b}"

    conflicts_b = item_b.get("conflicts") or item_b.get("contradicts") or []
    if isinstance(conflicts_b, str):
        conflicts_b = [conflicts_b]
    if any(c in src_a or src_a in c for c in conflicts_b):
        return True, f"Explicit conflict flag in {src_b} against {src_a}"

    # Extract entities
    entities_a = extract_entity_keys(item_a)
    entities_b = extract_entity_keys(item_b)
    common_entities = entities_a & entities_b

    # If no common entity by exact name, check substring match (e.g. 'four sacred secrets' vs 'sacred secrets')
    if not common_entities:
        for ea in entities_a:
            for eb in entities_b:
                if len(ea) > 4 and len(eb) > 4 and (ea in eb or eb in ea):
                    common_entities.add(ea)

    if not common_entities:
        return False, ""

    entity_str = ", ".join(sorted(common_entities))

    # 1. Relational conflict: Check opposite relations
    rel_a = str(item_a.get("relation") or item_a.get("graph_relation") or "").lower()
    rel_b = str(item_b.get("relation") or item_b.get("graph_relation") or "").lower()
    if rel_a and rel_b:
        opposites_a = OPPOSITE_RELATIONS.get(rel_a, set())
        if rel_b in opposites_a:
            return True, f"Opposite relation on '{entity_str}': '{rel_a}' vs '{rel_b}'"

    # 2. Attribute / Claim conflict: Check explicit attributes or claims
    attrs_a = item_a.get("attributes") or {}
    attrs_b = item_b.get("attributes") or {}
    if isinstance(attrs_a, dict) and isinstance(attrs_b, dict):
        for k in set(attrs_a.keys()) & set(attrs_b.keys()):
            val_a = str(attrs_a[k]).strip().lower()
            val_b = str(attrs_b[k]).strip().lower()
            if val_a != val_b and val_a and val_b:
                return True, f"Attribute '{k}' conflict on '{entity_str}': '{val_a}' vs '{val_b}'"

    claims_a = item_a.get("claims") or []
    claims_b = item_b.get("claims") or []
    if isinstance(claims_a, list) and isinstance(claims_b, list):
        for ca in claims_a:
            for cb in claims_b:
                if isinstance(ca, dict) and isinstance(cb, dict):
                    if ca.get("predicate") == cb.get("predicate") and ca.get("polarity") != cb.get("polarity"):
                        return True, f"Polarity claim conflict on '{entity_str}': {ca.get('predicate')}"

    # 3. Textual / Lexical conflict detection (ConflictRAG pattern)
    text_a = (item_a.get("text") or item_a.get("content") or item_a.get("description") or "").lower()
    text_b = (item_b.get("text") or item_b.get("content") or item_b.get("description") or "").lower()

    if not text_a or not text_b:
        return False, ""

    # Check for domain antonyms on the entity
    for positive_words, negative_words in DOMAIN_ANTONYMS:
        a_has_pos = any(re.search(rf"\b{re.escape(w)}\b", text_a) for w in positive_words)
        a_has_neg = any(re.search(rf"\b{re.escape(w)}\b", text_a) for w in negative_words)
        b_has_pos = any(re.search(rf"\b{re.escape(w)}\b", text_b) for w in positive_words)
        b_has_neg = any(re.search(rf"\b{re.escape(w)}\b", text_b) for w in negative_words)

        if (a_has_pos and not a_has_neg and b_has_neg and not b_has_pos) or (
            a_has_neg and not a_has_pos and b_has_pos and not b_has_neg
        ):
            return True, f"Contradictory polarity/antonyms on '{entity_str}'"

    # Check for negation mismatch on key predicates
    has_neg_a = bool(NEGATION_PATTERNS.search(text_a))
    has_neg_b = bool(NEGATION_PATTERNS.search(text_b))
    if has_neg_a != has_neg_b:
        # One has explicit negation. Check if they share key non-stop words describing the entity
        words_a = set(re.findall(r"\b\w{4,}\b", text_a)) - {"which", "their", "about", "there", "these", "would"}
        words_b = set(re.findall(r"\b\w{4,}\b", text_b)) - {"which", "their", "about", "there", "these", "would"}
        shared_predicates = (words_a & words_b) - {e.replace(" ", "") for e in common_entities}
        # Tightened requirement: shared predicates must include a verb-bearing action word
        if len(shared_predicates) >= 2 and any(_is_verb_predicate(w) for w in shared_predicates):
            return True, f"Negation asymmetry on shared predicates {list(shared_predicates)[:3]} for '{entity_str}'"

    # Check for numeric count mismatch on specific entities (e.g. "four sacred secrets" vs "five")
    numbers_a = _extract_adjacent_entity_numbers(text_a, common_entities)
    numbers_b = _extract_adjacent_entity_numbers(text_b, common_entities)
    if numbers_a and numbers_b and (numbers_a != numbers_b):
        # Mismatched numbers in text discussing same core entity
        return True, f"Numeric claim conflict on '{entity_str}': {numbers_a} vs {numbers_b}"

    return False, ""


_VERB_PREDICATE_STEMS = (
    "calm", "align", "creat", "lead", "caus", "heal", "help", "bring", "teach",
    "give", "prevent", "practic", "requir", "transform", "awaken", "liberat",
    "connect", "dissolv", "cultivat", "produc", "achiev", "destroy", "block",
    "guid", "enabl", "increas", "decreas", "reduc", "improv", "elevat", "harm",
)


def _is_verb_predicate(word: str) -> bool:
    """Check if a word represents an action or predicate verb."""
    w = word.lower()
    if any(w.startswith(stem) for stem in _VERB_PREDICATE_STEMS):
        return True
    return w.endswith(("ing", "ed", "es"))


def _extract_adjacent_entity_numbers(text: str, entities: set[str]) -> set[int]:
    """Extract small cardinal numbers that are adjacent to an entity mention.

    Tightens numeric count conflict detection so broad numbers in unrelated
    clauses (e.g. step numbers, timestamps, durations) do not trigger false conflicts.
    """
    if not text or not entities:
        return set()

    words = re.findall(r"\b\w+\b", text.lower())
    if not words:
        return set()

    entity_words: set[str] = set()
    for ent in entities:
        for ew in re.findall(r"\b\w+\b", ent.lower()):
            if len(ew) >= 3:
                entity_words.add(ew)

    entity_token_positions: set[int] = {
        idx for idx, w in enumerate(words) if w in entity_words
    }
    if not entity_token_positions:
        return set()

    nums: set[int] = set()
    for idx, w in enumerate(words):
        val = None
        if w in NUMBER_WORDS:
            val = NUMBER_WORDS[w]
        elif w.isdigit() and 1 <= int(w) <= 10:
            val = int(w)

        if val is not None and any(abs(idx - ep) <= 4 for ep in entity_token_positions):
            nums.add(val)

    return nums


def _extract_entity_numbers(text: str) -> set[int]:
    """Extract small cardinal numbers from text describing entity counts."""
    nums: set[int] = set()
    for word, val in NUMBER_WORDS.items():
        if re.search(rf"\b{word}\b", text, re.IGNORECASE):
            nums.add(val)
    for m in re.finditer(r"\b([1-9]|10)\b", text):
        nums.add(int(m.group(1)))
    return nums


def _is_suppressible_conflict(reason: str) -> bool:
    """Check if a detected conflict is strong enough to suppress chunks.

    Lexical negation asymmetry and broad numeric mismatches cannot suppress
    or delete chunks from generation context (preserving them as telemetry/metadata).
    Suppression is preserved for explicit-flag, relation, attribute, claim-polarity,
    domain antonyms, and tight entity-adjacent numeric count conflicts.
    """
    if not reason or reason.startswith("Negation asymmetry"):
        return False
    return True


def resolve_contradictions(
    chunks: list[dict[str, Any]],
    graph_entities: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Detect conflicts on core entities or contradictory factual claims between
    vector chunks and graph entities, prioritizing higher-ranking source authority.

    Source Authority Ranking:
      Rank 1 (Weight 1.0): Canonical published books and direct discourses.
      Rank 2 (Weight 0.7): Q&A sessions, podcasts, and video transcripts.
      Rank 3 (Weight 0.4): Community summaries, staging OKF, and secondary notes.

    Args:
        chunks: Dense passage evidence (vector chunks) from retrieval.
        graph_entities: Graph knowledge entities from Neo4j / LightRAG / OKF.

    Returns:
        tuple of (filtered_chunks, conflict_metadata):
          - filtered_chunks: Chunks with conflicting lower-authority passages removed
            and surviving chunks annotated with authority ranking and status.
          - conflict_metadata: Dict with:
            `{"contradiction_detected": bool,
              "contradiction_resolved_via": str,
              "conflicting_sources": list,
              "chosen_authority_rank": int}`
    """
    if not chunks and not graph_entities:
        return [], {
            "contradiction_detected": False,
            "contradiction_resolved_via": "none",
            "conflicting_sources": [],
            "chosen_authority_rank": 1,
            "conflicts_count": 0,
            "conflicts": [],
        }

    suppressed_chunk_indices: set[int] = set()
    conflicts_detected: list[dict[str, Any]] = []
    conflicting_sources: set[str] = set()
    winning_ranks: list[int] = []

    # Phase 1: Detect conflicts between Vector Chunks and Graph Entities
    for chunk_idx, chunk in enumerate(chunks):
        chunk_rank, chunk_weight = get_source_authority(chunk)
        chunk_src = _get_source_id(chunk)

        for entity in graph_entities:
            entity_rank, entity_weight = get_source_authority(entity)
            entity_src = _get_source_id(entity)

            has_conflict, reason = detect_conflict(chunk, entity)
            if has_conflict:
                conflicting_sources.add(chunk_src)
                conflicting_sources.add(entity_src)
                can_suppress = _is_suppressible_conflict(reason)

                # Authority comparison: Lower rank number = higher authority (Rank 1 > Rank 3)
                if can_suppress and entity_rank < chunk_rank:
                    # Graph entity has higher authority; vector chunk is suppressed
                    suppressed_chunk_indices.add(chunk_idx)
                    winning_ranks.append(entity_rank)
                    conflicts_detected.append({
                        "entity": list(extract_entity_keys(chunk) & extract_entity_keys(entity)),
                        "winner_source": entity_src,
                        "winner_rank": entity_rank,
                        "loser_source": chunk_src,
                        "loser_rank": chunk_rank,
                        "reason": reason,
                    })
                    logger.info(
                        "Contradiction resolved: '%s' (Rank %d) overruled '%s' (Rank %d). Reason: %s",
                        entity_src,
                        entity_rank,
                        chunk_src,
                        chunk_rank,
                        reason,
                    )
                elif can_suppress and chunk_rank < entity_rank:
                    # Vector chunk has higher authority; vector chunk is preserved, graph claim demoted
                    winning_ranks.append(chunk_rank)
                    conflicts_detected.append({
                        "entity": list(extract_entity_keys(chunk) & extract_entity_keys(entity)),
                        "winner_source": chunk_src,
                        "winner_rank": chunk_rank,
                        "loser_source": entity_src,
                        "loser_rank": entity_rank,
                        "reason": reason,
                    })
                    logger.info(
                        "Contradiction resolved: '%s' (Rank %d) overruled '%s' (Rank %d). Reason: %s",
                        chunk_src,
                        chunk_rank,
                        entity_src,
                        entity_rank,
                        reason,
                    )
                else:
                    winning_ranks.append(min(chunk_rank, entity_rank))
                    conflicts_detected.append({
                        "entity": list(extract_entity_keys(chunk) & extract_entity_keys(entity)),
                        "winner_source": chunk_src,
                        "winner_rank": chunk_rank,
                        "loser_source": entity_src,
                        "loser_rank": entity_rank,
                        "reason": reason,
                    })

    # Phase 2: Detect conflicts among Vector Chunks themselves
    for i, chunk_a in enumerate(chunks):
        if i in suppressed_chunk_indices:
            continue
        rank_a, weight_a = get_source_authority(chunk_a)
        src_a = _get_source_id(chunk_a)

        for j in range(i + 1, len(chunks)):
            if j in suppressed_chunk_indices:
                continue
            chunk_b = chunks[j]
            rank_b, weight_b = get_source_authority(chunk_b)
            src_b = _get_source_id(chunk_b)

            has_conflict, reason = detect_conflict(chunk_a, chunk_b)
            if has_conflict:
                conflicting_sources.add(src_a)
                conflicting_sources.add(src_b)
                can_suppress = _is_suppressible_conflict(reason)

                if can_suppress and rank_a < rank_b:
                    # chunk_a has higher authority
                    suppressed_chunk_indices.add(j)
                    winning_ranks.append(rank_a)
                    conflicts_detected.append({
                        "entity": list(extract_entity_keys(chunk_a) & extract_entity_keys(chunk_b)),
                        "winner_source": src_a,
                        "winner_rank": rank_a,
                        "loser_source": src_b,
                        "loser_rank": rank_b,
                        "reason": reason,
                    })
                elif can_suppress and rank_b < rank_a:
                    # chunk_b has higher authority
                    suppressed_chunk_indices.add(i)
                    winning_ranks.append(rank_b)
                    conflicts_detected.append({
                        "entity": list(extract_entity_keys(chunk_a) & extract_entity_keys(chunk_b)),
                        "winner_source": src_b,
                        "winner_rank": rank_b,
                        "loser_source": src_a,
                        "loser_rank": rank_a,
                        "reason": reason,
                    })
                    break  # chunk_a is suppressed, stop checking against it
                elif can_suppress:
                    # Equal rank tie-break: higher retrieval score wins
                    score_a = float(chunk_a.get("score") or chunk_a.get("rerank_score") or 0.0)
                    score_b = float(chunk_b.get("score") or chunk_b.get("rerank_score") or 0.0)
                    if score_a >= score_b:
                        suppressed_chunk_indices.add(j)
                        winning_ranks.append(rank_a)
                    else:
                        suppressed_chunk_indices.add(i)
                        winning_ranks.append(rank_b)
                        break
                    conflicts_detected.append({
                        "type": "authority_tie",
                        "entity": list(extract_entity_keys(chunk_a) & extract_entity_keys(chunk_b)),
                        "chunk_id": chunk_a.get("id", ""),
                        "entity_id": chunk_b.get("id", ""),
                        "reason": "equal_authority_rank_tie",
                    })
                else:
                    # Telemetry-only conflict without chunk suppression
                    winning_ranks.append(min(rank_a, rank_b))
                    conflicts_detected.append({
                        "entity": list(extract_entity_keys(chunk_a) & extract_entity_keys(chunk_b)),
                        "winner_source": src_a,
                        "winner_rank": rank_a,
                        "loser_source": src_b,
                        "loser_rank": rank_b,
                        "reason": reason,
                    })

    # Construct filtered and annotated chunk list
    filtered_chunks: list[dict[str, Any]] = []
    for idx, chunk in enumerate(chunks):
        rank, weight = get_source_authority(chunk)
        annotated = dict(chunk)
        annotated["authority_rank"] = rank
        annotated["authority_weight"] = weight

        if idx in suppressed_chunk_indices:
            # Drop suppressed chunk from active retrieval context
            continue

        src_id = _get_source_id(chunk)
        if conflicts_detected and src_id in conflicting_sources:
            annotated["contradiction_status"] = "resolved_authoritative"
        else:
            annotated["contradiction_status"] = "uncontested"

        filtered_chunks.append(annotated)

    # Edge-case safety: If all chunks were suppressed, preserve highest authority chunk
    if not filtered_chunks and chunks:
        sorted_by_rank = sorted(chunks, key=lambda c: get_source_authority(c)[0])
        best_chunk = dict(sorted_by_rank[0])
        rank, weight = get_source_authority(best_chunk)
        best_chunk["authority_rank"] = rank
        best_chunk["authority_weight"] = weight
        best_chunk["contradiction_status"] = "fallback_authoritative"
        filtered_chunks.append(best_chunk)

    contradiction_detected = len(conflicts_detected) > 0
    chosen_authority_rank = min(winning_ranks) if winning_ranks else 1

    conflict_metadata = {
        "contradiction_detected": contradiction_detected,
        "contradiction_resolved_via": "authority_hierarchy" if contradiction_detected else "none",
        "conflicting_sources": sorted(list(conflicting_sources)),
        "chosen_authority_rank": chosen_authority_rank,
        "conflicts_count": len(conflicts_detected),
        "conflicts": conflicts_detected,
    }

    return filtered_chunks, conflict_metadata
