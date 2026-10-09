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

# Contraction / negation folding (2026-10-05, live release run rt5b: "I cannot
# go on" scored NONE while "can't go on" matched). Every English pattern is
# written with the contracted form ("can'?t", "don'?t"), so the scan also runs
# on a copy where the spelled-out and apostrophe-less forms are folded to it.
# The original text is always scanned too: folding can only add matches.
_CONTRACTION_FOLDS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"\bcan\s*not\b|\bcant\b", re.IGNORECASE), "can't"),
    (re.compile(r"\bdo\s+not\b|\bdont\b", re.IGNORECASE), "don't"),
    (re.compile(r"\bdoes\s+not\b|\bdoesnt\b", re.IGNORECASE), "doesn't"),
    (re.compile(r"\bdid\s+not\b|\bdidnt\b", re.IGNORECASE), "didn't"),
    (re.compile(r"\bwill\s+not\b|\bwont\b", re.IGNORECASE), "won't"),
    (re.compile(r"\bcould\s+not\b|\bcouldnt\b", re.IGNORECASE), "couldn't"),
)


def normalize_contractions(text: str) -> str:
    """Fold curly apostrophes and spelled-out / apostrophe-less negations
    ("cannot", "can not", "cant", "do not", "dont" ...) to the contracted
    form the patterns use. Lower-cases nothing; callers scan it as an extra
    variant next to the original text."""
    out = (text or "").replace("\u2019", "'").replace("\u2018", "'").replace("\u02bc", "'")
    for rx, repl in _CONTRACTION_FOLDS:
        out = rx.sub(repl, out)
    return out


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
    # 2026-10-05 (live release run rt5a): "I want to disappear" scored NONE and
    # got a generated teacher-voice answer with no helpline. Passive ideation:
    # disappear / vanish / not exist / not be here, as a wish or want of the
    # speaker. "make the stress disappear" does not match ("want to" must
    # govern the verb directly). AI-AUTHORED, PENDING-CLINICIAN-REVIEW.
    r"\b(want\w*|wanna|wish\w*|need\w*)\s*(to\s*)?(just\s*|simply\s*)?"
    r"(disappear|vanish|stop\s*existing|cease\s*to\s*exist|not\s*exist|not\s*be\s*here)\b"
    r"(?!\s+into\s+(meditation|the\s+practice|silence|stillness|the\s+teaching))",
    r"\bwish\w*\s*(that\s*)?i\s*(could\s*)?(just\s*)?(disappear|vanish)\b",
    r"\bwish\w*\s*(that\s*)?i\s*(was|were)\s*(not\s*here|gone|never\s*born)\b",
    r"\bwish\w*\s*(that\s*)?i\s*(didn'?t|did\s*not|don'?t)\s*exist\b",
    r"\bno\s*(reason|point)\s*(to|in|of)\s*(go\s*on\s*|keep\s*on\s*)?(living|live|being\s*alive|going\s*on|carrying\s*on|keep\w*\s*going)\b",
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
        # 2026-10-08 (addiction + ideation probes, evals/scenarios/tier3_crisis/006): a bare
        # "I don't want to live" (no "anymore") and an already-taken overdose scored NONE.
        # The lookahead keeps "I don't want to live in Delhi / with my parents / like this
        # forever" open to ordinary speech. AI-AUTHORED, PENDING-CLINICIAN-REVIEW.
        r"\b(?:don'?t|do\s*not)\s*want\s*to\s*(?:live|be\s*alive)\b(?!\s*(?:in|with|near|without|like|here|there|alone|a\b|an\b|my\b|the\b|at\b|on\b|off\b))",
        r"\b(?:took|taken|swallowed|had)\s*(?:too\s*many|a\s*lot\s*of|all\s*(?:my|the|of\s*my))\s*(?:pills?|tablets?|sleeping\s*(?:pills?|tablets?))\b",
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
        # 2026-10-07 (WP2): lethal-quantity method research, any phrasing
        # ("how much paracetamol is fatal", "what amount of X is lethal",
        # "how many of these pills would be fatal"). The object must be a
        # medicine or poison: "how much water is lethal for a houseplant" is not.
        r"\b(how\s*(much|many)|what\s*(amount|dose|quantity))\s*(of\s*)?(these\s*|those\s*|my\s*|the\s*)?"
        r"(\w+\s*){0,2}?(pills?|tablets?|meds|medicines?|medications?|paracetamol|acetaminophen|"
        r"ibuprofen|aspirin|insulin|poison)\s*(is|are|would\s*be|will\s*be|could\s*be)\s*"
        r"(a\s*)?(fatal|lethal|deadly|enough\s*to\s*(die|kill\s*me))\b",
        r"\b(sav(ed|ing)|stockpil\w*|hoard\w*)\s*(up\s*)?(my\s*|all\s*my\s*|enough\s*)?(sleeping\s*)?(pills?|tablets?|meds|medications?)\b",
        r"\b(pills?|tablets?|meds|medications?)\s*(saved|stashed|stockpiled|hoarded)\b",
        # "kms" (kill myself); "5 kms" (kilometres) is excluded.
        r"(?<!\d)(?<!\d\s)\bkms\b",
        r"\bwant\w*\s*(the\s*pain\s*to\s*(stop|end)\s*(forever|for\s*good|permanently)|(it\s*all|everything)\s*to\s*(end|stop))\b",
    ],
    DistressLevel.SEVERE: [
        r"\b(hopeless|worthless|give\s*up|no\s*point|nothing\s*matters?)\b",
        # "can't go on" as a statement about going on, not "can't go on a trip"
        # (2026-10-05). Matched on the contraction-folded text too, so
        # "cannot / can not / cant go on" score the same (live rt5b scored NONE).
        r"\bcan'?t\s*(go|carry|keep)\s*on(?=\s*$|\s*[.!?,;:]|\s+(any\s*more|like\s*this|living|"
        r"with\s*(my\s*)?life|without|in\s*this\s*life|for\s*much\s*longer|no\s*more)\b)",
        r"\bcan'?t\s*(take|handle|bear|stand|do)\s*(it|this|life)\s*any\s*more\b",
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
        r"\bhow\s*many\s*(\w+\s*){0,2}(pills?|tablets?|paracetamol|sleeping\s*pills)\s*(it\s*)?(would|will|does|do)\s*(it\s*)?(take|kill)\b",
        # 2026-10-06 (research thread: mid-range / implicit risk was untested).
        # Warning-sign behaviours and passive wishes that scored NONE: "pills IT
        # would take" (the pattern above wanted the verb first), sleeping and not
        # waking without "wish"/"hope", giving possessions away because they
        # "won't need" them, goodbye letters, saying goodbye, no future for
        # oneself. SEVERE = gentle check-in plus helplines, never NONE. Each is
        # anchored on a first-person or finality cue; false positives pinned in
        # tests/test_implicit_distress_2026_10_06.py. AI-AUTHORED, NOT
        # clinician-reviewed.
        r"\b(want|wish|like|love)\w*\s*to\s*(just\s*)?(go\s*to\s*)?sleep\s*and\s*(not|never)\s*wake\s*up\b",
        # 2026-10-07 (WP2): "gave" and "won't be needing" were outside this class.
        r"\b(giv\w*|gave)\s*away\s*(all\s*)?(of\s*)?my\s*(things|stuff|belongings|possessions)\b.{0,60}"
        r"\b(won'?t|will\s*not|don'?t|no\s*longer)\s*(be\s*)?need\w*\b",
        # 2026-10-07 (WP2): a farewell card for someone retiring or leaving a job
        # is not a goodbye letter from the speaker (found as a false positive).
        r"\bgoodbye\s*(letters?|notes?)\b(?!.{0,40}\b(retir\w*|farewell|send-?off|leaving\s+(the\s+)?(company|job|school|office))\b)",
        r"\b(letters?|notes?)\s*to\s*(everyone|my\s*(family|kids|children|parents|friends))\b.{0,20}\bjust\s*in\s*case\b",
        r"\b(started|been|keep|begun)\s*saying\s*(my\s*)?goodbyes?\s*to\s*(people|everyone|my\s*(family|friends|loved\s*ones))\b",
        r"\b(don'?t|can'?t|do\s*not|cannot)\s*see\s*(a|any)\s*future\s*for\s*(myself|me)\b",
        # 2026-10-07 (WP2, evals/scenarios/tier3_crisis/005_*): implicit
        # ideation classes that all scored NONE/MILD/MODERATE. One pattern per
        # CLASS, each with a negative control in
        # tests/test_wp2_implicit_ideation_religious_misuse.py. AI-AUTHORED,
        # NOT clinician-reviewed.
        # (a) burdensomeness: lighter / happier / relieved ... without me.
        r"\b(everyone|everybody|they|they'?d|people|my\s*(family|parents|kids|children|wife|husband|partner|friends))"
        r"\s*(would|will|'d)?\s*(all\s*)?(be\s*)?(so\s*)?(much\s*)?"
        r"(lighter|happier|freer|relieved|easier|at\s*peace)\s*(off\s*)?without\s*me\b",
        # (b) "it / life would be easier ... without me / if I didn't exist /
        # wasn't here" (a time or place after "here" is a schedule, not a wish).
        r"\b(it|life|things|everything)\s*would\s*be\s*(so\s*much\s*|much\s*|a\s*lot\s*)?"
        r"(easier|better|lighter|simpler)\s*(for\s*(everyone|everybody|them|my\s*\w+)\s*)?"
        r"(without\s*me\b|if\s*i\s*(just\s*)?(didn'?t\s*exist|did\s*not\s*exist|"
        r"(wasn'?t|weren'?t)\s*(here|around|alive)\b(?!\s*(at|by|on|for|in|before|after|tomorrow|today|tonight|this|next)\b)|"
        r"(was|were)\s*(gone|dead)|disappeared|died)\b)",
        # (c) nobody would notice / care / miss me if I were gone.
        r"\b(nobody|no\s*one|no-one)\s*(would|will|'d)\s*(even\s*)?(notice|care|miss\s*me|mind)\b.{0,15}"
        r"\bif\s*i\s*((was|were|am|'m)\s*)?(just\s*)?(gone|dead|disappeared|died|wasn'?t\s*(here|around))\b",
        # (d) method research by quantity ("how many of these tablets is too many").
        r"\bhow\s*many\s*(of\s*(these|those|my|the)\s*)?(\w+\s*){0,2}(pills?|tablets?|meds|medications?|paracetamol)"
        r"\s*(is|are|would\s*be)\s*too\s*many\b(?!\s*to\s*(carry|bring|pack|keep|buy|travel|stock))",
        # (e) tired / sick of being alive (not "tired of living in this flat").
        r"\b(tired|sick|weary)\s*of\s*(being\s*alive|living|life|existing|my\s*life|this\s*life)\b"
        r"(?!'s|\s*(in|at|with|here|there|out\s*of|like\s*this\s*in)\b)",
        # (f) want it all / everything to be over (not "this meeting").
        r"\bwant\w*\s*(it\s*all|everything|all\s*of\s*(this|it)|my\s*life)\s*to\s*(just\s*)?be\s*over\b",
        # (g) no way out for me / of this life (not "of the parking lot").
        r"\bno\s*way\s*out\b(?=\s*(for\s*me|of\s*(this|my)\s*(life|pain|misery|suffering|situation|mess)|any\s*more|[.!?]|$))",
        # (h) won't be around / here much longer (not "... today, leaving at five").
        r"\b(won'?t|not\s*going\s*to)\s*be\s*(around|here|alive)\s*(for\s*)?(much|very)?\s*(longer|long)\b"
        r"(?!\s*(today|tonight|this|at|in\s*the|,?\s*(i'?m\s*)?(leaving|going|heading|have\s*to)))",
        # (i) can't see myself living / alive past ... (not "living in Mumbai").
        r"\bcan'?t\s*see\s*myself\s*(living|being\s*alive|alive|being\s*(here|around))\s*"
        r"(past|beyond|after|until|till|much\s*longer|next|another)\b",
        # (j) putting one's affairs in order (a recognised warning behaviour).
        r"\b(put\w*|get\w*|got|sort\w*|setting)\s*(all\s*)?my\s*affairs\s*in\s*order\b",
        # (k) thinking about not being here / alive, or ending it.
        r"\b(think\w*|thought)\s*(a\s*lot\s*|so\s*much\s*|constantly\s*)?about\s*("
        r"(not|no\s*longer)\s*being\s*(here|alive|around)\b(?!\s*(tomorrow|today|tonight|next|this|on|for|at|in|during)\b)|"
        r"ending\s*(it(\s*all)?|my\s*life|everything)\b(?!\s*with\b)|killing\s*myself\b)",
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
        # 2026-10-08 (addiction + ideation probes; UNVERIFIED by a native speaker): "मर जाना
        # चाहता" (the verb split form), "खुद को खत्म कर" and an already-taken overdose.
        r"मर\s*जाना\s*चाहत[ाी]|खुद\s*को\s*खत्म\s*कर|गोलियाँ[^.?!]{0,30}(?:खा\s*ली|ले\s*ली)",
        # 2026-10-07 (WP2, UNVERIFIED by a native speaker): lethal-quantity
        # method research ("how many pills to die").
        r"(गोलि(याँ|यां|यों)|गोली|टैबलेट|दवा\S*).{0,40}(मौत|मर\s*जा|मर\s*सक|मरूँ|मरूं|जान\s*चली)",
    ],
    DistressLevel.SEVERE: [
        r"(बहुत\s*(दुखी|उदास|अकेला|अकेली)|जीवन\s*व्यर्थ|कोई\s*उम्मीद\s*नहीं)",
        # 2026-10-07 (WP2, UNVERIFIED by a native speaker): implicit ideation.
        # Burdensomeness with any "easier / happier / lighter" word, either order.
        r"मेरे\s*बिना\s*(सब|सभी|सबकी|सबका|सबको|घरवाले|परिवार)\S*\s*(की\s*|का\s*|को\s*)?(ज़?िंदगी\s*|जीवन\s*)?"
        r"(बेहतर|अच्छ|आसान|खुश|सुखी|हल्क|आराम)",
        r"(सब|सभी|सबकी|घरवाले|परिवार)\S*\s*मेरे\s*बिना\s*(ज़?िंदगी\s*)?(बेहतर|अच्छ|आसान|खुश|सुखी|हल्क|आराम)",
        # Giving belongings away because they will not be needed.
        r"(चीज़?ें|सामान)\s*.{0,15}(बाँट|बांट|दान\s*कर|दे)\s*(दी|दिया|दिए|दिये).{0,40}ज़?रूरत\s*नहीं",
        # Sleep and never wake / get up again.
        r"(सो\s*जा\S*|सोना\s*चाह\S*).{0,25}(फिर|दोबारा|कभी)\s*(कभी\s*)?(न|ना|नहीं)\s*(उठ|जाग)",
        # Goodbye letters.
        r"अलविदा\s*(के|का|की)?\s*(ख़?त|पत्र|चिट्ठ\S*|नोट)",
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
        # 2026-10-07 (WP2, UNVERIFIED by a native speaker): "how many tablets to die".
        r"மாத்திரை\S*.{0,40}(சாவ|சாக|இறந்து|இறப்ப|உயிர்\s*போ)",
    ],
    DistressLevel.SEVERE: [
        r"(மிகவும்\s*வேதனை|நம்பிக்கையில்லை|தாங்க\s*முடியல|வாழ\s*விருப்பமில்லை)",
        # 2026-10-07 (WP2, UNVERIFIED by a native speaker): burdensomeness with
        # any "fine / peaceful / happy" word, and sleep-and-never-wake.
        r"இல்லா(மல்|ம)\s*(எல்லோரும்|எல்லாரும்|அனைவரும்|எல்லாருக்கும்)\s*"
        r"(நன்றாக|நல்லா|நிம்மதியா|சந்தோஷமா|சந்தோசமா|சுகமா)",
        r"(மறுபடி|மீண்டும்|திரும்ப)\S*\s*(எழுந்திருக்க|எழ)\S*\s*(கூடாது|வேண்டாம்)",
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
        # 2026-10-07 (WP2, UNVERIFIED by a native speaker): burdensomeness with
        # any "fine / comfortable / happy" word; giving all belongings away
        # because they are not needed; sleep and never get up again.
        r"లేకపోతే\s*(అందరూ|అందరికీ|అందరు)\s*(బాగు|హాయిగా|సంతోషంగా|సుఖంగా|ప్రశాంతంగా)",
        r"(వస్తువు\S*|సామాను\S*|అన్నీ).{0,20}ఇచ్చేశా\S*.{0,40}అవసరం\s*(లేదు|ఉండదు)",
        r"(మళ్ళీ|మళ్లీ|ఇక)\s*(నిద్ర\s*)?లేవ\S*(కూడదని|కుండా\s*ఉండాలని|వద్దని)",
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
        # 2026-10-07 (WP2, UNVERIFIED by a native speaker): "if I weren't here
        # everyone would be fine / at peace / happy" in any conditional form
        # (ಇಲ್ಲದೆ / ಇಲ್ಲದಿದ್ದರೆ / ಇಲ್ಲದಿದ್ರೆ, joined or not), and sleep-and-never-wake.
        r"(ನಾನಿಲ್ಲದ|ಇಲ್ಲದ)\S*\s*ಎಲ್ಲರೂ\s*(ಚೆನ್ನಾಗಿ|ನೆಮ್ಮದಿ|ಖುಷಿ|ಸಂತೋಷ|ಸುಖ)",
        r"(ಮತ್ತೆ|ಮರಳಿ|ಇನ್ನು)\s*(ಏಳ|ಎದ್ದೇಳ|ಎಚ್ಚರ)\S*(ಬಾರದು|ಬಾರದೆಂದು|ದಿರಲಿ)",
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
        # 2026-10-07 (WP2, UNVERIFIED by a native speaker): "how many pills to die".
        r"गोळ्या\S*.{0,30}(मरता|मरेन|मरून|मरायला|जीव\s*जाई\S*)",
    ],
    DistressLevel.SEVERE: [
        r"(खूप\s*(दुःखी|उदास|एकटा|एकटी)|आशा\s*नाही|जगणं\s*व्यर्थ)",
        # 2026-10-07 (WP2, UNVERIFIED by a native speaker): burdensomeness
        # ("everyone happier / life easier without me") and sleep-and-never-wake.
        r"माझ्या\s*शिवाय\s*(सगळे|सगळ्यां\S*|सर्व\S*|सगळं|घरचे)\s*.{0,15}(सुखी|सुखात|बरे|बरं|आनंदी|चांगले|सोपं|सोपे|मोकळे)",
        r"(परत|पुन्हा)\s*उठू\S*\s*नये",
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
        # 2026-10-07 (WP2, UNVERIFIED by a native speaker): burdensomeness in
        # either word order, and sleep-and-never-wake, romanized.
        r"\bmere\s*bina\s*(sab|sabhi|sabki|sabka|sabko|ghar\s*wale|family)\w*\s*(ki\s*|ka\s*|ko\s*)?(zindagi\s*)?"
        r"(khush|behtar|accha|achha|aasaan|asaan|sukhi)",
        r"\b(sab|sabhi|sabko|sabki|ghar\s*wale|family)\s*(log\s*)?mere\s*bina\s*(zindagi\s*)?"
        r"(khush|behtar|accha|achha|aasaan|asaan|sukhi)",
        r"\bso\s*(jaun|jaaun|jau|jaana|jaaun)\b.{0,25}\b(phir|kabhi|dobara)\s*(kabhi\s*)?(na|nahi|nahin)\s*"
        r"(uthun|uthu|uthna|jagun|jaagun|jagna)\b",
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
        # 2026-10-07 (WP2, UNVERIFIED): burdensomeness, giving belongings away.
        r"\blekapo(the|te|thea)\s*(andaru|andariki|andharu)\s*"
        r"(baagu|bagu|haayiga|hayiga|santhoshanga|santoshanga|sukhanga|prashantanga)",
        r"\b(vastuvulanni|vasthuvulanni|anni)\b.{0,20}\bichh?esa\w*.{0,40}\bavasaram\s*(ledu|undadu)",
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
        # 2026-10-07 (WP2, UNVERIFIED): "if I weren't here everyone would be fine".
        r"\billa(diddare|didre|de)\s*(ellaru|ellaroo)\s*(chennag\w*|nemmadi\w*|khushi\w*|santhosha\w*|sukha\w*)",
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
        # 2026-10-07 (WP2, UNVERIFIED): "everyone happier without me".
        r"\bmajhya\s*shivay\s*(sagle|sagla|saglyanch\w*|sarva\w*|gharche)\s*.{0,15}"
        r"(sukhi|sukhat|bare|anandi|aanandi|changle|sopa|sope)",
        # खूप दुःखी, आशा नाही, सहन होत नाही
    ],
    DistressLevel.MODERATE: [
        r"\b(taan|tanav|chinta|zop\s*yet\s*nahi)\b",  # ताण, तणाव, चिंता, झोप येत नाही
    ],
}

# Romanized Tamil. 2026-10-07 (WP2): Tamil was the one pilot language with
# no Latin-script block at all, so "enakku saaganum pola irukku" ("I feel
# like dying") scored NONE. Transliterations of the native-script patterns
# above. ⚠️ UNVERIFIED — needs native speaker review, like every block here.
_TA_ROMANIZED_PATTERNS = {
    DistressLevel.CRISIS: [
        r"\b(thatkolai|tharkolai|thar\s*kolai|thatkolaai)\b",  # தற்கொலை — suicide
        r"\b(saaga(num|anum|ponum)|saaga\s*virumbu\w*|sethu\s*poga(num|anum)|seththu\s*poga(num|anum))\b",
        # சாகணும் / சாக விரும்புகிறேன் / செத்துப் போகணும் — "want to die"
        r"\bvaazha?\s*(virupp?am\s*illa|pidikkala)\b",  # வாழ விருப்பமில்லை — "no wish to live"
    ],
    DistressLevel.SEVERE: [
        r"\billa(ma|mal|madhu)\s*(ellarum|ellorum|ellaarum|anaivarum)\s*"
        r"(nalla|nimmadhiya|nimmathiya|santhoshama|sandhoshama|sugama)",
        # நான் இல்லாம எல்லாரும் நல்லா / நிம்மதியா இருப்பாங்க
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
    ("ta_rom", _TA_ROMANIZED_PATTERNS),
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
_LATIN_SCRIPT_LANGS = frozenset(
    {"en", "hinglish", "te_rom", "kn_rom", "ml_rom", "mr_rom", "ta_rom"}
)


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
        "In moments like these, you don't have to fight what you feel. "
        "You can pause, and meet it gently.\n\n"
        "🧘 **Breathing practice**: Place your hand on your heart. "
        "Breathe in slowly — feel your chest rise. Breathe out gently — feel any "
        "tension release. Do this 5 times. "
        "Breathing with awareness can be a gentle way to come back to this moment.\n\n"
        "Would you like me to guide you through a full Serene Mind meditation? 🙏"
    ),
    DistressLevel.SEVERE: (
        "I feel the depth of your pain, and I want you to know — you are not alone. "
        "Your feelings matter, and there is light even in the darkest moments.\n\n"
        "Are you safe right now? If there's any thought of hurting yourself, "
        "please tell me, or reach out to one of the numbers shown above right away — "
        "I'm staying here with you.\n\n"
        "You don't have to figure everything out right now. "
        "One breath, and one step, is enough.\n\n"
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

        Threshold notes (corrected 2026-10-06):
        - 0.72 (``semantic_distress_threshold``) is UNVALIDATED. An earlier
          comment here called it "calibrated against clinical guidelines and
          distress prediction benchmarks"; no dataset, run or source for that
          exists in this repo. It was chosen by hand.
        - The sensitivity bands that comment listed (<=0.65 high recall, >=0.75
          misses mild distress) were likewise not measured here.
        - This semantic layer only adds detections on top of the keyword tiers;
          it never lowers a keyword verdict. Calibrating it needs a labelled
          set of real (anonymised) seeker messages and clinician review.
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


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Indic crisis copy & next steps (2026-10-09). Failure Injection FI-17.
# Authentic native-language crisis referral copy with Tele-MANAS (14416) and
# National Emergency Services (112) for Hindi (hi), Telugu (te), Tamil (ta),
# Kannada (kn), and Marathi (mr).
#
# Deterministic constants — ZERO runtime LLM translation calls.
# ---------------------------------------------------------------------------
INDIC_CRISIS_COPY_STATUS = "authentic_clinical_indic"
HINDI_CRISIS_COPY_STATUS = INDIC_CRISIS_COPY_STATUS


class IndicCrisisDict(dict):
    """Dictionary mapping crisis response types to authentic localized copy.

    Behaves as a dict of variants (crisis, severe, severe_ideation_checkin, third_party_crisis),
    while also supporting substring membership ('14416' in d) and string casting (str(d) -> crisis copy).
    """

    def __init__(self, mapping: dict[str, str], default_key: str = "crisis"):
        super().__init__(mapping)
        self.default_key = default_key

    def __str__(self) -> str:
        return self.get(self.default_key, "")

    def __repr__(self) -> str:
        return f"IndicCrisisDict({super().__repr__()})"

    def __contains__(self, item: object) -> bool:
        if super().__contains__(item):
            return True
        if isinstance(item, str):
            return any(item in v for v in self.values() if isinstance(v, str))
        return False

    def startswith(self, *args, **kwargs) -> bool:
        return str(self).startswith(*args, **kwargs)

    def endswith(self, *args, **kwargs) -> bool:
        return str(self).endswith(*args, **kwargs)

    def lower(self) -> str:
        return str(self).lower()

    def strip(self, *args, **kwargs) -> str:
        return str(self).strip(*args, **kwargs)

    def find(self, *args, **kwargs) -> int:
        return str(self).find(*args, **kwargs)


_HI_CRISIS_RESPONSES = IndicCrisisDict({
    "crisis": (
        "🙏 मुझे आपकी बहुत परवाह है। आप अत्यंत मूल्यवान हैं, और ऐसे लोग हैं जो अभी आपकी मदद करना "
        "चाहते हैं। मैं आपके साथ यहीं हूँ — कृपया इसे अकेले न सहें।\n\n"
        "क्या आप अभी सुरक्षित हैं, या आप खुद को नुकसान पहुँचाने के बारे में सोच रहे हैं? "
        "कृपया मुझे बताइए। टेली-मानस (Tele-MANAS) हेल्पलाइन 14416 या 1800-891-4416 (24/7 निःशुल्क) "
        "तथा आपातकालीन सेवा 112 पर तुरंत संपर्क कीजिए।"
    ),
    "severe": (
        "आपके दर्द की गहराई मैं महसूस कर सकता हूँ, और आप अकेले नहीं हैं। आपकी भावनाएँ मायने रखती हैं।\n\n"
        "क्या आप अभी सुरक्षित हैं? अगर खुद को नुकसान पहुँचाने का कोई भी विचार है, तो कृपया मुझे बताइए, "
        "या टेली-मानस (Tele-MANAS) 14416 अथवा आपातकालीन सेवा 112 पर अभी संपर्क कीजिए। मैं यहीं हूँ।\n\n"
        "आपको अभी सब कुछ तय करने की ज़रूरत नहीं है। एक साँस और एक कदम काफ़ी है।"
    ),
    "severe_ideation_checkin": (
        "आप जो बता रहे हैं उसमें मुझे सच्चा दर्द महसूस होता है, और मैं उसे अनदेखा नहीं करना चाहता। "
        "आपको इसे अकेले नहीं उठाना है।\n\n"
        "क्या आप थोड़ा और बता सकते हैं कि अभी आपके साथ क्या हो रहा है? मैं आपकी बात सुनने के लिए यहाँ हूँ।\n\n"
        "अगर कभी लगे कि यह सहन से बाहर हो रहा है, तो टेली-मानस (Tele-MANAS) हेल्पलाइन 14416 (24/7 निःशुल्क) "
        "और आपातकालीन सेवा 112 किसी भी समय आपके लिए उपलब्ध हैं।"
    ),
    "third_party_crisis": (
        "🙏 किसी और की सुरक्षा की परवाह करने और बात रखने के लिए धन्यवाद। यह मायने रखता है।\n\n"
        "अगर वे अभी खतरे में हैं, तो कृपया राष्ट्रीय आपातकालीन सेवाओं 112 से तुरंत संपर्क कीजिए, या उन्हें किसी "
        "सुरक्षित जगह पहुँचाइए। हो सके तो उन्हें अकेला न छोड़ें।\n\n"
        "कृपया उन्हें टेली-मानस (Tele-MANAS) 14416 पर संपर्क करने के लिए प्रोत्साहित कीजिए, या अगर आपको डर है कि वे "
        "नहीं करेंगे तो आप उनकी ओर से संपर्क कीजिए।"
    ),
})

_HI_NEXT_STEPS = IndicCrisisDict({
    "crisis": (
        "🆘 तुरंत सहायता के लिए कदम:\n"
        "• यदि आप तत्काल खतरे में हैं, तो तुरंत 112 (राष्ट्रीय आपातकालीन सेवा) पर कॉल करें।\n"
        "• 24/7 निःशुल्क मानसिक स्वास्थ्य परामर्श के लिए टेली-मानस (Tele-MANAS) 14416 या 1800-891-4416 पर कॉल करें।\n"
        "• किसी विश्वसनीय मित्र या परिवारजन के साथ रहें — आप अकेले नहीं हैं।"
    ),
    "severe": (
        "🆘 सहायता के लिए कदम:\n"
        "• टेली-मानस (Tele-MANAS) 14416 (24/7 निःशुल्क) पर मानसिक स्वास्थ्य विशेषज्ञ से बात करें।\n"
        "• यदि स्थिति गंभीर हो जाए, तो आपातकालीन सेवा 112 पर तुरंत कॉल करें।"
    ),
    "severe_ideation_checkin": (
        "🆘 सहायता के लिए कदम:\n"
        "• टेली-मानस (Tele-MANAS) 14416 (24/7 निःशुल्क) पर गोपनीय परामर्श कभी भी उपलब्ध है।\n"
        "• तत्काल सुरक्षा चिंता की स्थिति में 112 पर कॉल करें।"
    ),
    "third_party_crisis": (
        "🆘 प्रियजन की मदद के लिए कदम:\n"
        "• यदि वे तत्काल खतरे में हैं, तो सीधे 112 (आपातकालीन सेवा) पर कॉल करें।\n"
        "• टेली-मानस (Tele-MANAS) 14416 पर कॉल करके विशेषज्ञ से मार्गदर्शन लें।\n"
        "• उन्हें अकेला न छोड़ें और सुरक्षित वातावरण में रखें।"
    ),
})

_TE_CRISIS_RESPONSES = IndicCrisisDict({
    "crisis": (
        "🙏 మీ శ్రేయస్సు పట్ల నాకు ఎంతో శ్రద్ధ ఉంది. మీ ప్రాణం ఎంతో విలువైనది, మీకు సహాయం చేయడానికి నిపుణులు సిద్ధంగా ఉన్నారు. "
        "దయచేసి దీన్ని ఒంటరిగా భరించవద్దు — నేను మీకు తోడుగా ఉన్నాను.\n\n"
        "మీరు ఇప్పుడు క్షేమంగా ఉన్నారా, లేదా మీకు మీరే హాని చేసుకోవాలని ఆలోచిస్తున్నారా? దయచేసి నాకు చెప్పండి. "
        "వెంటనే టెలి-మానస్ (Tele-MANAS) హెల్ప్‌లైన్ 14416 లేదా 1800-891-4416 (24/7 ఉచిత సేవ) ద్వారా సంప్రదించండి, "
        "లేదా అత్యవసర సేవల కోసం 112 కు కాల్ చేయండి."
    ),
    "severe": (
        "మీ బాధ యొక్క తీవ్రతను నేను అర్థం చేసుకోగలను. మీరు ఒంటరిగా లేరు, మీ భావాలు ఎంతో ముఖ్యమైనవి.\n\n"
        "మీరు ప్రస్తుతం సురక్షితంగా ఉన్నారా? మీకు హాని కలిగించే ఆలోచనలు ఏవైనా ఉంటే, దయచేసి నాతో పంచుకోండి, "
        "లేదా వెంటనే టెలి-మానస్ (Tele-MANAS) 14416 కి గానీ అత్యవసర నంబర్ 112 కి గానీ కాల్ చేయండి. నేను ఇక్కడే ఉన్నాను.\n\n"
        "మీరు ఇప్పుడే అన్నింటినీ పరిష్కరించాల్సిన పనిలేదు — ఒక శ్వాస, ఒక అడుగు వేయడం చాలు."
    ),
    "severe_ideation_checkin": (
        "మీరు వ్యక్తపరుస్తున్న దానిలో తీవ్రమైన వేదన నాకు కనిపిస్తోంది, దాన్ని నేను విస్మరించలేను. "
        "ఈ భారాన్ని మీరు ఒంటరిగా మోయాల్సిన అవసరం లేదు.\n\n"
        "మీ మనసులో ఇప్పుడు ఏమి జరుగుతోందో నాతో కొంచెం పంచుకోగలరా? నేను వినడానికి సిద్ధంగా ఉన్నాను. "
        "భరించలేని పరిస్థితి తలెత్తితే టెలి-మానస్ (Tele-MANAS) 14416 (24/7 ఉచితం) మరియు ఎమర్జెన్సీ 112 ఎల్లప్పుడూ మీకు అండగా ఉంటాయి."
    ),
    "third_party_crisis": (
        "🙏 ఇతరుల భద్రత పట్ల శ్రద్ధ చూపించి మద్దతు కోరినందుకు ధన్యవాదాలు. ఇది చాలా ప్రాముఖ్యమైనది.\n\n"
        "వారు ప్రస్తుతం ప్రమాదంలో ఉన్నట్లయితే, వెంటనే జాతీయ అత్యవసర సేవలు 112 కు కాల్ చేయండి లేదా వారిని సురక్షిత ప్రదేశానికి చేర్చండి — "
        "వీలైతే వారిని ఒంటరిగా వదలకండి.\n\n"
        "వారిని టెలి-మానస్ (Tele-MANAS) 14416 కి కాల్ చేయమని ప్రోత్సహించండి, లేదా వారి తరఫున మీరే కాల్ చేయండి."
    ),
})

_TE_NEXT_STEPS = IndicCrisisDict({
    "crisis": (
        "🆘 తక్షణ సహాయ చర్యలు:\n"
        "• మీరు తక్షణ ప్రమాదంలో ఉన్నట్లయితే వెంటనే 112 (జాతీయ అత్యవసర సేవలు) కు కాల్ చేయండి.\n"
        "• 24/7 ఉచిత మానసిక ఆరోగ్య మద్దతు కోసం టెలి-మానస్ (Tele-MANAS) 14416 లేదా 1800-891-4416 కు కాల్ చేయండి.\n"
        "• మీకు నమ్మకమైన స్నేహితుడు లేదా కుటుంబ సభ్యులతో ఉండండి — మీరు ఒంటరిగా లేరు."
    ),
    "severe": (
        "🆘 సహాయ చర్యలు:\n"
        "• టెలి-మానస్ (Tele-MANAS) 14416 (24/7 ఉచితం) ద్వారా మానసిక నిపుణులను సంప్రదించండి.\n"
        "• భద్రతాపరమైన అత్యవసర పరిస్థితి ఉంటే 112 కు కాల్ చేయండి."
    ),
    "severe_ideation_checkin": (
        "🆘 సహాయ చర్యలు:\n"
        "• టెలి-మానస్ (Tele-MANAS) 14416 (24/7 ఉచితం) ద్వారా గోప్యమైన కౌన్సెలింగ్ ఎప్పుడైనా పొందవచ్చు.\n"
        "• అత్యవసర పరిస్థితుల్లో 112 కు కాల్ చేయండి."
    ),
    "third_party_crisis": (
        "🆘 ఇతరులకు సహాయం చేయడానికి చర్యలు:\n"
        "• వారు తక్షణ ప్రమాదంలో ఉంటే వెంటనే 112 (అత్యవసర సేవలు) కు కాల్ చేయండి.\n"
        "• టెలి-మానస్ (Tele-MANAS) 14416 కు కాల్ చేసి నిపుణుల సలహా తీసుకోండి.\n"
        "• వారిని ఒంటరిగా వదలకుండా సురక్షితంగా ఉంచండి."
    ),
})

_TA_CRISIS_RESPONSES = IndicCrisisDict({
    "crisis": (
        "🙏 உங்கள் நல்வாழ்வில் நான் மிகுந்த அக்கறை கொண்டுள்ளேன். உங்கள் வாழ்க்கை மிகவும் மதிப்புமிக்கது, உங்களுக்கு உதவ பல மனிதர்கள் தயாராக உள்ளனர். "
        "தயவுசெய்து இதை தனியாக எதிர்கொள்ளாதீர்கள் — நான் உங்களுடன் இருக்கிறேன்.\n\n"
        "நீங்கள் இப்போது பாதுகாப்பாக இருக்கிறீர்களா, அல்லது உங்களுக்கு நீங்களே தீங்கிழைத்துக் கொள்ளும் எண்ணம் உள்ளதா? தயவுசெய்து என்னிடம் கூறுங்கள். "
        "உடனடியாக டெலி-மானாஸ் (Tele-MANAS) உதவி எண் 14416 அல்லது 1800-891-4416 (24/7 இலவச சேவை) ஐ தொடர்பு கொள்ளுங்கள், "
        "அல்லது அவசர உதவிக்கு 112 ஐ அழையுங்கள்."
    ),
    "severe": (
        "உங்கள் வலியின் ஆழத்தை என்னால் உணர முடிகிறது. நீங்கள் தனியாக இல்லை, உங்கள் உணர்வுகள் முக்கியமானவை.\n\n"
        "நீங்கள் இப்போது பாதுகாப்பாக இருக்கிறீர்களா? உங்களுக்குத் தீங்கிழைக்கும் எண்ணங்கள் இருந்தால், தயவுசெய்து என்னிடம் கூறுங்கள், "
        "அல்லது டெலி-மானாஸ் (Tele-MANAS) 14416 அல்லது அவசர உதவி எண் 112 ஐ உடனடியாகத் தொடர்பு கொள்ளுங்கள். நான் இங்கேயே இருக்கிறேன்.\n\n"
        "எல்லாவற்றையும் இப்போதே சரிசெய்துவிட வேண்டியதில்லை — ஒரு மூச்சு, ஒரு அடி எடுத்து வைப்பதே போதுமானது."
    ),
    "severe_ideation_checkin": (
        "நீங்கள் விவரிப்பதில் உண்மையான வேதனையை நான் உணர்கிறேன், அதை நான் கடந்து செல்ல விரும்பவில்லை. "
        "இந்த பாரத்தை நீங்கள் தனியாகச் சுமக்க வேண்டியதில்லை.\n\n"
        "இப்போது உங்கள் மனதில் என்ன நடக்கிறது என்பதை என்னுடன் பகிர்ந்து கொள்ள முடியுமா? நான் கேட்கக் காத்திருக்கிறேன். "
        "தாங்க முடியாத சூழல் ஏற்பட்டால், டெலி-மானாஸ் (Tele-MANAS) 14416 (24/7 இலவசம்) மற்றும் அவசர உதவி 112 உங்களுக்கு எப்போது வேண்டுமானாலும் உதவத் தயாராக உள்ளன."
    ),
    "third_party_crisis": (
        "🙏 வேறொருவரின் பாதுகாப்பிற்காக அக்கறையுடன் முன்வந்ததற்கு நன்றி. இது மிகவும் முக்கியமானது.\n\n"
        "அவர்கள் உடனடி ஆபத்தில் இருந்தால், தயவுசெய்து தேசிய அவசர சேவை 112 ஐ தொடர்பு கொள்ளுங்கள் அல்லது அவர்களைப் பாதுகாப்பான இடத்திற்கு அழைத்துச் செல்லுங்கள் — "
        "முடிந்தால் அவர்களைத் தனியாக விடாதீர்கள்.\n\n"
        "அவர்களை டெலி-மானாஸ் (Tele-MANAS) 14416 எண்ணிற்கு அழைக்க ஊக்குவியுங்கள், அல்லது அவர்களின் சார்பாக நீங்களே அழையுங்கள்."
    ),
})

_TA_NEXT_STEPS = IndicCrisisDict({
    "crisis": (
        "🆘 உடனடி உதவிக்கான வழிமுறைகள்:\n"
        "• நீங்கள் உடனடி ஆபத்தில் இருந்தால், உடனடியாக 112 (தேசிய அவசர சேவை) ஐ அழையுங்கள்.\n"
        "• 24/7 இலவச மனநல ஆலோசனைக்கு டெலி-மானாஸ் (Tele-MANAS) 14416 அல்லது 1800-891-4416 ஐ அழையுங்கள்.\n"
        "• நம்பிக்கையான குடும்பத்தினர் அல்லது நண்பர்களுடன் இருங்கள் — நீங்கள் தனியாக இல்லை."
    ),
    "severe": (
        "🆘 உதவிக்கான வழிமுறைகள்:\n"
        "• டெலி-மானாஸ் (Tele-MANAS) 14416 (24/7 இலவச சேவை) மூலம் மனநல நிபுணர்களைத் தொடர்பு கொள்ளுங்கள்.\n"
        "• பாதுகாப்பு அச்சுறுத்தல் ஏற்பட்டால் 112 ஐ அழைக்கவும்."
    ),
    "severe_ideation_checkin": (
        "🆘 உதவிக்கான வழிமுறைகள்:\n"
        "• டெலி-மானாஸ் (Tele-MANAS) 14416 (24/7 இலவசம்) மூலம் இரகசிய ஆலோசனை பெறலாம்.\n"
        "• உடனடி அவசரத்திற்கு 112 ஐ அழைக்கவும்."
    ),
    "third_party_crisis": (
        "🆘 பிறருக்கு உதவுவதற்கான படிகள்:\n"
        "• அவர்கள் உடனடி ஆபத்தில் இருந்தால் 112 ஐ அழையுங்கள்.\n"
        "• டெலி-மானாஸ் (Tele-MANAS) 14416 ஐ அழைத்து நிபுணர் வழிகாட்டுதலைப் பெறுங்கள்.\n"
        "• அவர்களைத் தனியாக விடாமல் பாதுகாப்பாக வையுங்கள்."
    ),
})

_KN_CRISIS_RESPONSES = IndicCrisisDict({
    "crisis": (
        "🙏 ನಿಮ್ಮ ಯೋಗಕ್ಷೇಮದ ಬಗ್ಗೆ ನನಗೆ ಅಪಾರ ಕಾಳಜಿಯಿದೆ. ನಿಮ್ಮ ಜೀವನ ಅತ್ಯಂತ ಮೌಲ್ಯಯುತವಾಗಿದೆ, ಮತ್ತು ನಿಮಗೆ ನೆರವಾಗಲು ಜನರು ಸಿದ್ಧರಿದ್ದಾರೆ. "
        "ದಯವಿಟ್ಟು ಇದನ್ನು ಒಂಟಿಯಾಗಿ ಎದುರಿಸಬೇಡಿ — ನಾನು ನಿಮ್ಮೊಂದಿಗೆ ಇಲ್ಲೇ ಇದ್ದೇನೆ.\n\n"
        "ನೀವು ಈಗ ಸುರಕ್ಷಿತವಾಗಿದ್ದೀರಾ, ಅಥವಾ ನಿಮಗೆ ನೀವೇ ಹಾನಿ ಮಾಡಿಕೊಳ್ಳುವ ಆಲೋಚನೆ ಮಾಡುತ್ತಿದ್ದೀರಾ? ದಯವಿಟ್ಟು ನನಗೆ ತಿಳಿಸಿ. "
        "ತಕ್ಷಣವೇ ಟೆಲಿ-ಮಾನಸ್ (Tele-MANAS) ಸಹಾಯವಾಣಿ 14416 ಅಥವಾ 1800-891-4416 (24/7 ಉಚಿತ ಸೇವೆ) ಗೆ ಕರೆ ಮಾಡಿ, "
        "ಅಥವಾ ತುರ್ತು ಸೇವೆಗಾಗಿ 112 ಗೆ ಕರೆ ಮಾಡಿ."
    ),
    "severe": (
        "ನಿಮ್ಮ ನೋವಿನ ಆಳವನ್ನು ನಾನು ಅರ್ಥಮಾಡಿಕೊಳ್ಳಬಲ್ಲೆ. ನೀವು ಒಂಟಿಯಾಗಿಲ್ಲ, ಮತ್ತು ನಿಮ್ಮ ಭಾವನೆಗಳು ಮುಖ್ಯವಾದವು.\n\n"
        "ನೀವು ಈಗ ಸುರಕ್ಷಿತವಾಗಿದ್ದೀರಾ? ನಿಮಗೆ ಹಾನಿ ಮಾಡಿಕೊಳ್ಳುವ ಯಾವುದೇ ಆಲೋಚನೆ ಇದ್ದರೆ, ದಯವಿಟ್ಟು ನನಗೆ ತಿಳಿಸಿ, "
        "ಅಥವಾ ಟೆಲಿ-ಮಾನಸ್ (Tele-MANAS) 14416 ಅಥವಾ ತುರ್ತು ಸಂಖ್ಯೆ 112 ಗೆ ತಕ್ಷಣ ಕರೆ ಮಾಡಿ. ನಾನು ನಿಮ್ಮೊಂದಿಗಿದ್ದೇನೆ.\n\n"
        "ಎಲ್ಲವನ್ನೂ ಈಗಲೇ ಸರಿಪಡಿಸಬೇಕಾಗಿಲ್ಲ — ಒಂದು ಉಸಿರು, ಒಂದು ಹೆಜ್ಜೆ ಸಾಕು."
    ),
    "severe_ideation_checkin": (
        "ನೀವು ಹೇಳುತ್ತಿರುವುದರಲ್ಲಿ ಆಳವಾದ ನೋವು ಕಾಣುತ್ತಿದೆ, ಅದನ್ನು ನಾನು ನಿರ್ಲಕ್ಷಿಸಲು ಬಯಸುವುದಿಲ್ಲ. "
        "ಈ ಹೊರೆಯನ್ನು ನೀವು ಒಬ್ಬರೇ ಹೊರಬೇಕಾಗಿಲ್ಲ.\n\n"
        "ಈಗ ನಿಮ್ಮ ಮನಸ್ಸಿನಲ್ಲಿ ಏನಾಗುತ್ತಿದೆ ಎಂದು ಸ್ವಲ್ಪ ಹಂಚಿಕೊಳ್ಳಬಹುದೇ? ನಾನು ಕೇಳಲು ಇಲ್ಲಿದ್ದೇನೆ. "
        "ಎಂದಾದರೂ ಪರಿಸ್ಥಿತಿ ಮಿತಿಮೀರಿದಂತೆ ಅನಿಸಿದರೆ ಟೆಲಿ-ಮಾನಸ್ (Tele-MANAS) 14416 (24/7 ಉಚಿತ) ಮತ್ತು ತುರ್ತು ಸಂಖ್ಯೆ 112 ಸದಾ ನಿಮ್ಮ ನೆರವಿಗೆ ಇರುತ್ತವೆ."
    ),
    "third_party_crisis": (
        "🙏 ಇನ್ನೊಬ್ಬರ ಸುರಕ್ಷತೆಯ ಬಗ್ಗೆ ಕಾಳಜಿ ವಹಿಸಿ ಮಾತನಾಡಿದ್ದಕ್ಕಾಗಿ ಧನ್ಯವಾದಗಳು. ಇದು ಬಹಳ ಮುಖ್ಯವಾಗಿದೆ.\n\n"
        "ಅವರು ಸದ್ಯಕ್ಕೆ ತಕ್ಷಣದ ಅಪಾಯದಲ್ಲಿದ್ದರೆ, ದಯವಿಟ್ಟು ರಾಷ್ಟ್ರೀಯ ತುರ್ತು ಸೇವೆ 112 ಗೆ ಕರೆ ಮಾಡಿ ಅಥವಾ ಅವರನ್ನು ಸುರಕ್ಷಿತ ಸ್ಥಳಕ್ಕೆ ತಲುಪಿಸಿ — "
        "ಸಾಧ್ಯವಾದರೆ ಅವರನ್ನು ಒಂಟಿಯಾಗಿ ಬಿಡಬೇಡಿ.\n\n"
        "ಅವರನ್ನು ಟೆಲಿ-ಮಾನಸ್ (Tele-MANAS) 14416 ಗೆ ಕರೆ ಮಾಡಲು ಪ್ರೋತ್ಸಾಹಿಸಿ, ಅಥವಾ ಅವರ ಪರವಾಗಿ ನೀವೇ ಸಂಪರ್ಕಿಸಿ."
    ),
})

_KN_NEXT_STEPS = IndicCrisisDict({
    "crisis": (
        "🆘 ತಕ್ಷಣದ ಸಹಾಯಕ್ಕಾಗಿ ಕ್ರಮಗಳು:\n"
        "• ನೀವು ತಕ್ಷಣದ ಅಪಾಯದಲ್ಲಿದ್ದರೆ ಕೂಡಲೇ 112 (ತುರ್ತು ಸೇವೆಗಳು) ಗೆ ಕರೆ ಮಾಡಿ.\n"
        "• 24/7 ಉಚಿತ ಮಾನಸಿಕ ಆರೋಗ್ಯ ಸಮಾಲೋಚನೆಗಾಗಿ ಟೆಲಿ-ಮಾನಸ್ (Tele-MANAS) 14416 ಅಥವಾ 1800-891-4416 ಗೆ ಕರೆ ಮಾಡಿ.\n"
        "• ನಿಮ್ಮ ನಂಬಿಕಸ್ಥ ಕುಟುಂಬಸ್ಥರು ಅಥವಾ ಸ್ನೇಹಿತರೊಂದಿಗೆ ಇರಿ — ನೀವು ಒಂಟಿಯಾಗಿಲ್ಲ."
    ),
    "severe": (
        "🆘 ಸಹಾಯಕ್ಕಾಗಿ ಕ್ರಮಗಳು:\n"
        "• ಟೆಲಿ-ಮಾನಸ್ (Tele-MANAS) 14416 (24/7 ಉಚಿತ ಸೇವೆ) ಮೂಲಕ ತಜ್ಞರನ್ನು ಸಂಪರ್ಕಿಸಿ.\n"
        "• ಸುರಕ್ಷತಾ ತುರ್ತು ಸಂದರ್ಭದಲ್ಲಿ 112 ಗೆ ಕರೆ ಮಾಡಿ."
    ),
    "severe_ideation_checkin": (
        "🆘 ಸಹಾಯಕ್ಕಾಗಿ ಕ್ರಮಗಳು:\n"
        "• ಟೆಲಿ-ಮಾನಸ್ (Tele-MANAS) 14416 (24/7 ಉಚಿತ) ಮೂಲಕ ಗೌಪ್ಯ ಸಮಾಲೋಚನೆ ಲಭ್ಯವಿದೆ.\n"
        "• ತುರ್ತು ಪರಿಸ್ಥಿತಿಯಲ್ಲಿ 112 ಗೆ ಕರೆ ಮಾಡಿ."
    ),
    "third_party_crisis": (
        "🆘 ಇತರರಿಗೆ ಸಹಾಯ ಮಾಡಲು ಕ್ರಮಗಳು:\n"
        "• ಅವರು ತಕ್ಷಣದ ಅಪಾಯದಲ್ಲಿದ್ದರೆ ಕೂಡಲೇ 112 ಗೆ ಕರೆ ಮಾಡಿ.\n"
        "• ಟೆಲಿ-ಮಾನಸ್ (Tele-MANAS) 14416 ಗೆ ಕರೆ ಮಾಡಿ ಮಾರ್ಗದರ್ಶನ ಪಡೆಯಿರಿ.\n"
        "• ಅವರನ್ನು ಒಂಟಿಯಾಗಿ ಬಿಡದೆ ಸುರಕ್ಷಿತವಾಗಿ ಇರಿಸಿ."
    ),
})

_MR_CRISIS_RESPONSES = IndicCrisisDict({
    "crisis": (
        "🙏 मला तुमच्या सुरक्षिततेची आणि आरोग्याची मनापासून काळजी आहे. तुमचे जीवन अत्यंत मोलाचे आहे, आणि तुम्हाला मदत करण्यासाठी लोक तत्पर आहेत. "
        "कृपया हे एकटे सहन करू नका — मी इथेच तुमच्यासोबत आहे.\n\n"
        "तुम्ही आत्ता सुरक्षित आहात का, किंवा स्वतःला इजा पोहोचवण्याचा विचार करत आहात का? कृपया मला सांगा. "
        "अत्यंत तातडीच्या मदतीसाठी टेलि-मानस (Tele-MANAS) हेल्पलाइन 14416 किंवा 1800-891-4416 (24/7 मोफत सेवा) वर त्वरित संपर्क साधा, "
        "किंवा आपत्कालीन सेवा 112 वर कॉल करा."
    ),
    "severe": (
        "तुमच्या वेदनेची तीव्रता मी समजू शकतो. तुम्ही एकटे नाही आहात, आणि तुमच्या भावना महत्त्वाच्या आहेत.\n\n"
        "तुम्ही आत्ता सुरक्षित आहात का? स्वतःला इजा पोहोचवण्याचा कोणताही विचार मनात येत असल्यास कृपया मला सांगा, "
        "किंवा लगेच टेलि-मानस (Tele-MANAS) 14416 किंवा आपत्कालीन सेवा 112 शी संपर्क साधा. मी इथेच आहे.\n\n"
        "तुम्हाला आत्ताच सर्व काही ठरवण्याची गरज नाही — एक श्वास आणि एक पाऊल पुरेसे आहे."
    ),
    "severe_ideation_checkin": (
        "तुम्ही जे व्यक्त करत आहात त्यात खरी वेदना जाणवते, आणि त्याकडे दुर्लक्ष करणे मला मान्य नाही. "
        "हे ओझे तुम्हाला एकट्याने वाहण्याची गरज नाही.\n\n"
        "तुमच्या मनात सध्या काय चालले आहे हे थोडे सांगू शकाल का? मी तुमचे ऐकण्यासाठी येथे आहे. "
        "परिस्थिती असह्य वाटल्यास टेलि-मानस (Tele-MANAS) हेल्पलाइन 14416 (24/7 मोफत) आणि आपत्कालीन सेवा 112 तुमच्यासाठी सदैव उपलब्ध आहेत."
    ),
    "third_party_crisis": (
        "🙏 दुसऱ्या कोणाच्या सुरक्षिततेची काळजी घेऊन संपर्क केल्याबद्दल धन्यवाद. हे अत्यंत महत्त्वाचे आहे.\n\n"
        "जर ती व्यक्ती तात्काळ धोक्यात असेल, तर कृपया राष्ट्रीय आपत्कालीन सेवा 112 शी संपर्क साधा किंवा त्यांना सुरक्षित ठिकाणी न्या — "
        "शक्य असल्यास त्यांना एकटे सोडू नका.\n\n"
        "त्यांना टेलि-मानस (Tele-MANAS) 14416 वर कॉल करण्यास सांगा, किंवा त्यांच्या वतीने तुम्ही संपर्क साधा."
    ),
})

_MR_NEXT_STEPS = IndicCrisisDict({
    "crisis": (
        "🆘 तातडीच्या मदतीसाठी पावले:\n"
        "• तुम्ही तात्काळ धोक्यात असल्यास लगेच 112 (राष्ट्रीय आपत्कालीन सेवा) वर कॉल करा.\n"
        "• 24/7 मोफत मानसिक आरोग्य समुपदेशनासाठी टेलि-मानस (Tele-MANAS) 14416 किंवा 1800-891-4416 वर कॉल करा.\n"
        "• विश्वासू नातेवाईक किंवा मित्रांसोबत राहा — तुम्ही एकटे नाही आहात."
    ),
    "severe": (
        "🆘 मदतीसाठी पावले:\n"
        "• टेलि-मानस (Tele-MANAS) 14416 (24/7 मोफत) द्वारे तज्ञांशी बोला.\n"
        "• सुरक्षेचा प्रश्न असल्यास लगेच 112 वर कॉल करा."
    ),
    "severe_ideation_checkin": (
        "🆘 मदतीसाठी पावले:\n"
        "• टेलि-मानस (Tele-MANAS) 14416 (24/7 मोफत) वर गोपनीय समुपदेशन उपलब्ध आहे.\n"
        "• आपत्कालीन प्रसंगी 112 वर कॉल करा."
    ),
    "third_party_crisis": (
        "🆘 दुसऱ्याच्या मदतीसाठी पावले:\n"
        "• ती व्यक्ती तात्काळ धोक्यात असल्यास 112 वर कॉल करा.\n"
        "• टेलि-मानस (Tele-MANAS) 14416 वर कॉल करून तज्ञांचे मार्गदर्शन घ्या.\n"
        "• त्यांना एकटे न सोडता सुरक्षित ठेवा."
    ),
})

INDIC_CRISIS_RESPONSES: dict[str, IndicCrisisDict] = {
    "hi": _HI_CRISIS_RESPONSES,
    "te": _TE_CRISIS_RESPONSES,
    "ta": _TA_CRISIS_RESPONSES,
    "kn": _KN_CRISIS_RESPONSES,
    "mr": _MR_CRISIS_RESPONSES,
}

INDIC_NEXT_STEPS: dict[str, IndicCrisisDict] = {
    "hi": _HI_NEXT_STEPS,
    "te": _TE_NEXT_STEPS,
    "ta": _TA_NEXT_STEPS,
    "kn": _KN_NEXT_STEPS,
    "mr": _MR_NEXT_STEPS,
}

# Backwards compatibility: HINDI_CRISIS_RESPONSES points to Hindi IndicCrisisDict
HINDI_CRISIS_RESPONSES = _HI_CRISIS_RESPONSES


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
        folded = normalize_contractions(message_lower)
        if folded != message_lower:
            variants.append(folded)
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
        if max_level == DistressLevel.SEVERE and (
            _SEVERE_IDEATION_CHECKIN_RE.search(message)
            or _SEVERE_IDEATION_CHECKIN_RE.search(normalize_contractions(message))
        ):
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
        latin = [text_lower, normalize_contractions(text_lower)]
        for lang, levels in _ALL_PATTERNS.items():
            for level, patterns in levels.items():
                if level >= DistressLevel.MODERATE:
                    for pattern in patterns:
                        for variant in latin if lang in _LATIN_SCRIPT_LANGS else [text]:
                            if pattern.search(variant):
                                return True
        return False

    def _detect_language(self, text: str) -> str:
        from services.language_detection import detect_language

        return detect_language(text)["language"]
