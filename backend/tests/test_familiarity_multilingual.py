"""P1-AI-13 — multilingual familiarity classification.

Covers the two changes:
1. Raw-script Indic terms (Tamil "தீட்சா", etc.) now hit the advanced-keyword
   list directly, so non-EN queries are not defaulted to "Seeker" when the
   upstream translation path did not run (EN-preferred user typing Indic
   script; ``should_translate`` False).
2. Existing English keyword paths are unchanged.

The graph passes the translated-EN query to the classifier via
``question=user_msg_en`` (GraphStage), so Indic-preferred users are
classified on English text; the Indic variants cover the untranslated
residual path.
"""

from rag.nodes.generation import classify_user_familiarity


def test_tamil_deeksha_advanced():
    """Raw Tamil deeksha query -> Advanced Meditator (was Seeker)."""
    assert classify_user_familiarity("தீட்சா", []) == "Advanced Meditator"


def test_telugu_deeksha_advanced():
    """Raw Telugu deeksha query -> Advanced Meditator."""
    assert classify_user_familiarity("దీక్ష ఎలా ఇస్తారు", []) == "Advanced Meditator"


def test_hindi_devanagari_deeksha_advanced():
    """Raw Devanagari deeksha query -> Advanced Meditator."""
    assert classify_user_familiarity("दीक्षा क्या है", []) == "Advanced Meditator"


def test_tamil_meditation_practitioner():
    """Raw Tamil meditation term -> Practitioner (not Seeker)."""
    assert classify_user_familiarity("தியானம் எப்படி", []) == "Practitioner"


def test_english_keyword_still_works():
    """English advanced keyword path unchanged."""
    assert classify_user_familiarity("tell me about deeksha", []) == "Advanced Meditator"


def test_english_practitioner_still_works():
    """English practitioner keyword path unchanged."""
    assert classify_user_familiarity("I want a meditation instruction", []) == "Practitioner"


def test_seeker_default_unchanged():
    """Unrelated text still defaults to Seeker."""
    assert classify_user_familiarity("hello, how are you?", []) == "Seeker"
