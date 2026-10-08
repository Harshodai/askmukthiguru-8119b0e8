"""L-INDIC-INTERNAL-EN-1: graph generates/verifies in English once the query was translated."""

from app.language_utils import internal_pipeline_language as f


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
