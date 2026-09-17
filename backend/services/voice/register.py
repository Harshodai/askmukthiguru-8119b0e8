"""Per-teacher voice register, and the seeker-facing copy for every surface.

WHAT THIS IS
------------
One place that answers: "for this question, grounded in this teacher, what
register should the model write in, and what do we say when we cannot answer?"

Two things live here because they are the same job — what a seeker actually
reads — and splitting them is how the refusal paths ended up sounding like a
changelog while the answer paths got all the attention.

WHY A SHORT, CONDITIONAL BLOCK AND NOT A BIG PERSONA
-----------------------------------------------------
Measured in PRISM (https://arxiv.org/html/2603.18507v1): expert personas cost
3.6pp of MMLU accuracy (68.0% vs 71.6% baseline), and LONGER personas do MORE
damage to knowledge-dependent tasks — while helping writing, roleplay and
format-following. Their fix is intent-based selective routing rather than one
persona applied uniformly.

That is exactly our situation: this is a zero-hallucination RAG system, so a
heavy persona layer is a direct threat to the grounding gate. So the block is
short, it is selected by answer shape, and it governs FORM only. It never adds
doctrine, never supplies vocabulary the retrieved context lacks, and never
licenses a first-person sentence the teacher did not say.

WHY NOT RETRIEVED STYLE EXEMPLARS
----------------------------------
The largest study of LLM style imitation found going from 2 to 10 exemplars
"affects the four metrics very little" (https://arxiv.org/pdf/2509.14543). Our
exemplar corpus (``guru_tone_podcast``) is 12 points sharing one fabricated
question, and its top-ranked entry is a podcast host's book blurb mislabelled as
the teacher. Retrieval buys nothing here and currently injects noise.

The numbers in each block are MEASURED from that teacher's own verbatim speech
(``services/voice/profiles/*.json``, built by
``scripts/ops/build_voice_profiles.py``), not chosen by taste. That is what
makes onboarding teacher N+1 a script run rather than a writing exercise.

CACHE SAFETY
------------
The documented invariant is that ``cache_key`` is ``(language, message)`` only —
no ``user_id``, no ``tenant_id``. Voice selection therefore keys ONLY on the
question and the retrieved documents, both of which are already functions of
``(language, message)``. It never reads memory, profile, or identity. Two
seekers asking the same question in the same language get the same register, so
a cached answer is never personalised. ``select_teacher`` enforces this by
taking documents, not state.

FAILURE MODE
------------
Fail-open on availability, fail-closed on identity. A missing or unreadable
profile degrades to the lineage-neutral block (a seeker still gets an answer —
the voice layer must never cost an answer, matching the existing
``rag_graph_context_*`` fail-open precedent). But an unidentifiable teacher
NEVER yields a teacher-specific first-person register, because impersonating an
unverified speaker is a doctrine risk, not a cosmetic one.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from enum import Enum
from functools import lru_cache

from pydantic import BaseModel, Field

from services.voice.style import VoiceProfile, load_profile

# Teachers whose voice may be rendered. A teacher_id outside this set degrades
# to the neutral lineage register rather than being impersonated.
KNOWN_TEACHERS: dict[str, str] = {
    "preethaji": "Sri Preethaji",
    "krishnaji": "Sri Krishnaji",
    "preethaji_krishnaji": "Sri Preethaji and Sri Krishnaji",
    "ekam": "Sri Preethaji and Sri Krishnaji",
}
NEUTRAL_TEACHER = "preethaji_krishnaji"


class AnswerShape(str, Enum):
    """What the seeker asked for. Selects register, per PRISM-style routing."""

    TEACHING = "teaching"  # doctrine, definitions, philosophy → prose
    PRACTICE = "practice"  # ordered steps → the ONLY list-shaped case
    DISTRESS = "distress"  # grief, anxiety, crisis → warmth, minimal teaching
    COMPARATIVE = "comparative"  # two concepts / two teachers → prose, named parts
    CASUAL = "casual"  # greeting → one or two lines, no teaching


# Intent (from GraphState) → shape. Everything unmapped is TEACHING, which is
# the safe default: prose never looks broken, a wrongly-bulleted answer does.
_INTENT_TO_SHAPE: dict[str, AnswerShape] = {
    "DISTRESS": AnswerShape.DISTRESS,
    "MEDITATION": AnswerShape.PRACTICE,
    "COMPARATIVE": AnswerShape.COMPARATIVE,
    "RELATIONAL": AnswerShape.COMPARATIVE,
    "CASUAL": AnswerShape.CASUAL,
    "GREETING": AnswerShape.CASUAL,
}

# Question wording that genuinely asks for an ordered list. Kept narrow on
# purpose: measured 2026-09-15, bullet markup was the single largest contributor
# to the voice metric on live answers (markdown_rate z up to +823), so the
# burden of proof is on formatting, not on prose.
_PRACTICE_MARKERS = (
    "steps",
    "step by step",
    "step-by-step",
    "how do i practice",
    "how to practice",
    "how is it performed",
    "how do i do",
    "what are the stages",
    "in what order",
    "checklist",
    "exact 6",
    "list the",
)


class RegisterSpec(BaseModel):
    """A rendered register for one (teacher, shape) pair."""

    model_config = {"frozen": True}

    teacher_id: str
    display_name: str
    shape: AnswerShape
    allows_lists: bool = False
    block: str = ""
    certified: bool = Field(
        default=False,
        description="Profile passed its negative-control validation; see VoiceProfile.is_certified",
    )


def classify_shape(question: str, intent: str | None = None) -> AnswerShape:
    """Pick the answer shape from intent first, then question wording."""
    mapped = _INTENT_TO_SHAPE.get((intent or "").upper())
    if mapped is not None:
        return mapped
    lowered = (question or "").lower()
    if any(marker in lowered for marker in _PRACTICE_MARKERS):
        return AnswerShape.PRACTICE
    return AnswerShape.TEACHING


def select_teacher(docs: Sequence[dict] | None) -> tuple[str, bool]:
    """Choose whose register to use from the documents that ground the answer.

    Returns ``(teacher_id, is_cross_teacher)``. Reads ONLY the retrieved
    documents — never user state — so the shared ``(language, message)`` cache
    stays correct.

    Cross-teacher answers are desirable per the repo's unified-tenant decision,
    so when two distinct named teachers both contribute materially we do NOT
    pick a winner and speak as one of them. We fall back to the joint lineage
    register and let the attributed quotes carry each voice.
    """
    counts: dict[str, int] = {}
    for doc in docs or []:
        tid = str((doc or {}).get("teacher_id") or "").strip().lower()
        if tid in KNOWN_TEACHERS:
            counts[tid] = counts.get(tid, 0) + 1
    if not counts:
        return NEUTRAL_TEACHER, False
    named = {t for t in counts if t in ("preethaji", "krishnaji")}
    if len(named) > 1:
        return NEUTRAL_TEACHER, True
    return max(counts.items(), key=lambda kv: kv[1])[0], False


@lru_cache(maxsize=32)
def _profile(teacher_id: str) -> VoiceProfile | None:
    """Profiles are small JSON files read once per process, not per request."""
    return load_profile(teacher_id)


def _measured_lines(profile: VoiceProfile | None) -> str:
    """Render the measured targets. Falls back to prose when unmeasured."""
    if profile is None:
        return (
            '   Most sentences are short. Address the seeker as "you". Ask a real\n'
            "   question when it opens something."
        )
    mean = profile.mean
    return (
        f"   Measured from their own recorded speech: most sentences run about\n"
        f"   {mean['median_sentence_len']:.0f} words, but the lengths vary widely — short, short, then one\n"
        f'   long one. About {mean["second_person_rate"]:.0f} words in every 100 is "you" or "your".\n'
        f"   Roughly {mean['question_rate']:.0f} sentences in 100 are questions put back to the seeker.\n"
        f"   Their speech contains no bullet markers and no bold text at all."
    )


_CORE_RULES = """1. SPEAK TO THE SEEKER. Second person is the dominant register: "you are",
   "when you look", "notice what happens in you". Address the person in front
   of you, not an audience, and never "the individual" or "one".

2. KEEP THEIR FIRST PERSON WHERE THE TEACHINGS CARRY IT. If the provided context
   has them speaking as "I" or "we", preserve it and attribute it. Do NOT
   flatten their "I" into "they" — that turns a living teaching into a summary.
   Never invent a first-person sentence that is not in the context.

3. THEIR VOCABULARY, NOT DECORATION. Use a Sanskrit term only when the provided
   context uses it. Never insert one to sound authentic.

4. NO INVENTED TRADITION. Never write "Our ancients in India...", "The rishis
   understood...", "In our tradition..." unless the context says it. These are
   claims, not flavour.

5. NO ESSAY FURNITURE. Do not open by announcing what you are about to say
   ("Here's how they describe it:"). Begin with the teaching itself. Avoid
   "ultimately", "furthermore", "profound", "transformative", "it is important
   to note". Avoid "it's not just X, it's Y" — say what it is."""

_SHAPE_RULES: dict[AnswerShape, str] = {
    AnswerShape.TEACHING: (
        "6. WRITE PROSE, NOT A LIST. This is a teaching, not a specification. No\n"
        "   bullet markers, no bold labels, no headings. Short paragraphs. If a\n"
        "   story or image is in the context, tell it — that is how they teach."
    ),
    AnswerShape.COMPARATIVE: (
        "6. WRITE PROSE, NOT A TABLE. Name each part clearly in the sentence that\n"
        "   carries it. No bullet markers, no bold labels, no headings. A reader\n"
        "   should be able to hear this spoken aloud."
    ),
    AnswerShape.PRACTICE: (
        "6. THE STEPS MAY BE NUMBERED. This is a practice the seeker will follow,\n"
        "   so an ordered list earns its place. Introduce it in a sentence of\n"
        "   warmth, keep each step a plain instruction in second person, and close\n"
        "   in prose. No bold labels, no decorative markers, no headings."
    ),
    AnswerShape.DISTRESS: (
        "6. WARMTH FIRST, AND NO LIST. Someone is in pain. Meet them before you\n"
        "   teach. Two or three sentences of teaching at most, in plain prose.\n"
        "   Never bullet points, never headings, never bold text."
    ),
    AnswerShape.CASUAL: ("6. ONE OR TWO SENTENCES. Do not launch into a teaching unless asked."),
}


def build_register(
    teacher_id: str, shape: AnswerShape, *, cross_teacher: bool = False
) -> RegisterSpec:
    """Render the register block for one (teacher, shape)."""
    resolved = teacher_id if teacher_id in KNOWN_TEACHERS else NEUTRAL_TEACHER
    profile = _profile(resolved)
    display = KNOWN_TEACHERS[resolved]
    cross_note = (
        "\n\n7. TWO TEACHERS ARE PRESENT IN THE CONTEXT. Do not merge them into one\n"
        "   voice. Name who said what, and let each keep their own words."
        if cross_teacher
        else ""
    )
    block = (
        f"THE TEACHER'S VOICE — {display}. Match this register. It governs HOW you\n"
        f"write, never WHAT you claim: every fact still comes from the provided\n"
        f"context with its citation.\n\n"
        f"{_CORE_RULES}\n\n{_SHAPE_RULES[shape]}{cross_note}\n\n"
        f"{_measured_lines(profile)}"
    )
    return RegisterSpec(
        teacher_id=resolved,
        display_name=display,
        shape=shape,
        allows_lists=shape is AnswerShape.PRACTICE,
        block=block,
        certified=bool(profile and profile.is_certified),
    )


def register_for(
    question: str,
    *,
    intent: str | None = None,
    docs: Sequence[dict] | None = None,
) -> RegisterSpec:
    """Front door: question + intent + grounding docs -> register.

    Deliberately takes no ``GraphState`` and no user identity, so it cannot
    introduce per-user variation into a shared-cache answer.
    """
    teacher_id, cross = select_teacher(docs)
    return build_register(teacher_id, classify_shape(question, intent), cross_teacher=cross)


def apply_register(system_prompt: str, spec: RegisterSpec) -> str:
    """Append the register to a system prompt.

    Appending to the finished system prompt (rather than inserting into the
    persona layer) is deliberate: the persona layer is capped at
    ``generation_persona_token_budget`` (2048) and ``GURU_SYSTEM_PROMPT`` alone
    is ~1940 tokens, so anything added there is truncated mid-sentence. This is
    the same hook LANGHANAM already used successfully for that reason.
    """
    if not system_prompt:
        return spec.block
    return f"{system_prompt.rstrip()}\n\n{spec.block}"


# --------------------------------------------------------------------------
# Seeker-facing copy.
#
# None of this is grounded generation — it is fixed text we say about
# ourselves, so it carries ZERO grounding risk and is pure copywriting. It was
# 28% of all answers in the 36-question run of 2026-09-15, which made it the
# single highest impact-per-effort surface in the product.
#
# What it replaces, verbatim from the live run:
#   "I found relevant source material, but the generated draft did not pass the
#    full verification gate. Rather than give a bare refusal, here is a grounded
#    partial answer taken directly from the retrieved excerpts:"
#
# That names internal machinery ("verification gate", "generated draft") to
# someone who may be in pain, and reads as an engineer's changelog. The
# replacements say the same true thing in the teacher's register: we are
# handing you their words rather than our own.
# --------------------------------------------------------------------------

# Shown above verbatim excerpts when a generated draft failed verification.
PARTIAL_EVIDENCE_PREFACE = "Rather than put words in their mouths, let me give you theirs directly."

# Shown when redaction removed unsupported sentences from a draft.
REDACTION_NOTE_ONE = "_One line was set aside — the teachings here did not carry it._"
REDACTION_NOTE_MANY = "_{n} lines were set aside — the teachings here did not carry them._"

# Shown when nothing relevant was retrieved at all.
NO_TEACHING_FOUND = (
    "I do not have a teaching on this that I can stand behind, and I would "
    "rather tell you that than offer you something invented. Ask me in another "
    "way, or bring me a narrower question, and let us look again."
)

# Terminal fallback when the pipeline cannot produce an answer.
FALLBACK_RESPONSE = (
    "That one I cannot answer from the teachings I hold. Ask me differently and "
    "let us see what opens."
)

# --- Refusal recognition -------------------------------------------------
#
# Several call sites must RECOGNISE a refusal, not just render one: the cache
# must never store one under the shared (language, message) key, and
# verification must treat one as a bounded abstention rather than a draft to
# re-grade. Those sites each carried their OWN hardcoded copy of the old
# wording -- `app/pipeline/stages/cache_stage.py` and
# `rag/nodes/verification.py` -- so rewriting the copy here silently broke
# both: refusals became cacheable and re-servable to other seekers, and
# format_final_answer stopped recognising its own fallback.
#
# One matcher, derived from the constants above, so copy and recognition
# cannot drift apart again. Legacy phrasings stay listed because Redis still
# holds answers written before the rewrite, and telemetry rows reference them.
_LEGACY_REFUSAL_MARKERS: tuple[str, ...] = (
    "i don't have that specific teaching",
    "i don’t have that specific teaching",
    "please try asking another question",
    "don't have any specific teaching",
    "do not have that specific teaching",
    "i don't have enough reliable information",
    "i don't have enough information",
    "did not pass the full verification gate",
    "grounded partial answer taken directly from the retrieved excerpts",
)


def _first_sentence(text: str) -> str:
    stripped = " ".join((text or "").split())
    for end in (". ", "? ", "! "):
        idx = stripped.find(end)
        if idx != -1:
            return stripped[: idx + 1].strip().lower()
    return stripped.lower()


def refusal_markers() -> tuple[str, ...]:
    """Lowercased substrings that identify an answer as a refusal/abstention.

    Current copy contributes its opening sentence (the whole string is too
    long and too easily reformatted to match reliably); legacy phrasings are
    kept verbatim so previously-cached answers are still recognised.
    """
    current = tuple(
        _first_sentence(copy)
        for copy in (FALLBACK_RESPONSE, NO_TEACHING_FOUND, PARTIAL_EVIDENCE_PREFACE)
        if copy
    )
    return tuple(dict.fromkeys(current + _LEGACY_REFUSAL_MARKERS))


def is_refusal_text(answer: str) -> bool:
    """True when `answer` is a refusal/abstention rather than a teaching."""
    if not answer:
        return False
    low = " ".join(answer.split()).lower()
    return any(marker in low for marker in refusal_markers())


# Appended by format_final_answer below the faithfulness/confidence floor. This
# is the LAST text a seeker reads, and it ran in the same clinical register as
# the refusals ("The available passages do not support a fully confident
# conclusion"). The hedge itself is kept — honesty about uncertainty is a
# grounding property, not a tone choice — only its voice changes.
CONFIDENCE_HEDGE = (
    "I am holding this one lightly — what I have here does not let me speak with "
    "full certainty. Sit with the cited teaching itself, or ask me something "
    "narrower and I will go deeper."
)


def redaction_note(removed: int) -> str:
    """Seeker-facing note for redacted lines."""
    if removed <= 0:
        return ""
    return REDACTION_NOTE_ONE if removed == 1 else REDACTION_NOTE_MANY.format(n=removed)


# --- Attribution floor ---------------------------------------------------
#
# GURU_DEMO_READINESS F2: the product shipped "Sri Preethaji & Sri Krishnaji
# teach that this state is not dependent on external achievements..." with
# citations=[], source_count=0 and grounding_state=abstained. A doctrinal claim
# was attributed to the living Gurus by name with no source behind it, and
# nothing in the rendered answer said so.
#
# Prompt rules cannot enforce this -- the model either follows them or does
# not, and F2 was intermittent precisely because it depended on what the model
# happened to emit. This is the structural version: a sentence that names a
# teacher as the SOURCE of a claim cannot ship while the response carries zero
# citations. Applied at the terminal node, so it holds for every route.
#
# Names are DERIVED from KNOWN_TEACHERS above rather than retyped -- checkpoint
# §8 defect class 3 is "a canonical string re-transcribed elsewhere".

# Minimum prose that must survive stripping for the remainder to still be an
# answer. Below this the seeker gets the honest abstention instead of a
# fragment. Mirrors the bound already used by _redact_unsupported_sentences.
_MIN_SURVIVING_CHARS = 120


def _teacher_name_alternation() -> str:
    names: set[str] = set()
    for display in KNOWN_TEACHERS.values():
        for part in display.split(" and "):
            part = part.strip()
            if not part:
                continue
            names.add(part)  # "Sri Preethaji"
            names.add(part.split()[-1])  # "Preethaji"
    # Longest first so "Sri Preethaji" wins over "Preethaji".
    return "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))


_TEACHER_NAME_RE = re.compile(rf"\b(?:{_teacher_name_alternation()})\b", re.IGNORECASE)

# Verbs that make the named teacher the SOURCE of the surrounding claim.
# "state"/"states" is deliberately absent: "the Beautiful State is..." would
# match the noun on essentially every doctrine sentence.
_ATTRIBUTION_VERB_RE = re.compile(
    r"\b(?:teach(?:es)?|taught|say(?:s)?|said|speak(?:s)?|spoke|"
    r"describe[sd]?|explain(?:s|ed)?|remind(?:s|ed)?|tell(?:s)?|told|"
    r"offer(?:s|ed)?|suggest(?:s|ed)?|share(?:s|d)?|"
    r"emphasi[sz]e[sd]?|reveal(?:s|ed)?|invite[sd]?|urge[sd]?|"
    r"point(?:s|ed)?\s+out|according\s+to|teaching(?:s)?\s+of|words?\s+of)\b",
    re.IGNORECASE,
)
_POSSESSIVE_RE = re.compile(rf"\b(?:{_teacher_name_alternation()})\s*(?:'s|’s)", re.IGNORECASE)

# Capturing split keeps the separators, so rejoining is lossless and paragraph
# structure survives.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])(\s+)")


def is_attributed_claim(sentence: str) -> bool:
    """True when `sentence` names a lineage teacher as the source of a claim."""
    if not sentence or not _TEACHER_NAME_RE.search(sentence):
        return False
    return bool(_ATTRIBUTION_VERB_RE.search(sentence) or _POSSESSIVE_RE.search(sentence))


def strip_unsourced_attributions(answer: str) -> tuple[str, int]:
    """Remove sentences that attribute a claim to a teacher.

    Call ONLY when the response carries zero citations -- an attributed
    sentence with sources behind it is the voice the product is supposed to
    have (Option A, third person with attributed quotes).

    Returns `(surviving_answer, removed_count)`. A refusal is returned
    untouched: it legitimately names the teachers while carrying no citations,
    and it asserts nothing on their behalf.
    """
    if not answer or not answer.strip():
        return answer, 0
    if is_refusal_text(answer):
        return answer, 0

    parts = _SENTENCE_SPLIT_RE.split(answer)
    kept: list[str] = []
    removed = 0
    for index, part in enumerate(parts):
        if index % 2:  # separator captured by the split
            if kept:
                kept.append(part)
            continue
        if is_attributed_claim(part):
            removed += 1
            if kept and kept[-1].isspace():
                kept.pop()
            continue
        kept.append(part)

    if not removed:
        return answer, 0

    surviving = "".join(kept).strip()
    if len(surviving) < _MIN_SURVIVING_CHARS:
        return NO_TEACHING_FOUND, removed
    return surviving, removed


if __name__ == "__main__":
    # Shape routing: a doctrine question must NOT be list-shaped; a steps
    # question must be. This is the rule that drove the metric.
    assert classify_shape("What is the Beautiful State?") is AnswerShape.TEACHING
    assert classify_shape("What are the exact 6 steps of Soul Sync?") is AnswerShape.PRACTICE
    assert classify_shape("anything", intent="DISTRESS") is AnswerShape.DISTRESS
    assert not build_register("preethaji", AnswerShape.TEACHING).allows_lists
    assert build_register("preethaji", AnswerShape.PRACTICE).allows_lists

    # Teacher selection reads documents only, and refuses to pick a winner when
    # two named teachers are both present.
    assert select_teacher([{"teacher_id": "krishnaji"}] * 3) == ("krishnaji", False)
    assert select_teacher([{"teacher_id": "krishnaji"}, {"teacher_id": "preethaji"}]) == (
        NEUTRAL_TEACHER,
        True,
    )
    assert select_teacher([]) == (NEUTRAL_TEACHER, False)
    assert select_teacher([{"teacher_id": "someone_else"}]) == (NEUTRAL_TEACHER, False)

    # Unknown teacher must degrade, never impersonate.
    assert build_register("nobody", AnswerShape.TEACHING).teacher_id == NEUTRAL_TEACHER

    spec = register_for("What is the Beautiful State?", docs=[{"teacher_id": "preethaji"}])
    assert spec.certified, "profile should be certified; run scripts.ops.build_voice_profiles"
    assert "no bullet markers" in spec.block.lower()
    assert apply_register("BASE", spec).startswith("BASE")

    # The copy must not leak internal machinery at the seeker.
    for copy in (PARTIAL_EVIDENCE_PREFACE, NO_TEACHING_FOUND, FALLBACK_RESPONSE):
        low = copy.lower()
        assert not any(
            bad in low
            for bad in ("verification gate", "generated draft", "pipeline", "retrieved excerpts")
        ), copy
    assert redaction_note(1) == REDACTION_NOTE_ONE
    assert "3" in redaction_note(3)

    # Attribution floor (F2). The exact sentence that shipped with zero
    # citations must be recognised, and an honest refusal must not be.
    _f2 = (
        "Sri Preethaji & Sri Krishnaji teach that this state is not dependent "
        "on external achievements but emerges from inner transformation."
    )
    assert is_attributed_claim(_f2)
    assert is_attributed_claim("According to Sri Krishnaji, the mind quietens.")
    assert is_attributed_claim("Preethaji's teaching begins with the inner state.")
    # The noun "state" must not read as the verb "states".
    assert not is_attributed_claim(
        "The Beautiful State is a state of inner calm available to you now."
    )
    assert not is_attributed_claim("You can return to that state whenever you choose.")
    _body = (
        "The Beautiful State is an inner condition of calm and connection. "
        "It does not depend on what is happening around you, and it is "
        "available in any circumstance you find yourself in today."
    )
    _kept, _removed = strip_unsourced_attributions(_body + " " + _f2)
    assert _removed == 1, _removed
    assert _f2 not in _kept
    assert _kept.startswith("The Beautiful State is an inner condition")
    # Too little left over -> the honest abstention, never a fragment.
    assert strip_unsourced_attributions(_f2) == (NO_TEACHING_FOUND, 1)
    # A refusal names the teachers but asserts nothing on their behalf.
    assert strip_unsourced_attributions(NO_TEACHING_FOUND)[1] == 0

    print(f"register for preethaji/TEACHING (certified={spec.certified}):\n")
    print(spec.block)
    print("\nservices/voice/register.py self-check OK")
