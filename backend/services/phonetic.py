"""
Mukthi Guru — Indic Phonetic Matching (phonetic.py)

Provides a lightweight, Indic-optimized phonetic encoding algorithm (transliteration metaphone)
to resolve common phonetic spelling variations in transliterated Sanskrit/Hindi/Telugu terms.
Examples:
  - "deeksha", "diksha", "dikhsha" -> "DEEKSHA"
  - "mukthi", "mukti" -> "MUKTI"
  - "pranayama", "pranayam" -> "PRANAYAM"
  - "upanishad", "upanishada" -> "UPANISAD"
"""

import logging
import re

logger = logging.getLogger(__name__)


class IndicPhoneticMatcher:
    """
    Phonetic matcher tailored for transliterated Indic/Sanskrit spiritual terminology.
    Enables fuzzy search and misspelling tolerance in vector prefetch layers.
    """

    @staticmethod
    def encode(word: str) -> str:
        """
        Encode a word into its Indic phonetic key.
        """
        if not word:
            return ""

        # 1. Clean and lowercase
        val = word.strip().lower()
        if not val:
            return ""

        # Specific high-frequency spiritual term mapping to preserve correct spelling
        if any(variant in val for variant in ["deeksh", "diksh", "dikhsh"]):
            return "DEEKSHA"
        if val in ["ekam", "akam", "ekkam", "akkam"]:
            return "EKAM"

        # 2. Collapse double letters (except aa, ee, oo which are vowel representations)
        val = re.sub(r"([^aeiou])\1+", r"\1", val)

        # 3. Collapse common Indic transliteration patterns
        # ee/y -> i
        val = val.replace("ee", "i")
        val = val.replace("y", "i")
        # oo -> u
        val = val.replace("oo", "u")
        # ksh / khsh -> x
        val = val.replace("khsh", "x")
        val = val.replace("ksh", "x")
        # sh/zh -> s
        val = val.replace("sh", "s")
        val = val.replace("zh", "s")
        # th -> t
        val = val.replace("th", "t")
        # dh -> d
        val = val.replace("dh", "d")
        # bh -> b
        val = val.replace("bh", "b")
        # gh -> g
        val = val.replace("gh", "g")
        # kh -> k
        val = val.replace("kh", "k")
        # ch -> c
        val = val.replace("ch", "c")
        # ph -> f
        val = val.replace("ph", "f")

        # 4. Collapse word endings common in transliteration (silent final 'a')
        if len(val) > 4 and val.endswith("a") and val[-2] not in "aeiou":
            val = val[:-1]

        # 5. Collapse duplicate letters again
        val = re.sub(r"(.)\1+", r"\1", val)

        return val.upper()

    @classmethod
    def get_phonetic_tokens(cls, text: str) -> list[str]:
        """
        Extract and encode all non-trivial words from a text block.
        """
        if not text:
            return []

        words = re.findall(r"\b\w+\b", text.lower())
        stopwords = {
            "the", "and", "a", "of", "to", "is", "in", "that", "it", "you", "for", "on", "with",
            "as", "this", "are", "by", "i", "me", "my", "we", "our", "about", "your", "their",
            "who", "what", "where", "when", "why", "how", "which", "whose", "whom",
            "be", "been", "was", "were", "am", "do", "does", "did", "has", "have", "had",
            "can", "could", "will", "would", "should", "sri", "shri", "mr", "mrs", "dr",
            "input", "output", "text", "teaching", "propositions", "decompose", "summarize",
            "task", "prompt", "user", "request", "please", "verify", "correct", "error"
        }

        tokens = []
        for w in words:
            if w in stopwords or len(w) < 3:
                continue
            encoded = cls.encode(w)
            if encoded:
                tokens.append(encoded)
                # Query time backward-compatibility mapping for Ekam/Akam
                if encoded == "EKAM":
                    tokens.append("AKAM")
                elif encoded == "AKAM":
                    tokens.append("EKAM")

        return sorted(list(set(tokens)))
