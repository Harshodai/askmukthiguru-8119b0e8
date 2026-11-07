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

_RHETORICAL_OPENER_RE = re.compile(
    r"^(?:I am sure you too have tried to|have you ever wondered why)",
    re.IGNORECASE,
)

_ORPHAN_OPENER_RE = re.compile(
    r"^[\"'\u201c\u2018\s]*(?:yes(?:,|[^\w\s])\s*|(?:this|these|those|that)\s+(?:is|are|was|were)\b|these\s+are\b|this\s+space\b|it\s+is\s+possible\b|because\b|in\s+that\b"
    r"|and\b|but\b|or\b|then\b|which\b|that\s+is\s+why\b"
    r"|(?:it\b(?!\s*(?:is|was|['\u2019]s)\b)|(?:they|them|he|him|she|her)\b)|we\s+need\s+them\b|definitely\b"
    r"|i\s+(?:led|told|asked|gave|showed|took)\s+(?:him|her|them)\b"
    r"|i\s+(?:cannot|can't|couldn't)\s+help\s+(?:this|that|him|her|them)\b"
    r"|he\s+or\s+she\s+will\b"
    r"|the\s+(?:first|second|third|fourth|fifth)\s+(?:difference|one|thing|point)\b)",
    re.IGNORECASE,
)

_DISCOURSE_OPENER_RE = re.compile(
    r"^[\"'\u201c\u2018\s]*(?:so|okay|ok|well|right|alright|now|anyway)\s*[,.]\s",
    re.IGNORECASE,
)
_LATE_ORDINAL_OPENER_RE = re.compile(
    r"^[\"'\u201c\u2018\s]*the\s+(?:second|third|fourth|fifth|sixth|next|last)\s+\w+",
    re.IGNORECASE,
)
_STORY_OR_DEMONSTRATIVE_OPENER_RE = re.compile(
    r"^[\"'\u201c\u2018\s]*(?:"
    r"let\s+us\s+(?:observe|look\s+at|see|take)\s+[A-Z]\w*\b|"
    r"the\s+way\s+you\s+want\s+it\b|"
    r"this\s+(?:failure|impression|pattern|wound)\b"
    r")",
    re.IGNORECASE,
)

_HEALTH_CLAIM_RE = re.compile(
    r"\bcur(?:e|es|ed|ing)\b|\bcolic\w*|\bbedridden\b|\bcancer\b|\bdiabet\w+|\btumou?rs?\b"
    r"|\bchemotherap\w+|\bantidepressants?\b|\bmedications?\b|\bwrong signal to the universe\b|\byou will (?:have a )?fall\b|\bflooded by huge loads of sugar\b|\bscientifically proven\b|\boxytocin\b|\bprevent(?:ing)?\s+depression\b"
    r"|\bheal(?:ed|s|ing)?\s+(?:physically|(?:your|the|his|her|their)\s+(?:body|bodies|illness|disease)s?)\b"
    r"|\bhealed\s+(?:and\s+)?(?:physically|emotionally|spiritually)\b"
    r"|\b(?:will|would|can|could)\s+be\s+healed\b"
    r"|\bpsychiatric\s+(?:breakdown|disorder|illness|condition|patient)s?\b"
    r"|\bmental\s+(?:illness|disorder|breakdown)s?\b"
    r"|\b(?:cur(?:e|ed|ing)|heal(?:ed|ing)?|overcom(?:e|ing)|recover(?:y|ed|ing)?\s+from)\s+"
    r"(?:(?:an?|the|your|his|her|their|my)\s+)?addictions?\b"
    r"|\baddictions?\b[^.?!,]{0,40}\b(?:cured|healed)\b"
    r"|\bdestroys?\s+(?:your\s+)?(?:body|heart|consciousness)\b|\binternally\s+i\s+can\s+say\s+you\s+are\s+dead\b",
    re.IGNORECASE,
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
    r"|\b(?:like\s+i\s+said\s+(?:yesterday|earlier|in\s+the\s+last))\b",
    re.IGNORECASE,
)

_DANGLING_QUESTION_TAIL_RE = re.compile(
    r"(?:why\s+(?:is|are|was|were)\s+that|how\s+(?:do|can)\s+we|what\s+about\s+you|when\s+[^?]{3,80},\s*what\s+do\s+you\s+do)\s*\?\s*$",
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
    r"|\bstrangl\w+|\bhit(?:s|ting)?\s+"
    + _TARGET_PERSON_PHRASE
    + r"\b|\b"
    + _PASSIVE_HIT_BY_PHRASE
    + r"\b|\b(?:shoot(?:s|ing)?|shot)\b",
    re.IGNORECASE,
)
_SELF_HARM_CLIP_RE = re.compile(r"\b(?:self\s*-\s*harm|suicid\w*)\b", re.IGNORECASE)


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
    if _DANGLING_QUESTION_TAIL_RE.search(stripped):
        return "dangling_question_tail"
    if _DISCOURSE_OPENER_RE.match(text) or _LATE_ORDINAL_OPENER_RE.match(text):
        return "discourse_opener"
    if _STORY_OR_DEMONSTRATIVE_OPENER_RE.match(text):
        return "orphan_opener"
    if _ORPHAN_OPENER_RE.match(text) and not _CORE_WISDOM_KEYWORDS_RE.search(text):
        return "orphan_opener"
    if _EVENT_MARKER_RE.search(text):
        return "event_marker"
    if _HEALTH_CLAIM_RE.search(text):
        return "health_claim"
    return _clip_length_problem(text, settings_override=settings_override)


def _context_standalone_problem(texts: Iterable[str]) -> Optional[str]:
    """Context-aware subset of standalone rules, shared without English-only checks."""
    text_list = tuple(str(text or "") for text in texts)
    if not text_list:
        return None
    first = text_list[0]
    whole = " ".join(text.strip() for text in text_list)
    if _DISCOURSE_OPENER_RE.match(first) or _LATE_ORDINAL_OPENER_RE.match(first):
        return "discourse_opener"
    if _STORY_OR_DEMONSTRATIVE_OPENER_RE.match(first):
        return "orphan_opener"
    if _ORPHAN_OPENER_RE.match(first) and not _CORE_WISDOM_KEYWORDS_RE.search(first):
        return "orphan_opener"
    if problem := _clip_length_problem(whole):
        return problem
    if _HEALTH_CLAIM_RE.search(whole):
        return "health_claim"
    if any(_EVENT_MARKER_RE.search(text) for text in text_list):
        return "event_marker"
    # Unlike the former harness implementation, also reject an answer window
    # that still ends in a dangling rhetorical question.
    if _DANGLING_QUESTION_TAIL_RE.search(whole.rstrip()):
        return "dangling_question_tail"
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
        if _self_harm_for_context(query, text):
            reasons.append("unsolicited_self_harm_reference")
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
        if "violent_relationship_context" in reasons:
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
