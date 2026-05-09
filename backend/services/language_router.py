
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
            LanguageCode.BN: "\n\nগুরুত্বপূর্ণ: সবসময় বাংলায় উত্তর দিন। সংস্কৃত শব্দগুলি (ধর্ম, কর্ম, মোক্ষ) অপরিবর্তিত রাখুন।",
            LanguageCode.HINGLISH: "\n\nIMPORTANT: Reply in Hinglish (Hindi-English mix) using the same style as the user. Spiritual Sanskrit terms ko as-is rakho.",
        }
        return suffixes.get(lang, "")
