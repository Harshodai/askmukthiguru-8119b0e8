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


JUDGE_SYSTEM_PROMPT = _build_judge_system_prompt()

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


def select_index(scores: list[dict[str, Any]], answerable: bool, minimum: int) -> Optional[int]:
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
    if not eligible:
        return None
    best = max(eligible, key=lambda s: (s["relevance"], -s["i"]))
    return int(best["i"])


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


async def judge_select_async(
    question: str,
    clips: list[dict[str, Any]],
    llm_service: Any,
    *,
    minimum: int,
    timeout_s: float,
    scores_out: Optional[list[int]] = None,
    judge_meta_out: Optional[dict[str, Any]] = None,
) -> Optional[int]:
    """One judge call. Index to serve, None (below minimum), or INDETERMINATE."""
    import asyncio

    if not clips or llm_service is None or not hasattr(llm_service, "generate"):
        return INDETERMINATE
    user_prompt = build_judge_prompt(question, clips)

    async def _call() -> str:
        res = llm_service.generate(
            system_prompt=JUDGE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_format=JUDGE_JSON_SCHEMA,
            **judge_call_kwargs(judge_model()),
        )
        if inspect.isawaitable(res):
            res = await res
        return str(res)

    try:
        raw = await asyncio.wait_for(_call(), timeout=timeout_s)
    except Exception as exc:  # noqa: BLE001 - any failure is indeterminate (fail closed)
        logger.info("[FPJudge] judge call indeterminate: %s", type(exc).__name__)
        return INDETERMINATE
    parsed = parse_judge_reply(raw, len(clips))
    if parsed is None:
        logger.info("[FPJudge] judge reply rejected by the strict parser; abstaining")
        return INDETERMINATE
    scores, answerable = parsed
    if scores_out is not None:
        scores_out[:] = [int(s["relevance"]) for s in scores]
    chosen = select_index(scores, answerable, minimum)
    if judge_meta_out is not None:
        judge_meta_out.update(
            {
                "scores": scores,
                "question_answerable": answerable,
                "selected": chosen,
            }
        )
        editorial_set = build_editorial_set_from_judge(judge_meta_out, query=question)
        if editorial_set is not None:
            judge_meta_out["editorial_set"] = editorial_set
    return chosen
