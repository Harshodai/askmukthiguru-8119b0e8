from services.context_compressor import _estimate_tokens

# Tamil (U+0B80-0BFF) — ~1 char ≈ 1 token, never 0.25.
_TAMIL_SAMPLE = (
    "அன்பே ஓர் ஆன்மீக பயணம். தியானம் என்பது மனதை அமைதிப்படுத்தும் வழி. வாழ்க்கை ஒரு பயணம்; அதை அன்புடன் வாழ்க."
)
_TELUGU_SAMPLE = "ప్రేమ ఒక ఆధ్యాత్మిక ప్రయాణం. ధ్యానం అనేది మనస్సును ప్రశాంతపరిచే మార్గం. జీవితం ఒక ప్రయాణం."


def test_tamil_token_estimate():
    # 4000-char Tamil answer: len//4 would estimate 1000 tokens, but Tamil
    # tokenizes at ~1 char/token. Fix must estimate >= 2000 (len//2).
    text = (_TAMIL_SAMPLE * 200)[:4000]
    assert len(text) == 4000
    estimate = _estimate_tokens(text)
    assert estimate >= 2000
    assert estimate <= 2000, "Tamil estimate should be exactly len//2"


def test_english_token_estimate():
    # 4000-char English: len//4 semantics must be preserved (~1000 tokens).
    text = ("The path of meditation is a journey of the heart and mind. " * 100)[:4000]
    assert len(text) == 4000
    estimate = _estimate_tokens(text)
    assert 800 <= estimate <= 1200


def test_mixed_script_estimate():
    # Mixed Latin + Indic: estimate must sit between the pure-English and
    # pure-Indic bounds (conservative: uses the Indic factor).
    tamil_estimate = _estimate_tokens(_TAMIL_SAMPLE)
    english_estimate = _estimate_tokens("The path of meditation is a journey.")
    mixed = "The path of meditation: " + _TAMIL_SAMPLE
    mixed_estimate = _estimate_tokens(mixed)
    assert english_estimate <= mixed_estimate <= tamil_estimate + len("The path of meditation: ")


def test_indic_factor_applies_to_all_major_scripts():
    # Every Indic script the app ships must use the 2-char factor, not 4.
    for sample in (_TAMIL_SAMPLE, _TELUGU_SAMPLE):
        estimate = _estimate_tokens(sample)
        assert estimate == len(sample) // 2, f"sample should estimate len//2, got {estimate}"


def test_empty_text_estimates_one_token():
    assert _estimate_tokens("") == 1
