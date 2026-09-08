"""Tests for unified language detection with Hinglish support."""

from services.language_detection import detect_language


class TestHindiScript:
    def test_devanagari_detected_as_hi(self):
        result = detect_language("नमस्ते, आप कैसे हैं?")
        assert result["language"] == "hi"
        assert result["confidence"] == 0.95
        assert result["is_code_switched"] is False

    def test_telugu_detected_as_te(self):
        result = detect_language("తెలుగు లో చెప్పండి")
        assert result["language"] == "te"
        assert result["confidence"] == 0.95

    def test_kannada_detected_as_kn(self):
        result = detect_language("ಕನ್ನಡದಲ್ಲಿ ಹೇಳಿ")
        assert result["language"] == "kn"
        assert result["confidence"] == 0.95

    def test_tamil_detected_as_ta(self):
        result = detect_language("தமிழில் பதிலளிக்கவும்")
        assert result["language"] == "ta"
        assert result["confidence"] == 0.95

    def test_bengali_detected_as_bn(self):
        result = detect_language("বাংলায় উত্তর দিন")
        assert result["language"] == "bn"
        assert result["confidence"] == 0.95

    def test_gujarati_detected_as_gu(self):
        result = detect_language("ગુજરાતીમાં જવાબ આપો")
        assert result["language"] == "gu"
        assert result["confidence"] == 0.95

    def test_malayalam_detected_as_ml(self):
        result = detect_language("മലയാളത്തിൽ മറുപടി നൽകുക")
        assert result["language"] == "ml"
        assert result["confidence"] == 0.95


class TestEnglish:
    def test_plain_english(self):
        result = detect_language("What is the meaning of stillness?")
        assert result["language"] == "en"
        assert result["confidence"] == 0.8
        assert result["is_code_switched"] is False

    def test_english_hello(self):
        result = detect_language("Hello how are you")
        assert result["language"] == "en"


class TestHinglish:
    def test_meditation_kaise(self):
        result = detect_language("Mujhe meditation kaise karni chahiye?")
        assert result["language"] == "hi"
        assert result["is_code_switched"] is True
        assert result["confidence"] > 0.5

    def test_aap_kaise_ho(self):
        result = detect_language("Aap kaise ho? Main theek hoon")
        assert result["language"] == "hi"
        assert result["is_code_switched"] is True

    def test_karma_ek_achha(self):
        result = detect_language("karma ek achha concept hai")
        assert result["language"] == "hi"
        assert result["is_code_switched"] is True

    def test_low_hindi_ratio_stays_english(self):
        result = detect_language("just one word yoga")
        assert result["language"] == "en"
        assert result["is_code_switched"] is False


class TestUserPreference:
    def test_preference_tiebreaker_low_confidence(self):
        result = detect_language("meditation helps", user_preference="hi")
        assert result["language"] == "hi"

    def test_preference_not_overriding_high_confidence(self):
        result = detect_language("नमस्ते", user_preference="en")
        assert result["language"] == "hi"

    def test_preference_hinglish_not_overridden(self):
        result = detect_language("mujhe karna hai", user_preference="en")
        assert result["language"] == "hi"
        assert result["is_code_switched"] is True


class TestEdgeCases:
    def test_empty_string(self):
        result = detect_language("")
        assert result["language"] == "en"
        assert result["confidence"] == 0.3
        assert result["is_code_switched"] is False

    def test_whitespace_only(self):
        result = detect_language("   ")
        assert result["language"] == "en"
        assert result["confidence"] == 0.3

    def test_none_equivalent(self):
        result = detect_language("")
        assert result["language"] == "en"
