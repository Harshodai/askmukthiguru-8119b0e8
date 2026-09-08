import logging
from dataclasses import dataclass
from enum import Enum

from services.language_detection import detect_language

logger = logging.getLogger(__name__)


class LanguageCode(str, Enum):
    EN = "en"
    HI = "hi"  # Hindi (Devanagari)
    TA = "ta"  # Tamil
    TE = "te"  # Telugu
    KN = "kn"  # Kannada
    ML = "ml"  # Malayalam
    BN = "bn"  # Bengali
    GU = "gu"  # Gujarati
    MR = "mr"  # Marathi
    PA = "pa"  # Punjabi
    OR = "or"  # Odia
    UR = "ur"  # Urdu
    AS = "as"  # Assamese
    MAI = "mai"  # Maithili
    SA = "sa"  # Sanskrit
    KS = "ks"  # Kashmiri
    NE = "ne"  # Nepali
    SD = "sd"  # Sindhi
    KOK = "kok"  # Konkani
    DOI = "doi"  # Dogri
    MNI = "mni"  # Manipuri
    SAT = "sat"  # Santali
    BRX = "brx"  # Bodo
    HINGLISH = "hinglish"  # Code-mixed Hindi-English
    TANGLISH = "tanglish"  # Code-mixed Tamil-English


@dataclass
class LanguageDetection:
    primary: LanguageCode
    confidence: float
    is_codemixed: bool
    scripts_detected: list[str]
    recommendation: str  # Which model/prompt variant to use


class LanguageRouter:
    """
    Multi-script language detection for Indian languages.

    Handles:
    - Pure script detection (Devanagari, Tamil, etc.)
    - Code-mixed detection (Hinglish, Tanglish)
    - Romanized Indic text (transliterated Hindi, Tamil)
    - Language routing to appropriate model
    """

    # Unicode script ranges
    SCRIPT_RANGES = {
        "Devanagari": ("\u0900", "\u097f"),  # Hindi, Marathi, Sanskrit
        "Tamil": ("\u0b80", "\u0bff"),
        "Telugu": ("\u0c00", "\u0c7f"),
        "Kannada": ("\u0c80", "\u0cff"),
        "Bengali": ("\u0980", "\u09ff"),
        "Gujarati": ("\u0a80", "\u0aff"),
        "Gurmukhi": ("\u0a00", "\u0a7f"),  # Punjabi
        "Malayalam": ("\u0d00", "\u0d7f"),
    }

    # Code-mixed indicators
    HINGLISH_PATTERNS = [
        r"\b(kya|kaise|kyun|kyunki|agar|lekin|par|aur|nahi|haan|hoon|hai|tha|thi|"
        r"acha|theek|bas|yaar|bhai|dost|dil|mann|zindagi|khush|dukhi|pyaar|"
        r"shanti|sukh|dukh|moksha|atma|parmatma|jeevan|karma|dharma)\b",
    ]

    TANGLISH_PATTERNS = [
        r"\b(enna|epdi|yaaru|ennaachu|seri|kadavul|anbu|santhosam|"
        r"dukkam|manasu|uyir|vaazhkai|aanandham|shanthi)\b",
    ]

    def detect(self, text: str) -> LanguageDetection:
        """Detect language with confidence score.

        Delegates to the shared ``detect_language()`` utility and maps the
        result into the ``LanguageDetection`` dataclass expected by callers.
        """
        result = detect_language(text)
        lang_code = result["language"]
        is_code_switched = result["is_code_switched"]
        confidence = result["confidence"]
        scripts = self._detect_scripts(text)

        # Map shared-utility language code to LanguageCode enum.
        # detect_language() returns "hi" for both Devanagari Hindi and
        # Hinglish; "ta" for both Tamil script and Tanglish.
        # is_code_switched distinguishes the two.
        if lang_code == "hi" and is_code_switched:
            primary = LanguageCode.HINGLISH
        elif lang_code == "ta" and is_code_switched:
            primary = LanguageCode.TANGLISH
        elif lang_code == "hi":
            primary = LanguageCode.HI
        elif lang_code == "ta":
            primary = LanguageCode.TA
        else:
            try:
                primary = LanguageCode(lang_code)
            except ValueError:
                primary = LanguageCode.EN

        recommendation = f"sarvam-30b-{primary.value}"

        return LanguageDetection(
            primary=primary,
            confidence=confidence,
            is_codemixed=is_code_switched,
            scripts_detected=scripts,
            recommendation=recommendation,
        )

    def _detect_scripts(self, text: str) -> list[str]:
        """Detect which Unicode scripts are present in text."""
        scripts = []
        for script_name, (start, end) in self.SCRIPT_RANGES.items():
            if any(start <= c <= end for c in text):
                scripts.append(script_name)
        return scripts

    def get_system_prompt_suffix(self, lang: LanguageCode) -> str:
        """
        Get language-specific instruction suffix for system prompts.
        Ensures the guru responds in the user's language.
        """
        suffixes = {
            LanguageCode.EN: "",
            LanguageCode.HI: "\n\nमहत्वपूर्ण: हमेशा हिंदी में जवाब दें। संस्कृत शब्दों (धर्म, कर्म, মোক্ষ, आत्मा) को जैसे हैं वैसे ही रखें।",
            LanguageCode.TA: "\n\nமுக்கியம்: எப்போதும் தமிழில் பதிலளிக்கவும். சமஸ்கிருத சொற்கள் (தர்மம், கர்மா, மோட்சம்) அப்படியே வைத்திருக்கவும்.",
            LanguageCode.TE: "\n\nముఖ్యం: ఎల్లప్పుడూ తెలుగులో సమాధానం ఇవ్వండి. సంస్కృత పదాలను (ధర్మ, కర్మ, మోక్ష) అలాగే ఉంచండి.",
            LanguageCode.KN: "\n\nಮುಖ್ಯ: ಯಾವಾಗಲೂ ಕನ್ನಡದಲ್ಲಿ ಉತ್ತರಿಸಿ. ಸಂಸ್ಕೃತ ಪದಗಳನ್ನು (ಧರ್ಮ, ಕರ್ಮ, ಮೋಕ್ಷ) ಹಾಗೆಯೇ ಉಳಿಸಿ.",
            LanguageCode.ML: "\n\nപ്രധാനമാണ്: എല്ലായ്പ്പോഴും മലയാളത്തിൽ മറുപടി നൽകുക. സംസ്കൃത പദങ്ങൾ (ധർമ്മ, കർമ്മ, മോക്ഷ) അതേപടി നിലനിർത്തുക.",
            LanguageCode.BN: "\n\nগুরুত্বপূর্ণ: সবসময় বাংলায় উত্তর দিন। সংস্কৃত শব্দগুলি (ধর্ম, কর্ম, মোক্ষ) অপরিবর্তিত রাখুন।",
            LanguageCode.GU: "\n\nમહત્વપૂર્ણ: હંમેશા ગુજરાતીમાં જવાબ આપો. સંસ્કૃત શબ્દો (ધર્મ, કર્મ, મોક્ષ) જેમ છે તેમ રાખો.",
            LanguageCode.MR: "\n\nमहत्त्वाचे: नेहमी मराठीत उत्तर द्या. संस्कृत शब्द (धर्म, कर्म, मोक्ष) तसेच ठेवा.",
            LanguageCode.PA: "\n\nਮਹੱਤਵਪੂਰਨ: ਹਮੇਸ਼ਾ ਪੰਜਾਬੀ ਵਿੱਚ ਜਵਾਬ ਦਿਓ। ਸੰਸਕ੍ਰਿਤ ਸ਼ਬਦਾਂ (ਧਰਮ, ਕਰਮ, ਮੋਕਸ਼) ਨੂੰ ਜਿਵੇਂ ਹਨ ਤਿਵੇਂ ਰੱਖੋ।",
            LanguageCode.OR: "\n\nଗୁରୁତ୍ୱପୂର୍ଣ୍ଣ: ସବୁବେଳେ ଓଡ଼ିଆରେ ଉତ୍ତର ଦିଅନ୍ତୁ। ସଂସ୍କୃତ ଶବ୍ଦଗୁଡ଼ିକ (ଧର୍ମ, କର୍ମ, ମୋକ୍ଷ) ଅପରିବର୍ତ୍ତିତ ରଖନ୍ତୁ।",
            LanguageCode.UR: "\n\nاہم: ہمیشہ اردو میں جواب دیں۔ سنسکرت الفاظ (دھرم، کرم، موکش) کو جوں کا توں رکھیں۔",
            LanguageCode.AS: "\n\nগুৰুত্বপূর্ণ: সদায় অসমীয়াত উত্তৰ দিয়ক। সংস্কৃত শব্দ (ধর্ম, কর্ম, মোক্ষ) একেদৰে ৰাখক।",
            LanguageCode.MAI: "\n\nमहत्वपूर्ण: सदिखन मैथिलीमे उत्तर दिअ। संस्कृत शब्द (धर्म, कर्म, मोक्ष) जेकाँ अछि तेकाँ राखू।",
            LanguageCode.SA: "\n\nमहत्त्वपूर्णम्: सर्वदा संस्कृतेन उत्तरं ददातु। धर्म, कर्म, मोक्ष इत्यादीनि पदानि यथावत् स्थापयतु।",
            LanguageCode.KS: "\n\nImportant: Always reply in Kashmiri. Preserve Sanskrit spiritual terms such as dharma, karma, and moksha as-is.",
            LanguageCode.NE: "\n\nमहत्त्वपूर्ण: सधैं नेपालीमा जवाफ दिनुहोस्। संस्कृत शब्दहरू (धर्म, कर्म, मोक्ष) यथावत् राख्नुहोस्।",
            LanguageCode.SD: "\n\nImportant: Always reply in Sindhi. Preserve Sanskrit spiritual terms such as dharma, karma, and moksha as-is.",
            LanguageCode.KOK: "\n\nमहत्त्वाचें: सदांच कोंकणींत जाप दिवची. संस्कृत उतरां (धर्म, कर्म, मोक्ष) तशींच दवरचीं.",
            LanguageCode.DOI: "\n\nImportant: Always reply in Dogri. Preserve Sanskrit spiritual terms such as dharma, karma, and moksha as-is.",
            LanguageCode.MNI: "\n\nImportant: Always reply in Manipuri. Preserve Sanskrit spiritual terms such as dharma, karma, and moksha as-is.",
            LanguageCode.SAT: "\n\nImportant: Always reply in Santali. Preserve Sanskrit spiritual terms such as dharma, karma, and moksha as-is.",
            LanguageCode.BRX: "\n\nImportant: Always reply in Bodo. Preserve Sanskrit spiritual terms such as dharma, karma, and moksha as-is.",
            LanguageCode.HINGLISH: "\n\nIMPORTANT: Reply in Hinglish (Hindi-English mix) using the same style as the user. Spiritual Sanskrit terms ko as-is rakho.",
        }
        return suffixes.get(lang, "")
