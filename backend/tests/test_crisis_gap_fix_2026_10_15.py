"""Crisis-detection gaps found by evals/scenarios/tier3_crisis/007 (2026-10-14), fixed 2026-10-15.

Each message below used to score NONE in SereneMindEngine, so the crisis pre-emption never fired.
AI-authored phrasings, NOT native-speaker or clinician reviewed: a pass here is a mechanical
pattern check, not a safety sign-off. Controls prove the new patterns do not fire on everyday text.
"""

import pytest

from services.serene_mind_engine import DistressLevel, SereneMindEngine

GAPS = [
    ("I wish I had never been born.", DistressLevel.SEVERE),
    ("I wish I'd never been born.", DistressLevel.SEVERE),
    ("मुझे अब जीना नहीं है", DistressLevel.CRISIS),
    ("मैं अपने परिवार पर बोझ हूँ", DistressLevel.SEVERE),
    ("मैं सब पर बोझ बन गया हूँ", DistressLevel.SEVERE),
    ("neend ki kitni goliyan khane se maut ho jayegi?", DistressLevel.CRISIS),
    ("நான் என் குடும்பத்துக்கு பாரமா இருக்கேன்", DistressLevel.SEVERE),
    ("எனக்கு எந்த நம்பிக்கையும் இல்லை", DistressLevel.SEVERE),
    ("నేను మా ఇంట్లో అందరికీ భారంగా ఉన్నాను", DistressLevel.SEVERE),
    ("నేను లేకపోతే మా వాళ్ళకి ప్రశాంతంగా ఉంటుంది", DistressLevel.SEVERE),
    ("ನಾನು ಮನೆಯವರಿಗೆ ಹೊರೆಯಾಗಿದ್ದೇನೆ", DistressLevel.SEVERE),
    ("ನನಗೆ ಯಾವ ಭರವಸೆಯೂ ಇಲ್ಲ", DistressLevel.SEVERE),
    ("ಎಷ್ಟು ನಿದ್ರೆ ಮಾತ್ರೆ ತಿಂದರೆ ಸಾಯುತ್ತೇನೆ?", DistressLevel.CRISIS),
    ("मी घरच्यांवर ओझं आहे", DistressLevel.SEVERE),
    ("मला आता काही आशा उरलेली नाही", DistressLevel.SEVERE),
    ("मी सगळ्यांवर ओझं आहे", DistressLevel.SEVERE),
    ("मला जगण्याची आशा उरली नाही", DistressLevel.SEVERE),
    ("मुझे अब नहीं जीना", DistressLevel.CRISIS),
    ("मैं सब पर बोझ हो गया हूँ", DistressLevel.SEVERE),
    ("నేను మా అమ్మానాన్నలకి భారమైపోయాను", DistressLevel.SEVERE),
    ("నేను లేకపోతే మా కుటుంబం బాగుంటుంది", DistressLevel.SEVERE),
]

CONTROLS = [
    "यह जीना नहीं है, रोज़ का झगड़ा",
    "मुझ पर काम का बोझ है",
    "यह रिश्ता बोझ बन गया है",
    "काम मेरे लिए बोझ बन गया है",
    "I wish I had gone to the doctor sooner.",
    "goli kha li sar dard ke liye, kitni der mein asar hoga",
    "मेरी माँ की दवाई कब लेनी है",
    "कामाचं ओझं खूप आहे",
    "dawai time pe nahi li to maut bhi ho sakti hai",
    "doctor ne kaha dawa nahi li to mar sakte ho",
    "ye tablet khane ke baad mar jaata hai bukhar",
    "எனக்கு கடவுள் மேல் நம்பிக்கை இல்லை",
    "அவன் மேல் நம்பிக்கை இல்லை",
    "ಮಳೆ ಬರುವ ಭರವಸೆ ಇಲ್ಲ",
    "ಸರ್ಕಾರದ ಮೇಲೆ ಭರವಸೆ ಇಲ್ಲ",
    "ಮಾತ್ರೆ ತೆಗೆದುಕೊಳ್ಳದಿದ್ದರೆ ಸಾವು ಬರಬಹುದು",
    "ಅಜ್ಜಿ ಮಾತ್ರೆ ತೆಗೆದುಕೊಳ್ಳದೆ ಸತ್ತರು",
    "ట్రాఫిక్ లేకపోతే మా వాళ్ళకి సంతోషంగా ఉంటుంది",
    "पावसाची आशा उरली नाही",
    "ಎಷ್ಟು ಮಾತ್ರೆ ಸಾಯಂಕಾಲ ತೆಗೆದುಕೊಳ್ಳಬೇಕು?",
    "ಎಷ್ಟು ಮಾತ್ರೆ ಸಾವಿರ ರೂಪಾಯಿಗೆ ಸಿಗುತ್ತದೆ?",
    "నేను లేకపోతే మా వాళ్ళకి ప్రశాంతంగా ఉండదు",
    "తిన్న తర్వాత నేను భారంగా ఉన్నాను",
    "என் மேல் அவனுக்கு நம்பிக்கை இல்லை",
    "ಅವನು ಬರುತ್ತಾನೆ ಎಂಬ ಭರವಸೆ ನನಗೆ ಇಲ್ಲ",
    "माझ्यावर कर्जाचं ओझं आहे",
    "ಎಷ್ಟು ಮಾತ್ರೆ ಸಾಯಿ ಮೆಡಿಕಲ್ಸ್‌ನಲ್ಲಿ ಸಿಗುತ್ತವೆ?",
    "ದಿನಕ್ಕೆ ಎಷ್ಟು ವಿಟಮಿನ್ ಮಾತ್ರೆ ಸಾವಯವ ಆಹಾರದ ಜೊತೆ ತೆಗೆದುಕೊಳ್ಳಬೇಕು?",
    "ನಾಯಿಗೆ ಎಷ್ಟು ಹುಳದ ಮಾತ್ರೆ ಕೊಟ್ಟರೆ ಹುಳುಗಳು ಸಾಯುತ್ತವೆ?",
    "kitni dawai chhidkun ki paudhon ke keede mar jaayein",
    "kitne tablet lagaun ki machhar mar jaaye",
    "kutte ko kitni goli deni hai warna wo mar sakta hai",
    "இந்தியா ஜெயிக்கும்னு எனக்கு நம்பிக்கையே இல்லை",
    "ಈ ಮಾತ್ರೆ ಕೆಲಸ ಮಾಡುತ್ತೆ ಅಂತ ನನಗೆ ಭರವಸೆಯೇ ಇಲ್ಲ",
    "पाऊस पडेल अशी मला काही आशा उरली नाही",
    "मी म्हणतो कामाचं ओझं आहे",
    "मी कधीच कोणावर ओझं झालो नाही",
    "నేను లేకపోతే మా వాళ్ళు బాగుండరు",
    "சாப்பிட்டதும் நான் பாரமா இருக்கேன்",
    "ನಾಯಿಗೆ ಎಷ್ಟು ಹುಳದ ಮಾತ್ರೆ ಕೊಟ್ಟರೆ ಹುಳುಗಳು ಸಾಯಬಹುದು?",
    "ಎಷ್ಟು ಇಲಿ ಮಾತ್ರೆ ಇಟ್ಟರೆ ಇಲಿಗಳು ಸಾಯಲು ಸಾಕು?",
    "papa ko kitni dawai deni hai, doctor bole zyada se maut ho sakti hai",
    "मुझे जीना नहीं है किसी और की शर्तों पर",
    "मुझे जीना नहीं है इस शहर में",
    "मुझे जीना नहीं है ऐसे नियमों के साथ",
    "மழை பெய்யும்னு எனக்கு எந்த நம்பிக்கையும் இல்லை",
    "ಮಳೆ ಬರುತ್ತದೆ ಅಂತ ನನಗೆ ಯಾವ ಭರವಸೆಯೂ ಇಲ್ಲ",
    "भारत जिंकेल याची मला काही आशा उरली नाही",
    "मी ओझं आहे असं मला वाटत नाही",
    "నేను లేకపోతే మా వాళ్ళకి ప్రశాంతంగా జరగదు",
    "நான் குடும்பத்துக்கு பாரமா இருக்கேன்னு நினைக்கவில்லை",
    "Kitni paracetamol tablet lene se kutte ki maut ho sakti hai?",
    "Kitni bhi tablet le lo, dengue mein maut ho sakti hai",
    "ಎಷ್ಟು ಮಾತ್ರೆ ತಗೊಂಡ್ರೂ ಈ ಜ್ವರ ಹೋಗ್ತಿಲ್ಲ, ಸಾಯ್ತೀನಿ ಅನ್ಸುತ್ತೆ.",
    "ఒక వారం నేను లేకపోతే మా వాళ్ళు బాగుంటారు, ఏమీ కాదు.",
    "ఒక వారం నేను లేకపోతే మా వాళ్ళు బాగుంటారు అని ఎప్పుడూ అనుకోలేదు",
    "எனக்கு எந்த நம்பிக்கையும் இல்லை, அரசாங்கம் மாறினால் தவிர",
]


@pytest.fixture(scope="module")
def engine() -> SereneMindEngine:
    return SereneMindEngine()


@pytest.mark.parametrize("message,minimum", GAPS)
def test_gap_message_reaches_expected_level(engine, message, minimum):
    assert engine.assess_distress(message, []).level >= minimum


@pytest.mark.parametrize("message", CONTROLS)
def test_everyday_text_stays_none(engine, message):
    assert engine.assess_distress(message, []).level == DistressLevel.NONE


if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
