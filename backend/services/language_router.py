
import re
import logging
from enum import Enum
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

class LanguageCode(str, Enum):
    EN = "en"
    HI = "hi"           # Hindi (Devanagari)
    TA = "ta"           # Tamil
    TE = "te"           # Telugu
    KN = "kn"           # Kannada
    ML = "ml"           # Malayalam
    BN = "bn"           # Bengali
    GU = "gu"           # Gujarati
    MR = "mr"           # Marathi
    PA = "pa"           # Punjabi
    OR = "or"           # Odia
    UR = "ur"           # Urdu
    AS = "as"           # Assamese
    MAI = "mai"         # Maithili
    SA = "sa"           # Sanskrit
    KS = "ks"           # Kashmiri
    NE = "ne"           # Nepali
    SD = "sd"           # Sindhi
    KOK = "kok"         # Konkani
    DOI = "doi"         # Dogri
    MNI = "mni"         # Manipuri
    SAT = "sat"         # Santali
    BRX = "brx"         # Bodo
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
        "Devanagari": ("\u0900", "\u097F"),   # Hindi, Marathi, Sanskrit
        "Tamil": ("\u0B80", "\u0BFF"),
        "Telugu": ("\u0C00", "\u0C7F"),
        "Kannada": ("\u0C80", "\u0CFF"),
        "Malayalam": ("\u0D00", "\u0D7F"),
        "Bengali": ("\u0980", "\u09FF"),
        "Gujarati": ("\u0A80", "\u0AFF"),
        "Gurmukhi": ("\u0A00", "\u0A7F"),    # Punjabi
    }
    
    # Code-mixed indicators
    HINGLISH_PATTERNS = [
        r'\b(kya|kaise|kyun|kyunki|agar|lekin|par|aur|nahi|haan|hoon|hai|tha|thi|'
        r'acha|theek|bas|yaar|bhai|dost|dil|mann|zindagi|khush|dukhi|pyaar|'
        r'shanti|sukh|dukh|moksha|atma|parmatma|jeevan|karma|dharma)\b',
    ]
    
    TANGLISH_PATTERNS = [
        r'\b(enna|epdi|yaaru|ennaachu|seri|kadavul|anbu|santhosam|'
        r'dukkam|manasu|uyir|vaazhkai|aanandham|shanthi)\b',
    ]
    
    def detect(self, text: str) -> LanguageDetection:
        """Detect language with confidence score."""
        scripts = self._detect_scripts(text)
        
        # Pure script-based detection
        if "Devanagari" in scripts:
            return LanguageDetection(
                primary=LanguageCode.HI,
                confidence=0.95,
                is_codemixed=False,
                scripts_detected=scripts,
                recommendation="sarvam-30b-devanagari",
            )
        elif "Tamil" in scripts:
            return LanguageDetection(
                primary=LanguageCode.TA,
                confidence=0.95,
                is_codemixed=False,
                scripts_detected=scripts,
                recommendation="sarvam-30b-tamil",
            )
        elif "Telugu" in scripts:
             return LanguageDetection(
                primary=LanguageCode.TE,
                confidence=0.95,
                is_codemixed=False,
                scripts_detected=scripts,
                recommendation="sarvam-30b-telugu",
            )
        elif "Kannada" in scripts:
             return LanguageDetection(
                primary=LanguageCode.KN,
                confidence=0.95,
                is_codemixed=False,
                scripts_detected=scripts,
                recommendation="sarvam-30b-kannada",
            )
        elif "Malayalam" in scripts:
             return LanguageDetection(
                primary=LanguageCode.ML,
                confidence=0.95,
                is_codemixed=False,
                scripts_detected=scripts,
                recommendation="sarvam-30b-malayalam",
            )
        elif "Bengali" in scripts:
             return LanguageDetection(
                primary=LanguageCode.BN,
                confidence=0.95,
                is_codemixed=False,
                scripts_detected=scripts,
                recommendation="sarvam-30b-bengali",
            )
        elif "Gujarati" in scripts:
             return LanguageDetection(
                primary=LanguageCode.GU,
                confidence=0.95,
                is_codemixed=False,
                scripts_detected=scripts,
                recommendation="sarvam-30b-gujarati",
            )
        elif "Gurmukhi" in scripts:
             return LanguageDetection(
                primary=LanguageCode.PA,
                confidence=0.95,
                is_codemixed=False,
                scripts_detected=scripts,
                recommendation="sarvam-30b-punjabi",
            )
        
        # Code-mixed detection for Roman text
        text_lower = text.lower()
        
        hinglish_score = sum(1 for p in self.HINGLISH_PATTERNS if re.search(p, text_lower))
        tanglish_score = sum(1 for p in self.TANGLISH_PATTERNS if re.search(p, text_lower))
        
        if hinglish_score >= 2:
            return LanguageDetection(
                primary=LanguageCode.HINGLISH,
                confidence=min(0.5 + hinglish_score * 0.1, 0.9),
                is_codemixed=True,
                scripts_detected=["Latin"],
                recommendation="sarvam-30b-hinglish",
            )
        elif tanglish_score >= 2:
            return LanguageDetection(
                primary=LanguageCode.TANGLISH,
                confidence=min(0.5 + tanglish_score * 0.1, 0.9),
                is_codemixed=True,
                scripts_detected=["Latin"],
                recommendation="sarvam-30b-tanglish",
            )
        
        # Default to English
        return LanguageDetection(
            primary=LanguageCode.EN,
            confidence=0.8,
            is_codemixed=False,
            scripts_detected=["Latin"],
            recommendation="sarvam-30b",
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
