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
DEFAULT_DOCTRINE_TERMS: dict[str, list[str]] = {
    "Ekam": ["Acam", "Akam", "Akham", "Ecom", "Ecoms", "Acom", "Acoms", "Ekum", "ECAM", "Eikam", "acome"],
    "Sri Preethaji": ["Sri Pretty Ji", "Sri Preeti Ji", "Pretaji", "Pritaji", "Preetha ji"],
    "Preethaji": ["Pretty Ji", "Preeti Ji"],
    "Sri Krishnaji": ["Sri Krishna Ji"],
    "Krishnaji": ["Krishna Ji", "Krishna G"],
    "Deeksha": ["Diksha"],
    "Soul Sync": ["Soulsync", "SoulSync", "soul sink"],
    "Mukthi": ["Mukti"],
    "Sadhana": [],
    "the Beautiful State": [],
    "Oneness": [],
    "Ekam World Centre": [],
    "the Four Sacred Secrets": [],
    "Manifest 2026": [],
    "Limitless Field": [],
}

# Variants whose lowercase form is a legitimate word and must NOT be auto-corrected in lowercase
# (e.g. Tamil "akam" = the inner self). For these only the Capitalised form is corrected.
_CAPITALISED_ONLY_VARIANTS = frozenset({"akam"})

_TTL_SECONDS = 300.0
_cache_terms: dict[str, list[str]] | None = None
_cache_regexes: list[tuple[re.Pattern, str]] | None = None
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


def _build_regexes(terms: dict[str, list[str]]) -> list[tuple[re.Pattern, str]]:
    """Compile word-boundary variant->canonical rules. Case rule lives ONLY here."""
    out: list[tuple[re.Pattern, str]] = []
    for canonical, variants in terms.items():
        for v in variants:
            if not v:
                continue
            # Capitalised form -> canonical (always safe; it is a proper noun there).
            out.append((re.compile(rf"\b{re.escape(v)}\b"), canonical))
            low = v.lower()
            # Lowercase form -> lowercase canonical, UNLESS it is a real word (Tamil "akam" etc.).
            if low != v and low not in _CAPITALISED_ONLY_VARIANTS:
                out.append((re.compile(rf"\b{re.escape(low)}\b"), canonical.lower()))
    return out


def apply_corrections(text: str) -> str:
    """Deterministic doctrine-term correction. Used by the ingest corrector and the output cleanup."""
    if not text:
        return text
    load_doctrine_terms()  # ensures _cache_regexes is populated
    for pattern, replacement in _cache_regexes or []:
        text = pattern.sub(replacement, text)
    return text


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
    assert "Ekam" in get_whisper_initial_prompt()
    assert "misheard" in correction_term_lines()
    print("doctrine_terms self-check: all asserts passed")
