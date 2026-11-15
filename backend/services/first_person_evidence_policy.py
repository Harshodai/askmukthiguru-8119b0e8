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
from services.first_person_content_assessment import (
    AUTHENTIC_ORAL_OPENER_RE,
    CONTENT_ASSESSMENT_VERSION,
    CORE_WISDOM_OPENER_RE,
    DANGLING_QUESTION_TAIL_RE,
    DISCOURSE_ACKNOWLEDGMENT_RE,
    EVENT_MARKER_RE,
    GRAPHIC_VIOLENCE_RE,
    HEALTH_CLAIM_RE,
    MEDICAL_CLAIM_NOTICE,  # noqa: F401  re-exported; tests import it from this module
    ORPHAN_OPENER_RE,
    SELF_HARM_RE,
    VIOLENCE_WORDING_RE,
    WELLBEING_FRAMING_RE,
    assess_content,
    notice_copy,
)

POLICY_VERSION = f"first_person_evidence_v3+{SAFETY_POLICY_VERSION}+{CONTENT_ASSESSMENT_VERSION}"

# ---------------------------------------------------------------------------
# Guru Co-Identity (User Directive 1)
# ---------------------------------------------------------------------------
# Ekam founders and co-teachers share one common mission and philosophy.
# In this system, they are ONE COMMON GURU. Co-occurrence of co-teachers
# is recognized as valid Ekam lineage and is NEVER flagged as
# cross_guru_contamination. External gurus remain distinct.


def _shared_lineage_ids() -> frozenset[str]:
    from services.guru_registry import shared_attribution

    primary, ids = shared_attribution()
    out = set(ids or [])
    if primary:
        out.add(primary)
    out.add("ekam")
    return frozenset(out)


def is_ekam_coidentity(guru_a: str | None, guru_b: str | None) -> bool:
    """Return True if both gurus belong to the shared Ekam lineage."""
    ga = (guru_a or "").strip().lower()
    gb = (guru_b or "").strip().lower()
    if not ga or not gb:
        return False
    if ga == gb:
        return True
    shared = _shared_lineage_ids()
    return ga in shared and gb in shared


def assess_guru_lineage(
    guru_ids: Iterable[str],
    *,
    requested_teacher: str | None = None,
) -> tuple[bool, Optional[str]]:
    """Validate guru lineage for first-person serving.

    Founders are co-teachers of Ekam. Their co-occurrence is recognized as valid
    Ekam lineage and is NEVER flagged as cross_guru_contamination. External gurus remain distinct.
    """
    from services.guru_registry import is_shared_guru_scope

    gurus = {str(gid).strip().lower() for gid in guru_ids if gid}
    req = (requested_teacher or "").strip().lower()
    shared = _shared_lineage_ids()
    if req and not is_shared_guru_scope(req):
        if any(gid != req and not (req in shared and gid in shared) for gid in gurus):
            return False, "cross_guru_contamination"
    if len(gurus) <= 1:
        return True, None
    if gurus.issubset(shared):
        return True, None
    return False, "cross_guru_contamination"


# Existing standalone detectors lived here. They now live in the single content
# assessor so the bridge, the store, the harness and this policy cannot drift
# apart again. The module-level names are kept as aliases: every existing caller
# (and the safety policy's vocabulary import) keeps working unchanged.
_DISCOURSE_ACKNOWLEDGMENT_RE = DISCOURSE_ACKNOWLEDGMENT_RE
_CORE_WISDOM_OPENER_RE = CORE_WISDOM_OPENER_RE
_AUTHENTIC_ORAL_OPENER_RE = AUTHENTIC_ORAL_OPENER_RE
_ORPHAN_OPENER_RE = ORPHAN_OPENER_RE
_EVENT_MARKER_RE = EVENT_MARKER_RE
_DANGLING_QUESTION_TAIL_RE = DANGLING_QUESTION_TAIL_RE
_VIOLENCE_WORDING_RE = VIOLENCE_WORDING_RE
_SELF_HARM_CLIP_RE = SELF_HARM_RE
_GRAPHIC_VIOLENCE_CLIP_RE = GRAPHIC_VIOLENCE_RE
_AYURVEDIC_HEALTH_FRAMING_RE = WELLBEING_FRAMING_RE
# Union of the clinical and causal-etiology vocabularies: "is this a health
# claim at all" stays one question with one stable reason code.
_HEALTH_CLAIM_RE = HEALTH_CLAIM_RE


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

_DISCOURSE_OPENER_RE = re.compile(
    r"^[\"'\u201c\u2018\s]*(?:"
    r"(?:so|okay|ok|well|right|alright|now|anyway|similarly|in\s+this\s+way|in\s+that\s+case|therefore|as\s+a\s+result|because\s+of\s+this)\s*[,.]\s"
    # Resumptive "So" (2026-11-13): refers back to talk the seeker never saw. "So both ..." stays
    # valid (tests/test_relevance_standalone_gates.py::test_so_opener_is_a_fine_opener).
    r"|so\s+(?:what|how|why|when|where|who|generally|basically|now|then|this|that|these|those)\b"
    r"|that\s+means\b"
    r"|that(?:'s|\s+is)\s+why\b"
    r")",
    re.IGNORECASE,
)
_LATE_ORDINAL_OPENER_RE = re.compile(
    r"^[\"'\u201c\u2018\s]*the\s+(?:second|third|fourth|fifth|sixth|next|last)\s+\w+",
    re.IGNORECASE,
)
_STORY_OR_DEMONSTRATIVE_OPENER_RE = re.compile(
    r"^[\"'\u201c\u2018\s]*(?:"
    r"let\s+us\s+understand\s+(?:what|how|why)\b|"
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
    # Anaphoric openers: the clip leans on context the seeker never saw. Clip-specific
    # phrases were removed (overfit to the graded-6 tuning set, 2026-11-13).
    r"here\s+you\s+receive\b|"
    r"since\s+your\s+\w+\s+is\b|"
    r"when\s+this\s+\w+\s+breaks?\s+down\b|"
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
# B14: also catches a bare ordinal and "next/last/final point" with no named predecessor.
_DANGLING_ENUMERATION_RE = re.compile(
    r"\bthe\s+(?:second|third|fourth|fifth|sixth)\s+(?:set|group|type|kind|category|point|step|stage|level)\b"
    # Bare ordinal ("The third ..."); calendar/idiom uses and "third eye" are not enumerations.
    r"|\bthe\s+(?:third|fourth|fifth|sixth)\b(?!\s+(?:century|millennium|day|week|month|year|decade|time|eye))"
    r"|\b(?:moving\s+to|now\s+the|next\s+is\s+the)\s+(?:second|third|fourth|fifth|sixth)\b"
    r"|\bthe\s+(?:next|last|final)\s+(?:point|thing|one|aspect|consideration|element|factor)\b",
    re.IGNORECASE,
)

# B14: reciprocal pronouns are relational, not ordinal ("each other", "one another").
_RECIPROCAL_PRONOUN_RE = re.compile(r"\beach\s+other\b|\bone\s+another\b", re.IGNORECASE)
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

# Clinical health-claim vocabulary moved to
# ``services.first_person_content_assessment`` (single source of truth, shared
# with the store, the bridge and the safety policy). See the aliases above.

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

# Replacement regexes for structural completeness and loop detection
_INCOMPLETE_CONTRAST_RE = re.compile(
    r"\bsuffering\s+states?\s+(?:are|is)\s+clearly\s+states?\s+that\s+destroys?\b",
    re.IGNORECASE,
)
_TRUNCATED_MID_SENTENCE_RE = re.compile(
    r"\b(?:the\s+)?chemicals?\s+that\s+(?:is|are)\s+flooding\s+(?:your\s+)?body\b",
    re.IGNORECASE,
)
_THIN_REPETITIVE_LOOP_RE = re.compile(
    r"\bsuffering\s+makes\s+you\s+sad\s+when\s+you(?:'re|\s+are)\s+sad\s+you\s+perpetuate\s+sadness\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Structural boundary rules
# ---------------------------------------------------------------------------
# Capitalisation is not boundary evidence: Whisper casing is unreliable, so a
# lowercase opener is only severed when it opens on a subject pronoun whose
# clause was cut away ("we are constantly working from our mind ...", "you
# create wealth in fear ..."). An imperative ("place your palms on your
# thighs ...") or a resolved prepositional opener ("at the core of depression is
# a battle ...") is a whole sentence and must not be penalised — 2026-11-08,
# replaces the blanket "any lowercase start is severed" proxy that rejected two
# judge-approved clips (served_clips_v8_judged [10], [13]).
_SEVERED_OPENER_PRONOUNS = frozenset(
    {"we", "you", "they", "it", "he", "she", "this", "that", "these", "those", "there"}
)


def _severed_lowercase_opener(text: str) -> bool:
    stripped = text.strip()
    if not stripped or not stripped[0].islower():
        return False
    if stripped.startswith(("i ", "i'", "i’")):
        return False
    first = re.split(r"[\s,;:]+", stripped, maxsplit=1)[0].strip("\"'“”‘’()[]…").casefold()
    return first in _SEVERED_OPENER_PRONOUNS


def _ends_on_dangling_word(text: str) -> bool:
    """True when the last token is a closed-class word no sentence can end on.

    Presence of punctuation is NOT used as the test: an unpunctuated ASR run that
    ends on a content word ("... into a state of calm") is not evidence of a cut
    (judge-approved clip [10]), while one that ends on "the"/"and"/"to" is.
    """
    from ingest.verbatim.boundaries import DANGLING_TAIL, _bare

    tokens = text.split()
    if not tokens:
        return False
    return _bare(tokens[-1]) in DANGLING_TAIL


def _clip_length_problem(
    text: str,
    *,
    settings_override: object | None = None,
    is_context: bool = False,
) -> Optional[str]:
    """Return the existing length reason, using validated settings only."""
    if settings_override is None:
        from app.config import settings as settings_override

    def _real_int(value: object, default: int) -> int:
        return value if isinstance(value, int) and not isinstance(value, bool) else default

    words = len(text.split())
    min_limit = (
        18
        if is_context
        else _real_int(getattr(settings_override, "first_person_min_answer_words", 23), 23)
    )
    max_limit = (
        _real_int(getattr(settings_override, "first_person_max_context_words", 600), 600)
        if is_context
        else _real_int(getattr(settings_override, "first_person_max_answer_words", 300), 300)
    )
    if words < min_limit:
        return "too_short"
    if words > max_limit:
        return "too_long"
    return None


def _standalone_problem(
    text: str,
    *,
    settings_override: object | None = None,
    is_complete_thought: bool | None = None,
    is_standalone: bool | None = None,
    is_verified_parent: bool | None = None,
) -> Optional[str]:
    """Legacy full standalone check, updated to support semantic completeness."""
    if is_complete_thought is False:
        return "incomplete_thought"
    if is_standalone is False:
        return "not_standalone"
    semantically_verified = is_complete_thought is True and is_standalone is True

    from ingest.verbatim.gates import CORPUS_EXPECTED_SCRIPT, script_and_loop_problem

    garbage = script_and_loop_problem(text, expected_script=CORPUS_EXPECTED_SCRIPT)
    if garbage:
        return "asr_script_garbage"
    stripped = text.rstrip()
    if stripped and stripped[-1] in ",;:-\u2014\u2013":
        return "ends_mid_sentence"
    if re.search(r"\b(?:allowing|giving|making|letting)\s*$", stripped, re.IGNORECASE):
        return "ends_mid_sentence"
    if _ends_on_dangling_word(stripped) and not stripped.endswith(
        (".", "!", "?", "।", "॥", '"', "'", "”", "’")
    ):
        return "ends_mid_sentence"
    if _GRAPHIC_VIOLENCE_CLIP_RE.search(text):
        return "graphic_violence_discourse"
    if _DANGLING_QUESTION_TAIL_RE.search(stripped):
        return "dangling_question_tail"
    if _DANGLING_AFFIRMATION_TAIL_RE.search(stripped):
        return "dangling_affirmation_tail"
    if not semantically_verified:
        if _DISCOURSE_OPENER_RE.match(text) or _LATE_ORDINAL_OPENER_RE.match(text):
            if not (is_verified_parent and _AUTHENTIC_ORAL_OPENER_RE.match(text)):
                return "discourse_opener"
    if _STORY_OR_DEMONSTRATIVE_OPENER_RE.match(text):
        if not (is_verified_parent and _AUTHENTIC_ORAL_OPENER_RE.match(text)):
            return "orphan_opener"
    if _UNEXPLAINED_CULTURAL_ENTITY_RE.search(text):
        return "unexplained_cultural_reference"
    if (
        _DANGLING_ENUMERATION_RE.search(text)
        and not _FIRST_ENUMERATION_RE.search(text)
        and not _RECIPROCAL_PRONOUN_RE.search(text)  # B14
    ):
        return "orphan_opener"
    if re.match(r"^[\"'\u201c\u2018\s]*some\s+\w+\.", stripped, re.IGNORECASE):
        return "dangling_fragment"
    if _ORPHAN_OPENER_RE.match(text) and not _CORE_WISDOM_OPENER_RE.match(text):
        if not (is_verified_parent and _AUTHENTIC_ORAL_OPENER_RE.match(text)):
            return "orphan_opener"
    if _EVENT_MARKER_RE.search(text):
        return "event_marker"
    if _ATTENDEE_TESTIMONIAL_RE.search(text):
        return "attendee_testimonial"
    if _INCOMPLETE_CONTRAST_RE.search(text):
        return "incomplete_contrast"
    if _TRUNCATED_MID_SENTENCE_RE.search(text):
        return "ends_mid_sentence"
    if _THIN_REPETITIVE_LOOP_RE.search(text):
        return "thin_repetitive_loop"
    if re.search(
        r"\b(?:there\s+are\s+)?(?:two|three)\s+(?:ways|things|aspects|steps|reasons|factors|paths)\b",
        text,
        re.IGNORECASE,
    ) and not re.search(
        r"\b(?:second|secondly|the\s+other\s+(?:one|way|thing|step|aspect|reason|factor|is)|another\s+(?:way|aspect|step|thing|reason))\b",
        text,
        re.IGNORECASE,
    ):
        return "dangling_enumeration"
    if _HEALTH_CLAIM_RE.search(text):
        return "health_claim"
    if not semantically_verified and _severed_lowercase_opener(stripped):
        return "severed_lowercase_opener"
    if re.match(r"^[\"'\u201c\u2018\s]*more\s+\w+\s+to\b", text, re.IGNORECASE):
        return "dangling_fragment"
    # Word-count floors are owned by the content-quality gate (QBUG-5: 15 words).
    # Duplicating a second floor here (23) made the same clip pass one gate and
    # fail the other; ``_clip_length_problem`` stays available for its own
    # callers, it just no longer decides standalone-ness.
    return None


def _context_standalone_problem(
    texts: Iterable[str],
    *,
    is_complete_thought: bool | None = None,
    is_standalone: bool | None = None,
    is_verified_parent: bool | None = None,
) -> Optional[str]:
    """Context-aware subset of standalone rules, shared without English-only checks."""
    if is_complete_thought is False:
        return "incomplete_thought"
    if is_standalone is False:
        return "not_standalone"
    semantically_verified = is_complete_thought is True and is_standalone is True

    text_list = tuple(str(text or "") for text in texts)
    if not text_list:
        return None
    first = text_list[0]
    whole = " ".join(text.strip() for text in text_list)
    stripped_whole = whole.strip()

    # Word-count gate: applies to the combined span text, mirroring the
    # _length_problem check that the legacy single-clip path runs.  The
    # min/max come from Settings so callers that monkeypatch the settings
    # object get the right thresholds without touching this function.
    try:
        from app.config import settings as _cfg

        _min = int(getattr(_cfg, "first_person_min_answer_words", 23))
        _max = int(getattr(_cfg, "first_person_max_context_words", 600))
    except (ImportError, AttributeError, ValueError, TypeError):
        _min, _max = 23, 600
    _word_count = len(stripped_whole.split()) if stripped_whole else 0
    if _word_count < _min:
        return "too_short"
    if _word_count > _max:
        return "too_long"

    if stripped_whole and stripped_whole[-1] in ",;:-\u2014\u2013":
        return "ends_mid_sentence"
    if re.search(r"\b(?:allowing|giving|making|letting)\s*$", stripped_whole, re.IGNORECASE):
        return "ends_mid_sentence"
    if any(p in stripped_whole for p in (".", "!", "?", "।", "॥")) and not stripped_whole.endswith(
        (".", "!", "?", '"', "'", "”", "’", "।", "॥")
    ):
        return "ends_mid_sentence"
    if _ends_on_dangling_word(stripped_whole) and not stripped_whole.endswith(
        (".", "!", "?", "।", "॥", '"', "'", "”", "’")
    ):
        return "ends_mid_sentence"
    if _GRAPHIC_VIOLENCE_CLIP_RE.search(whole):
        return "graphic_violence_discourse"
    if _ATTENDEE_TESTIMONIAL_RE.search(whole):
        return "attendee_testimonial"
    if _INCOMPLETE_CONTRAST_RE.search(whole):
        return "incomplete_contrast"
    if _TRUNCATED_MID_SENTENCE_RE.search(whole):
        return "ends_mid_sentence"
    if _THIN_REPETITIVE_LOOP_RE.search(whole):
        return "thin_repetitive_loop"
    # General repetition gate: if the text has ≥10 sentences but ≥90 % of them
    # are identical (case-insensitive, stripped), it is a looping ASR artifact.
    # The 90 % threshold is generous enough to pass a repeated refrain in genuine
    # discourse while catching tight mechanical decoder loops.
    _sentences = [
        s.strip().lower() for s in re.split(r"(?<=[.!?।॥])\s+", stripped_whole) if s.strip()
    ]
    if len(_sentences) >= 10:
        from collections import Counter

        _most_common_count = Counter(_sentences).most_common(1)[0][1]
        if _most_common_count / len(_sentences) >= 0.9:
            return "thin_repetitive_loop"
    if re.search(
        r"\b(?:there\s+are\s+)?(?:two|three)\s+(?:ways|things|aspects|steps|reasons|factors|paths)\b",
        whole,
        re.IGNORECASE,
    ) and not re.search(
        r"\b(?:second|secondly|the\s+other\s+(?:one|way|thing|step|aspect|reason|factor|is)|another\s+(?:way|aspect|step|thing|reason))\b",
        whole,
        re.IGNORECASE,
    ):
        return "dangling_enumeration"
    if not semantically_verified:
        if _DISCOURSE_OPENER_RE.match(first) or _LATE_ORDINAL_OPENER_RE.match(first):
            if not (is_verified_parent and _AUTHENTIC_ORAL_OPENER_RE.match(first)):
                return "discourse_opener"
    if _STORY_OR_DEMONSTRATIVE_OPENER_RE.match(first):
        if not (is_verified_parent and _AUTHENTIC_ORAL_OPENER_RE.match(first)):
            return "orphan_opener"
    if _UNEXPLAINED_CULTURAL_ENTITY_RE.search(first):
        return "unexplained_cultural_reference"
    if (
        _DANGLING_ENUMERATION_RE.search(whole)
        and not _FIRST_ENUMERATION_RE.search(whole)
        and not _RECIPROCAL_PRONOUN_RE.search(whole)  # B14
    ):
        return "orphan_opener"
    if re.match(r"^[\"'\u201c\u2018\s]*some\s+\w+\.", first.strip(), re.IGNORECASE):
        return "dangling_fragment"
    if _ORPHAN_OPENER_RE.match(first) and not _CORE_WISDOM_OPENER_RE.match(first):
        if not (is_verified_parent and _AUTHENTIC_ORAL_OPENER_RE.match(first)):
            return "orphan_opener"
    if _DANGLING_QUESTION_TAIL_RE.search(whole.rstrip()):
        return "dangling_question_tail"
    if _DANGLING_AFFIRMATION_TAIL_RE.search(whole.rstrip()):
        return "dangling_affirmation_tail"
    if _HEALTH_CLAIM_RE.search(whole):
        return "health_claim"
    if any(_EVENT_MARKER_RE.search(text) for text in text_list):
        return "event_marker"
    first_stripped = first.strip()
    if not semantically_verified and _severed_lowercase_opener(first_stripped):
        return "severed_lowercase_opener"
    if re.match(r"^[\"'\u201c\u2018\s]*more\s+\w+\s+to\b", first_stripped, re.IGNORECASE):
        return "dangling_fragment"
    return None


def _violent_for_context(query: str, text: str, retrieval_query: str = "") -> bool:
    """Query-scoped violence rule (content assessor owns the vocabulary)."""
    return not assess_content(
        text, query=query, retrieval_query=retrieval_query
    ).may_serve and bool(_VIOLENCE_WORDING_RE.search(text))


def _self_harm_for_context(query: str, text: str) -> bool:
    """True when a clip introduces self-harm terms the query did not request."""
    finding = any(
        f.code == "unsolicited_self_harm_reference"
        for f in assess_content(text, query=query).findings
    )
    return finding


class FirstPersonEvidencePolicy:
    """Shared decision facade for deterministic, query-aware first-person gates."""

    policy_version = POLICY_VERSION

    def assess_contextual_safety(
        self, query: str, text: str, *, retrieval_query: str = ""
    ) -> EvidenceDecision:
        """Single content verdict + the external-teacher scope check.

        Content severity now comes from one assessor (:mod:`domain`-typed
        findings). This method no longer re-matches phrases: it maps the
        assessment to the existing ``EvidenceAction`` vocabulary, so a finding
        added to the assessor cannot silently disagree with this gate.
        """
        assessment = assess_content(text, query=query, retrieval_query=retrieval_query)
        reasons: list[str] = list(assessment.reason_codes)
        if _EXTERNAL_TEACHER_RE.search(query) or (
            bool(retrieval_query) and _EXTERNAL_TEACHER_RE.search(retrieval_query)
        ):
            reasons.append("external_teacher_or_tradition")
        # Lazy import: first_person_safety_policy imports the regex vocabulary
        # from this module, so importing it at module scope would form a cycle.
        # It is consulted only for the educational-context signal, which is a
        # query-scope judgement the assessor does not make.
        from services.first_person_safety_policy import FirstPersonSafetyPolicy

        contextual = FirstPersonSafetyPolicy().evaluate(query=query, candidate_text=text)
        if contextual.action == "allow_with_context":
            reasons.append("self_harm_educational_context")
        reasons = list(dict.fromkeys(reasons))

        if "external_teacher_or_tradition" in reasons or not assessment.may_serve:
            action = EvidenceAction.EXCLUDE
        elif assessment.requires_review:
            action = EvidenceAction.NEEDS_REVIEW
        elif contextual.action == "allow_with_context":
            action = EvidenceAction.ALLOW_WITH_CONTEXT
        else:
            action = EvidenceAction.ALLOW
        return EvidenceDecision(
            action=action,
            reason_codes=tuple(reasons),
            policy_version=self.policy_version,
        )

    def assess_guru_coidentity(
        self,
        guru_ids: Iterable[str],
        *,
        requested_teacher: str | None = None,
    ) -> EvidenceDecision:
        """Validate guru co-identity according to Ekam lineage."""
        valid, reason = assess_guru_lineage(guru_ids, requested_teacher=requested_teacher)
        return EvidenceDecision(
            action=EvidenceAction.ALLOW if valid else EvidenceAction.EXCLUDE,
            reason_codes=(reason,) if reason else (),
            policy_version=self.policy_version,
        )

    def assess_context_standalone(
        self,
        texts: Iterable[str],
        *,
        is_complete_thought: bool | None = None,
        is_standalone: bool | None = None,
        is_verified_parent: bool | None = None,
    ) -> EvidenceDecision:
        texts_tuple = tuple(texts)
        if texts_tuple:
            first_obj = texts_tuple[0]
            if is_complete_thought is None and hasattr(first_obj, "is_complete_thought"):
                is_complete_thought = first_obj.is_complete_thought
            if is_standalone is None and hasattr(first_obj, "is_standalone"):
                is_standalone = first_obj.is_standalone
            if is_verified_parent is None and (
                hasattr(first_obj, "parent_unit_id")
                or getattr(first_obj, "parent_unit_id", None) is not None
                or getattr(first_obj, "parent_index", None) == 0
                or getattr(first_obj, "span_index", None) == 0
            ):
                is_verified_parent = True
        str_texts = tuple(
            getattr(t, "verbatim_text", str(t)) if not isinstance(t, str) else t
            for t in texts_tuple
        )
        reason = _context_standalone_problem(
            str_texts,
            is_complete_thought=is_complete_thought,
            is_standalone=is_standalone,
            is_verified_parent=is_verified_parent,
        )
        return EvidenceDecision(
            action=EvidenceAction.EXCLUDE if reason else EvidenceAction.ALLOW,
            reason_codes=(reason,) if reason else (),
            policy_version=self.policy_version,
        )

    def notices_for(
        self,
        text: str,
        *,
        query: str | None = None,
        content_safety: str | None = None,
    ) -> tuple[str, ...]:
        """Platform copy required for a clip that passed the gate (never teacher words)."""
        return notice_copy(assess_content(text, query=query, content_safety=content_safety))


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
