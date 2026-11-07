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
        "You judge recorded teaching clips for one seeker question. For each clip give "
        "relevance 0-3 (3 = directly answers the question, 2 = closely related, "
        "1 = loosely related, 0 = unrelated) and answers = true only if the clip itself "
        "answers this specific question. "
        f"ATTRIBUTION INVARIANT: The recorded clips in this archive are exclusively from {allowed}. "
        "If the seeker's question specifically asks what ANOTHER spiritual teacher, philosopher, "
        "author, or tradition teaches (such as Thich Nhat Hanh, the Buddha, Eckhart Tolle, Sadhguru, "
        "Marcus Aurelius, Zen, Kabbalah, etc.), a clip from this archive CANNOT answer "
        "what that other teacher teaches. For any such attribution mismatch, score relevance 0 and answers false. "
        "Set question_answerable = true only if the "
        "question is about inner life, spiritual practice or the teachings. Reply with "
        'one JSON object: {"scores": [{"i": 0, "relevance": 0, "answers": false}], '
        '"question_answerable": false}, one entry per clip index, nothing else. ' + data_notice("clip")
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
                        "required": ["i", "relevance", "answers"],
                        "properties": {
                            "i": {"type": "integer"},
                            "relevance": {"type": "integer"},
                            "answers": {"type": "boolean"},
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


def parse_judge_reply(raw: Any, n_clips: int) -> Optional[tuple[list[dict[str, Any]], bool]]:
    """Strict parse. Returns (scores ordered by index, question_answerable) or None."""
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
        if not isinstance(item, dict) or set(item) != {"i", "relevance", "answers"}:
            return None
        i, rel, ans = item["i"], item["relevance"], item["answers"]
        if isinstance(i, bool) or not isinstance(i, int) or not 0 <= i < n_clips:
            return None
        if isinstance(rel, bool) or not isinstance(rel, int) or not 0 <= rel <= 3:
            return None
        if not isinstance(ans, bool) or i in by_index:
            return None
        by_index[i] = item
    if len(by_index) != n_clips:
        return None
    return [by_index[i] for i in range(n_clips)], answerable


def select_index(scores: list[dict[str, Any]], answerable: bool, minimum: int) -> Optional[int]:
    """Serve rule (§3.4). None means no clip qualifies (abstain below minimum)."""
    if not answerable:
        return None
    eligible = [s for s in scores if s["answers"] and s["relevance"] >= minimum]
    if not eligible:
        return None
    best = max(eligible, key=lambda s: (s["relevance"], -s["i"]))
    return int(best["i"])


async def judge_select_async(
    question: str,
    clips: list[dict[str, Any]],
    llm_service: Any,
    *,
    minimum: int,
    timeout_s: float,
    scores_out: Optional[list[int]] = None,
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
    return select_index(scores, answerable, minimum)
