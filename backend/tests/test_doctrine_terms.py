"""'Never again' guard for doctrine-term corrections.

The Akam->Ekam leak happened because the same corrections were duplicated across whisper,
the ingest corrector and the output cleanup — they drifted. These tests enforce the single
source of truth (services.doctrine_terms) and fail CI if a local correction dict is
re-introduced anywhere.
"""

from pathlib import Path

from services.doctrine_terms import (
    DEFAULT_DOCTRINE_TERMS,
    apply_corrections,
    correction_term_lines,
    get_whisper_initial_prompt,
)

_BACKEND = Path(__file__).resolve().parents[1]


def test_every_variant_is_corrected_to_its_canonical():
    for canonical, variants in DEFAULT_DOCTRINE_TERMS.items():
        for v in variants:
            out = apply_corrections(f"start {v} end")
            assert canonical in out, f"{v!r} was not corrected to {canonical!r}: {out!r}"


def test_tamil_akam_lowercase_is_preserved():
    # "akam" (lowercase) is the Tamil word for the inner self — must NOT become "ekam".
    out = apply_corrections("The word akam means the inner self.")
    assert "akam" in out and "ekam" not in out.lower()


def test_capitalised_proper_noun_is_corrected():
    assert apply_corrections("At Akam we practice.") == "At Ekam we practice."


def test_db_down_falls_back_to_code_defaults():
    # apply_corrections must never raise when Supabase is unavailable (it is, in tests).
    assert apply_corrections("Sri Pretty Ji at Akam") == "Sri Preethaji at Ekam"


def test_whisper_prompt_and_llm_term_lines_derive_from_source():
    assert "Ekam" in get_whisper_initial_prompt()
    assert "Sri Preethaji" in correction_term_lines()


def test_no_stray_correction_dicts_in_call_sites():
    """The three correction points must route through doctrine_terms — no local dicts.
    This fails loudly if someone re-introduces a `REPLACEMENTS`/`FAST_REPLACEMENTS` map,
    which is exactly how the Akam drift happened."""
    for rel, banned in [
        ("services/whisper_local_service.py", ("REPLACEMENTS = {",)),
        ("ingest/corrector.py", ("FAST_REPLACEMENTS = {", "REPLACEMENTS = {")),
        ("rag/nodes/generation.py", ("REPLACEMENTS = {", "FAST_REPLACEMENTS = {")),
    ]:
        src = (_BACKEND / rel).read_text(encoding="utf-8")
        for token in banned:
            assert token not in src, (
                f"{rel} re-introduced a local correction dict ({token!r}). Use "
                f"services.doctrine_terms.apply_corrections instead."
            )
        assert "doctrine_terms" in src, f"{rel} no longer imports the shared doctrine_terms source"


if __name__ == "__main__":
    for _name, _fn in list(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            _fn()
    print("doctrine-terms 'never again' guard: all asserts passed")
