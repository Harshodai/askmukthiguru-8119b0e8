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


def test_apply_corrections_also_runs_the_derived_lexicon():
    """The map above is hand-typed, so it only ever covers what someone thought of.

    "Ojas" is a real Ekam practice name that nobody added, so the corpus kept
    "Ujash"/"Ujasi"/"Ojasi" from the same video that spelt it right 15 times.
    apply_corrections must therefore chain the derived lexicon after the map —
    otherwise the lexicon exists but corrects nothing, which is exactly the
    failure mode this file was written to catch.
    """
    import services.doctrine_terms as module
    from services.doctrine_lexicon import get_lexicon

    src = Path(module.__file__).read_text(encoding="utf-8")
    assert "doctrine_lexicon" in src, (
        "apply_corrections no longer routes through the derived lexicon; the "
        "hand-typed map alone cannot cover variants nobody typed."
    )

    if get_lexicon() is None:
        return  # lexicon not built on this host — the fallback path, tested below
    assert apply_corrections("The Ujash practice.") == "The Ojas practice."
    assert apply_corrections("Ojasi meditation") == "Ojas meditation"


def test_derived_lexicon_never_rewrites_ordinary_english():
    """Precision is the property that matters: a false positive corrupts doctrine.

    These pairs are the ones that broke earlier designs — `piece`/`peace` scores
    HIGHER on similarity (0.880) than `ujash`/`ojas` (0.783), so no threshold can
    separate them. Only vocabulary coverage can.
    """
    from services.doctrine_lexicon import get_lexicon

    if get_lexicon() is None:
        return
    for word in ("peace", "piece", "soar", "steel", "bodhi", "citta", "soul", "shield"):
        assert apply_corrections(f"the {word} here") == f"the {word} here", (
            f"{word!r} — ordinary English — was rewritten"
        )


def test_missing_lexicon_degrades_to_the_curated_map(monkeypatch):
    """A fresh checkout has no built lexicon. That must cost recall, never a crash."""
    import services.doctrine_lexicon as lex

    monkeypatch.setattr(lex, "_SHARED", None)
    monkeypatch.setattr(lex, "_LOAD_FAILED", False)
    monkeypatch.setattr(lex, "LEXICON_PATH", Path("/nonexistent/doctrine_lexicon.json"))
    assert lex.get_lexicon() is None
    assert apply_corrections("At Akam we practice.") == "At Ekam we practice."
    lex.reload_lexicon()


def test_whisper_initial_prompt_contains_all_canonical_mantras_and_names():
    prompt = get_whisper_initial_prompt()
    required_terms = [
        "Ekam",
        "Sri Preethaji",
        "Sri Krishnaji",
        "Sri Bhagavan",
        "Sri Amma",
        "Sri Amma Bhagavan",
        "Anandagiri",
        "Hamsa Soham Ekam",
        "Om Ishe Ekapadi Bhava",
        "Om Urje Dwipadi Bhava",
        "Om Rayasposhaya Tripadi Bhava",
        "Om Mayobhavyaya Chatushpadi Bhava",
        "Om Prajabhyah Panchapadi Bhava",
        "Om Ritubhyah Shatpadi Bhava",
        "Om Sakhe Saptapadi Bhava",
        "Moola Mantra",
        "Om Sat Chit Ananda Parabrahma",
        "Purushothama Paramatma",
        "Sri Bhagavathi Sametha",
        "Sri Bhagavathe Namaha",
        "Sparsha Deeksha",
        "Smarana Deeksha",
        "Prana Deeksha",
        "Netra Deeksha",
    ]
    for term in required_terms:
        assert term in prompt, f"Expected {term!r} in Whisper initial prompt: {prompt}"


def test_apply_corrections_with_ledger_mantras_and_names():
    from services.doctrine_terms import apply_corrections_with_ledger

    text = "We chant Hamsa Suha Mikam and Om Isha Ekapati Bhava before Sri Bhagwan and Ammaji."
    corrected, ledger = apply_corrections_with_ledger(text, segment_id="seg_mantra_01")
    assert "Hamsa Soham Ekam" in corrected
    assert "Om Ishe Ekapadi Bhava" in corrected
    assert "Sri Bhagavan" in corrected
    assert "Sri Amma" in corrected
    assert len(ledger) == 4

    rule_ids = {entry["rule_id"] for entry in ledger}
    assert "DOCTRINE_HAMSA_SOHAM_EKAM" in rule_ids
    assert "DOCTRINE_OM_ISHE_EKAPADI_BHAVA" in rule_ids
    assert "DOCTRINE_SRI_BHAGAVAN" in rule_ids
    assert "DOCTRINE_SRI_AMMA" in rule_ids


def test_ledger_reversal_round_trip():
    from services.doctrine_terms import (
        apply_corrections_with_ledger,
        revert_corrections_from_ledger,
    )

    original = "At Akam with Sri Pretty Ji we chanted Hamsa Suham Ekam and performed parshadiksha."
    corrected, ledger = apply_corrections_with_ledger(original, segment_id="seg_reversal_01")
    assert "Ekam" in corrected
    assert "Sri Preethaji" in corrected
    assert "Hamsa Soham Ekam" in corrected
    assert "Sparsha Deeksha" in corrected
    assert len(ledger) == 4

    reverted = revert_corrections_from_ledger(corrected, ledger)
    assert reverted == original


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
