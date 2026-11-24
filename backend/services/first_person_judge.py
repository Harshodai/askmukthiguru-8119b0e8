"""Evidence judge for the first-person lane (T4-06, ADR-009), default off.

One structured call scores every candidate clip: ``relevance`` 0 to 3 (the
scorer's rubric), ``answers`` (does this clip answer this question) and
``question_answerable`` for the whole question. The judge never writes text.

Contract: ``RETRIEVAL_AND_RAG_SPEC.md`` §3.4. Serve the clip with the highest
relevance that is at least ``first_person_relevance_min_score`` and has
``answers == true``; ties go to the earlier retrieval rank. Any error,
refusal, timeout, wrong shape or missing index is ``relevance_indeterminate``.

Activation needs both ``first_person_judge_enabled`` (default False) and a
non-empty ``first_person_judge_model``. D-16 (owner decision 2026-11-07) named
the model: the relevance scorer's own, ``anthropic/claude-haiku-5.5``, so the
flag is now the only switch, and it stays off until the comparison below. When active it replaces the relevance scorer
call (L4). The rerank (L3) and answerability (L2) calls stay until the frozen
bank comparison shows the judge is not worse (T4-06 exit criterion).
"""

from __future__ import annotations

import inspect
import json
import logging
import time
from contextvars import ContextVar
from typing import Any, Optional

from services.untrusted import data_notice, fence_inline, neutralise

logger = logging.getLogger(__name__)

INDETERMINATE = -1  # same value as first_person_pipeline._RELEVANCE_INDETERMINATE
JUDGE_MAX_TOKENS = 1024


def _build_judge_system_prompt() -> str:
    from services.guru_registry import allowed_speaker_labels

    allowed = " and ".join(sorted(allowed_speaker_labels()))
    return (
        "You judge recorded teaching clips for one seeker question across multiple semantic dimensions.\n"
        "For each clip evaluate:\n"
        "- relevance: integer 0-3 (3 = directly answers the question, 2 = closely related, "
        "1 = loosely related, 0 = unrelated).\n"
        "- answers: boolean, true only if the clip itself directly answers this specific question.\n"
        "- is_complete_thought: boolean, true if the quote forms a grammatically complete, coherent thought without severed phrases or mid-sentence cutoffs.\n"
        "- is_standalone: boolean, true if interpretable on its own without requiring missing prior conversational context or unresolved pronouns.\n"
        "- covered_facets: list of strings indicating which question facets this clip addresses (e.g. 'definition', 'distinction', 'practice', 'cause', 'experience', 'inner_state', 'transformation', 'general').\n"
        "- content_safety: string, one of 'clean' (authentic spiritual/wellbeing guidance), 'distress' (acute distress/crisis), 'clinical_promise' (unsubstantiated medical cure claims), 'harm' (violence or self-harm).\n\n"
        f"ATTRIBUTION INVARIANT: The recorded clips in this archive are exclusively from {allowed}. "
        "If the seeker's question specifically asks what ANOTHER spiritual teacher, philosopher, "
        "author, or tradition teaches (such as Thich Nhat Hanh, the Buddha, Eckhart Tolle, Sadhguru, "
        "Marcus Aurelius, Zen, Kabbalah, etc.), a clip from this archive CANNOT answer "
        "what that other teacher teaches. For any such attribution mismatch, score relevance 0 and answers false.\n\n"
        "Set question_answerable = true only if the question is about inner life, spiritual practice, relationships, or wisdom teachings.\n"
        'Reply with one JSON object: {"scores": [{"i": 0, "relevance": 0, "answers": false, '
        '"is_complete_thought": true, "is_standalone": true, "covered_facets": ["general"], '
        '"content_safety": "clean"}], "question_answerable": false}, one entry per clip index, nothing else. '
        + data_notice("clip")
    )


JUDGE_SYSTEM_PROMPT = _build_judge_system_prompt()  # the v1 rubric; importers rely on it

# Rubric v2 (default off, FIRST_PERSON_JUDGE_RUBRIC): v1 plus this block. The output
# schema is unchanged, so ``parse_judge_reply`` needs no change.
JUDGE_RUBRIC_V2_BLOCK = (
    "STRICT COMPLETENESS RULES (apply to every clip, in addition to the above):\n"
    "A clip that is merely related to the topic must not be marked as answering. "
    "Set answers to false and relevance to 2 or lower when any of these applies:\n"
    "1. It addresses the broad theme but not the specific question asked "
    "(question: how to forgive a parent; clip: a general talk about why forgiveness matters).\n"
    "2. It starts a list or framework and ends before finishing it "
    "(announces three steps, gives only the first).\n"
    "3. It starts an analogy, story or parable and ends before its conclusion "
    "(describes a farmer and a field, stops before the point is drawn).\n"
    "4. It opens by pointing at context the seeker cannot see "
    '("as I said earlier", "everyone asked me this", "that question you raised").\n'
    "5. It stops in the middle of an argument, before the conclusion that answers the question.\n"
    "When unsure whether a clip is complete and on the exact question, choose answers false."
)

JUDGE_RUBRICS = ("v1", "v2")


def judge_rubric() -> str:
    """Active rubric, read per call so the flag is live."""
    from app.config import settings

    return str(getattr(settings, "first_person_judge_rubric", "v2") or "v2")


def judge_system_prompt(rubric: Optional[str] = None) -> str:
    """System prompt for ``rubric`` (default: the configured one). v1 is byte-identical to
    ``JUDGE_SYSTEM_PROMPT``; an unknown value raises rather than silently using v1."""
    r = rubric or judge_rubric()
    if r == "v1":
        return JUDGE_SYSTEM_PROMPT
    if r == "v2":
        return JUDGE_SYSTEM_PROMPT + "\n\n" + JUDGE_RUBRIC_V2_BLOCK
    raise ValueError(f"unknown first_person_judge_rubric: {r!r}")


JUDGE_JSON_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "first_person_evidence_judge",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["scores", "question_answerable"],
            "properties": {
                "scores": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "i",
                            "relevance",
                            "answers",
                            "is_complete_thought",
                            "is_standalone",
                            "covered_facets",
                            "content_safety",
                        ],
                        "properties": {
                            "i": {"type": "integer"},
                            "relevance": {"type": "integer"},
                            "answers": {"type": "boolean"},
                            "is_complete_thought": {"type": "boolean"},
                            "is_standalone": {"type": "boolean"},
                            "covered_facets": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "content_safety": {
                                "type": "string",
                                "enum": ["clean", "distress", "clinical_promise", "harm"],
                            },
                        },
                    },
                },
                "question_answerable": {"type": "boolean"},
            },
        },
    },
}


def judge_enabled() -> bool:
    from app.config import settings

    return bool(getattr(settings, "first_person_judge_enabled", False))


def judge_model() -> str:
    from app.config import settings

    return str(getattr(settings, "first_person_judge_model", "") or "").strip()


def judge_active() -> bool:
    """True only with the flag on and a model chosen (D-16)."""
    return judge_enabled() and bool(judge_model())


def judge_call_kwargs(model: str) -> dict[str, Any]:
    """Model-specific call shape, the same as the relevance scorer's (D-16).

    An Anthropic model reasons before it answers: it needs room for the
    reasoning (max_tokens 2048, the "verify" ceiling, low effort). A model in
    the scorer's no-temperature set rejects a non-default temperature (CA-1),
    so ``None`` tells the provider service to omit the key.
    """
    from services.first_person_pipeline import _SCORER_NO_TEMPERATURE_MODELS

    kwargs: dict[str, Any] = {"model": model, "max_tokens": JUDGE_MAX_TOKENS, "temperature": 0.0}
    if model.startswith("anthropic/"):
        kwargs.update(max_tokens=2048, operation="verify", reasoning_effort="low")
    if model in _SCORER_NO_TEMPERATURE_MODELS:
        kwargs["temperature"] = None
    return kwargs


def build_judge_prompt(question: str, clips: list[dict[str, Any]]) -> str:
    lines = []
    for i, clip in enumerate(clips):
        text = " ".join(str(clip.get("verbatim_text") or "").split())
        lines.append(f"[{i}] {fence_inline('clip', text)}")
    return f"Question: {neutralise(question)}\n\nClips:\n" + "\n".join(lines)


ALLOWED_ITEM_KEYS = frozenset(
    {
        "i",
        "relevance",
        "answers",
        "is_complete_thought",
        "is_standalone",
        "covered_facets",
        "content_safety",
    }
)
REQUIRED_BASE_KEYS = frozenset({"i", "relevance", "answers"})


def parse_judge_reply(raw: Any, n_clips: int) -> Optional[tuple[list[dict[str, Any]], bool]]:
    """Strict parse with multi-dimensional decoding and backward compatibility.

    Returns (scores ordered by index, question_answerable) or None.
    """
    text = str(raw or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    if not (text.startswith("{") and text.endswith("}")):
        return None
    try:
        decoded = json.loads(text)
    except ValueError:
        return None
    if not isinstance(decoded, dict) or set(decoded) != {"scores", "question_answerable"}:
        return None
    answerable = decoded["question_answerable"]
    scores = decoded["scores"]
    if not isinstance(answerable, bool) or not isinstance(scores, list):
        return None
    by_index: dict[int, dict[str, Any]] = {}
    for item in scores:
        if not isinstance(item, dict):
            return None
        keys = set(item)
        if not REQUIRED_BASE_KEYS.issubset(keys) or not keys.issubset(ALLOWED_ITEM_KEYS):
            return None
        i, rel, ans = item["i"], item["relevance"], item["answers"]
        if isinstance(i, bool) or not isinstance(i, int) or not 0 <= i < n_clips:
            return None
        if isinstance(rel, bool) or not isinstance(rel, int) or not 0 <= rel <= 3:
            return None
        if not isinstance(ans, bool) or i in by_index:
            return None

        # Multi-dimensional semantic evaluation fields with defaults for backward compatibility
        ict = item.get("is_complete_thought", True)
        if not isinstance(ict, bool):
            return None

        isa = item.get("is_standalone", True)
        if not isinstance(isa, bool):
            return None

        cf = item.get("covered_facets")
        if cf is not None:
            if not isinstance(cf, list) or not all(isinstance(f, str) for f in cf):
                return None
            facets_list = list(cf)
        else:
            facets_list = ["general"] if ans else []

        cs = item.get("content_safety", "clean")
        if not isinstance(cs, str) or not cs:
            return None

        by_index[i] = {
            "i": i,
            "relevance": rel,
            "answers": ans,
            "is_complete_thought": bool(ict),
            "is_standalone": bool(isa),
            "covered_facets": facets_list,
            "content_safety": str(cs),
        }
    if len(by_index) != n_clips:
        return None
    return [by_index[i] for i in range(n_clips)], answerable


def rejection_reason(scores: list[dict[str, Any]], answerable: bool, minimum: int) -> str:
    """Why ``select_index`` returned None, per clip, for logs (never a verdict on its own)."""
    if not answerable:
        return "question_not_answerable"
    parts = []
    for s in scores:
        failed = []
        if not s["answers"]:
            failed.append("answers=false")
        if s["relevance"] < minimum:
            failed.append(f"relevance={s['relevance']}<min{minimum}")
        if s.get("content_safety", "clean") not in ("clean", "safe", "wellbeing_notice"):
            failed.append(f"safety={s.get('content_safety')}")
        if not s.get("is_complete_thought", True):
            failed.append("incomplete_thought")
        if not s.get("is_standalone", True):
            failed.append("not_standalone")
        parts.append(f"clip{s['i']}[{','.join(failed) or 'passed'}]")
    return " ".join(parts) or "no_scores"


def select_index(
    scores: list[dict[str, Any]],
    answerable: bool,
    minimum: int,
    *,
    allow_weak_match: bool = False,
) -> Optional[int]:
    """Serve rule (§3.4). None means no clip qualifies (abstain below minimum)."""
    if not answerable:
        return None
    eligible = [
        s
        for s in scores
        if s["answers"]
        and s["relevance"] >= minimum
        and s.get("content_safety", "clean") in ("clean", "safe", "wellbeing_notice")
        and s.get("is_complete_thought", True)
        and s.get("is_standalone", True)
    ]
    if eligible:
        best = max(eligible, key=lambda s: (s["relevance"], -s["i"]))
        return int(best["i"])
    if allow_weak_match:
        # Under weak-match serving (Invariant 2 in AGENTS.md), if direct answer is absent
        # but a clean, standalone clip has relevance >= minimum, select it as weak match.
        weak_eligible = [
            s
            for s in scores
            if s["relevance"] >= minimum
            and s.get("content_safety", "clean") in ("clean", "safe", "wellbeing_notice")
            and s.get("is_complete_thought", True)
            and s.get("is_standalone", True)
        ]
        if weak_eligible:
            best_weak = max(weak_eligible, key=lambda s: (s["relevance"], -s["i"]))
            return int(best_weak["i"])
    return None


def build_editorial_set_from_judge(
    judge_meta: dict[str, Any],
    query: str = "",
    is_direct: bool = True,
) -> Optional[dict[str, Any]]:
    """Build a typed editorial_set record from the judge's selected evaluation."""
    if not judge_meta or judge_meta.get("selected") is None:
        return None
    scores = judge_meta.get("scores", [])
    selected = judge_meta.get("selected")
    if not isinstance(selected, int) or not (0 <= selected < len(scores)):
        return None
    item = scores[selected]
    answers = bool(item.get("answers", False))
    rel = int(item.get("relevance", 0))
    is_direct_judge = answers and rel >= 3 and is_direct
    status = "supported" if is_direct_judge else "partial"
    covered_facets = list(item.get("covered_facets") or ["general"])
    candidate_facets = list(dict.fromkeys(["general"] + covered_facets))
    facet_coverage = {f: "direct" if is_direct_judge else "indirect" for f in candidate_facets}
    return {
        "status": status,
        "primary_intent": covered_facets[0] if covered_facets else "general",
        "candidate_facets": candidate_facets,
        "covered_facets": covered_facets,
        "facet_coverage": facet_coverage,
        "is_complete_thought": item.get("is_complete_thought", True),
        "is_standalone": item.get("is_standalone", True),
        "content_safety": item.get("content_safety", "clean"),
        "reasons": [
            "judge_verified_direct" if is_direct_judge else "judge_related_only",
            "semantic_judge_evaluation",
        ],
    }


# U1 (2026-11-16): the harness sets a list here; each judge retry appends one entry so the
# per-request summary line can report how many calls were retried. None outside the harness.
JUDGE_RETRY_LOG: ContextVar[Optional[list[int]]] = ContextVar("fp_judge_retry_log", default=None)


async def _call_or_none(call: Any, timeout_s: float, label: str) -> Optional[str]:
    """Run one judge-model call under its timeout; None on any failure.

    The single fail-closed handler for both judge calls: a timeout, a provider
    error or a cancelled budget all mean "indeterminate", and the caller abstains.
    """
    import asyncio

    try:
        return await asyncio.wait_for(call(), timeout=timeout_s)
    except Exception as exc:  # noqa: BLE001 - any failure is indeterminate (fail closed)
        logger.info("[FPJudge] %s call indeterminate: %s", label, type(exc).__name__)
        return None


async def judge_select_async(
    question: str,
    clips: list[dict[str, Any]],
    llm_service: Any,
    *,
    minimum: int,
    timeout_s: float,
    scores_out: Optional[list[int]] = None,
    judge_meta_out: Optional[dict[str, Any]] = None,
    rubric: Optional[str] = None,
) -> Optional[int]:
    """One judge call. Index to serve, None (below minimum), or INDETERMINATE.

    ``rubric`` overrides the configured rubric for this call only (offline replay)."""

    if not clips or llm_service is None or not hasattr(llm_service, "generate"):
        return INDETERMINATE
    user_prompt = build_judge_prompt(question, clips)
    system_prompt = judge_system_prompt(rubric)

    async def _call() -> str:
        res = llm_service.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format=JUDGE_JSON_SCHEMA,
            **judge_call_kwargs(judge_model()),
        )
        if inspect.isawaitable(res):
            res = await res
        return str(res)

    # U1: one retry on failure/timeout/unparseable reply, inside the SAME total budget
    # (the second attempt gets only the time left, never a fresh timeout_s).
    deadline = time.monotonic() + timeout_s
    parsed = None
    for attempt in (0, 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        if attempt:
            retry_log = JUDGE_RETRY_LOG.get()
            if retry_log is not None:
                retry_log.append(1)
        raw = await _call_or_none(_call, remaining, "judge")
        if raw is None:
            continue
        parsed = parse_judge_reply(raw, len(clips))
        if parsed is not None:
            break
        logger.info("[FPJudge] judge reply rejected by the strict parser (attempt %d)", attempt + 1)
    if parsed is None:
        return INDETERMINATE
    scores, answerable = parsed
    if scores_out is not None:
        scores_out[:] = [int(s["relevance"]) for s in scores]
    from app.config import settings

    allow_weak = bool(getattr(settings, "first_person_serve_weak_match", True))
    chosen = select_index(scores, answerable, minimum, allow_weak_match=allow_weak)
    is_direct = bool(scores[chosen]["answers"]) if chosen is not None and 0 <= chosen < len(scores) else False
    if judge_meta_out is not None:
        judge_meta_out.update(
            {
                "scores": scores,
                "question_answerable": answerable,
                "selected": chosen,
                "is_direct": is_direct,
            }
        )
        editorial_set = build_editorial_set_from_judge(judge_meta_out, query=question, is_direct=is_direct)
        if editorial_set is not None:
            judge_meta_out["editorial_set"] = editorial_set
    return chosen


# --- Comparative judge (Candidate A, SAME_CLIP_DEFECT_2026-11-13) -----------------------------
# Default off (first_person_comparative_judge_enabled). Every candidate here already passed
# the per-clip judge; this call only compares them. The model returns an INDEX or null, never
# text (invariant 15). Any failure is INDETERMINATE and the caller abstains (fail closed).

COMPARATIVE_SYSTEM_PROMPT = (
    "You choose among recorded teaching clips for one seeker question. Every clip below "
    "already passed an individual check. Pick the ONE clip that most directly answers THIS "
    "specific question. Being on the same broad topic is not answering. If none of the clips "
    "answers this specific question directly, choose none.\n"
    'Reply with one JSON object: {"best": <clip index>} or {"best": null}, nothing else. '
    + data_notice("clip")
)

COMPARATIVE_JSON_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "first_person_comparative_judge",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["best"],
            "properties": {"best": {"type": ["integer", "null"]}},
        },
    },
}


def comparative_enabled() -> bool:
    from app.config import settings

    return bool(getattr(settings, "first_person_comparative_judge_enabled", False))


def build_comparative_prompt(question: str, clips: list[dict[str, Any]]) -> str:
    return build_judge_prompt(question, clips)


def parse_comparative_reply(raw: Any, n_clips: int) -> Optional[int]:
    """Strict parse of ``{"best": <int> | null}``. INDETERMINATE for anything else."""
    text = str(raw or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    if not (text.startswith("{") and text.endswith("}")):
        return INDETERMINATE
    try:
        decoded = json.loads(text)
    except ValueError:
        return INDETERMINATE
    if not isinstance(decoded, dict) or set(decoded) != {"best"}:
        return INDETERMINATE
    best = decoded["best"]
    if best is None:
        return None
    if isinstance(best, bool) or not isinstance(best, int) or not 0 <= best < n_clips:
        return INDETERMINATE
    return best


async def comparative_select_async(
    question: str,
    clips: list[dict[str, Any]],
    llm_service: Any,
    *,
    timeout_s: float,
    token_sink: Optional[list[int]] = None,
) -> Optional[int]:
    """One comparative call. Index to serve, None (no clip answers), or INDETERMINATE."""

    if not clips or llm_service is None or not hasattr(llm_service, "generate"):
        return INDETERMINATE
    user_prompt = build_comparative_prompt(question, clips)

    async def _call() -> str:
        res = llm_service.generate(
            system_prompt=COMPARATIVE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_format=COMPARATIVE_JSON_SCHEMA,
            **judge_call_kwargs(judge_model()),
        )
        if inspect.isawaitable(res):
            res = await res
        return str(res)

    raw = await _call_or_none(_call, timeout_s, "comparative")
    if raw is None:
        return INDETERMINATE
    if token_sink is not None:
        from services.first_person_pipeline import _estimate_fp_tokens

        token_sink.append(_estimate_fp_tokens(COMPARATIVE_SYSTEM_PROMPT, user_prompt, raw))
    chosen = parse_comparative_reply(raw, len(clips))
    if chosen == INDETERMINATE:
        logger.info("[FPJudge] comparative reply rejected by the strict parser; abstaining")
    return chosen
