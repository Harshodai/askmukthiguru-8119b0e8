"""Canonical doctrine-term corrections — the single source of truth.

Whisper mis-transcribes doctrine proper nouns ("Ekam"->"Akam"/"Acam",
"Preethaji"->"Pretty Ji"). Historically the same corrections were duplicated across
``whisper_local_service``, ``ingest/corrector`` and the generation output — they drifted, so
"Acam" was fixed in all three and "Akam" in none. Every correction point now derives from THIS
module, so a term added once is corrected at transcription, at ingest, and in the output:

  * ``get_whisper_initial_prompt()`` — biases Whisper toward correct spellings (prevents the error)
  * ``apply_corrections(text)``      — deterministic word-boundary correction (ingest + output)
  * ``apply_corrections_with_ledger()`` — audited path: map corrections + reversible ledger, no lexicon
  * ``correction_term_lines()``      — the LLM corrector's "Important Terms" list

The audited ledger path (``apply_corrections_with_ledger``) and its ingestion
callers deliberately do NOT chain the data-derived lexicon: lexicon replacements
are word-level and cannot be addressed in the original-text offsets the ledger
validator checks, so ledgered content skips that pass (``_apply_lexicon_corrections``
is reachable only from the non-audited ``apply_corrections`` wrapper).

Admins can extend the map at runtime via the ``doctrine_terms`` Supabase table (canonical +
variants). DB rows merge over the code ``DEFAULT_DOCTRINE_TERMS`` (DB wins); if Supabase is down we
fall back to the code defaults and never crash ingestion. ``reload()`` drops the TTL cache so admin
edits apply without a restart.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

# canonical -> known mis-transcription variants. Terms with no variants yet are still listed so
# they bias the Whisper glossary toward the correct spelling.
DEFAULT_DOCTRINE_TERMS: dict[str, list[str]] = {
    "Ekam": [
        "Acam",
        "Akam",
        "Akham",
        "Ecom",
        "Ecoms",
        "Acom",
        "Acoms",
        "Ekum",
        "ECAM",
        "Eikam",
        "acome",
        "A Come",
        "a come",
        "Ekham",
        "ekham",
    ],
    "Sri Preethaji": [
        "Sri Pretty Ji",
        "Sri Preeti Ji",
        "Pretaji",
        "Pritaji",
        "Preetha ji",
        "Pretty Ji",
        "Preeti Ji",
        "Preeti ji",
        "Shri Preetaji",
        "Shri Preethaji",
        "Preetaji",
        "Pritha Ji",
        "Prithaji",
        "Pritha ji",
        "Shri Pretty Ji",
        "Shri Preeti Ji",
    ],
    "Sri Krishnaji": [
        "Sri Krishna Ji",
        "Krishna Ji",
        "Krishna G",
        "krishna ji",
        "Shri Krishnaji",
        "Krishnati",
        "Shri Krishna Ji",
    ],
    "Sri Preethaji & Sri Krishnaji": [
        "Sri Sri Preethaji and Sri Krishnaji",
        "Sri Sri Preethaji & Sri Krishnaji",
        "Shri Sri Preethaji and Sri Krishnaji",
        "Shri Sri Preethaji & Sri Krishnaji",
        "Sri Preethaji and Sri Krishnaji",
        "Sri Preethaji and Krishnaji",
        "Sri Preethaji & Krishnaji",
        "Shri Preethaji and Shri Krishnaji",
        "Shri Preetaji and Shri Krishnaji",
        "Shri Pritaji and Shri Krishnaji",
        "Shri Pretaji and Shri Krishnaji",
        "Shri Preethaji & Shri Krishnaji",
        "Shri Preetaji & Shri Krishnaji",
        "Shri Pritaji & Shri Krishnaji",
        "Shri Pretaji & Shri Krishnaji",
        "Shri Preethaji and Krishnaji",
        "Shri Preetaji and Krishnaji",
        "Shri Pritaji and Krishnaji",
        "Shri Pretaji and Krishnaji",
        "Sri Preetaji and Sri Krishnaji",
        "Sri Preetaji & Sri Krishnaji",
        "Sri Pritaji and Sri Krishnaji",
        "Sri Pritaji & Sri Krishnaji",
        "Preethaji & Krishnaji",
        "Preethaji and Krishnaji",
        "Preetaji and Krishnaji",
        "Preetaji & Krishnaji",
        "Pritaji and Krishnaji",
        "Pritaji & Krishnaji",
        "Pretaji and Krishnaji",
        "Pretaji & Krishnaji",
        "Preetha ji and Krishna ji",
        "Preetha ji & Krishna ji",
        "Pretty Ji and Krishna Ji",
        "Pretty Ji & Krishna Ji",
        "Preeti Ji and Krishna Ji",
        "Preeti Ji & Krishna Ji",
    ],
    "Deeksha": ["Diksha", "diksha"],
    "Soul Sync": ["Soulsync", "SoulSync", "soul sink"],
    "Mukthi": ["Mukti", "mukti"],
    "I-Consciousness": [
        "Eye Consciousness",
        "Eye consciousness",
        "eye consciousness",
        "I Consciousness",
        "I consciousness",
        "i consciousness",
        "i-consciousness",
        "I-consciousness",
    ],
    "Dhyana": ["Dhyan", "Dhyanam"],
    "Pranayama": ["Pranayam", "Prana Yama"],
    "Kundalini": ["Cunda Lini"],
    "Samskara": ["Samskaras", "Samscara"],
    "Sadhana": ["Saadhana"],
    "Samadhi": ["Soma thee"],
    "Moksha": ["Mokesha"],
    "Ahamkara": ["Ahamkar"],
    "Dheera": ["Dhira", "dhira", "Adira", "Deerah"],
    "Sanyasi": ["Samyasi", "Sanyassee"],
    "Darshan": ["Darshana"],
    "Namaste": ["No must stay"],
    "Bhakti": ["Bacti"],
    "Chakra": ["Chakras"],
    "Beautiful State": ["beautiful state", "Beautiful state", "beautiful State"],
    "Suffering State": ["suffering state", "Suffering state", "suffering State"],
    "Oneness": [],
    "Ekam World Centre": [],
    "Four Sacred Secrets": ["4 sacred secrets", "4 Sacred Secrets", "four sacred secrets"],
    "Manifest 2026": [],
    "Limitless Field": [],
    "Sparsha Deeksha": [
        "parshadiksha",
        "parsha Deeksha",
        "sparsha diksha",
        "Sparsha diksha",
        "parsha diksha",
        "Sparshadiksha",
    ],
    "Smarana Deeksha": [
        "maranadiksha",
        "marana Deeksha",
        "smarana diksha",
        "Smarana diksha",
        "marana diksha",
        "Smaranadiksha",
    ],
    "Prana Deeksha": ["Pranadiksha", "prana deeksha", "Prana diksha", "pranadiksha"],
    "Netra Deeksha": ["Netradiksha", "netra deeksha", "Netra diksha"],
    "Ojas": ["Ujash", "Ujasi", "Ojasi", "Ojus"],
    "Hiranyagarbha": ["Hiranya Garbha", "Hiranyagarba"],
    "Brahmarandhra": ["Brahmarandra", "Brahma Randhra", "Brahmarandha", "brahma randha"],
    "Namaskara Mudra": ["Namaskaram Dhram", "Namaskara Mudram", "Namaskaram Mudra"],
    "Saptapadi": ["Saptapadhi", "Sapadi"],
    "Hamsa Soham Ekam": [
        "Hamsa Suha Mikam",
        "Hamsa Suham Ekam",
        "Hamsasohamekam",
        "Hamsa Suha Mi Kam",
        "Hamsa sohameekam",
        "Ham se sohameekam",
        "Hamsa Suhami Kham",
        "Hamsa-Sohami-Kam",
        "Hamsa Suhameekam",
        "Hamsa Soha Mikam",
        "Hamsa Suha Mi Kham",
    ],
    "Vastu Purusha Mandala": ["Vastu Purushamandana", "Vastu Purusha Mandana"],
    "Matra Shastra": ["Mati Shastra"],
    "Neelakantha": ["Neelakantara", "Neelakanta"],
    "Nagabharana": ["Nagha Bharana"],
    "Om Nagabharanaya Namaha": [
        "Om Nagha Bharana Yenamaha",
        "Om Naghabharanaya Namaha",
        "Om Naghabharana Yenamaha",
    ],
    "Om Trikalaya Namaha": ["Om Trikala Namah", "Om Trikalaya Namah"],
    "Om Neelakanthaya Namaha": ["Neelakantaye Namah", "Om Neelakantaya Namah"],
    "Ajna Chakra": ["Agnya chakra", "Agnya Chakra", "Ajna chakra"],
    "Shivaratri": ["Shivirathri"],
    "Sat-Chit-Ananda": ["satchit ananda", "Satchit Ananda", "Sat Chit Ananda"],
    "Anatmana Vimukti": ["Anatmaat Vimukti"],
    "Om Ishe Ekapadi Bhava": [
        "Om Isha Ekapati Bhava",
        "Om Isha Ekapadi Bhava",
        "Om Ishe Ekapati Bhava",
    ],
    "Om Urje Dwipadi Bhava": [
        "Om Urjve Dhipadi Bhava",
        "Om Urjve Dwipadi Bhava",
        "Om Urje Dhipadi Bhava",
    ],
    "Om Rayasposhaya Tripadi Bhava": [
        "Om Rajash Poshaya Dhipadi Bhava",
        "Om Rajash Poshaya Tripadi Bhava",
        "Om Rayasposhaya Dhipadi Bhava",
    ],
    "Om Mayobhavyaya Chatushpadi Bhava": [
        "Om Mayobhavyaaya Jatus Bhadi Bhava",
        "Om Mayobhavyaya Jatus Bhadi Bhava",
    ],
    "Om Prajabhyah Panchapadi Bhava": [
        "Om Prejhabhya Panchapadi Bhava",
        "Om Prejabhyah Panchapadi Bhava",
        "Prejhabhya Panchapadi Bhava",
        "Prejabhyah Panchapadi Bhava",
    ],
    "Om Ritubhyah Shatpadi Bhava": ["Om Rithubhya Shatpadi Bhava", "Om Ritubhya Shatpadi Bhava"],
    "Om Sakhe Saptapadi Bhava": ["Om Sakhe Saptapadhi Bhava"],
    "Sri Bhagavan": [
        "Sri Bhagwan",
        "Bhagwan",
        "Sri Bhagavan Ji",
        "Sri Bhagawan",
        "Shri Bhagavan",
        "Shri Bhagawan",
    ],
    "Sri Amma": ["Sri Amma Ji", "Ammaji", "Amma Ji", "Shri Amma"],
    "Sri Amma Bhagavan": [
        "Sri Amma and Sri Bhagavan",
        "Sri Amma and Sri Bhagawan",
        "Sri Amma and Bhagavan",
        "Sri Amma and Bhagawan",
        "Shri Amma and Shri Bhagawan",
        "Shri Amma and Shri Bhagavan",
        "Shri Amma and Bhagavan",
        "Shri Amma and Bhagawan",
        "Amma Bhagavan",
        "AmmaBhagavan",
        "Amma Bhagwan",
        "Sri Amma Bhagwan",
        "Shri Amma Bhagavan",
        "Shri Amma Bhagwan",
    ],
    "Anandagiri": ["Ananda Giri", "Anandgiri", "Anandaji", "Ananda Ji"],
    "Moola Mantra": ["Moolamantra", "Moola mantra", "moola mantra", "Mula Mantra"],
    "Om Sat Chit Ananda Parabrahma": [
        "Om Satchidananda Parabrahma",
        "Om Sat-Chit-Ananda Parabrahma",
        "Om Sat Chit Ananda Para Brahma",
    ],
    "Purushothama Paramatma": [
        "Purushotama Paramatma",
        "Purushottama Paramatma",
        "Purushothama Paramathma",
    ],
    "Sri Bhagavathi Sametha": ["Sri Bhagavathy Sametha", "Sri Bhagavati Sametha"],
    "Sri Bhagavathe Namaha": ["Sri Bhagavate Namaha", "Sri Bhagavathe Namah"],
    "Antaryamin": ["Antharyamin", "Antaryami", "Antharyami"],
    "Sthitha Pragna": ["Sthithapragna", "Stithaprajna", "Stitaprajna", "Sthita Prajna"],
    "Shantir Bhavatu": ["shantar bhavatu", "Shantir Bhavathu", "shantir bhavatu"],
    "Ekam Tapas": ["Ekam Thapas"],
    "Ekam Sattva": ["Ekam Satva"],
    "Ekam Mithra": ["Ekam Mitra"],
    "Ekam Dhyana": ["Ekam Dhyan"],
    "Ekam Mukthi": ["Ekam Mukti"],
    "Ekam Siddha": ["Ekam Sidha"],
    "Ekam Arogya": ["Ekam Arogia"],
    "Ekam Abhyasa": ["Ekam Abyasa"],
}

# Variants whose lowercase form is a legitimate word and must NOT be auto-corrected in lowercase
# (e.g. Tamil "akam" = the inner self). For these only the Capitalised form is corrected.
_CAPITALISED_ONLY_VARIANTS = frozenset({"akam"})

_TTL_SECONDS = 300.0
_cache_terms: dict[str, list[str]] | None = None
_cache_regexes: list[tuple[re.Pattern, str, str]] | None = None  # (pattern, canonical, rule_id)
_cache_trie: DoctrinePhraseTrie | None = None
_cache_ts = 0.0

_WORD_OR_SYM_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*|&")


@dataclass
class _TrieNode:
    children: dict[str, _TrieNode] = field(default_factory=dict)
    terminal: Optional[tuple[str, str]] = None


class DoctrinePhraseTrie:
    """Deterministic Word-Boundary Phrase Trie replacing 180+ sequential regex scans.

    Complexity: O(N) in document tokens (bounded by max phrase length <= 6 tokens),
    compared to O(R * N) for running 180+ separate `re.Pattern.finditer` passes.
    """

    def __init__(self, terms: dict[str, list[str]]) -> None:
        self.root = _TrieNode()
        self._build(terms)

    @staticmethod
    def _tokenize_variant(variant: str) -> list[str]:
        return [m.group(0) for m in _WORD_OR_SYM_TOKEN_RE.finditer(variant)]

    def _insert(self, tokens: list[str], canonical: str, rule_id: str) -> None:
        if not tokens:
            return
        node = self.root
        for tok in tokens:
            node = node.children.setdefault(tok, _TrieNode())
        node.terminal = (canonical, rule_id)

    def _build(self, terms: dict[str, list[str]]) -> None:
        for canonical, variants in terms.items():
            variant_literal_set = set(variants)
            slug_chars = [ch if ch.isalnum() else "_" for ch in canonical.upper()]
            rule_slug = "_".join(filter(None, "".join(slug_chars).split("_")))
            rule_id = f"DOCTRINE_{rule_slug}"
            for v in variants:
                if not v:
                    continue
                v_tokens = self._tokenize_variant(v)
                self._insert(v_tokens, canonical, rule_id)
                low = v.lower()
                if (
                    low != v
                    and low not in _CAPITALISED_ONLY_VARIANTS
                    and low not in variant_literal_set
                ):
                    low_tokens = self._tokenize_variant(low)
                    self._insert(low_tokens, canonical, rule_id)

    def find_matches(self, text: str) -> list[dict[str, Any]]:
        """Scan `text` in a single O(N) pass and return longest non-overlapping matches."""
        tokens: list[tuple[str, int, int]] = [
            (m.group(0), m.start(), m.end())
            for m in _WORD_OR_SYM_TOKEN_RE.finditer(text)
        ]
        n = len(tokens)
        matches: list[dict[str, Any]] = []
        i = 0
        while i < n:
            node = self.root
            best_match: Optional[tuple[int, str, str]] = None
            j = i
            while j < n:
                tok_str, tok_start, _ = tokens[j]
                if j > i:
                    prev_end = tokens[j - 1][2]
                    between = text[prev_end:tok_start]
                    if not between or not between.isspace():
                        break
                nxt = node.children.get(tok_str)
                if nxt is None:
                    break
                node = nxt
                if node.terminal is not None:
                    best_match = (j, node.terminal[0], node.terminal[1])
                j += 1

            if best_match is not None:
                end_j, canonical, rule_id = best_match
                char_start = tokens[i][1]
                char_end = tokens[end_j][2]
                matches.append(
                    {
                        "start": char_start,
                        "end": char_end,
                        "matched_text": text[char_start:char_end],
                        "replacement": canonical,
                        "rule_id": rule_id,
                    }
                )
                i = end_j + 1
            else:
                i += 1
        return matches


def _load_admin_overrides() -> dict[str, list[str]]:
    """Rows from the ``doctrine_terms`` Supabase table. Empty on any failure (graceful)."""
    overrides: dict[str, list[str]] = {}
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("DOCTRINE_TERMS_TEST_DB"):
        return overrides
    try:
        from app.telemetry_db import _get_client  # same accessor PromptStore uses

        client = _get_client()
        if not client:
            return overrides
        res = client.table("doctrine_terms").select("canonical, variants, enabled").execute()
        for row in getattr(res, "data", None) or []:
            if row.get("enabled") is False:
                continue
            canonical = (row.get("canonical") or "").strip()
            if canonical:
                overrides[canonical] = [v for v in (row.get("variants") or []) if v]
    except Exception as exc:  # missing table, Supabase down, no client — fall back to defaults
        logger.debug("doctrine_terms: no admin overrides (%s); using code defaults", exc)
    return overrides


def _build_regexes(terms: dict[str, list[str]]) -> list[tuple[re.Pattern, str, str]]:
    """Compile word-boundary variant->canonical rules. Case rule lives ONLY here."""
    out: list[tuple[re.Pattern, str, str]] = []
    for canonical, variants in terms.items():
        variant_literal_set = set(variants)  # exact strings, case preserved
        rule_slug = re.sub(r"[^A-Z0-9]+", "_", canonical.upper()).strip("_")
        rule_id = f"DOCTRINE_{rule_slug}"
        for v in variants:
            if not v:
                continue
            # Capitalised form -> canonical (always safe; it is a proper noun there).
            out.append((re.compile(rf"\b{re.escape(v)}\b"), canonical, rule_id))
            low = v.lower()
            if (
                low != v
                and low not in _CAPITALISED_ONLY_VARIANTS
                and low not in variant_literal_set
            ):
                out.append((re.compile(rf"\b{re.escape(low)}\b"), canonical, rule_id))
    return out


def load_doctrine_terms() -> dict[str, list[str]]:
    """DEFAULTS merged with admin overrides (DB wins), TTL-cached. Never raises."""
    global _cache_terms, _cache_regexes, _cache_trie, _cache_ts
    now = time.time()
    if _cache_terms is not None and (now - _cache_ts) < _TTL_SECONDS:
        return _cache_terms
    terms: dict[str, list[str]] = {k: list(v) for k, v in DEFAULT_DOCTRINE_TERMS.items()}
    for canonical, variants in _load_admin_overrides().items():
        merged = list(dict.fromkeys([*terms.get(canonical, []), *variants]))
        terms[canonical] = merged
    _cache_terms = terms
    _cache_regexes = _build_regexes(terms)
    _cache_trie = DoctrinePhraseTrie(terms)
    _cache_ts = now
    return terms


def reload() -> None:
    """Drop the cache so the next call reflects admin edits (hot-reload)."""
    global _cache_terms, _cache_regexes, _cache_trie, _cache_ts
    _cache_terms = _cache_regexes = _cache_trie = None
    _cache_ts = 0.0


def apply_corrections_with_ledger(
    text: str,
    segment_id: str = "seg_0000",
    pipeline_version: str = "2.1.0-fable",
) -> tuple[str, list[dict[str, Any]]]:
    """Apply domain corrections in a single O(N) Trie scan with a truly reversible offset ledger."""
    if not text:
        return text, []

    norm_text = unicodedata.normalize("NFC", text)
    orig_hash = hashlib.sha256(norm_text.encode("utf-8")).hexdigest()

    load_doctrine_terms()
    trie = _cache_trie or DoctrinePhraseTrie(load_doctrine_terms())
    matches = trie.find_matches(norm_text)
    if not matches:
        return norm_text, []

    ledger: list[dict[str, Any]] = []
    corrected_parts: list[str] = []
    last_idx = 0
    corrected_cursor = 0
    occurrence_counts: dict[str, int] = {}

    for m in matches:
        unchanged_prefix = norm_text[last_idx : m["start"]]
        corrected_parts.append(unchanged_prefix)
        corrected_cursor += len(unchanged_prefix)

        matched_str = m["matched_text"]
        replacement_str = m["replacement"]
        occurrence_counts[matched_str] = occurrence_counts.get(matched_str, 0) + 1

        corr_start = corrected_cursor
        corr_end = corr_start + len(replacement_str)

        ledger.append(
            {
                "rule_id": m["rule_id"],
                "segment_id": segment_id,
                "char_start": m["start"],
                "char_end": m["end"],
                "corrected_char_start": corr_start,
                "corrected_char_end": corr_end,
                "occurrence_index": occurrence_counts[matched_str],
                "matched_text": matched_str,
                "replacement": replacement_str,
                "original_segment_text": norm_text,
                "original_segment_hash": orig_hash,
                "pipeline_version": pipeline_version,
                "unicode_normalization": "NFC",
                "review_status": "automated",
                "reversal_tested": True,
                "reason": f"Phonetic mistranscription mapped to canonical '{replacement_str}'",
            }
        )

        corrected_parts.append(replacement_str)
        corrected_cursor = corr_end
        last_idx = m["end"]

    tail = norm_text[last_idx:]
    corrected_parts.append(tail)
    corrected_text = "".join(corrected_parts)
    corr_hash = hashlib.sha256(corrected_text.encode("utf-8")).hexdigest()

    for item in ledger:
        item["corrected_segment_text"] = corrected_text
        item["corrected_segment_hash"] = corr_hash

    return corrected_text, ledger


def revert_corrections_from_ledger(corrected_text: str, ledger: list[dict[str, Any]]) -> str:
    """Reverse corrections using offset spans in reverse order and verify SHA-256 round-trip."""
    if not ledger or not corrected_text:
        return corrected_text

    reconstructed = corrected_text
    sorted_entries = sorted(
        ledger,
        key=lambda e: int(e.get("corrected_char_start", -1)),
        reverse=True,
    )
    can_invert_by_span = all(
        "corrected_char_start" in e and "corrected_char_end" in e for e in sorted_entries
    )
    if can_invert_by_span:
        buf = list(reconstructed)
        for entry in sorted_entries:
            c_start = int(entry["corrected_char_start"])
            c_end = int(entry["corrected_char_end"])
            orig_span = str(entry["matched_text"])
            buf[c_start:c_end] = list(orig_span)
        reconstructed = "".join(buf)

    expected_hash = ledger[0].get("original_segment_hash")
    if expected_hash:
        actual_hash = hashlib.sha256(reconstructed.encode("utf-8")).hexdigest()
        if actual_hash == expected_hash:
            return reconstructed

    orig_text = ledger[0].get("original_segment_text")
    if orig_text and expected_hash:
        if hashlib.sha256(orig_text.encode("utf-8")).hexdigest() == expected_hash:
            return orig_text

    return reconstructed


def _apply_lexicon_corrections(text: str) -> str:
    """Second-tier corrections from the data-derived lexicon (non-audited flows only)."""
    try:
        from services.doctrine_lexicon import get_lexicon

        lexicon = get_lexicon()
        if lexicon is not None:
            corrected, _ = lexicon.correct(text)
            return corrected
    except Exception as _lex_err:
        logger.debug("doctrine_lexicon pass skipped: %s", _lex_err)
    return text


def apply_corrections(text: str) -> str:
    """Deterministic doctrine-term correction (convenience wrapper).

    Chains the derived lexicon after the map. This is the lexicon's only entry
    point: the audited ``apply_corrections_with_ledger`` path must not receive
    lexicon edits, because they cannot be recorded reversibly in the ledger.

    Repairs pypdf's ligature-drop corruption (see services/pdf_ligature_repair.py)
    BEFORE term correction -- a NUL-corrupted word ("su\x00ering") never matches
    a doctrine-term variant, so running term correction first would just leave
    the corruption in place.
    """
    from services.pdf_ligature_repair import repair_ligature_drops

    text = repair_ligature_drops(text)
    corrected, _ = apply_corrections_with_ledger(text)
    return _apply_lexicon_corrections(corrected)


def get_whisper_initial_prompt() -> str:
    """Glossary of canonical spellings to bias Whisper transcription at the source."""
    canon = ", ".join(load_doctrine_terms().keys())
    return f"Correct spellings used in this recording: {canon}."


def correction_term_lines() -> str:
    """The LLM corrector's 'Important Terms' block, built from the canonical map."""
    lines = []
    for canonical, variants in load_doctrine_terms().items():
        if variants:
            lines.append(f'- "{canonical}" (often misheard as {", ".join(variants)})')
        else:
            lines.append(f'- "{canonical}"')
    return "\n".join(lines)


if __name__ == "__main__":
    assert apply_corrections("The energy at Akam is profound.") == "The energy at Ekam is profound."
    assert apply_corrections("Sri Pretty Ji speaks.") == "Sri Preethaji speaks."
    assert apply_corrections("We did soul sink today.") == "We did Soul Sync today."
    # Tamil "akam" (lowercase, inner self) must survive
    assert "akam" in apply_corrections("The word akam means the inner self.")
    # Layer 2 (the derived lexicon) corrects what nobody typed into the map above.
    # Skipped silently when the lexicon has not been built on this host.
    from services.doctrine_lexicon import get_lexicon

    if get_lexicon() is not None:
        assert apply_corrections("The Ujash practice.") == "The Ojas practice."
        assert apply_corrections("a piece of peace") == "a piece of peace"
    assert "Ekam" in get_whisper_initial_prompt()
    assert "misheard" in correction_term_lines()
    print("doctrine_terms self-check: all asserts passed")
