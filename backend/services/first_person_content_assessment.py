"""Single content assessor for first-person serving.

Before this module, the same content vocabulary lived in four places with four
slightly different severities:

- ``first_person_evidence_policy`` (clinical claims, graphic violence, self-harm)
- ``first_person_store`` (outcome promises / miracle claims)
- ``first_person_bridge`` (Ayurvedic framing notice)
- ``first_person_safety_policy`` (outcome promises again, violence vocabulary
  imported but never emitted)

They disagreed, so a fix in one copy moved the failure to another. This module
owns the vocabulary once and returns a typed :class:`ContentAssessment`; every
serving path reads that record instead of re-matching its own regexes.

Scope rule: this module decides *content* only. Structural completeness,
boundary evidence, ASR loops, rights, speaker evidence, and relevance stay with
their existing owners.

Determinism: pure regex + query scoping. No I/O, no LLM calls, no corpus reads.
"""

from __future__ import annotations

import re

from domain.first_person_decision import (
    DECISION_CONTRACT_VERSION,
    AssessmentKind,
    ContentAssessment,
    ContentFinding,
    FindingSeverity,
)

CONTENT_ASSESSMENT_VERSION = f"first_person_content_v1+{DECISION_CONTRACT_VERSION}"

# ---------------------------------------------------------------------------
# Clinical / medical vocabulary
# ---------------------------------------------------------------------------
# Clinical assertions. These may not be served: a spiritual teaching that makes
# a medical, psychiatric, or pharmacological assertion is outside the product's
# competence regardless of how it is framed.
_CLINICAL_SRC = (
    r"\bcur(?:e|es|ed|ing)\b|\bcolic\w*|\bbedridden\b|\bcancer\b|\bdiabet\w+|\btumou?rs?\b"
    r"|\bchemotherap\w+|\bantidepressants?\b|\bmedications?\b|\bwrong signal to the universe\b"
    r"|\byou will (?:have a )?fall\b|\bflooded by huge loads of sugar\b|\bscientifically proven\b"
    r"|\boxytocin\b|\bprevent(?:ing)?\s+depression\b"
    r"|\bheal(?:ed|s|ing)?\s+(?:physically|(?:your|the|his|her|their)\s+(?:body|bodies|illness|disease)s?)\b"
    r"|\bhealed\s+(?:and\s+)?(?:physically|emotionally|spiritually)\b"
    r"|\b(?:will|would|can|could)\s+be\s+healed\b"
    r"|\b(?:repair|regeneration)\s+of\s+neurons\b|\bneurons?\s+in\s+your\s+brain\b"
    r"|\bpsychiatric\s+(?:breakdown|disorder|illness|condition|patient)s?\b"
    r"|\bmental\s+(?:illness|disorder|breakdown)s?\b"
    r"|\b(?:cur(?:e|ed|ing)|heal(?:ed|ing)?|overcom(?:e|ing)|recover(?:y|ed|ing)?\s+from)\s+"
    r"(?:(?:an?|the|your|his|her|their|my)\s+)?addictions?\b"
    r"|\baddictions?\b[^.?!,]{0,40}\b(?:cured|healed)\b"
    r"|\b100\s*%\s*(?:you\s*can\s*)?heal\b"
    r"|\bthere\s+is\s+no\s+hope\s+at\s+all\b"
    r"|\b(?:love|state|energy|it|this)\s+(?:itself\s+)?has\s+(?:tremendous\s+)?power\s+to\s+heal\b"
    r"|\bhas\s+(?:tremendous\s+)?power\s+to\s+heal\b"
    r"|\b40\s*,?\s*000\s+neurons\b"
    r"|\bwrong\s+signals?\s+(?:to|into)\s+the\s+universe\b"
    r"|\bcome(?:s)?\s+as\s+health\s+issues\b"
    r"|\babundance\s+in\s+health\b"
    r"|\bwhy\s+is\s+someone\s+abusing\b"
    r"|\bcompletely\s+free\s+of\s+anxiety\b"
    r"|\bheal\s+the\s+person\b"
    r"|\bso\s+that\s+is\s+how\s+you\s+heal\s+the\s+person\b"
    r"|\bdestroys?\s+(?:your\s+)?(?:body|heart|consciousness)\b|\binternally\s+i\s+can\s+say\s+you\s+are\s+dead\b"
    r"|\b(?:get(?:ting)?|become|becoming)\s+diseased\b|\bdiseased\b|\binsulin(?:\s+levels?)?\b"
    r"|\b(?:regions?|parts?)\s+of\s+(?:your|the)\s+brain\b"
)

# Causal-etiology assertions: the text claims a physiological disease process is
# *caused by* a spiritual/mental state. Distinct from a clinical assertion (it
# never names a treatment) but equally unservable. Kept as its own kind so audit
# records can tell the two apart while the severity stays identical.
_CAUSAL_ETIOLOGY_SRC = (
    r"\bthese\s+diseases\s+are\s+(?:actually\s+)?caused\s+by\b"
    r"|\bundigested\s+(?:material|toxins?)\b"
    r"|\btoxins?\s+that\s+is\s+flowing\b"
    r"|\baging\s+is\s+caused\s+or\s+disease\s+is\s+caused\b"
    r"|\bdisease\s+is\s+caused\s+by\s+(?:the\s+)?undigested\b"
)

CLINICAL_CLAIM_RE = re.compile(_CLINICAL_SRC, re.IGNORECASE)
CAUSAL_ETIOLOGY_RE = re.compile(_CAUSAL_ETIOLOGY_SRC, re.IGNORECASE)

# Actual literal clinical/medical assertions, used when semantic content_safety is clean
# to distinguish authentic spiritual wellbeing metaphors from acute disease promises.
_LITERAL_CLINICAL_DISEASE_RE = re.compile(
    r"\b(?:cancer|diabet\w+|tumou?rs?|chemotherap\w+|antidepressants?|medications?|insulin|"
    r"colic\w*|bedridden|psychiatric\s+(?:breakdown|disorder|illness|condition|patient)s?|"
    r"(?:cur(?:e|es|ed|ing))\s+(?:cancer|diabetes|illness|disease|addictions?))\b",
    re.IGNORECASE,
)

# Backwards-compatible union: callers that only need "is this a health claim at
# all" (standalone completeness, ingest gates) keep one pattern and one code.
HEALTH_CLAIM_RE = re.compile(f"(?:{_CLINICAL_SRC})|(?:{_CAUSAL_ETIOLOGY_SRC})", re.IGNORECASE)

# Spiritual/Ayurvedic physiology framing. NOT a clinical claim: the teacher is
# describing a traditional wellbeing model. Served with platform copy that is
# never presented as the teacher's words.
WELLBEING_FRAMING_RE = re.compile(
    r"\bundigested\s+(?:material|toxins?|food|emotions?|experiences?|past)\b"
    r"|\btoxins?\s+(?:in\s+(?:your|the)\s+body|flow(?:ing)?\s+in\s+the\s+body|accumulated?)\b"
    r"|\bdisease\s+is\s+caused\s+by\s+(?:the\s+)?undigested\b"
    r"|\baging\s+is\s+caused\s+(?:or|and|by)\s+disease\b"
    r"|\bevery\s+muscle\s+in\s+(?:your|the)\s+body\s+(?:relaxes?|opens?|softens?)\b"
    r"|\bphysiologically?\s+(?:dead|dying|destroyed|relaxed)\b"
    r"|\bwhen\s+you\s+truly\s+feel\s+peace.*(?:every\s+(?:cell|muscle)|body\s+relaxes?)\b"
    r"|\b(?:causes?\s+)?ill\s+health\b"
    r"|\bbody\s+agitated\b"
    r"|\binner\s+disturbance\s+leaves\s+your\s+body\b"
    # D7: spiritual / metaphorical inner-death framing, not clinical. "destroys your
    # body/heart/consciousness" stays in HEALTH_CLAIM_RE (hard exclude), so
    # "consciousness" is deliberately absent from the destroy/kill alternation below.
    r"|\bdead\s+inside\b"
    r"|\b(?:heart|soul|spirit)\s+(?:is\s+)?(?:destroyed|dead|empty|hollow|broken\s+completely)\b"
    r"|\bempty\s+inside\b"
    r"|\bhollowed?\s+out\s+inside\b"
    r"|\b(?:destroys?|kills?|murders?)\s+(?:your\s+)?(?:peace|joy|bliss|inner\s+life|awareness|presence)\b"
    r"|\binternally\s+(?:empty|hollow|void|numb)\b",
    re.IGNORECASE,
)

MEDICAL_CLAIM_NOTICE = (
    "This teaching shares a spiritual and Ayurvedic perspective on wellbeing. "
    "It is not a substitute for medical advice. "
    "Please consult a qualified physician or healthcare provider for any physical health concerns."
)

# ---------------------------------------------------------------------------
# Outcome promises / miracle claims
# ---------------------------------------------------------------------------
# One vocabulary, two former owners (store + safety policy). Hard exclude.
OUTCOME_PROMISE_RE = re.compile(
    r"\b(?:"
    r"guaranteed?\s+to"
    r"|will\s+definitely"
    r"|100\s*%\s+(?:sure|certain|guaranteed?)"
    r"|promise\s+(?:you|that)\s+(?:this|it)\s+will"
    r"|you\s+will\s+(?:always|never\s+again|be\s+completely)"
    r"|melt like ice(?:\s+in\s+the\s+heat\s+of\s+the\s+sun)?"
    r"|problems?\s+(?:will\s+)?(?:all\s+)?melt(?:\s+away|\s+like\s+ice)?"
    r"|guarantee(?:d|s)?\s+(?:a\s+)?miracle"
    r"|instant\s+miracle"
    r"|guaranteed\s+(?:outcome|result|healing|cure|solution|wealth|success)"
    r"|promise\s+(?:you\s+)?(?:a\s+)?miracle"
    r"|dissolve\s+(?:all\s+)?(?:your\s+)?(?:anxiet\w+|conflicts?|wounds?)"
    r")\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Violence / self-harm vocabulary
# ---------------------------------------------------------------------------
_TARGET_PERSON_PHRASE = (
    r"(?:her|him|them|me|you|(?:(?:a|an|the|his|her|their|my|your|our)\s+)?"
    r"(?:(?:\w+\s+)?(?:woman|women|man|men|wife|wives|husband|husbands|spouse|spouses|"
    r"partner|partners|child|children|son|sons|daughter|daughters|mother|mothers|"
    r"father|fathers|mom|moms|dad|dads|boyfriend|boyfriends|girlfriend|girlfriends|"
    r"someone|anyone|anybody|person|people|girl|girls|boy|boys)))"
)
_PASSIVE_HIT_BY_PHRASE = (
    r"(?:(?:was|were|being|got|gets|is|are)\s+)?hit\s+by\s+"
    r"(?:(?:a|an|the|his|her|their|my|your|our)\s+)?"
    r"(?:(?:\w+\s+)?(?:woman|women|man|men|wife|wives|husband|husbands|spouse|spouses|"
    r"partner|partners|child|children|son|sons|daughter|daughters|mother|mothers|"
    r"father|fathers|mom|moms|dad|dads|boyfriend|boyfriends|girlfriend|girlfriends|"
    r"someone|anyone|anybody|person|people|girl|girls|boy|boys))"
)

VIOLENCE_WORDING_RE = re.compile(
    r"\bstab(?:s|bed|bing)?\b|\bkill(?:s|ed|ing)?\b|\bmurder\w*|\bbeat(?:s|ing|en)?\b"
    r"|\bslap\w*|\bpunch\w*|\bkick(?:s|ed|ing)?\b|\bchok\w+|\bmanhandl\w+"
    r"|\bstrangl\w+|\babuse[ds]?\b|\babusing\b|\bhit(?:s|ting)?\s+"
    + _TARGET_PERSON_PHRASE
    + r"\b|\b"
    + _PASSIVE_HIT_BY_PHRASE
    + r"\b|\b(?:shoot(?:s|ing)?|shot)\b",
    re.IGNORECASE,
)

SELF_HARM_RE = re.compile(r"\b(?:self\s*-\s*harm|suicid\w*)\b", re.IGNORECASE)

_STATISTICAL_SELF_HARM_RE = re.compile(
    r"\b(?:"
    r"leading\s+cause\s+of\s+death"
    r"|(?:rates?|statistics?|prevalence)\s+of\s+(?:death|mortality|suicide|self[\s-]harm)"
    r"|(?:death|mortality|suicide)\s+(?:rate|rates|statistic|statistics)"
    r"|age\s+group"
    r")\b",
    re.IGNORECASE,
)

GRAPHIC_VIOLENCE_RE = re.compile(
    r"\b(?:"
    r"crush(?:ing)?\s+another's\s+throat"
    r"|throat\s+to\s+death"
    r"|burn(?:ing)?\s+down\s+someone's\s+home"
    r"|racial\s+violence"
    r"|act\s+of\s+unthinkable\s+cruelty"
    r")\b",
    re.IGNORECASE,
)

# Queries that explicitly concern mental health: self-harm content there is
# educational, not unsolicited.
_MENTAL_HEALTH_QUERY_RE = re.compile(
    r"\b(?:"
    r"suicid\w*"
    r"|self[\s\-]harm"
    r"|mental\s+health"
    r"|depression"
    r"|anxiety"
    r"|therapy"
    r"|therapist"
    r"|counseling"
    r"|counselling"
    r"|psychiatric"
    r"|emotional\s+(?:health|wellbeing|wellness)"
    r")\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Discourse / event vocabulary (contextual, not content claims)
# ---------------------------------------------------------------------------
EVENT_MARKER_RE = re.compile(
    r"can\s+someone\s+tell\s+me|congratulations,?\s+you\s+have|first\s+day\s+of\s+your"
    r"|that'?s\s+the\s+day\s+today|today\s+is\s+the\s+day\s+of"
    r"|\btoday,?\s+we\s+(?:will|shall|are\s+going\s+to)\b"
    r"|\btomorrow\s+(?:is|we)\b|\bthis\s+coming\b|\bin\s+this\s+coming\b"
    r"|\bwhen\s+i\s+bless\s+you\b|\bi\s+will\s+bless\s+you\b"
    r"|\btoday,?\s+i\s+want\s+you\s+to\s+hold\s+the\s+intention\b|\bon\s+this\s+day\b"
    r"|\b(?:corona|covid(?:-19)?|lockdowns?|quarantine|pandemic)\b"
    r"|\b(?:the\s+previous\s+(?:question|person|speaker|talk|session))\b"
    r"|\b(?:in\s+the\s+last\s+(?:session|question|talk))\b"
    r"|\b(?:like\s+i\s+said\s+(?:yesterday|earlier|in\s+the\s+last))\b"
    r"|\bi\s+don'?t\s+know\s+if\s+you'?re\s+(?:there|here|present)\b"
    r"|\bnamaste\b"
    # Promotional and upcoming-program phrasing (R2)
    r"|\bahead\s+of\s+(?:us|you)\s+is\b"
    # Promotional "lead you" needs an object that is not a practice: "I will lead
    # you into a deep process" is an event pitch, "I will lead you through a
    # breathing practice" is teaching (measured false positive 2026-11-15).
    r"|\b(?:i|we)\s+will\s+lead\s+(?:you\s+and\s+your|your)\b"
    r"|\b(?:this|the|upcoming|next)\s+manifest\s+(?:journey|process|festival|gathering|event|family\s+harmony|program|course)\b"
    r"|\b(?:upcoming|next)\s+manifest\b"
    # "can"/"is" are dropped: "this manifest can be seen as the play of
    # consciousness" is philosophy, not a program announcement.
    r"|\bthis\s+manifest\s+(?:you|would|will|shall)\b"
    r"|\bmanifest\s+family\s+harmony\b"
    r"|\bjourneying\s+into\s+birthing\b"
    r"|\b(?:register\s+(?:for|now|here|today|online)|(?:to|please)\s+register|registration|enroll(?:ment)?|sign\s+up|join\s+(?:us|me)\s+for)\b"
    r"|\b(?:upcoming|announcing)\s+(?:event|program|course|webinar|workshop|retreat|immersion|journey|festival|satsang)\b"
    r"|\bwelcome\s+to\s+this\s+(?:program|gathering|retreat|immersion|workshop|webinar|event|manifest)\b",
    re.IGNORECASE,
)

PRACTICE_INVITATION_RE = re.compile(
    r"\b(?:let(?:\s+us|[\s'\u2019]*s)\s+move\s+into\s+meditation\b|\bmove\s+into\s+meditation(?:\s+now)?\b)"
    # B9: wider guided-practice phrasing. NOTE: this only adds a NOTICE finding; the
    # EVENT_MARKER_RE check below is independent and still runs on the same text.
    r"|\b(?:close\s+your\s+eyes|gently\s+close\s+your\s+eyes|softly\s+close\s+your\s+eyes)\b"
    r"|\bsit\s+(?:comfortably|quietly|still|upright|straight|with\s+your\s+spine)\b"
    r"|\btake\s+a\s+(?:deep\s+)?breath(?:\s+in(?:\s+and\s+out)?)?\b"
    r"|\b(?:observe|watch|notice|be\s+aware\s+of)\s+your\s+(?:breath|breathing|inhalation|exhalation|thoughts?|mind|sensations?)\b"
    r"|\bgently\s+(?:close|rest|place|bring|direct)\b[^.]{0,30}\b(?:eyes|hands|attention|awareness|focus)\b"
    r"|\bfocus\s+(?:your\s+attention\s+)?on\s+(?:your\s+)?(?:breath|breathing|inhalation|exhalation|sensations?|present\s+moment)\b"
    r"|\brelax\s+(?:your\s+)?(?:body|shoulders|jaw|mind|hands|belly|muscles)\b"
    r"|\ballow\s+(?:yourself|your\s+body|your\s+mind)\s+to\s+(?:relax|settle|breathe|soften|sink|be\s+still)\b"
    r"|\bbring\s+your\s+awareness\s+(?:to|back\s+to)\b"
    r"|\bin\s+this\s+meditation\b|\bduring\s+this\s+practice\b|\bin\s+this\s+practice\b",
    re.IGNORECASE,
)

DANGLING_QUESTION_TAIL_RE = re.compile(
    r"(?:why\s+(?:is|are|was|were)\s+that|how\s+(?:do|can)\s+we|what\s+about\s+you|shall\s+we\s+[^?]{0,50}|when\s+[^?]{3,80},\s*what\s+do\s+you\s+do)\s*\?\s*$"
    r"|(?:and\s+)?why\s+(?:is|are|was|were)\s+[^?]{1,60}\?\s*$"
    r"|(?:why\s+did\s+[^?]{3,80}\?|or\s+why\s+[^?]{3,80}\?)\s*$"
    # B14: wider rhetorical tails that leave the clip open-ended.
    r"|\bdo\s+you\s+(?:know|understand|see|follow|get\s+it|follow\s+me|see\s+what\s+I\s+mean)\s*\?\s*$"
    r"|\bare\s+you\s+(?:following|with\s+me|getting\s+it|understanding)\s*\?\s*$"
    r"|\bcan\s+you\s+imagine\s*\?\s*$"
    r"|\bisn['\u2019]t\s+(?:it|that)\s+(?:right|so|true|amazing|beautiful|interesting)\s*\?\s*$"
    r"|\bdoes(?:n['\u2019]t)?\s+(?:it|that)\s+(?:make\s+sense|ring\s+a\s+bell|sound\s+familiar|sound\s+right)\s*\?\s*$"
    r"|\bso\s+what\s+(?:do\s+(?:we|you)|should\s+(?:we|you)|can\s+(?:we|you))\s+(?:do|say|think|understand)\s*\?\s*$"
    r"|\bwhat\s+(?:is|are)\s+(?:the\s+)?(?:purpose|point|meaning|reason|significance)\s+of\s+(?:all\s+)?(?:this|that|these|it)\s*\?\s*$"
    r"|\bright\s*\?\s*$|\bokay\s*\?\s*$",
    re.IGNORECASE,
)

ORPHAN_OPENER_RE = re.compile(
    r"^[\"'\u201c\u2018\s]*(?:yes(?:,|[^\w\s])\s*|(?:this|these|those|that)\s+(?:is|are|was|were)\b|these\s+are\b|this\s+space\b|it\s+is\s+possible\b|because\b|in\s+that\b"
    r"|and\b|but\b|or\b|then\b|which\b|that(?:'s|\s+is)\s+why\b"
    r"|(?:it\b(?!\s*(?:is|was|['\u2019]s)\b)|(?:they|them|their|theirs|he|him|his|she|her|hers)\b)|we\s+need\s+them\b|definitely\b"
    r"|i\s+(?:led|told|asked|gave|showed|took)\s+(?:him|her|them)\b"
    r"|i\s+(?:cannot|can't|couldn't)\s+help\s+(?:this|that|him|her|them)\b"
    r"|he\s+or\s+she\s+will\b"
    r"|the\s+(?:first|second|third|fourth|fifth)\s+(?:difference|one|thing|point)\b)",
    re.IGNORECASE,
)

CORE_WISDOM_OPENER_RE = re.compile(
    r"^[\"'\u201c\u2018\s]*(?:(?:and\s+)?in\s+that\s+(?:beautiful|serene|sacred|connected)\s+state|(?:and\s+)?when\s+you\s+see\s+the\s+truth)\b",
    re.IGNORECASE,
)

# Authentic oral discourse openings: teachers naturally open oral discourses with
# demonstrative, equational, or causal connective framings ("This is...", "It is...",
# "Because..."). When part of a verified parent unit, these are genuine teacher
# discourse beginnings rather than severed orphaned clauses.
AUTHENTIC_ORAL_OPENER_RE = re.compile(
    r"^[\"'\u201c\u2018\s]*(?:"
    r"(?:this|these|that|those)\s+(?:is|are|was|were)\b|"
    r"this\s+space\b|"
    r"it\s+(?:is|was|['\u2019]s)\b|"
    r"because\b"
    r")",
    re.IGNORECASE,
)


DISCOURSE_ACKNOWLEDGMENT_RE = re.compile(
    r"^(?:"
    r"yes,?\s+as you mentioned|"
    r"yes,?\s+as I mentioned|"
    r"yes,?\s+as we mentioned|"
    r"as I was saying|"
    r"as we discussed|"
    r"so,?\s+as I said|"
    r"right,?\s+so|"
    r"exactly,?\s+so|"
    r"yeah,?\s+so"
    r")",
    re.IGNORECASE,
)

# A short clip that opens with a discourse acknowledgment is very likely host
# turn bleed.
_SHORT_CLIP_WORDS = 40

VIOLENCE_QUERY_CONTEXT_CODE = "violent_relationship_context"
SELF_HARM_UNSOLICITED_CODE = "unsolicited_self_harm_reference"
CLINICAL_CLAIM_CODE = "health_claim"
OUTCOME_PROMISE_CODE = "outcome_promise"
WELLBEING_FRAMING_CODE = "wellbeing_framing_notice"
GRAPHIC_VIOLENCE_CODE = "graphic_violence_discourse"
EVENT_BOUND_CODE = "event_bound"
DANGLING_DEPENDENCY_CODE = "dangling_dependency"
CROSS_TURN_CODE = "cross_turn_reference"

# Platform copy attached to a served clip, keyed by finding kind. Never presented
# as the teacher's words.
NOTICE_COPY: dict[AssessmentKind, str] = {
    AssessmentKind.WELLBEING_FRAMING: MEDICAL_CLAIM_NOTICE,
}


def assess_content(
    text: str,
    *,
    query: str | None = None,
    retrieval_query: str = "",
    content_safety: str | None = None,
    is_verified_parent: bool = False,
) -> ContentAssessment:
    """Assess one text (or one joined context window).

    ``query=None`` means "no query is available" (cache-replay validation):
    query-scoped detectors (self-harm, relationship violence) are skipped rather
    than guessed. Passing a query — including an empty string — enables them;
    an empty query is treated as benign, exactly like the safety policy.

    ``content_safety`` is an optional semantic classification from FirstPersonJudge
    ('clean', 'distress', 'clinical_promise', 'harm'). When 'clean', authentic
    spiritual/wellbeing metaphors are distinguished from literal clinical promises.

    ``is_verified_parent`` indicates the text originates from or includes the opening
    of a verified parent unit, allowing authentic oral discourse openings ("This is...",
    "It is...", "Because...") without false orphan rejection.
    """
    body = str(text or "")
    if not body.strip():
        return ContentAssessment(contract_version=CONTENT_ASSESSMENT_VERSION)
    try:
        findings = _collect_findings(
            body,
            query=query,
            retrieval_query=retrieval_query,
            content_safety=content_safety,
            is_verified_parent=is_verified_parent,
        )
    except Exception:  # noqa: BLE001 - a detector failure must fail closed
        return ContentAssessment(
            degraded=True,
            contract_version=CONTENT_ASSESSMENT_VERSION,
        )
    return ContentAssessment(
        findings=tuple(findings),
        contract_version=CONTENT_ASSESSMENT_VERSION,
    )


def _collect_findings(
    body: str,
    *,
    query: str | None,
    retrieval_query: str,
    content_safety: str | None = None,
    is_verified_parent: bool = False,
) -> list[ContentFinding]:

    findings: list[ContentFinding] = []

    has_clinical = bool(CLINICAL_CLAIM_RE.search(body))
    is_semantic_clean = content_safety in ("clean", "safe", "wellbeing_notice")

    if has_clinical:
        if is_semantic_clean and not _LITERAL_CLINICAL_DISEASE_RE.search(body):
            findings.append(
                _finding(
                    WELLBEING_FRAMING_CODE,
                    AssessmentKind.WELLBEING_FRAMING,
                    FindingSeverity.NOTICE,
                    "semantic_wellbeing_metaphor_classifier",
                )
            )
        else:
            findings.append(
                _finding(
                    CLINICAL_CLAIM_CODE,
                    AssessmentKind.CLINICAL_CLAIM,
                    FindingSeverity.EXCLUDE,
                    "clinical_claim_detector",
                )
            )
    if CAUSAL_ETIOLOGY_RE.search(body):
        findings.append(
            _finding(
                CLINICAL_CLAIM_CODE,
                AssessmentKind.CAUSAL_ETIOLOGY,
                FindingSeverity.EXCLUDE,
                "causal_etiology_detector",
            )
        )
    if WELLBEING_FRAMING_RE.search(body) and not any(
        f.kind is AssessmentKind.WELLBEING_FRAMING for f in findings
    ):
        findings.append(
            _finding(
                WELLBEING_FRAMING_CODE,
                AssessmentKind.WELLBEING_FRAMING,
                FindingSeverity.NOTICE,
                "wellbeing_framing_detector",
            )
        )
    if OUTCOME_PROMISE_RE.search(body) or content_safety == "clinical_promise":
        findings.append(
            _finding(
                OUTCOME_PROMISE_CODE,
                AssessmentKind.OUTCOME_PROMISE,
                FindingSeverity.EXCLUDE,
                "outcome_promise_detector",
            )
        )
    if GRAPHIC_VIOLENCE_RE.search(body):
        findings.append(
            _finding(
                GRAPHIC_VIOLENCE_CODE,
                AssessmentKind.GRAPHIC_VIOLENCE,
                FindingSeverity.EXCLUDE,
                "graphic_violence_detector",
            )
        )
    if content_safety in ("harm", "distress") and not any(
        f.severity is FindingSeverity.EXCLUDE for f in findings
    ):
        findings.append(
            _finding(
                "judge_content_safety_exclusion",
                AssessmentKind.VIOLENCE if content_safety == "harm" else AssessmentKind.SELF_HARM,
                FindingSeverity.EXCLUDE,
                "semantic_judge_safety_classifier",
            )
        )

    # ---- Query-scoped detectors (skipped when no query is available) ----
    if query is not None:
        if VIOLENCE_WORDING_RE.search(body) and _relationship_safety_needed(query, retrieval_query):
            findings.append(
                _finding(
                    VIOLENCE_QUERY_CONTEXT_CODE,
                    AssessmentKind.VIOLENCE,
                    FindingSeverity.EXCLUDE,
                    "relationship_violence_detector",
                )
            )
        if SELF_HARM_RE.search(body) and not _MENTAL_HEALTH_QUERY_RE.search(query):
            findings.append(
                _finding(
                    SELF_HARM_UNSOLICITED_CODE,
                    AssessmentKind.SELF_HARM,
                    FindingSeverity.NOTICE
                    if _STATISTICAL_SELF_HARM_RE.search(body)
                    else FindingSeverity.EXCLUDE,
                    "self_harm_unsolicited_detector",
                )
            )

    # ---- Contextual (review) signals ----
    if PRACTICE_INVITATION_RE.search(body):
        findings.append(
            _finding(
                "practice_invitation",
                AssessmentKind.PRACTICE_INVITATION,
                FindingSeverity.NOTICE,
                "practice_invitation_detector",
            )
        )
    if EVENT_MARKER_RE.search(body):
        findings.append(
            _finding(
                EVENT_BOUND_CODE,
                AssessmentKind.EVENT_BOUND,
                FindingSeverity.REVIEW,
                "event_marker_detector",
            )
        )
    stripped = body.rstrip()
    if DANGLING_QUESTION_TAIL_RE.search(stripped):
        findings.append(
            _finding(
                DANGLING_DEPENDENCY_CODE,
                AssessmentKind.DANGLING_DEPENDENCY,
                FindingSeverity.REVIEW,
                "dangling_question_tail_detector",
            )
        )
    if (
        ORPHAN_OPENER_RE.match(body)
        and not CORE_WISDOM_OPENER_RE.match(body)
        and not (is_verified_parent and AUTHENTIC_ORAL_OPENER_RE.match(body))
    ):
        findings.append(
            _finding(
                DANGLING_DEPENDENCY_CODE,
                AssessmentKind.DANGLING_DEPENDENCY,
                FindingSeverity.REVIEW,
                "orphan_opener_detector",
            )
        )
    if DISCOURSE_ACKNOWLEDGMENT_RE.match(body) and len(body.split()) < _SHORT_CLIP_WORDS:
        findings.append(
            _finding(
                CROSS_TURN_CODE,
                AssessmentKind.CROSS_TURN,
                FindingSeverity.REVIEW,
                "cross_turn_discourse_detector",
            )
        )
    return findings


def _relationship_safety_needed(query: str, retrieval_query: str) -> bool:
    from guardrails.lightweight_handler import needs_relationship_safety_boundary

    return bool(needs_relationship_safety_boundary(query)) or (
        bool(retrieval_query) and bool(needs_relationship_safety_boundary(retrieval_query))
    )


def _finding(
    code: str,
    kind: AssessmentKind,
    severity: FindingSeverity,
    detector: str,
    confidence: float = 1.0,
) -> ContentFinding:
    return ContentFinding(
        code=code,
        kind=kind,
        severity=severity,
        detector=detector,
        confidence=confidence,
        contract_version=CONTENT_ASSESSMENT_VERSION,
    )


def notice_copy(assessment: ContentAssessment) -> tuple[str, ...]:
    """Platform copy this assessment requires, in stable kind order.

    A clip that will not be served carries no notice: copy attached to an
    excluded clip would be shown to nobody and could imply the clip was offered
    with a caveat.
    """
    if not assessment.may_serve:
        return ()
    texts: list[str] = []
    for kind in assessment.notice_kinds:
        text = NOTICE_COPY.get(kind)
        if text and text not in texts:
            texts.append(text)
    return tuple(texts)


def blocks_serving(text: str, *, query: str | None = None) -> bool:
    """Convenience predicate for gates that only need the verdict."""
    return not assess_content(text, query=query).may_serve


if __name__ == "__main__":
    _clean = assess_content("Stillness arises when attention is clear.", query="What is peace?")
    assert _clean.may_serve and _clean.severity is None

    _clinical = assess_content("This will cure your cancer.", query="What is peace?")
    assert not _clinical.may_serve
    assert _clinical.exclusion_codes == (CLINICAL_CLAIM_CODE,)
    assert _clinical.findings[0].kind is AssessmentKind.CLINICAL_CLAIM

    _etiology = assess_content(
        "These diseases are actually caused by your thoughts.", query="What is peace?"
    )
    assert not _etiology.may_serve
    assert _etiology.findings[0].kind is AssessmentKind.CAUSAL_ETIOLOGY

    _framing = assess_content(
        "When you truly feel peace every muscle in your body relaxes.",
        query="What is peace?",
    )
    assert _framing.may_serve
    assert AssessmentKind.WELLBEING_FRAMING in _framing.notice_kinds
    assert notice_copy(_framing) == (MEDICAL_CLAIM_NOTICE,)

    _promise = assess_content("Your problems will all melt like ice.", query="What is peace?")
    assert not _promise.may_serve

    _harm_benign = assess_content("Some people who are suicidal withdraw.", query="What is love?")
    assert not _harm_benign.may_serve
    _harm_educational = assess_content(
        "Some people who are suicidal withdraw.", query="How do I support someone who is suicidal?"
    )
    assert _harm_educational.may_serve

    # No query available → query-scoped detectors are skipped, not guessed.
    assert assess_content("Some people who are suicidal withdraw.").may_serve

    _event = assess_content("During the covid lockdown we sat together.", query="What is peace?")
    assert _event.may_serve and _event.requires_review

    assert blocks_serving("This will cure your cancer.")
    print("first_person_content_assessment self-check passed")
