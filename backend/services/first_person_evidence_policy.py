"""Shared deterministic evidence policy for first-person serving paths.

The policy returns bounded decisions only; it never generates, edits, or
attributes teaching text. Existing integrity, rights, speaker, relevance,
answerability, and rendering gates remain in their current owners.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Optional

from domain.first_person_evidence import EvidenceAction, EvidenceDecision
from domain.first_person_safety import SAFETY_POLICY_VERSION

POLICY_VERSION = f"first_person_evidence_v2+{SAFETY_POLICY_VERSION}"

# Existing standalone detectors moved here so both the legacy clip path and the
# fp-context harness use the same policy vocabulary. Compatibility imports in
# first_person_pipeline keep existing call sites and ingest tools stable.
_DISCOURSE_ACKNOWLEDGMENT_RE = re.compile(
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

_CORE_WISDOM_KEYWORDS_RE = re.compile(
    r"(?i)\b(?:"
    r"beautiful state|"
    r"suffering state|"
    r"two states|"
    r"inner conflict|"
    r"connection|"
    r"inner peace|"
    r"presence|"
    r"preoccupation|"
    r"stressful state|"
    r"no\s*-?\s*stress state|"
    r"oneness"
    r")\b"
)

_CORE_WISDOM_OPENER_RE = re.compile(
    r"^[\"'\u201c\u2018\s]*(?:(?:and\s+)?in\s+that\s+(?:beautiful|serene|sacred|connected)\s+state|(?:and\s+)?when\s+you\s+see\s+the\s+truth)\b",
    re.IGNORECASE,
)

_RHETORICAL_OPENER_RE = re.compile(
    r"^(?:I am sure you too have tried to|have you ever wondered why)",
    re.IGNORECASE,
)

_ORPHAN_OPENER_RE = re.compile(
    r"^[\"'\u201c\u2018\s]*(?:yes(?:,|[^\w\s])\s*|(?:this|these|those|that)\s+(?:is|are|was|were)\b|these\s+are\b|this\s+space\b|it\s+is\s+possible\b|because\b|in\s+that\b"
    r"|and\b|but\b|or\b|then\b|which\b|that(?:'s|\s+is)\s+why\b"
    r"|(?:it\b(?!\s*(?:is|was|['\u2019]s)\b)|(?:they|them|their|theirs|he|him|his|she|her|hers)\b)|we\s+need\s+them\b|definitely\b"
    r"|i\s+(?:led|told|asked|gave|showed|took)\s+(?:him|her|them)\b"
    r"|i\s+(?:cannot|can't|couldn't)\s+help\s+(?:this|that|him|her|them)\b"
    r"|he\s+or\s+she\s+will\b"
    r"|the\s+(?:first|second|third|fourth|fifth)\s+(?:difference|one|thing|point)\b)",
    re.IGNORECASE,
)

_DISCOURSE_OPENER_RE = re.compile(
    r"^[\"'\u201c\u2018\s]*(?:"
    r"(?:so|okay|ok|well|right|alright|now|anyway|similarly|in\s+this\s+way|in\s+that\s+case|therefore|as\s+a\s+result|because\s+of\s+this)\s*[,.]\s"
    r"|that\s+means\b"
    r")",
    re.IGNORECASE,
)
_LATE_ORDINAL_OPENER_RE = re.compile(
    r"^[\"'\u201c\u2018\s]*the\s+(?:second|third|fourth|fifth|sixth|next|last)\s+\w+",
    re.IGNORECASE,
)
_STORY_OR_DEMONSTRATIVE_OPENER_RE = re.compile(
    r"^[\"'\u201c\u2018\s]*(?:"
    r"let\s+us\s+understand\s+what\b|"
    r"let\s+us\s+(?:observe|look\s+at|see|take)\s+[A-Z]\w*\b|"
    r"the\s+way\s+you\s+want\s+it\b|"
    r"this\s+(?:failure|impression|pattern|wound)\b|"
    r"these\s+(?:diseases?|illness(?:es)?|conditions?|problems?|paths?|states?)\b|"
    r"the\s+problem\s*,\s*however\b|"
    r"none\s+of\s+these\s+(?:three\s+)?paths\b|"
    r"well\s+yes\b|"
    r"be\s+it\s+in\s+(?:his|her|their)\s+\w+\b|"
    r"possibility\s+(?:one|two|three|four)\b|"
    r"it\s+is\s+to\s+live\b|"
    r"you\s+could\s+be\s+a\s+(?:beggar|couple|monk)\b|"
    r"you\s+will\s+be\b|"
    r"if\s+all\s+that\s+happens\b|"
    r"leave\s+alone\b|"
    r"you(?:'re|\s+are)\s+also\s+thinking\b|"
    r"the\s+first\s+is\b|"
    r"in\s+this\s+story\b|"
    r"not\s+(?:from|only|just)\b|"
    r"think\s+about\s+it\b|"
    r"(?:actually\s*,\s*)?none\s+of\s+(?:these|those|this|that)\s+(?:\w+\s+)*(?:factors?|reasons?|causes?|things?|aspects?|paths?)\b|"
    r"actually\s*,\s*none\s+of\s+(?:these|those|this|that)\b"
    r")",
    re.IGNORECASE,
)
_DANGLING_ENUMERATION_RE = re.compile(
    r"\bthe\s+(?:second|third|fourth|fifth|sixth)\s+(?:set|group|type|kind|category|point|step|stage|level)\b",
    re.IGNORECASE,
)
_FIRST_ENUMERATION_RE = re.compile(r"\bfirst\b", re.IGNORECASE)

_UNEXPLAINED_CULTURAL_ENTITY_RE = re.compile(
    r"\bthat\s+\w+\s+(?:bird|story|king|saint|sage|monk|master|teaching|parable|tale|fable)\b"
    r"|\bthat\s+(?:chataka|yaksha|gandharva|apsara|rishi|muni)\b"
    r"|\b(?:this|that|these|those)\s+samskaras?\b|\bthe\s+other\s+two\s+is\s+wounded\b",
    re.IGNORECASE,
)

_ATTENDEE_TESTIMONIAL_RE = re.compile(
    r"\b(?:ekam\s+tapas\s+has\s+gifted\s+me|the\s+challenge\s+that\s+i\s+was\s+having\s+before\s+was|"
    r"gifted\s+me\s+with\s+various\s+states|so\s+you\s+are\s+both\s+young\s+women|"
    r"as\s+a\s+participant|my\s+experience\s+during\s+the\s+meditation)\b",
    re.IGNORECASE,
)

_HEALTH_CLAIM_RE = re.compile(
    r"\bcur(?:e|es|ed|ing)\b|\bcolic\w*|\bbedridden\b|\bcancer\b|\bdiabet\w+|\btumou?rs?\b"
    r"|\bchemotherap\w+|\bantidepressants?\b|\bmedications?\b|\bwrong signal to the universe\b|\byou will (?:have a )?fall\b|\bflooded by huge loads of sugar\b|\bscientifically proven\b|\boxytocin\b|\bprevent(?:ing)?\s+depression\b"
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
    r"|\bthese\s+diseases\s+are\s+(?:actually\s+)?caused\s+by\b"
    r"|\b(?:love|state|energy|it|this)\s+(?:itself\s+)?has\s+(?:tremendous\s+)?power\s+to\s+heal\b"
    r"|\bhas\s+(?:tremendous\s+)?power\s+to\s+heal\b"
    r"|\b40\s*,?\s*000\s+neurons\b"
    r"|\bwrong\s+signals?\s+(?:to|into)\s+the\s+universe\b"
    r"|\bcomes\s+as\s+health\s+issues\b"
    r"|\babundance\s+in\s+health\b"
    r"|\bwhy\s+is\s+someone\s+abusing\b"
    r"|\bcompletely\s+free\s+of\s+anxiety\b"
    r"|\bheal\s+the\s+person\b"
    r"|\bso\s+that\s+is\s+how\s+you\s+heal\s+the\s+person\b"
    r"|\bdestroys?\s+(?:your\s+)?(?:body|heart|consciousness)\b|\binternally\s+i\s+can\s+say\s+you\s+are\s+dead\b"
    r"|\bundigested\s+(?:material|toxins?)\b|\btoxins?\s+that\s+is\s+flowing\b|\baging\s+is\s+caused\s+or\s+disease\s+is\s+caused\b"
    r"|\b(?:get(?:ting)?|become|becoming)\s+diseased\b|\bdiseased\b|\binsulin(?:\s+levels?)?\b|\b(?:regions?|parts?)\s+of\s+(?:your|the)\s+brain\b",
    re.IGNORECASE,
)

# Ayurvedic / spiritual-physiology framing patterns.
# These are DISTINCT from clinical health claims (_HEALTH_CLAIM_RE) which are hard-excluded.
# Clips matching this pattern are SERVED with a medical safety notice rather than excluded.
_AYURVEDIC_HEALTH_FRAMING_RE = re.compile(
    r"\bundigested\s+(?:material|toxins?|food|emotions?|experiences?|past)\b"
    r"|\btoxins?\s+(?:in\s+(?:your|the)\s+body|flow(?:ing)?\s+in\s+the\s+body|accumulated?)\b"
    r"|\bdisease\s+is\s+caused\s+by\s+(?:the\s+)?undigested\b"
    r"|\baging\s+is\s+caused\s+(?:or|and|by)\s+disease\b"
    r"|\bevery\s+muscle\s+in\s+(?:your|the)\s+body\s+(?:relaxes?|opens?|softens?)\b"
    r"|\bphysiologically?\s+(?:dead|dying|destroyed|relaxed)\b"
    r"|\bwhen\s+you\s+truly\s+feel\s+peace.*(?:every\s+(?:cell|muscle)|body\s+relaxes?)\b"
    r"|\b(?:causes?\s+)?ill\s+health\b"
    r"|\bbody\s+agitated\b"
    r"|\binner\s+disturbance\s+leaves\s+your\s+body\b",
    re.IGNORECASE,
)

# Medical safety notice appended to clips that match _AYURVEDIC_HEALTH_FRAMING_RE.
# Platform copy only — never presented as the teacher's words.
MEDICAL_CLAIM_NOTICE = (
    "This teaching shares a spiritual and Ayurvedic perspective on wellbeing. "
    "It is not a substitute for medical advice. "
    "Please consult a qualified physician or healthcare provider for any physical health concerns."
)

_EVENT_MARKER_RE = re.compile(
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
    r"|\bnamaste\b",
    re.IGNORECASE,
)

_DANGLING_QUESTION_TAIL_RE = re.compile(
    r"(?:why\s+(?:is|are|was|were)\s+that|how\s+(?:do|can)\s+we|what\s+about\s+you|shall\s+we\s+[^?]{0,50}|when\s+[^?]{3,80},\s*what\s+do\s+you\s+do)\s*\?\s*$"
    r"|(?:and\s+)?why\s+(?:is|are|was|were)\s+[^?]{1,60}\?\s*$"
    r"|(?:why\s+did\s+[^?]{3,80}\?|or\s+why\s+[^?]{3,80}\?)\s*$",
    re.IGNORECASE,
)
_DANGLING_AFFIRMATION_TAIL_RE = re.compile(
    r"(?:[.!?]\s+)(?:yes|okay|alright)\s*[.?!]?\s*$",
    re.IGNORECASE,
)

_EXTERNAL_TEACHER_RE = re.compile(
    r"\b(?:thich\s+nhat\s+hanh|sadhguru|isha\s+kriya|eckhart\s+tolle|osho|ramana\s+maharshi|"
    r"paramahansa\s+yogananda|yogananda|deepak\s+chopra|sri\s+sri\s+ravi\s+shankar|art\s+of\s+living|"
    r"sudarshan\s+kriya|marcus\s+aurelius|dalai\s+lama|buddha|alan\s+watts|jiddu\s+krishnamurti|"
    r"shankaracharya|advaita\s+vedanta)\b",
    re.IGNORECASE,
)

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
_VIOLENCE_WORDING_RE = re.compile(
    r"\bstab(?:s|bed|bing)?\b|\bkill(?:s|ed|ing)?\b|\bmurder\w*|\bbeat(?:s|ing|en)?\b|\bslap\w*|\bpunch\w*|\bkick(?:s|ed|ing)?\b|\bchok\w+|\bmanhandl\w+"
    r"|\bstrangl\w+|\babuse[ds]?\b|\babusing\b|\bhit(?:s|ting)?\s+"
    + _TARGET_PERSON_PHRASE
    + r"\b|\b"
    + _PASSIVE_HIT_BY_PHRASE
    + r"\b|\b(?:shoot(?:s|ing)?|shot)\b",
    re.IGNORECASE,
)
_SELF_HARM_CLIP_RE = re.compile(r"\b(?:self\s*-\s*harm|suicid\w*)\b", re.IGNORECASE)
_GRAPHIC_VIOLENCE_CLIP_RE = re.compile(
    r"\b(?:"
    r"crush(?:ing)?\s+another's\s+throat"
    r"|throat\s+to\s+death"
    r"|burn(?:ing)?\s+down\s+someone's\s+home"
    r"|racial\s+violence"
    r"|act\s+of\s+unthinkable\s+cruelty"
    r")\b",
    re.IGNORECASE,
)


def _clip_length_problem(text: str, *, settings_override: object | None = None) -> Optional[str]:
    """Return the existing length reason, using validated settings only."""
    if settings_override is None:
        from app.config import settings as settings_override

    def _real_int(value: object, default: int) -> int:
        return value if isinstance(value, int) and not isinstance(value, bool) else default

    words = len(text.split())
    if words < _real_int(getattr(settings_override, "first_person_min_answer_words", 23), 23):
        return "too_short"
    if words > _real_int(getattr(settings_override, "first_person_max_answer_words", 300), 300):
        return "too_long"
    return None


def _standalone_problem(text: str, *, settings_override: object | None = None) -> Optional[str]:
    """Legacy full standalone check, retained byte-for-byte in decision order."""
    from ingest.verbatim.gates import CORPUS_EXPECTED_SCRIPT, script_and_loop_problem

    garbage = script_and_loop_problem(text, expected_script=CORPUS_EXPECTED_SCRIPT)
    if garbage:
        return "asr_script_garbage"
    stripped = text.rstrip()
    if stripped and stripped[-1] in ",;:-\u2014\u2013":
        return "ends_mid_sentence"
    if re.search(r"\b(?:allowing|giving|making|letting)\s*$", stripped, re.IGNORECASE):
        return "ends_mid_sentence"
    if len(text.split()) > 25 and not any(p in text for p in (".", "!", "?", "।", "॥")):
        return "ends_mid_sentence"
    if _GRAPHIC_VIOLENCE_CLIP_RE.search(text):
        return "graphic_violence_discourse"
    if _DANGLING_QUESTION_TAIL_RE.search(stripped):
        return "dangling_question_tail"
    if _DANGLING_AFFIRMATION_TAIL_RE.search(stripped):
        return "dangling_affirmation_tail"
    if _DISCOURSE_OPENER_RE.match(text) or _LATE_ORDINAL_OPENER_RE.match(text):
        return "discourse_opener"
    if _STORY_OR_DEMONSTRATIVE_OPENER_RE.match(text):
        return "orphan_opener"
    if _UNEXPLAINED_CULTURAL_ENTITY_RE.search(text):
        return "unexplained_cultural_reference"
    if _DANGLING_ENUMERATION_RE.search(text) and not _FIRST_ENUMERATION_RE.search(text):
        return "orphan_opener"
    if re.match(r"^[\"'\u201c\u2018\s]*some\s+\w+\.", stripped, re.IGNORECASE):
        return "dangling_fragment"
    if _ORPHAN_OPENER_RE.match(text) and not _CORE_WISDOM_OPENER_RE.match(text):
        return "orphan_opener"
    if _EVENT_MARKER_RE.search(text):
        return "event_marker"
    if "suffering states are clearly states that destroys your inner world" in text:
        return "incomplete_contrast"
    if "chemicals that is flooding your body" in text:
        return "ends_mid_sentence"
    if "suffering makes you sad when you're sad you perpetuate sadness" in text:
        return "thin_repetitive_loop"
    if (
        re.search(
            r"\b(?:there\s+are\s+)?two\s+(?:ways|things|aspects|steps|reasons|factors|paths)\b",
            text,
            re.IGNORECASE,
        )
        and re.search(
            r"\bthe\s+first\s+(?:one|way|thing|step|aspect|reason|factor|is)\b",
            text,
            re.IGNORECASE,
        )
        and not re.search(
            r"\b(?:second|secondly|the\s+other\s+(?:one|way|thing|step|aspect|reason|factor|is)|another\s+(?:way|aspect|step|thing|reason))\b",
            text,
            re.IGNORECASE,
        )
    ):
        return "dangling_enumeration"
    if _HEALTH_CLAIM_RE.search(text):
        return "health_claim"
    if stripped and stripped[0].islower() and not stripped.startswith(("i ", "i'", "i’")):
        return "severed_lowercase_opener"
    if re.match(r"^[\"'\u201c\u2018\s]*more\s+\w+\s+to\b", text, re.IGNORECASE):
        return "dangling_fragment"
    return _clip_length_problem(text, settings_override=settings_override)


def _context_standalone_problem(texts: Iterable[str]) -> Optional[str]:
    """Context-aware subset of standalone rules, shared without English-only checks."""
    text_list = tuple(str(text or "") for text in texts)
    if not text_list:
        return None
    first = text_list[0]
    whole = " ".join(text.strip() for text in text_list)
    stripped_whole = whole.strip()
    if stripped_whole and stripped_whole[-1] in ",;:-\u2014\u2013":
        return "ends_mid_sentence"
    if re.search(r"\b(?:allowing|giving|making|letting)\s*$", stripped_whole, re.IGNORECASE):
        return "ends_mid_sentence"
    if any(p in stripped_whole for p in (".", "!", "?", "।", "॥")) and not stripped_whole.endswith(
        (".", "!", "?", '"', "'", "”", "’", "।", "॥")
    ):
        return "ends_mid_sentence"
    if len(whole.split()) > 25 and not any(p in whole for p in (".", "!", "?", "।", "॥")):
        return "ends_mid_sentence"
    if _GRAPHIC_VIOLENCE_CLIP_RE.search(whole):
        return "graphic_violence_discourse"
    if _ATTENDEE_TESTIMONIAL_RE.search(whole):
        return "attendee_testimonial"
    if "suffering states are clearly states that destroys your inner world" in whole:
        return "incomplete_contrast"
    if "chemicals that is flooding your body" in whole:
        return "ends_mid_sentence"
    if "suffering makes you sad when you're sad you perpetuate sadness" in whole:
        return "thin_repetitive_loop"
    if (
        re.search(
            r"\b(?:there\s+are\s+)?two\s+(?:ways|things|aspects|steps|reasons|factors|paths)\b",
            whole,
            re.IGNORECASE,
        )
        and re.search(
            r"\bthe\s+first\s+(?:one|way|thing|step|aspect|reason|factor|is)\b",
            whole,
            re.IGNORECASE,
        )
        and not re.search(
            r"\b(?:second|secondly|the\s+other\s+(?:one|way|thing|step|aspect|reason|factor|is)|another\s+(?:way|aspect|step|thing|reason))\b",
            whole,
            re.IGNORECASE,
        )
    ):
        return "dangling_enumeration"
    if _DISCOURSE_OPENER_RE.match(first) or _LATE_ORDINAL_OPENER_RE.match(first):
        return "discourse_opener"
    if _STORY_OR_DEMONSTRATIVE_OPENER_RE.match(first):
        return "orphan_opener"
    if _UNEXPLAINED_CULTURAL_ENTITY_RE.search(first):
        return "unexplained_cultural_reference"
    if _DANGLING_ENUMERATION_RE.search(whole) and not _FIRST_ENUMERATION_RE.search(whole):
        return "orphan_opener"
    if re.match(r"^[\"'\u201c\u2018\s]*some\s+\w+\.", first.strip(), re.IGNORECASE):
        return "dangling_fragment"
    if _ORPHAN_OPENER_RE.match(first) and not _CORE_WISDOM_OPENER_RE.match(first):
        return "orphan_opener"
    if _DANGLING_QUESTION_TAIL_RE.search(whole.rstrip()):
        return "dangling_question_tail"
    if _DANGLING_AFFIRMATION_TAIL_RE.search(whole.rstrip()):
        return "dangling_affirmation_tail"
    if problem := _clip_length_problem(whole):
        return problem
    if _HEALTH_CLAIM_RE.search(whole):
        return "health_claim"
    if any(_EVENT_MARKER_RE.search(text) for text in text_list):
        return "event_marker"
    first_stripped = first.strip()
    if first_stripped and first_stripped[0].islower() and not first_stripped.startswith(("i ", "i'", "i’")):
        return "severed_lowercase_opener"
    if re.match(r"^[\"'\u201c\u2018\s]*more\s+\w+\s+to\b", first_stripped, re.IGNORECASE):
        return "dangling_fragment"
    return None


def _violent_for_context(query: str, text: str, retrieval_query: str = "") -> bool:
    """Existing query-scoped violence rule; text is never altered."""
    from guardrails.lightweight_handler import needs_relationship_safety_boundary

    return bool(_VIOLENCE_WORDING_RE.search(text)) and (
        needs_relationship_safety_boundary(query)
        or (bool(retrieval_query) and needs_relationship_safety_boundary(retrieval_query))
    )


def _self_harm_for_context(query: str, text: str) -> bool:
    """Block self-harm/suicide terms introduced by a clip not requested in query."""
    return bool(_SELF_HARM_CLIP_RE.search(text)) and not bool(_SELF_HARM_CLIP_RE.search(query))


class FirstPersonEvidencePolicy:
    """Shared decision facade for deterministic, query-aware first-person gates."""

    policy_version = POLICY_VERSION

    def assess_contextual_safety(
        self, query: str, text: str, *, retrieval_query: str = ""
    ) -> EvidenceDecision:
        reasons: list[str] = []
        if _violent_for_context(query, text, retrieval_query):
            reasons.append("violent_relationship_context")
        if _GRAPHIC_VIOLENCE_CLIP_RE.search(text):
            reasons.append("graphic_violence_discourse")
        if _self_harm_for_context(query, text):
            reasons.append("unsolicited_self_harm_reference")
        if _EXTERNAL_TEACHER_RE.search(query) or (bool(retrieval_query) and _EXTERNAL_TEACHER_RE.search(retrieval_query)):
            reasons.append("external_teacher_or_tradition")
        # Lazy import: first_person_safety_policy imports the regex vocabulary
        # from this module, so importing it at module scope would form a cycle.
        from services.first_person_safety_policy import FirstPersonSafetyPolicy

        contextual = FirstPersonSafetyPolicy().evaluate(query=query, candidate_text=text)
        reasons.extend(contextual.reason_codes)
        reasons = list(dict.fromkeys(reasons))
        # Event-bound wording alone is a review signal, not an exclusion: the
        # candidate may still be servable once a reviewer confirms the context.
        # Any other exclusion reason keeps the hard exclude.
        event_bound_only_exclusion = contextual.action == "exclude" and set(reasons) == {
            "event_bound"
        }
        if "violent_relationship_context" in reasons or "external_teacher_or_tradition" in reasons or "graphic_violence_discourse" in reasons:
            action = EvidenceAction.EXCLUDE
        elif event_bound_only_exclusion:
            action = EvidenceAction.NEEDS_REVIEW
        elif contextual.action == "exclude" or any(
            reason in reasons
            for reason in ("unsolicited_self_harm_reference", "health_claim", "outcome_promise")
        ):
            action = EvidenceAction.EXCLUDE
        elif contextual.action == "needs_review" or any(
            reason in reasons
            for reason in ("event_bound", "dangling_dependency", "cross_turn_reference")
        ):
            action = EvidenceAction.NEEDS_REVIEW
        elif contextual.action == "allow_with_context":
            action = EvidenceAction.ALLOW_WITH_CONTEXT
        elif contextual.action == "allow":
            action = EvidenceAction.ALLOW
        else:
            action = EvidenceAction.NEEDS_REVIEW
        return EvidenceDecision(
            action=action,
            reason_codes=tuple(reasons),
            policy_version=self.policy_version,
        )

    def assess_context_standalone(self, texts: Iterable[str]) -> EvidenceDecision:
        reason = _context_standalone_problem(texts)
        return EvidenceDecision(
            action=EvidenceAction.EXCLUDE if reason else EvidenceAction.ALLOW,
            reason_codes=(reason,) if reason else (),
            policy_version=self.policy_version,
        )


first_person_evidence_policy = FirstPersonEvidencePolicy()


if __name__ == "__main__":
    _safe = first_person_evidence_policy.assess_contextual_safety(
        "How do I find peace?", "Stillness can arise when attention is clear."
    )
    _unsafe = first_person_evidence_policy.assess_contextual_safety(
        "How do I find peace?", "The word suicidal appears in this description."
    )
    assert _safe.may_serve
    assert _unsafe.reason_codes == ("unsolicited_self_harm_reference",)
    assert first_person_evidence_policy.assess_context_standalone(
        ("What about you?",)
    ).reason_codes == ("dangling_question_tail",)
    print("first_person_evidence_policy self-check passed")
