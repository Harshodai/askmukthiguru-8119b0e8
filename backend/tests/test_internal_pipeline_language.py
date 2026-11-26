"""L-INDIC-INTERNAL-EN-1: graph generates/verifies in English once the query was translated."""

from app.language_utils import detect_message_lang
from app.language_utils import internal_pipeline_language as f


def test_detect_message_lang_typography_and_scripts():
    # Em-dash and curly quotes must not classify English as non_en
    assert detect_message_lang("One must overcome fear — it is an inward journey.") == "en"
    assert detect_message_lang("“The beautiful state is a state of connection.”") == "en"
    # IAST Sanskrit letters (Latin Extended Additional)
    assert detect_message_lang("Sri Kṛṣṇa teaches the path of wisdom.") == "en"
    # Indic scripts
    assert detect_message_lang("శాంతిని ఎలా పొందాలి?") == "te"
    assert detect_message_lang("शान्ति कैसे प्राप्त करें?") == "hi"
    # Non-Latin foreign scripts
    assert detect_message_lang("你好世界") == "non_en"
    assert detect_message_lang("Привет мир") == "non_en"


def test_translated_hindi_runs_graph_in_english():
    assert f("hi", "सुंदर अवस्था क्या है?", "What is the beautiful state?") == "en"


def test_translated_telugu_runs_graph_in_english():
    assert f("te", "సుందర స్థితి అంటే ఏమిటి?", "What is the beautiful state?") == "en"


def test_failed_translation_keeps_seeker_language():
    q = "सुंदर अवस्था क्या है?"
    assert f("hi", q, q) == "hi"


def test_english_and_hinglish_untouched():
    assert f("en", "what is joy", "what is joy") == "en"
    assert f("hinglish", "mera mann ashaant hai", "my mind is restless") == "hinglish"
