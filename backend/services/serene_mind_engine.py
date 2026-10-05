from __future__ import annotations

"""
Mukthi Guru — Serene Mind Emotional Intelligence Engine

Multi-language distress detection with graduated response levels.
Designed for Indian spiritual context with support for 10+ Indian languages.

Design Patterns:
  - Strategy Pattern: Multiple detection strategies (keyword, embedding, LLM)
  - Chain of Responsibility: Escalating detection severity levels
  - Observer Pattern: Conversation history analysis for escalation

Distress Levels:
  - NONE → Normal interaction
  - MILD → Light stress, gentle acknowledgment
  - MODERATE → Significant distress, meditation offer
  - SEVERE → Deep suffering, guided meditation + helpline
  - CRISIS → Immediate danger, helpline information first
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional

import numpy as np

from services.text_normalize import compact_letters, deobfuscate, looks_obfuscated

logger = logging.getLogger(__name__)


class DistressLevel(IntEnum):
    """Graduated distress severity levels."""

    NONE = 0
    MILD = 1
    MODERATE = 2
    SEVERE = 3
    CRISIS = 4


@dataclass
class DistressAssessment:
    """Result of a Serene Mind distress evaluation."""

    level: DistressLevel
    confidence: float  # 0.0 - 1.0
    detected_signals: list[str] = field(default_factory=list)
    language_detected: str = "en"
    recommended_response_type: str = "normal"  # normal, gentle, meditation, crisis


# ---------------------------------------------------------------------------
# Multi-language distress patterns
# ---------------------------------------------------------------------------

# English distress patterns
# Letters-only crisis phrases for obfuscated input (see assess_distress).
_OBFUSCATED_CRISIS = re.compile(
    r"suicid|kil+myself|endmylife|takemyownlife|wanttodie|hangmyself|notworthliving"
)

# 2026-09-28 (owner-approved "escalate-only + re-tier"): passive ideation and
# ambiguous spiritual framing WITHOUT stated intent/plan/method/timeframe.
# Defined once here (not duplicated inline in _EN_PATTERNS[SEVERE] below) so
# assess_distress() can tag a match against this exact list and route it to
# the gentle SEVERE check-in response instead of the pre-existing generic
# SEVERE template (which itself contains "are you safe right now?" wording
# too close to the full CRISIS copy for an ambiguous, no-plan message).
# AI-AUTHORED, PENDING-CLINICIAN-REVIEW — see the W2 review packet.
_SEVERE_IDEATION_CHECKIN_MARKERS = [
    r"wish\w*\s*(i\s*)?(could\s*)?(just\s*)?(go\s*to\s*)?(sleep\s*and\s*)?(never|not)\s*wake\s*up",
    r"\bwish\w*\s*(i\s*)?(was|were)\s*dead\b",
    r"\bdon'?t\s*want\s*to\s*exist\b",
    r"\b(i\s*want\s*to|let\s*me|i\s*wish\s*to)\s*leave\s*(this|my)\s*body\b",
]
_SEVERE_IDEATION_CHECKIN_RE = re.compile("|".join(_SEVERE_IDEATION_CHECKIN_MARKERS), re.IGNORECASE)

_EN_PATTERNS = {
    DistressLevel.CRISIS: [
        # 2026-09-27 (URGENT regression fix): "suicid" alone can never match —
        # the trailing \b requires a word boundary immediately after those 6
        # letters, but every real word built on this stem ("suicide",
        # "suicidal") continues with another word character ('e'/'a'), so the
        # boundary assertion always failed. This is not cosmetic: it meant
        # "I am suicidal" AND bare "suicide" (with a word boundary after,
        # e.g. "suicide is wrong") never matched this pattern at all — only
        # the (unrelated) hinglish/other-language buckets happened to catch
        # some phrasings. `suicid\w*` matches the stem plus any suffix.
        r"\b(suicid\w*|kill\s*my\s*self|kill\s*myself|end\s*(my|it)\s*all|want\w*\s*to\s*die|self[\s-]*harm)\b",
        r"\b(overdose|no\s*reason\s*to\s*live|not\s*worth\s*living)\b",
        # 2026-09-27: method-inquiry phrasings ("how to die quickly", "way to
        # die without pain", "how many sleeping pills to die") were missed
        # entirely — the only "how to die" coverage required the word "plan"
        # immediately before it (see the "plan* to die" alternative below),
        # and there was no pill/tablet-to-die phrasing at all.
        r"\b(how|way)s?\s+to\s+die\b",
        r"\b(pills?|tablets?)\s*to\s*die\b",
        # 2026-09-27: (hurt|harm|cut) + myself, covering the gerund/plural/past
        # forms the previous bare "hurt myself"/"cut myself" literals missed
        # ("hurting myself", "harming myself", "cutting myself" all scored
        # NONE before this). A negative lookahead excludes the common
        # ordinary-injury framings a red-team pass flagged ("I hurt myself
        # playing cricket", "cut myself shaving") so this widening doesn't
        # also widen the false-positive surface.
        # ponytail: this is a fixed exclusion word-list, not a real intent
        # classifier — extend it if a new benign false positive turns up
        # (never shrink it to "simplify", each entry was found empirically).
        r"\b(hurt|harm|cut)(?:ting|ing|s|ed)?\s*(my\s*)?self\b"
        r"(?!\s*(while\s+)?(playing|cooking|shaving|exercising|doing\s+(?!(?:it|this|that|so|again|them)\b)\w+|"
        r"at\s+(the\s+)?(gym|game|match|practice)))",
        # Question/gerund-framed ideation ("how do i stop wanting to die",
        # "planning how to leave this world") — evades the fixed phrasings above.
        # 2026-09-22: "not want to be here" required the literal word "not" and
        # missed the far more common colloquial "don't"/"doesn't" negation
        # ("I don't want to be here anymore") — found via the same eval-harness
        # pass as the "end my life" gap below. `(not|don'?t|doesn'?t)` now
        # covers both; "don'?t" mirrors the existing contraction-handling
        # pattern already used in the SEVERE tier just below (don'?t know if
        # i can go on), which was correct — this one just wasn't consistent
        # with it. First version of this fix regressed to a false positive on
        # ordinary preference statements ("I don't want to be here at this
        # meeting", "I did not wake up early enough") — anchoring on a
        # finality/duration qualifier (anymore/any more/one day/again/
        # tomorrow) is what actually distinguishes ideation phrasing from
        # mundane negation; caught by direct false-positive testing before
        # landing, not shipped broken.
        r"(leave\s*this\s*world|plan\w*\s*(to\s*die|how\s*to\s*(die|leave|end\s*it))|"
        r"(not|don'?t|doesn'?t)\s*want\w*\s*to\s*(live|be\s*here|wake\s*up|जीना)\s*(any\s*)?more|"
        # 2026-09-22 round 2: "जीना" (Devanagari "to live") added alongside
        # "live" to catch code-mixed messages that frame the sentence in
        # English but drop in a single Hindi verb ("I don't want to जीना
        # anymore") — a common code-switching pattern. This reuses the exact
        # same anchored "don't/doesn't/not want to X anymore" construction
        # already validated against false positives above, just widening the
        # verb alternation by one option; it is matched against message_lower
        # (English/Latin-script bucket), which only case-folds ASCII, so the
        # Devanagari literal is unaffected and matches as-is.
        r"(not|don'?t|doesn'?t)\s*want\w*\s*to\s*wake\s*up\b|"
        r"not\s*wak\w*\s*up\s*(one\s*day|again|tomorrow|anymore)|"
        # 2026-09-22 (red-team R3): "not wake up" without a "want to" verb —
        # hoping-framed ("I keep hoping I just don't wake up tomorrow") and
        # decision-framed ("I have decided to go to sleep and not wake up")
        # indirect finality phrasings. Both require a qualifier word (hop*/
        # decid*) immediately governing the negation, same false-positive
        # discipline as the "want to wake up" pattern above — bare "don't
        # wake up" alone is too broad (e.g. "don't wake up the baby").
        r"hop\w*\s*(i('m|\s*am)?\s*)?(just\s*)?(not|don'?t|doesn'?t)\s*wake\s*up|"
        r"decid\w*\s*to\s*(go\s*to\s*sleep\s*and\s*)?(not|never)\s*wake\s*up)",
        # 2026-09-22 (evals/scenarios/tier3_crisis, PLAN.md B1): "end my life" /
        # "ending my life" is one of the most common first-person ideation
        # phrasings in English and matched NONE of the above — "end (my|it)
        # all" only covers "all", not "life", and "want to die" requires the
        # exact word "die". Found by evals/run_safety_scenarios.py's mechanical
        # runner testing crisis-002 ("I want to end my life."), which returned
        # DistressLevel.NONE. Confirmed by direct interactive testing before
        # fixing — this was not a test-harness artifact.
        r"\bend(ing)?\s*(my|this|his|her|their)\s*(own\s*)?life\b",
        # 2026-09-22: passive ideation via perceived burdensomeness
        # ("everyone would be better off without me") is a well-documented,
        # common way suicidal ideation is expressed indirectly — distinct
        # from an active statement of intent, but CRISIS-tier per this
        # product's own crisis-preemption design (DistressStage docstring:
        # passive framing must not be missed). Also found via the eval
        # harness (crisis-001 scenario), previously undetected.
        r"(better\s*off\s*without\s*me|(everyone|they'?d|people)\s*(would\s*be\s*)?better\s*off\s*without\s*(me|us))",
        # 2026-09-28 (owner-approved "escalate-only + re-tier" design):
        # spiritual/doctrinal framing of ending one's life is now split by
        # whether it carries INTENT, A PLAN, A METHOD, or A TIMEFRAME.
        # Decisive plan verbs ("I'm going to" / "I will" / "I'm ready to") are
        # a plan/intent statement on their own — CRISIS regardless of an
        # explicit time word, per the owner's rule. An explicit time marker
        # ("tonight"/"tomorrow"/"today"/"now") after ANY of these phrasings is
        # also CRISIS even under a weaker modal ("I want to leave this body
        # tonight"). "merge with the divine and end it" carries its own
        # explicit finality ("end it") and stays CRISIS unconditionally.
        # Ambiguous desire/permission-seeking with NO plan/time/method
        # ("I want to leave this body", "let me leave my body") is demoted to
        # SEVERE below — a check-in, not the full crisis copy. The doctrinal
        # boundary is unchanged either way: a genuine question ("what does it
        # mean to leave the body at death?", "can I leave my body during
        # meditation?") is phrased with can/what/how, never with a
        # first-person verb directly in front of "leave the body", so it
        # cannot match either tier. Verified both directions with unit tests
        # (test_serene_mind.py, test_crisis_w2_expansion.py). AI-AUTHORED,
        # NOT verified by a clinician — see the W2 review packet.
        r"\b(i'?m\s*going\s*to|i\s*will|i'?m\s*ready\s*to)\s*leave\s*(this|my)\s*body\b",
        r"\b(i\s*want\s*to|let\s*me|i\s*wish\s*to)\s*leave\s*(this|my)\s*body\s*"
        r"(tonight|today|tomorrow|now)\b",
        r"\bmerge\s*with\s*the\s*divine\s*and\s*end\s*it\b",
        # 2026-10-04 (product audit): first-turn phrasings that scored NONE and
        # matched no guardrail rail, so no helplines were shown. Pinned both
        # ways by tests/test_crisis_phrasing_gaps_2026_10_04.py.
        # "killing myself" -- the alternation above only takes bare "kill".
        r"\bkill(?:ing|ed)\s*my\s*self\b",
        r"\b(don'?t|do\s*not|doesn'?t|no\s*longer)\s*want\w*\s*to\s*be\s*alive\b",
        r"\b(going\s*to|gonna|want\w*\s*to|will|plan\w*\s*to|about\s*to)\s*jump\s*(off|from|in\s*front\s*of)\b",
        r"\blethal\s*dose\b",
        r"\b(sav(ed|ing)|stockpil\w*|hoard\w*)\s*(up\s*)?(my\s*|all\s*my\s*|enough\s*)?(sleeping\s*)?(pills?|tablets?|meds|medications?)\b",
        r"\b(pills?|tablets?|meds|medications?)\s*(saved|stashed|stockpiled|hoarded)\b",
        # "kms" (kill myself); "5 kms" (kilometres) is excluded.
        r"(?<!\d)(?<!\d\s)\bkms\b",
        r"\bwant\w*\s*(the\s*pain\s*to\s*(stop|end)\s*(forever|for\s*good|permanently)|(it\s*all|everything)\s*to\s*(end|stop))\b",
    ],
    DistressLevel.SEVERE: [
        r"\b(hopeless|worthless|can'?t\s*go\s*on|give\s*up|no\s*point|nothing\s*matters?)\b",
        # 2026-09-28 (owner-approved re-tier, C-SSRS screener-item-1 style
        # passive ideation): "I wish I could sleep and never wake up", "I
        # wish I were dead", "I don't want to exist", and ambiguous spiritual
        # framing with NO plan/time/method — genuine distress signals, but
        # WITHOUT stated intent, plan, method, or timeframe (see the CRISIS
        # tier's own comment above for the full boundary reasoning against
        # the intent-bearing versions). Moved down from CRISIS (2026-09-27)
        # to SEVERE per the owner's explicit re-tier decision: these get a
        # gentle check-in + helplines, not the full "are you safe right now"
        # CRISIS copy. NEVER NONE. Defined once in
        # `_SEVERE_IDEATION_CHECKIN_MARKERS` above (not duplicated here) so
        # assess_distress() can also tag a match against that exact list and
        # route to the distinct check-in response. AI-AUTHORED, NOT verified
        # by a clinician — see the W2 review packet.
        *_SEVERE_IDEATION_CHECKIN_MARKERS,
        r"\b(don'?t\s*know\s*if\s*i\s*can\s*go\s*on)\b",
        # 2026-10-04 (product audit). "What is the point of life?" stays a
        # doctrine question; only living / being alive / life anymore counts.
        r"\bwhat('?s|\s*is)\s*the\s*point\s*(of|in)\s*(living|being\s*alive|going\s*on|life\s*any\s*more)\b",
        r"\b(i'?m|i\s*am|i\s*feel\s*like)\s*(just\s*|such\s*)?a\s*burden\b",
        r"\bhow\s*many\s*(\w+\s*){0,2}(pills?|tablets?|paracetamol|sleeping\s*pills)\s*(would|will|does|do)\s*(it\s*)?(take|kill)\b",
        # Passive ideation (red team 2026-09-26): "don't see the point of going on".
        r"\bdon'?t\s+see\s+(the\s+)?point\s+(of|in)\s+(going\s+on|continuing|living|trying)\b",
        r"\b(deeply?\s*(depressed|sad|lonely)|unbearable\s*pain)\b",
        r"\b(meaningless|empty\s*inside)\b",
        # "broken" is SEVERE only as a self-description. Bare "broken" matched "can love
        # heal a broken relationship?" and pre-empted a teaching question with crisis
        # helplines (bake-off 2026-09-27); it now falls to MODERATE below.
        r"\b(i\s*(am|'?m|feel|felt)\s*(so\s*|completely\s*|totally\s*|just\s*)?broken|broken\s*inside|(i'?m|i\s*am)\s*a\s*broken\s*(person|man|woman|soul))\b",
    ],
    DistressLevel.MODERATE: [
        r"\bbroken\b",
        r"\b(stressed|anxious|anxiety|panic|overwhelm\w*|can'?t\s*sleep|insomnia)\b",
        r"\b(depressed|sad|unhappy|miserable|frustrated|angry|furious)\b",
        r"\b(scared|afraid|terrified|worried|fear|nervous)\b",
        r"\b(lonely|isolated|alone|abandoned|rejected)\b",
        r"\b(burn\s*out|burned\s*out|pointless|crying|don'?t\s*feel\s*like\s*myself)\b",
        # Directional/existential stuckness
        r"\bstuck\s+(in|with|on)\b",
        r"\bdon'?t\s+know\s+(where|what|how)\b",
        r"\bno\s+(way|direction|path)\b",
        r"\bdead\s*end\b",
        r"\btrapped\b",
        r"\bnowhere\s*to\s*(go|turn)\b",
    ],
    DistressLevel.MILD: [
        r"\b(tired|exhausted|drained|burnout)\b",
        r"\b(confused|lost|uncertain|stuck|struggling)\b",
        r"\b(uneasy|uncomfortable|restless|unsettled)\b",
    ],
}

# Hindi distress patterns (Devanagari)
_HI_PATTERNS = {
    # 2026-09-22: widened for the same gap-class found in English
    # (L-CRISIS-REGEX-GAP-1) — "जीना नहीं चाहता" (bare "don't want to
    # live"), "जिंदगी"/"ज़िंदगी" (both common spellings — with and without
    # nuqta on ज़/ज — only the nuqta form was covered), an active-verb "end
    # my life" phrasing, and "better off without me" passive-ideation
    # framing had zero coverage. NOT verified by a native Hindi speaker —
    # see evals/README.md and lessons.md L-INDIC-CRISIS-REGEX-1.
    DistressLevel.CRISIS: [
        r"(मरना\s*चाहता|मरना\s*चाहती|आत्महत्या|ज़?िंदगी\s*खत्म|जीने\s*का\s*मन\s*नहीं)",
        r"(खुद\s*को\s*मारना|सब\s*खत्म\s*करना|जीना\s*नहीं\s*चाहता|जीना\s*नहीं\s*चाहती)",
        r"(ज़?िंदगी\s*खत्म\s*कर|अपनी\s*जान\s*ले)",
        r"(मेरे\s*बिना\s*(सब|सभी)\s*(बेहतर|अच्छा)|सबको\s*मेरे\s*बिना\s*(अच्छा|बेहतर)|"
        r"(सब|सभी)\s*मेरे\s*बिना\s*(बेहतर|अच्छा))",
        # 2026-09-22 (red-team R3, UNVERIFIED — needs native speaker review):
        # "जीने की इच्छा नहीं" (no desire/will to live — uses इच्छा "desire"
        # instead of मन "mind/heart", a different but equally common wording)
        # and "नहीं जी सकता" (modal "can't live [anymore]", distinct from the
        # existing "जीना नहीं चाहता" "don't want to live" volitional phrasing).
        r"(जीने\s*की\s*इच्छा\s*नहीं|नहीं\s*जी\s*सकत[ाी]|जी\s*नहीं\s*सकत[ाी])",
        # 2026-09-27 (live probe, UNVERIFIED — needs native speaker review):
        # "अपनी जान देना" ("give my life") scored NONE; only "अपनी जान ले"
        # ("take my life") was covered. Known false positive: devotional
        # hyperbole ("उसके लिए अपनी जान दे दूँगा") — accepted, a miss costs more.
        r"अपनी\s*जान\s*दे",
    ],
    DistressLevel.SEVERE: [
        r"(बहुत\s*(दुखी|उदास|अकेला|अकेली)|जीवन\s*व्यर्थ|कोई\s*उम्मीद\s*नहीं)",
        r"(सहन\s*नहीं\s*हो\s*रहा|टूट\s*गया|टूट\s*गई|निराशा)",
    ],
    DistressLevel.MODERATE: [
        r"(तनाव|चिंता|घबराहट|परेशान|नींद\s*नहीं|अवसाद)",
        r"(दुखी|उदास|रोना|गुस्सा|डर|अकेलापन)",
        r"(तकलीफ|कष्ट|पीड़ा|दर्द)",
    ],
    DistressLevel.MILD: [
        r"(थका|थकान|उलझन|भ्रम|अशांत|बेचैन)",
    ],
}

# Tamil distress patterns
_TA_PATTERNS = {
    # 2026-09-22: widened for the same gap-class as Hindi above (bare
    # "don't want to live", active "end my life", "better off without me").
    # NOT verified by a native Tamil speaker — see evals/README.md.
    DistressLevel.CRISIS: [
        r"(தற்கொலை|உயிரை\s*மாய்க்க|சாக\s*விரும்புகிறேன்)",
        r"(வாழ\s*விரும்ப(வில்லை|முடியவில்லை)|உயிரை\s*முடித்து|உயிர்\s*விட)",
        r"(இல்லாமல்\s*(எல்லோரும்|அனைவரும்)\s*(நன்றாக|நல்லா))",
    ],
    DistressLevel.SEVERE: [
        r"(மிகவும்\s*வேதனை|நம்பிக்கையில்லை|தாங்க\s*முடியல|வாழ\s*விருப்பமில்லை)",
    ],
    DistressLevel.MODERATE: [
        r"(கஷ்டப்படுகிறேன்|பயம்|கவலை|தூக்கமின்மை|சோகம்|தனிமை)",
    ],
}

# Telugu distress patterns
_TE_PATTERNS = {
    # 2026-09-22: widened for the same gap-class as above. NOT verified by
    # a native Telugu speaker — see evals/README.md.
    DistressLevel.CRISIS: [
        r"(ఆత్మహత్య|చచ్చిపోవాలని|బతకడం\s*ఇష్టం\s*లేదు)",
        # 2026-10-04: standard "chanipo" ("I want to die"); only the colloquial
        # "chachipo" was covered. UNVERIFIED by a native speaker.
        r"(చనిపోవాల|చనిపోతాను|చావాలని)",
        r"(బతకాలని\s*(అనుకోవడం\s*లేదు|లేదు)|జీవితాన్ని\s*(అంతం|ముగించు))",
        r"(లేకపోతే\s*(అందరూ|అందరికీ)\s*బాగు)",
    ],
    DistressLevel.SEVERE: [
        r"(చాలా\s*బాధగా|ఎందుకు\s*బతకాలి|నిరాశ|తట్టుకోలేను)",
    ],
    DistressLevel.MODERATE: [
        r"(ఒత్తిడి|ఆందోళన|భయం|ఒంటరిగా|దుఃఖం|నిద్ర\s*రాదు)",
    ],
}

# Kannada distress patterns
_KN_PATTERNS = {
    # 2026-09-22: widened for the same gap-class as above. NOT verified by
    # a native Kannada speaker — see evals/README.md.
    DistressLevel.CRISIS: [
        r"(ಆತ್ಮಹತ್ಯೆ|ಸಾಯಬೇಕು|ಬದುಕಲು\s*ಇಷ್ಟ\s*ಇಲ್ಲ)",
        # 2026-10-04: formal "I wish to die". UNVERIFIED by a native speaker.
        r"(ಸಾಯಲು\s*ಬಯಸ)",
        r"(ಬದುಕಲು\s*ಬಯಸುವುದಿಲ್ಲ|ಜೀವನವನ್ನು\s*ಕೊನೆಗೊಳಿಸ)",
        r"(ಇಲ್ಲದೆ\s*ಎಲ್ಲರೂ\s*ಚೆನ್ನಾಗಿರು|ನಾನಿಲ್ಲದೆ\s*ಎಲ್ಲರೂ)",
        # 2026-09-22 (red-team R3, UNVERIFIED — needs native speaker review):
        # the sandhi-joined "ಇಷ್ಟವಿಲ್ಲ" ("don't like/want") is the natural
        # single-word form of "ಇಷ್ಟ ಇಲ್ಲ" — the existing `\s*` between them
        # only makes the space optional, it does not match the glide-inserted
        # "ವ" that Kannada sandhi actually produces joining the two words.
        r"(ಬದುಕಲು\s*ಇಷ್ಟವಿಲ್ಲ)",
    ],
    DistressLevel.SEVERE: [
        r"(ತುಂಬಾ\s*ನೋವು|ನಂಬಿಕೆ\s*ಇಲ್ಲ|ಸಹಿಸಲು\s*ಆಗುತ್ತಿಲ್ಲ|ಬದುಕು\s*ಅರ್ಥಹೀನ)",
    ],
    DistressLevel.MODERATE: [
        r"(ಒತ್ತಡ|ಭಯ|ಆತಂಕ|ದುಃಖ|ಒಂಟಿ|ನಿದ್ದೆ\s*ಬರಲ್ಲ)",
    ],
    DistressLevel.MILD: [
        r"(ಆಯಾಸ|ಗೊಂದಲ|ಚಡಪಡ|ಅಶಾಂತ)",
    ],
}

# Bengali distress patterns
_BN_PATTERNS = {
    # 2026-09-22: widened for the same gap-class as above. NOT verified by
    # a native Bengali speaker — see evals/README.md.
    DistressLevel.CRISIS: [
        r"(আত্মহত্যা|মরে\s*যেতে\s*চাই|বেঁচে\s*থাকতে\s*চাই\s*না)",
        r"(বাঁচতে\s*চাই\s*না|জীবন\s*শেষ\s*করে)",
        r"(ছাড়া\s*(সবাই|সকলে)\s*ভালো\s*থাক)",
    ],
    DistressLevel.SEVERE: [
        r"(অসহ্য|আর\s*পারছি\s*না|কোনো\s*আশা\s*নেই|জীবন\s*অর্থহীন)",
    ],
    DistressLevel.MODERATE: [
        r"(চাপ|ভয়|উদ্বেগ|দুঃখ|একা|ঘুম\s*আসে\s*না)",
    ],
    DistressLevel.MILD: [
        r"(ক্লান্ত|বিভ্রান্ত|অস্বস্তি|অশান্ত)",
    ],
}

# Malayalam distress patterns
_ML_PATTERNS = {
    # 2026-09-22: widened for the same gap-class as above. NOT verified by
    # a native Malayalam speaker — see evals/README.md.
    DistressLevel.CRISIS: [
        r"(ആത്മഹത്യ|മരിക്കണം|ജീവിക്കാൻ\s*ആഗ്രഹമില്ല)",
        r"(ജീവിക്കണ്ട|ജീവിതം\s*അവസാനിപ്പിക്ക)",
        r"(ഇല്ലെങ്കിൽ\s*എല്ലാവരും\s*നന്നായി)",
        # 2026-09-22 (red-team R3, UNVERIFIED — needs native speaker review):
        # "ജീവിക്കാൻ തോന്നുന്നില്ല" ("don't feel like living") is a more
        # colloquial way to express the same thing as "ആഗ്രഹമില്ല" ("no
        # desire") above. Anchored to "ജീവിക്കാൻ" (to live) — bare
        # "തോന്നുന്നില്ല" ("don't feel like [X]") alone is a generic verb
        # construction used for completely mundane things and would false-
        # positive constantly if unanchored.
        r"(ജീവിക്കാൻ\s*തോന്നുന്നില്ല)",
    ],
    DistressLevel.SEVERE: [
        r"(വളരെ\s*വേദന|പ്രതീക്ഷയില്ല|സഹിക്കാൻ\s*കഴിയുന്നില്ല|ജീവിതം\s*അർത്ഥരഹിതം)",
    ],
    DistressLevel.MODERATE: [
        r"(സമ്മർദ്ദം|ഭയം|ആകാംക്ഷ|ദുഃഖം|ഒറ്റയ്ക്ക്|ഉറക്കം\s*വരുന്നില്ല)",
    ],
    DistressLevel.MILD: [
        r"(ക്ഷീണം|ആശയക്കുഴപ്പം|അസ്വസ്ഥ|ചഞ്ചല)",
    ],
}

# Marathi distress patterns.
# 2026-09-22: Marathi had NO pattern block at all until this fix — a pilot
# language (CLAUDE.md's 6 real-translation locales: en/hi/te/kn/ta/mr) with
# zero crisis-detection coverage in assess_distress(). The admission-level
# pre-screen in distress_stage.py's _INDIC_CRISIS_KEYWORDS already had two
# vetted Marathi idioms ("जीव देणे", "जीव संपवणे") for bypassing unrelated
# rejection gates (e.g. the context-limit check), but that pre-screen only
# decides whether a message is ALLOWED to reach DistressStage — the actual
# classification that decides CRISIS vs SEVERE vs nothing, and therefore
# whether crisis preemption fires at all, is assess_distress() via this
# per-language pattern dict. A Marathi-speaking user could pass the
# pre-screen and still receive zero crisis response, because nothing here
# ever classified their message above NONE.
# ⚠️ Built by cross-referencing Hindi's structure (closest related
# language, also Devanagari) and the two idioms distress_stage.py already
# vetted, NOT verified by a native Marathi speaker. Flag in lessons.md and
# evals/README.md: needs native-speaker review before pilot launch, same as
# the widened hi/ta/te/kn/bn/ml patterns below.
_MR_PATTERNS = {
    DistressLevel.CRISIS: [
        r"(जीव\s*द्या\w*|जीव\s*देणे|जीव\s*संपवणे|आत्महत्या|मरायच[ें]\s*आहे|मरायची\s*इच्छा)",
        r"(जगायची\s*इच्छा\s*नाही|जगायचं\s*नाही|संपवून\s*टाकतो|संपवून\s*टाकते)",
        # 2026-09-22 round 2 (fresh-reviewer re-test, UNVERIFIED — needs
        # native speaker review): "जगण्याची इच्छा नाही" is a distinct
        # morphological form of the same "no desire to live" phrase —
        # जगण्याची (verbal-noun/gerund genitive of जगणे) vs the जगायची form
        # already covered above. Both are valid, commonly-used constructions.
        r"(जगण्याची\s*इच्छा\s*नाही)",
    ],
    DistressLevel.SEVERE: [
        r"(खूप\s*(दुःखी|उदास|एकटा|एकटी)|आशा\s*नाही|जगणं\s*व्यर्थ)",
        r"(सहन\s*होत\s*नाही|तुटलो|तुटले|निराशा)",
    ],
    DistressLevel.MODERATE: [
        r"(ताण|तणाव|चिंता|काळजी|झोप\s*येत\s*नाही|नैराश्य)",
        r"(दुःखी|उदास|रडू|राग|भीती|एकटेपणा)",
    ],
    DistressLevel.MILD: [
        r"(थकवा|गोंधळ|अस्वस्थ|बेचैन)",
    ],
}

# Hinglish / Romanized Hindi
_HINGLISH_PATTERNS = {
    DistressLevel.CRISIS: [
        r"\b(marna\s*chahta|suicide|zindagi\s*khatam|jeene\s*ka\s*mann\s*nahi)\b",
        # 2026-09-22 round 2 (UNVERIFIED — needs native speaker review):
        # "jeena nahi hai" ("I don't want to live anymore") is a distinct
        # construction from "jeene ka mann nahi" (different verb form: jeena
        # vs jeene, no "ka mann"). Anchored to a first-person subject
        # ("mujhe"/"mera") immediately before it, NOT bare "jeena nahi hai" —
        # that bare phrase is also a common non-crisis Hindi idiom ("yeh
        # jeena nahi hai" = "this isn't [real] living", a complaint about a
        # situation, not ideation) and would false-positive constantly if
        # unanchored.
        r"\b(mujhe|mera)\s*(ab\s*)?jeena\s*nahi\s*(hai\s*)?\b",
        # 2026-09-27 (live probe, UNVERIFIED): romanized "apni jaan de/le"
        # ("give/take my life") had no coverage at all. Same hyperbole caveat
        # as the Devanagari pattern in _HI_PATTERNS.
        r"\bapni\s*jaan\s*(de|le)",
    ],
    DistressLevel.SEVERE: [
        r"\b(bahut\s*(dukhi|udaas|akela)|koi\s*ummeed\s*nahi|sab\s*khatam)\b",
    ],
    DistressLevel.MODERATE: [
        r"\b(tension|tanav|pareshan|neend\s*nahi|ghabra|akela)\b",
        r"\b(dukhi|udaas|rona|gussa|darr)\b",
    ],
}

# 2026-09-22 (red-team R3): romanized (Latin-script) pattern blocks for
# Telugu, Kannada, Malayalam and Marathi — before this fix only Hindi had a
# romanized block (_HINGLISH_PATTERNS above); the other four pilot Indic
# languages had ZERO coverage for users typing in Latin script, which is
# extremely common on mobile keyboards. Each phrase below is a Roman
# transliteration of an ALREADY-PRESENT native-script pattern in this same
# file (see the language's own _XX_PATTERNS block above), chosen to keep the
# same false-positive discipline (multi-word/phrase-level, not single common
# syllables) as _HINGLISH_PATTERNS.
# ⚠️ UNVERIFIED — needs native speaker review. I am not a native or fluent
# speaker of Telugu, Kannada, Malayalam, or Marathi; these are best-effort
# transliterations using common informal romanization conventions, not
# clinically or linguistically validated. Do not treat a pass in the test
# suite as sign-off — see evals/README.md and CLAUDE.md's "Open work"
# section, same caveat as every other Indic pattern in this file.

# Romanized Telugu
_TE_ROMANIZED_PATTERNS = {
    DistressLevel.CRISIS: [
        r"\b(atma\s*hatya|aatma\s*hatya)\b",  # ఆత్మహత్య — suicide
        r"\b(bathakalani\s*ledu|brathakalani\s*ledu|bratakalani\s*ledu|batkalani\s*ledu|bathakadam\s*ishtam\s*ledu)\b",
        # 2026-09-22 round 2: "bratakalani" (no 'h' after 'b', distinct from
        # "brathakalani") is a third common spelling variant of this word,
        # found by a fresh reviewer re-testing "naaku ika bratakalani ledu".
        # బతకాలని లేదు / బతకడం ఇష్టం లేదు — "don't want to live"
        r"\b(jeevitanni\s*antham|jeevitanni\s*muginchu)\b",  # జీవితాన్ని అంతం/ముగించు
        # 2026-10-04: "want to die" verb forms (chachipovalani / chanipovalani /
        # chanipothanu / chaavaalani). Past forms ("chanipoyaru", someone died)
        # are deliberately excluded: grief is not ideation. UNVERIFIED.
        r"\b(chachipov[aā]+l\w*|chanipov[aā]+l\w*|chachipotha\w*|chanipotha\w*|chaav[aā]*li\w*|chavali\w*)\b",
    ],
    DistressLevel.SEVERE: [
        r"\b(niraasha|tattukoleni)\b",  # నిరాశ, తట్టుకోలేను
    ],
    DistressLevel.MODERATE: [
        r"\b(ottidi|aandolana|ontariga)\b",  # ఒత్తిడి, ఆందోళన, ఒంటరిగా
    ],
}

# Romanized Kannada
_KN_ROMANIZED_PATTERNS = {
    DistressLevel.CRISIS: [
        r"\b(aatmahatye|atmahatye)\b",  # ಆತ್ಮಹತ್ಯೆ — suicide
        # 2026-09-27: added "saaya"/"saaya beku" double-a spelling variants —
        # this exact spelling was already recognized by distress_stage.py's
        # separate pre-screen keyword list but missing here, so a message
        # matching the pre-screen never actually reached CRISIS (the real
        # bug behind "nange saayabeku anisuttide" not crisis-preempting).
        r"\b(saya\s*beku|sayabeku|saaya\s*beku|saayabeku)\b",  # ಸಾಯಬೇಕು — "must/want to die"
        r"\b(badukalu\s*ishta\s*illa|badukalu\s*bayasuvudilla)\b",
        # ಬದುಕಲು ಇಷ್ಟ ಇಲ್ಲ / ಬಯಸುವುದಿಲ್ಲ — "don't want to live"
    ],
    DistressLevel.SEVERE: [
        r"\b(sahisalu\s*aagutilla)\b",  # ಸಹಿಸಲು ಆಗುತ್ತಿಲ್ಲ — "can't bear it"
    ],
    DistressLevel.MODERATE: [
        r"\b(ottada|aatanka|nidde\s*barolla)\b",  # ಒತ್ತಡ, ಆತಂಕ, ನಿದ್ದೆ ಬರಲ್ಲ
    ],
}

# Romanized Malayalam
_ML_ROMANIZED_PATTERNS = {
    DistressLevel.CRISIS: [
        r"\b(aatmahathya|atmahathya)\b",  # ആത്മഹത്യ — suicide
        r"\b(marikkanam)\b",  # മരിക്കണം — "must die"
        r"\b(jeevikkan\s*aagrahamilla|jeevikkan\s*thonnunnilla|jeevikkanda)\b",
        # ജീവിക്കാൻ ആഗ്രഹമില്ല / തോന്നുന്നില്ല / ജീവിക്കണ്ട
    ],
    DistressLevel.SEVERE: [
        r"\b(sahikkan\s*kazhiyunnilla|pratheekshayilla)\b",
        # സഹിക്കാൻ കഴിയുന്നില്ല, പ്രതീക്ഷയില്ല
    ],
    DistressLevel.MODERATE: [
        r"\b(sammardham|urakkam\s*varunnilla)\b",  # സമ്മർദ്ദം, ഉറക്കം വരുന്നില്ല
    ],
}

# Romanized Marathi
_MR_ROMANIZED_PATTERNS = {
    DistressLevel.CRISIS: [
        r"\b(jeev\s*dyava|jeev\s*denne|aatmahatya|atmahatya)\b",
        # जीव द्यावा, जीव देणे, आत्महत्या
        r"\b(maraya?ch[e]?n?\s*aahe|jagaychi\s*ichha\s*nahi|jagaycha\s*nahi)\b",
        # मरायचे आहे, जगायची इच्छा नाही, जगायचं नाही
    ],
    DistressLevel.SEVERE: [
        r"\b(khup\s*dukhi|aasha\s*nahi|sahan\s*hot\s*nahi)\b",
        # खूप दुःखी, आशा नाही, सहन होत नाही
    ],
    DistressLevel.MODERATE: [
        r"\b(taan|tanav|chinta|zop\s*yet\s*nahi)\b",  # ताण, तणाव, चिंता, झोप येत नाही
    ],
}

# Compile all patterns into a single lookup
_ALL_PATTERNS: dict[str, dict[DistressLevel, list[re.Pattern]]] = {}
for _name, _patterns in [
    ("en", _EN_PATTERNS),
    ("hi", _HI_PATTERNS),
    ("ta", _TA_PATTERNS),
    ("te", _TE_PATTERNS),
    ("kn", _KN_PATTERNS),
    ("bn", _BN_PATTERNS),
    ("ml", _ML_PATTERNS),
    ("mr", _MR_PATTERNS),
    ("hinglish", _HINGLISH_PATTERNS),
    ("te_rom", _TE_ROMANIZED_PATTERNS),
    ("kn_rom", _KN_ROMANIZED_PATTERNS),
    ("ml_rom", _ML_ROMANIZED_PATTERNS),
    ("mr_rom", _MR_ROMANIZED_PATTERNS),
]:
    _ALL_PATTERNS[_name] = {
        level: [re.compile(p, re.IGNORECASE | re.UNICODE) for p in patterns]
        for level, patterns in _patterns.items()
    }

# Latin-script language codes registered above — these must be matched
# case-insensitively against the *lowercased* message (mirrors "en" and
# "hinglish"); every other code is a native (non-Latin) script matched
# against the raw message. Centralized here so assess_distress() and
# _quick_distress_check() (which each had their own independent copy of the
# ("en", "hinglish") tuple) can't drift out of sync when a new romanized
# block is added.
_LATIN_SCRIPT_LANGS = frozenset({"en", "hinglish", "te_rom", "kn_rom", "ml_rom", "mr_rom"})


def get_non_english_crisis_patterns() -> list[re.Pattern]:
    """All non-English CRISIS-tier compiled patterns, flattened across every
    language bucket in `_ALL_PATTERNS` (native script + romanized).

    Single source of truth for "does this look like acute Indic crisis
    language" — see `app/pipeline/stages/distress_stage.py`'s pre-screen,
    which is DERIVED from this instead of maintaining its own separately
    hand-typed keyword list.

    2026-09-27 (structural fix): two independently hand-maintained lists for
    the same phrases drifted — the pre-screen had the romanized Kannada
    spelling "saayabeku" (double-a) that `_KN_ROMANIZED_PATTERNS` did not
    (only "sayabeku", single-a), so a message matching the pre-screen never
    actually escalated to CRISIS in `assess_distress()`. Deriving the
    pre-screen from these same compiled patterns makes that class of
    divergence structurally impossible: any phrase added here is
    automatically covered by the pre-screen with no second edit, and the
    pre-screen can never claim a match this function itself would miss.
    """
    return [
        pattern
        for lang, levels in _ALL_PATTERNS.items()
        if lang != "en"  # English has its own separately-scoped pre-screen
        for pattern in levels.get(DistressLevel.CRISIS, [])
    ]


# ---------------------------------------------------------------------------
# Crisis resources by region
#
# This dictionary used to be hardcoded with helpline numbers literally inlined
# into multi-line strings. Helplines now come from
# `services.crisis_helplines` (which in turn reads
# `backend/config/router_routes.yaml`). The region keys here just select what
# subset to show; the numbers themselves are never duplicated.
# ---------------------------------------------------------------------------


def _region_label_for_key(key: str) -> str | None:
    """Map the legacy region keys here to the canonical labels used in the
    YAML registry. Returning None means 'no region filter, show everything'."""
    return {
        "global": None,
        "international": None,
        "india": "India",
        "us": "United States",
        "uk": "United Kingdom",
    }.get(key)


def get_crisis_resource(region_key: str = "global") -> str:
    """Render a crisis-helpline block for a region.

    Args:
        region_key: legacy key — "india" | "us" | "uk" | "global". Unknown
                    keys fall back to "global" (show everything).
    """
    from services.crisis_helplines import format_helplines_block

    region = _region_label_for_key(region_key)
    intro = (
        "🆘 If you're in crisis: Please reach out for help."
        if region_key == "global"
        else f"🆘 Crisis Helplines ({region or 'International'}):"
    )
    return format_helplines_block(region=region, style="bullet", intro=intro)


# Backwards-compatible read-only dict surface. Existing call sites that
# do `CRISIS_RESOURCES["india"]` continue to work, but each access now
# resolves through the YAML-driven helper above. Module-level dict was
# previously the only API and is preserved on purpose.
class _CrisisResourcesView:
    """Dict-like read-only accessor backed by `get_crisis_resource()`."""

    def __getitem__(self, key: str) -> str:
        return get_crisis_resource(key)

    def get(self, key: str, default: str = "") -> str:  # type: ignore[override]
        try:
            return get_crisis_resource(key)
        except Exception:  # noqa: BLE001
            return default

    def __contains__(self, key: str) -> bool:  # for `"india" in CRISIS_RESOURCES`
        return _region_label_for_key(key) is not None or key in ("global", "international")


CRISIS_RESOURCES = _CrisisResourcesView()


# ---------------------------------------------------------------------------
# Graduated response templates
# ---------------------------------------------------------------------------

DISTRESS_RESPONSES = {
    DistressLevel.MILD: (
        "I sense you may be going through a challenging time. "
        "Remember, every moment of discomfort "
        "is an invitation to deepen your awareness.\n\n"
        "🌱 **Quick grounding technique**: Take a slow breath in for 4 counts, "
        "hold for 4, exhale for 6. Repeat 3 times. This simple practice "
        "can anchor you back to the present moment.\n\n"
        "Would you like to explore a specific teaching that might help, "
        "or try a Serene Mind micro-meditation?"
    ),
    DistressLevel.MODERATE: (
        "I hear you, and I want you to know that your feelings are completely valid. "
        "In moments like these, the teachings remind us that suffering is a doorway "
        "to transformation — not something to fight against, but to move through with awareness.\n\n"
        "🧘 **Breathing practice**: Place your hand on your heart. "
        "Breathe in slowly — feel your chest rise. Breathe out gently — feel any "
        "tension release. Do this 5 times. "
        "When you breathe with awareness, you return to the beautiful state.\n\n"
        "Would you like me to guide you through a full Serene Mind meditation? 🙏"
    ),
    DistressLevel.SEVERE: (
        "I feel the depth of your pain, and I want you to know — you are not alone. "
        "Your feelings matter, and there is light even in the darkest moments.\n\n"
        "Are you safe right now? If there's any thought of hurting yourself, "
        "please tell me, or reach out to one of the numbers shown above right away — "
        "I'm staying here with you.\n\n"
        "When you stop running from your suffering and turn towards it "
        "with awareness, transformation begins.\n\n"
        "🌸 **5-4-3-2-1 grounding**: Name 5 things you see, 4 you can touch, "
        "3 you hear, 2 you smell, 1 you taste. This brings you firmly into the present.\n\n"
        "I'd like to guide you through a Serene Mind meditation. "
        "Would you like to begin?\n"
    ),
    DistressLevel.CRISIS: (
        "🙏 I care deeply about your wellbeing. Please know that you are valued, "
        "and there are people who want to help you right now. I'm staying here "
        "with you — please don't go through this alone.\n\n"
        "Are you safe right now, or are you thinking about harming yourself? "
        "Please tell me. And please reach out to one of the numbers shown above right away.\n"
    ),
}


# ---------------------------------------------------------------------------
# LLM Distress Classification Prompt (Stage 2)
#
# System message for `NimService.classify_distress_structured`. The model must
# return STRICT JSON parseable by `json.loads` using the canonical schema
# {is_distress, confidence, reason} — same as ollama/sarvam/openrouter. The
# consumer (`async_assess_distress`) only checks `is_distress` (true →
# DistressLevel.MODERATE); gradation is not used, so a binary flag + float
# confidence is sufficient.
# ---------------------------------------------------------------------------

DISTRESS_CLASSIFICATION_SYSTEM_PROMPT = (
    "You are a sensitive emotional-distress classifier for a spiritual "
    "wellness companion (Mukthi Guru / Serene Mind). The user may write in "
    "any language, including Indian languages and Romanized (Hinglish).\n\n"
    "Decide whether the message shows emotional distress (a cry for help, "
    "sustained anxiety, sadness, loneliness, overwhelm, hopelessness, or "
    "deep suffering without explicit self-harm intent — crisis is handled "
    "elsewhere).\n\n"
    "Guidelines:\n"
    "1. Base the decision on the user's words and emotional tone only.\n"
    "2. A normal spiritual or factual question is NOT distress — do not over-flag.\n"
    "3. Set `confidence` to your certainty (0.0 = no distress, 1.0 = clear distress).\n"
    "4. If unsure, lean toward `is_distress: false` with a low confidence.\n"
    "5. Respond with STRICT JSON only. No prose, no markdown fences, no extra keys.\n"
    "6. Output schema:\n"
    '   {"is_distress": <true|false>, "confidence": <0.0-1.0>, '
    '"reason": "<short phrase>"}'
)


# ---------------------------------------------------------------------------
# Semantic Distress Detection
# ---------------------------------------------------------------------------

_SEMANTIC_DISTRESS_EXAMPLES = {
    DistressLevel.CRISIS: [
        "I want to end my life. There is no point in living anymore.",
        "I can't take this pain anymore. I want to die.",
        "Nobody would miss me if I was gone. I should just kill myself.",
    ],
    DistressLevel.SEVERE: [
        "I feel completely hopeless. Nothing matters anymore.",
        "I am worthless. My life has no meaning.",
        "The pain is unbearable. I can't go on like this.",
    ],
    DistressLevel.MODERATE: [
        "I feel so anxious all the time. I can't breathe.",
        "I am so stressed and overwhelmed. I can't handle this.",
        "I feel so lonely and disconnected from everyone.",
        "I can't sleep. My mind won't stop racing with worries.",
    ],
    DistressLevel.MILD: [
        "I feel stuck. I don't know what to do with my life.",
        "I am so tired all the time. I have no energy.",
        "I feel restless and uneasy. Something feels off.",
    ],
}


class SemanticDistressDetector:
    """
    Embedding-based semantic distress detection.

    Compares user message against pre-computed distress example embeddings.
    Captures nuance that keyword matching misses.
    """

    def __init__(self, embedding_service, threshold: float | None = None):
        """
        Initialize the semantic distress detector.

        Threshold Calibration Notes:
        - The default threshold of 0.72 has been calibrated against clinical guidelines
          and distress prediction benchmarks (e.g., llm-mental-health-risk-detection /
          sonia-health).
        - Benchmark sensitivity mapping:
          * HIGH Sensitivity (threshold <= 0.65): High recall for distress cues but high
            false positive rate on normal query sharing.
          * MEDIUM Sensitivity (threshold 0.68 - 0.73): Balanced tradeoff, capturing authentic
            emotional vulnerability without interrupting standard spiritual queries.
          * LOW Sensitivity (threshold >= 0.75): Low false positive rate, but misses early-stage
            mild/moderate distress cues.
        - Selected: 0.72 (Medium tier) to prevent gating normal conversation while ensuring
          seeker safety during emotional crises.
        """
        from app.config import settings

        self._embedder = embedding_service
        self._threshold = (
            threshold if threshold is not None else settings.semantic_distress_threshold
        )
        self._distress_embeddings = {}  # level -> list of embeddings
        self._initialized = False

    async def initialize(self):
        """Pre-compute distress example embeddings."""
        if self._initialized or not self._embedder:
            return

        try:
            for level, examples in _SEMANTIC_DISTRESS_EXAMPLES.items():
                # Use encode_batch if available, else encode individually
                if hasattr(self._embedder, "encode_batch"):
                    embeddings = await asyncio.to_thread(self._embedder.encode_batch, examples)
                    self._distress_embeddings[level] = embeddings["dense"]
                else:
                    level_embs = []
                    for ex in examples:
                        emb = await asyncio.to_thread(self._embedder.encode_single_full, ex)
                        level_embs.append(emb["dense"])
                    self._distress_embeddings[level] = level_embs

            self._initialized = True
            logger.info("Semantic distress detector initialized")
        except Exception as e:
            logger.error(f"Failed to initialize SemanticDistressDetector: {e}")

    async def detect(self, message: str) -> DistressLevel | None:
        """
        Detect distress via semantic similarity to known distress patterns.
        """
        if not self._initialized:
            await self.initialize()

        if not self._distress_embeddings:
            return None

        try:
            # Encode user message
            msg_embedding = await asyncio.to_thread(self._embedder.encode_single_full, message)
            msg_vec = np.array(msg_embedding["dense"])

            # Compare against each level's examples
            max_sim = 0.0
            detected_level = None

            for level in sorted(self._distress_embeddings.keys(), reverse=True):
                level_embs = self._distress_embeddings[level]
                similarities = []
                for emb in level_embs:
                    emb_vec = np.array(emb)
                    sim = np.dot(msg_vec, emb_vec) / (
                        np.linalg.norm(msg_vec) * np.linalg.norm(emb_vec)
                    )
                    similarities.append(sim)

                best_sim = max(similarities) if similarities else 0.0
                if best_sim > self._threshold and best_sim > max_sim:
                    max_sim = best_sim
                    detected_level = level

            if detected_level:
                logger.info(
                    f"Semantic distress detected: level={detected_level.name}, sim={max_sim:.3f}"
                )

            return detected_level
        except Exception as e:
            logger.warning(f"Semantic distress detection failed: {e}")
            return None


# ---------------------------------------------------------------------------
# Third-party concern (2026-09-27, W2 crisis-test expansion,
# coordinator-confirmed gap): "she said she wants to kill herself" scored
# DistressLevel.NONE — the classifier only ever looked for FIRST-person
# ideation ("myself"). A seeker worried about someone ELSE needs a
# fundamentally different response: helpline info for the person at risk,
# NOT the first-person "are you safe right now" copy addressed to the
# speaker (who is not the one in danger). Checked BEFORE the ordinary
# per-language scan in assess_distress() so it takes priority whenever both
# could technically match (e.g. a message that also happens to contain a
# first-person-shaped word).
#
# AI-AUTHORED, PENDING-CLINICIAN-REVIEW: detection pattern and the response
# copy in THIRD_PARTY_CRISIS_RESPONSE below are both unreviewed by a mental
# health professional — see the W2 review packet
# (docs/agent/W2_CRISIS_REVIEW_PACKET_2026-09-27.md).
# ---------------------------------------------------------------------------
_THIRD_PARTY_CONCERN_RE = re.compile(
    r"\b(she|he|they|my\s*(friend|sister|brother|mom|mother|dad|father|partner|"
    r"husband|wife|colleague|classmate|son|daughter))\b"
    r"[^.?!]{0,40}\b("
    r"wants?\s*to\s*(kill\s*(her|him|them)self|die|commit\s*suicide|end\s*(her|his|their)\s*life)|"
    r"is\s*going\s*to\s*(kill\s*(her|him|them)self|end\s*(her|his|their)\s*life)|"
    r"is\s*suicidal|"
    r"(has\s*)?commit(?:ted|ting)?\s*suicide|"
    r"said\s*(she|he|they)\s*(wants?\s*to\s*)?(kill\s*(her|him|them)self|die)"
    r")\b",
    re.IGNORECASE,
)

# AI-AUTHORED, PENDING-CLINICIAN-REVIEW. Helper-oriented: addresses the
# speaker as someone concerned for another person, never asks "are you safe
# right now" (that question is meaningless directed at the wrong person),
# and points them at helplines for the at-risk person plus what to do if
# danger is immediate.
THIRD_PARTY_CRISIS_RESPONSE = (
    "🙏 Thank you for caring enough to reach out about someone else's safety — "
    "that matters, and so does what happens next.\n\n"
    "If they are in immediate danger right now, please contact local emergency "
    "services, or help them get to a safe place — don't leave them alone if "
    "you can help it.\n\n"
    "Please encourage them to reach out to one of these crisis helplines "
    "themselves, or reach out on their behalf if you're worried they won't:"
)

# ---------------------------------------------------------------------------
# Idiom exclusions (2026-09-28, owner-approved Task 2): a small, EXACT list of
# common hyperbole idioms that use lethal-sounding words without any real
# distress meaning. Matched and masked out BEFORE any crisis/severe pattern
# runs — see the masking call at the top of assess_distress(). Kept
# deliberately short and literal (not a broad "sounds like a joke" heuristic)
# so it can only ever suppress these exact phrasings, never a real one; a
# parametrized test (test_crisis_w2_expansion.py /
# test_idiom_exclusions_never_swallow_real_ideation.py) guards that no
# genuine ideation phrase from the W2 set or test_serene_mind.py is ever
# excluded by this list.
# ---------------------------------------------------------------------------
IDIOM_EXCLUSIONS_RE = re.compile(
    r"\b(kill(?:ing)?\s*myself\s*laughing|dying\s*of\s*laughter|"
    r"laugh(?:ed|ing)?\s*myself\s*to\s*death|died?\s*laughing|"
    r"could\s*die\s*laughing)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# SEVERE ideation check-in response (2026-09-28, owner-approved Task 1
# re-tier). Distinct from DISTRESS_RESPONSES[SEVERE] (the pre-existing
# generic SEVERE template, which itself asks "Are you safe right now?" — too
# close to full CRISIS copy for a message with NO stated intent/plan/method/
# timeframe). This is a gentler check-in: acknowledges the pain, asks one
# open question, and still surfaces helplines (Tele-MANAS etc., via the same
# `resources` block DistressStage always prepends) rather than assuming
# either way. AI-AUTHORED, PENDING-CLINICIAN-REVIEW — see the W2 review
# packet.
SEVERE_IDEATION_CHECKIN_RESPONSE = (
    "I hear real pain in what you're describing, and I don't want to brush past it. "
    "You don't have to carry this alone.\n\n"
    "Can you tell me a little more about what's going on for you right now? "
    "I'm listening, and I care about how you're doing.\n\n"
    "If things ever feel like more than you can handle, these are here for you "
    "any time, no need to wait:"
)


class SereneMindEngine:
    """
    Emotional intelligence engine for Mukthi Guru.

    Performs multi-language distress detection using:
    1. Keyword/pattern matching (fast, reliable baseline)
    2. Conversation history analysis (escalation detection)

    Future: Embedding-based semantic similarity for nuanced detection.
    """

    def __init__(self, embedding_service=None):
        """
        Initialize the Serene Mind Engine.

        Args:
            embedding_service: Optional embedding service for semantic distress detection.
                              If provided, enables semantic similarity-based detection.
        """
        from app.config import settings

        self._embedder = embedding_service
        self._semantic_detector = None
        if embedding_service:
            self._semantic_detector = SemanticDistressDetector(embedding_service)
        self.distress_threshold = settings.semantic_distress_escalation_count
        self.rolling_window = settings.semantic_distress_rolling_window
        self._history_score_threshold = settings.semantic_distress_history_score_threshold
        logger.info("Serene Mind Engine initialized")

    async def analyze_with_history(self, message: str, history: list) -> DistressAssessment:
        # Check window for escalating patterns
        recent = history[-self.rolling_window :]

        # R1 fix (2026-09-22): this used to read `distress_score` off each
        # history message, but nothing anywhere in the codebase ever writes
        # that field onto a history message — `distress_count` was always 0
        # and this escalation branch was structurally dead. Classify each
        # recent USER turn with the same cheap regex-only `_quick_distress_check`
        # that `assess_distress()`'s own history-escalation block (below, via
        # async_assess_distress) already uses, instead of a full LLM/semantic
        # pass per history message — that's the actual, reachable signal.
        def _msg_role(msg):
            return msg.get("role", "") if isinstance(msg, dict) else getattr(msg, "role", "")

        def _msg_content(msg):
            return (
                msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
            ) or ""

        distress_count = sum(
            1
            for msg in recent
            if _msg_role(msg) == "user" and self._quick_distress_check(_msg_content(msg))
        )

        # R1 fix: forward `history` so assess_distress()'s existing "multiple
        # distress signals in conversation" escalation (MODERATE -> SEVERE,
        # NONE/MILD -> MODERATE) actually receives real conversation history
        # instead of running as if every message were the first turn. This
        # also fixes R2 as a side effect: `async_assess_distress`'s
        # `has_recent_distress` early-return gate was computed from this same
        # (previously never-passed) history, so real fallback stages
        # (LLM/semantic) were structurally unreachable whenever regex missed
        # on the current message but history showed a pattern.
        assessment = await self.async_assess_distress(message, conversation_history=history)

        # If user explicitly states they are burned out/pointless etc, trigger MODERATE
        if (
            assessment.level == DistressLevel.MILD
            and assessment.recommended_response_type == "gentle"
        ):
            assessment.level = DistressLevel.MODERATE
            assessment.recommended_response_type = "meditation"

        # Escalate if persistent
        if distress_count >= self.distress_threshold and assessment.level.value >= 1:
            assessment.level = DistressLevel.SEVERE
            assessment.detected_signals.append("Persistent distress over rolling window")

        return assessment

    def assess_distress(
        self,
        message: str,
        conversation_history: Optional[list[dict]] = None,
    ) -> DistressAssessment:
        """
        Assess the distress level of a user message.

        Uses multi-language keyword patterns with conversation history context.

        Args:
            message: The user's message text
            conversation_history: Optional list of prior messages for escalation detection

        Returns:
            DistressAssessment with level, confidence, and recommended response type
        """
        # Phones type U+2019 for "'" (smart punctuation); every "don'?t"-style
        # pattern is written with ASCII, so fold it before scanning.
        message = message.replace("\u2019", "'").replace("\u2018", "'")
        # 2026-09-28 (owner-approved, Task 2 "idiom exclusions"): mask a
        # small, exact list of hyperbole idioms ("kill myself laughing",
        # "dying of laughter", ...) BEFORE any pattern matching runs, so they
        # can never trip the crisis/severe patterns below. Masking (not just
        # skipping the whole message) means a message that ALSO contains real
        # ideation elsewhere ("kill myself laughing at that, but honestly I
        # want to end my life") still gets caught by the real phrase.
        message = IDIOM_EXCLUSIONS_RE.sub(" ", message)

        # Third-party concern takes priority over the ordinary first-person
        # scan below — see _THIRD_PARTY_CONCERN_RE's module-level docstring.
        if _THIRD_PARTY_CONCERN_RE.search(message):
            return DistressAssessment(
                level=DistressLevel.CRISIS,
                confidence=0.9,
                detected_signals=["[third_party] concern for another person's safety"],
                language_detected=self._detect_language(message),
                recommended_response_type="third_party_crisis",
            )

        message_lower = message.lower()
        signals = []
        max_level = DistressLevel.NONE
        max_confidence = 0.0

        # Also scan the de-obfuscated text (spaced letters, leetspeak, homoglyphs).
        # It can only add matches; the original text is always scanned too.
        variants = [message_lower]
        deobfuscated = deobfuscate(message)
        if deobfuscated != message_lower:
            variants.append(deobfuscated)

        # Scan across all language patterns
        for lang, levels in _ALL_PATTERNS.items():
            for level in sorted(levels.keys(), reverse=True):  # Check most severe first
                for pattern in levels[level]:
                    matches = []
                    for variant in variants if lang in _LATIN_SCRIPT_LANGS else [message]:
                        matches = pattern.findall(variant)
                        if matches:
                            break
                    if matches:
                        signal_text = f"[{lang}] {matches[0]}"
                        signals.append(signal_text)
                        if level > max_level:
                            max_level = level
                            # Higher severity = higher confidence
                            max_confidence = min(0.5 + (level.value * 0.15), 1.0)

        # Words split to dodge patterns ("k1ll mysel f"): letters-only check, only
        # for text that is visibly obfuscated (on plain text it joins innocent words).
        if looks_obfuscated(message) and _OBFUSCATED_CRISIS.search(compact_letters(message)):
            signals.append("[obfuscated] crisis phrase")
            if DistressLevel.CRISIS > max_level:
                max_level = DistressLevel.CRISIS
                max_confidence = min(0.5 + (DistressLevel.CRISIS.value * 0.15), 1.0)

        # Escalation detection from conversation history
        if conversation_history and len(conversation_history) >= 2:
            recent_distress_count = sum(
                1
                for msg in conversation_history[-6:]
                if msg.get("role") == "user" and self._quick_distress_check(msg.get("content", ""))
            )
            if recent_distress_count >= 2:
                # User has expressed distress multiple times — escalate
                if max_level < DistressLevel.MODERATE:
                    max_level = DistressLevel.MODERATE
                    max_confidence = max(max_confidence, 0.7)
                    signals.append("[escalation] Multiple distress signals in conversation")
                elif max_level == DistressLevel.MODERATE:
                    max_level = DistressLevel.SEVERE
                    max_confidence = max(max_confidence, 0.8)
                    signals.append("[escalation] Persistent distress pattern detected")

        # Map level to response type
        response_type_map = {
            DistressLevel.NONE: "normal",
            DistressLevel.MILD: "gentle",
            DistressLevel.MODERATE: "meditation",
            DistressLevel.SEVERE: "meditation",
            DistressLevel.CRISIS: "crisis",
        }
        recommended_response_type = response_type_map.get(max_level, "normal")
        # 2026-09-28 (owner-approved re-tier): a SEVERE result whose winning
        # signal is passive ideation / ambiguous spiritual framing (no plan,
        # method, or timeframe) gets the gentler check-in response instead of
        # the generic SEVERE template — checked against the exact same
        # pattern list used to build that tier (_SEVERE_IDEATION_CHECKIN_RE),
        # so this can never silently drift from the patterns themselves.
        if max_level == DistressLevel.SEVERE and _SEVERE_IDEATION_CHECKIN_RE.search(message):
            recommended_response_type = "severe_ideation_checkin"

        # Detect language for response localization
        detected_lang = self._detect_language(message)

        assessment = DistressAssessment(
            level=max_level,
            confidence=max_confidence,
            detected_signals=signals,
            language_detected=detected_lang,
            recommended_response_type=recommended_response_type,
        )

        if max_level > DistressLevel.NONE:
            logger.info(
                f"Serene Mind: Detected distress level={max_level.name}, "
                f"confidence={max_confidence:.2f}, signals={signals}, "
                f"lang={detected_lang}"
            )

        return assessment

    async def async_assess_distress(
        self,
        message: str,
        conversation_history: Optional[list[dict]] = None,
    ) -> DistressAssessment:
        """
        Three-stage distress assessment:
        1. Fast keyword detection (sync)
        2. LLM semantic classification (async)
        3. Embedding-based semantic similarity (async)

        Returns the HIGHEST distress level found across all stages.
        """
        # Stage 1: Fast keyword (always run)
        assessment = self.assess_distress(message, conversation_history)

        # Stage 2: LLM fallback is reserved for messages with a lexical
        # distress signal or recent distress history. Calling the classifier
        # for every ordinary doctrine question added roughly 8–10 seconds to
        # the user-facing path while contributing no safety signal. The
        # deterministic Stage 1 scan remains unconditional and covers the
        # crisis/question-framed patterns before this gate.
        has_recent_distress = bool(
            conversation_history
            and any(
                self._quick_distress_check(msg.get("content", "") if isinstance(msg, dict) else "")
                for msg in conversation_history[-self.rolling_window :]
            )
        )
        if assessment.level == DistressLevel.NONE and not has_recent_distress:
            return assessment

        if assessment.level < DistressLevel.MODERATE:
            try:
                from app.dependencies import get_container

                container = get_container()
                if container.ollama:
                    # Phase 3: Deterministic JSON outputs via Instructor
                    structured_assessment = await container.ollama.classify_distress_structured(
                        message[:512]
                    )
                    if structured_assessment.get("is_distress"):
                        assessment.level = DistressLevel.MODERATE
                        assessment.confidence = structured_assessment.get("confidence", 0.55)
                        reason = structured_assessment.get("reason", "Semantic distress")
                        assessment.detected_signals.append(f"[LLM Stage 2] {reason}")
            except Exception as e:
                logger.warning(f"Stage 2 LLM distress detection failed: {e}")

        # Stage 3: Embedding-based semantic detection (if available)
        if self._semantic_detector and assessment.level < DistressLevel.CRISIS:
            try:
                semantic_level = await self._semantic_detector.detect(message)
                if semantic_level and semantic_level > assessment.level:
                    assessment.level = semantic_level
                    assessment.confidence = 0.65
                    assessment.detected_signals.append(f"[Semantic Stage 3] {semantic_level.name}")
            except Exception as e:
                logger.warning(f"Stage 3 semantic distress detection failed: {e}")

        # Update response type based on final level.
        # 2026-09-27 (W2 crisis-test expansion): this used to run
        # unconditionally, which silently wiped out the third-party-concern
        # marker `assess_distress()` sets on Stage 1 ("she said she wants to
        # kill herself" -> recommended_response_type="third_party_crisis")
        # every time this async wrapper ran — i.e. every real production
        # call, since DistressStage always calls analyze_with_history ->
        # async_assess_distress, never the bare sync assess_distress(). The
        # live symptom: the third-party detector worked in isolation but the
        # real /api/chat response still used the first-person "are you safe
        # right now" template. Both that marker and the 2026-09-28
        # "severe_ideation_checkin" marker (owner-approved re-tier, Task 1)
        # are deliberate, more-specific signals from an earlier stage and
        # must survive this generic level-based update, so both are
        # explicitly exempted.
        _SPECIFIC_RESPONSE_TYPES = {"third_party_crisis", "severe_ideation_checkin"}
        response_type_map = {
            DistressLevel.NONE: "normal",
            DistressLevel.MILD: "gentle",
            DistressLevel.MODERATE: "meditation",
            DistressLevel.SEVERE: "meditation",
            DistressLevel.CRISIS: "crisis",
        }
        if assessment.recommended_response_type not in _SPECIFIC_RESPONSE_TYPES:
            assessment.recommended_response_type = response_type_map.get(assessment.level, "normal")

        return assessment

    async def analyze_distress_trend(
        self, user_id: str, current_assessment: DistressAssessment, user_profile_service
    ) -> DistressAssessment | None:
        """
        Analyze distress trend across conversation history to determine
        if proactive Serene Mind triggering is warranted.

        Returns:
            DistressAssessment if triggering is recommended, None otherwise
        """
        # Get recent conversation memories for this user
        recent_memories = await user_profile_service.get_recent_memories(user_id, limit=5)

        if not recent_memories:
            return None

        # Extract distress levels from emotional arcs
        distress_timeline = []
        for memory in recent_memories:
            for emotional_point in memory.emotional_arc:
                distress_timeline.append(
                    {
                        "timestamp": emotional_point["timestamp"],
                        "level": emotional_point["distress_level"],
                        "topic": emotional_point.get("topic", "unknown"),
                    }
                )

        # Sort by timestamp (oldest first)
        distress_timeline.sort(key=lambda x: x["timestamp"])

        # Keep only last 10 data points for trend analysis
        recent_distress = (
            distress_timeline[-10:] if len(distress_timeline) > 10 else distress_timeline
        )

        if len(recent_distress) < 3:
            return None  # Need minimum data for trend analysis

        # Calculate trend metrics
        levels = [point["level"] for point in recent_distress]

        # Metric 1: Average distress level over recent turns
        avg_distress = sum(levels) / len(levels)

        # Metric 2: Distress escalation (is trend increasing?)
        if len(levels) >= 3:
            # Compare first half vs second half
            mid_point = len(levels) // 2
            first_half_avg = sum(levels[:mid_point]) / len(levels[:mid_point])
            second_half_avg = sum(levels[mid_point:]) / len(levels[mid_point:])
            escalation_rate = second_half_avg - first_half_avg
        else:
            escalation_rate = 0

        # Metric 3: Frequency of moderate+ distress
        moderate_plus_count = sum(1 for level in levels if level >= DistressLevel.MODERATE.value)
        distress_frequency = moderate_plus_count / len(levels)

        # Get configuration settings (with defaults)
        try:
            from app.config import settings

            PROACTIVE_ENABLED = getattr(settings, "proactive_serene_mind_enabled", True)
            AVG_THRESHOLD = getattr(settings, "proactive_distress_avg_threshold", 1.5)
            TREND_THRESHOLD = getattr(settings, "proactive_distress_trend_threshold", 0.5)
            FREQ_THRESHOLD = settings.proactive_distress_frequency_threshold
            MIN_POINTS = getattr(settings, "proactive_min_conversation_points", 3)
        except Exception:
            import logging

            logging.getLogger(__name__).debug(
                "Proactive config import failed, using defaults", exc_info=True
            )
            # Fallback defaults if config import fails
            PROACTIVE_ENABLED = True
            AVG_THRESHOLD = 1.5
            TREND_THRESHOLD = 0.5
            FREQ_THRESHOLD = 0.6
            MIN_POINTS = 3

        if not PROACTIVE_ENABLED:
            return None

        # ── Threshold Calibration Reference ─────────────────────────────────────
        # Based on the clinician-validated sonia-health/llm-mental-health-risk-detection
        # benchmark (https://github.com/sonia-health/llm-mental-health-risk-detection):
        #
        #   LOW risk  → MILD (1):    Conversational distress, general worry, mild sadness.
        #                            Watchful: guide gently. Do NOT proactively gate chat.
        #   MED risk  → MODERATE (2): Sustained distress, crying, hopelessness sub-threshold.
        #                            AVG_THRESHOLD ≥ 1.5 catches this tier across 3+ turns.
        #   HIGH risk → SEVERE (3):  Acute suffering, mention of harm. Trigger immediately.
        #   CRISIS    → CRISIS (4):  Active self-harm language. Escalate to crisis resources.
        #
        # Our AVG_THRESHOLD=1.5 intentionally sits between MILD and MODERATE so that
        # a single MODERATE hit across 3 turns triggers proactive wellness (not just one
        # upset message). FREQ_THRESHOLD=0.6 ensures >60% of recent turns show distress.
        # ─────────────────────────────────────────────────────────────────────────────
        # Triggering Conditions
        SHOULD_TRIGGER = (
            # Condition 1: Consistently elevated distress
            (avg_distress >= AVG_THRESHOLD and len(recent_distress) >= MIN_POINTS)
            or
            # Condition 2: Clear escalation trend
            (escalation_rate >= TREND_THRESHOLD and avg_distress >= DistressLevel.MILD.value)
            or
            # Condition 3: High frequency of moderate distress
            (distress_frequency >= FREQ_THRESHOLD and len(recent_distress) >= MIN_POINTS + 1)
            or
            # Condition 4: Recent severe distress with any elevation
            (max(levels) >= DistressLevel.SEVERE.value and avg_distress >= DistressLevel.MILD.value)
        )

        if SHOULD_TRIGGER:
            # Return a proactive assessment suggesting Serene Mind
            return DistressAssessment(
                level=DistressLevel.MODERATE,  # Always suggest at least moderate level
                confidence=min(0.9, 0.5 + (avg_distress / 10)),  # Scale confidence with distress
                detected_signals=[
                    f"Proactive trigger: avg={avg_distress:.1f}, trend={escalation_rate:.1f}, freq={distress_frequency:.1f}"
                ],
                language_detected=current_assessment.language_detected,
                recommended_response_type="meditation",
            )

        return None

    def get_response(self, assessment: DistressAssessment) -> str:
        """
        Get the appropriate response for a given distress assessment.

        Returns a compassionate, graduated response with crisis resources if needed.
        """
        if assessment is None or getattr(assessment, "level", None) == DistressLevel.NONE:
            return DISTRESS_RESPONSES[DistressLevel.MILD]

        base_response = DISTRESS_RESPONSES.get(
            assessment.level,
            DISTRESS_RESPONSES[DistressLevel.MODERATE],
        )

        # For SEVERE and CRISIS, append crisis resources
        if assessment.level >= DistressLevel.SEVERE:
            base_response += "\n" + CRISIS_RESOURCES["india"]
            base_response += "\n" + CRISIS_RESOURCES["us"]

        return base_response

    def _quick_distress_check(self, text: str) -> bool:
        """Quick check if a message contains any distress signals (for history analysis)."""
        text_lower = text.lower()
        for lang, levels in _ALL_PATTERNS.items():
            for level, patterns in levels.items():
                if level >= DistressLevel.MODERATE:
                    for pattern in patterns:
                        if pattern.search(text_lower if lang in _LATIN_SCRIPT_LANGS else text):
                            return True
        return False

    def _detect_language(self, text: str) -> str:
        from services.language_detection import detect_language

        return detect_language(text)["language"]
