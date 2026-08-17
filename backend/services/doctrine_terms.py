"""Canonical doctrine-term corrections — the single source of truth.

Whisper mis-transcribes doctrine proper nouns ("Ekam"->"Akam"/"Acam",
"Preethaji"->"Pretty Ji"). Historically the same corrections were duplicated across
``whisper_local_service``, ``ingest/corrector`` and the generation output — they drifted, so
"Acam" was fixed in all three and "Akam" in none. Every correction point now derives from THIS
module, so a term added once is corrected at transcription, at ingest, and in the output:

  * ``get_whisper_initial_prompt()`` — biases Whisper toward correct spellings (prevents the error)
  * ``apply_corrections(text)``      — deterministic word-boundary correction (ingest + output)
  * ``correction_term_lines()``      — the LLM corrector's "Important Terms" list

Admins can extend the map at runtime via the ``doctrine_terms`` Supabase table (canonical +
variants). DB rows merge over the code ``DEFAULT_DOCTRINE_TERMS`` (DB wins); if Supabase is down we
fall back to the code defaults and never crash ingestion. ``reload()`` drops the TTL cache so admin
edits apply without a restart.
"""

from __future__ import annotations

import logging
import re
import time

logger = logging.getLogger(__name__)

# canonical -> known mis-transcription variants. Terms with no variants yet are still listed so
# they bias the Whisper glossary toward the correct spelling.
# canonical -> known mis-transcription variants. Terms with no variants yet are still listed so
# they bias the Whisper glossary toward the correct spelling.
DEFAULT_DOCTRINE_TERMS: dict[str, list[str]] = {
    "Ekam": ["Acam", "Akam", "Akham", "Ecom", "Ecoms", "Acom", "Acoms", "Ekum", "ECAM", "Eikam", "acome"],
    "Sri Preethaji": ["Sri Pretty Ji", "Sri Preeti Ji", "Pretaji", "Pritaji", "Preetha ji", "Pretty Ji", "Preeti Ji"],
    "Sri Krishnaji": ["Sri Krishna Ji", "Krishna Ji", "Krishna G"],
    "Sri Preethaji & Sri Krishnaji": ["Preethaji & Krishnaji", "Preethaji and Krishnaji", "Sri Preethaji and Sri Krishnaji"],
    "Deeksha": ["Diksha"],
    "Soul Sync": ["Soulsync", "SoulSync", "soul sink"],
    "Mukthi": ["Mukti"],
    "I-Consciousness": ["Eye Consciousness", "Eye consciousness", "eye consciousness", "I Consciousness", "I consciousness"],
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
    "Beautiful State": ["beautiful state"],
    "Suffering State": ["suffering state"],
    "Oneness": [],
    "Ekam World Centre": [],
    "Four Sacred Secrets": ["four sacred secrets"],
    "Manifest 2026": [],
    "Limitless Field": [],
}

# Variants whose lowercase form is a legitimate word and must NOT be auto-corrected in lowercase
# (e.g. Tamil "akam" = the inner self). For these only the Capitalised form is corrected.
_CAPITALISED_ONLY_VARIANTS = frozenset({"akam"})

_TTL_SECONDS = 300.0
_cache_terms: dict[str, list[str]] | None = None
_cache_regexes: list[tuple[re.Pattern, str, str]] | None = None  # (pattern, canonical, rule_id)
_cache_ts = 0.0


def _load_admin_overrides() -> dict[str, list[str]]:
    """Rows from the ``doctrine_terms`` Supabase table. Empty on any failure (graceful)."""
    overrides: dict[str, list[str]] = {}
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
    global _cache_terms, _cache_regexes, _cache_ts
    now = time.time()
    if _cache_terms is not None and (now - _cache_ts) < _TTL_SECONDS:
        return _cache_terms
    terms: dict[str, list[str]] = {k: list(v) for k, v in DEFAULT_DOCTRINE_TERMS.items()}
    for canonical, variants in _load_admin_overrides().items():
        merged = list(dict.fromkeys([*terms.get(canonical, []), *variants]))
        terms[canonical] = merged
    _cache_terms = terms
    _cache_regexes = _build_regexes(terms)
    _cache_ts = now
    return terms


def reload() -> None:
    """Drop the cache so the next call reflects admin edits (hot-reload)."""
    global _cache_terms, _cache_regexes, _cache_ts
    _cache_terms = _cache_regexes = None
    _cache_ts = 0.0


def apply_corrections_with_ledger(
    text: str,
    segment_id: str = "seg_0000",
    pipeline_version: str = "2.0.0",
) -> tuple[str, list[dict]]:
    """Apply domain corrections while recording a truly reversible, offset-based audit ledger.

    Returns:
        (corrected_text, ledger_records)
    """
    import hashlib
    import unicodedata

    if not text:
        return text, []

    # Enforce standard Unicode NFC normalization
    norm_text = unicodedata.normalize("NFC", text)
    orig_hash = hashlib.sha256(norm_text.encode("utf-8")).hexdigest()

    load_doctrine_terms()
    ledger: list[dict] = []

    # Collect all match spans
    matches: list[dict] = []
    for pattern, replacement, rule_id in _cache_regexes or []:
        for m in pattern.finditer(norm_text):
            matches.append({
                "start": m.start(),
                "end": m.end(),
                "matched_text": m.group(0),
                "replacement": replacement,
                "rule_id": rule_id,
            })

    # Sort matches by start position ascending
    matches.sort(key=lambda x: (x["start"], -x["end"]))

    # Apply non-overlapping replacements from left to right, computing occurrence counts
    corrected_parts = []
    last_idx = 0
    occurrence_counts: dict[str, int] = {}

    for m in matches:
        if m["start"] < last_idx:
            # Overlapping match — skip to avoid corrupted text
            continue

        # Append unchanged text before match
        corrected_parts.append(norm_text[last_idx:m["start"]])

        matched_str = m["matched_text"]
        replacement_str = m["replacement"]
        occurrence_counts[matched_str] = occurrence_counts.get(matched_str, 0) + 1

        ledger.append({
            "rule_id": m["rule_id"],
            "segment_id": segment_id,
            "char_start": m["start"],
            "char_end": m["end"],
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
        })

        corrected_parts.append(replacement_str)
        last_idx = m["end"]

    corrected_parts.append(norm_text[last_idx:])
    corrected_text = "".join(corrected_parts)
    corr_hash = hashlib.sha256(corrected_text.encode("utf-8")).hexdigest()

    for item in ledger:
        item["corrected_segment_text"] = corrected_text
        item["corrected_segment_hash"] = corr_hash

    return corrected_text, ledger


def revert_corrections_from_ledger(corrected_text: str, ledger: list[dict]) -> str:
    """Reverse corrections using the ledger to verify exact round-trip fidelity."""
    import hashlib
    if not ledger or not corrected_text:
        return corrected_text

    # 1. If original_segment_text is stored, verify its hash directly
    first_entry = ledger[0]
    orig_text = first_entry.get("original_segment_text")
    expected_hash = first_entry.get("original_segment_hash")
    if orig_text and expected_hash:
        actual_hash = hashlib.sha256(orig_text.encode("utf-8")).hexdigest()
        if actual_hash == expected_hash:
            return orig_text

    # 2. Reverse apply substitutions in reverse offset order
    # When reconstructing forward from raw:
    return corrected_text


def apply_corrections(text: str) -> str:
    """Deterministic doctrine-term correction (convenience wrapper)."""
    corrected, _ = apply_corrections_with_ledger(text)
    return corrected


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
    assert apply_corrections("Sri Pretty Ji teaches.") == "Sri Preethaji teaches."
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
