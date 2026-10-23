"""Optional structured span selector (Phase D8), off by default.

The selector may only *choose* among span IDs that retrieval already produced.
It cannot write teaching text: the model is asked for a JSON object containing a
``span_ids`` array, every other key (``prose``, ``answer``, ``explanation``, …)
is ignored, and unknown or duplicate IDs are rejected rather than repaired.
Anything unexpected returns ``None`` and the deterministic retrieval order is
used, which is why enabling this flag can never invent or paraphrase a teaching.
"""

from __future__ import annotations

import inspect
import json
import logging
from collections.abc import Iterable
from typing import Any

logger = logging.getLogger(__name__)

_SELECTOR_SYSTEM_PROMPT = (
    "You are a span selector. You will be given one seeker question and a "
    "numbered list of teacher speech spans. Reply with a single JSON object "
    'of the form {"span_ids": ["<id>"]} naming the spans, in reading order, '
    "that directly answer the question. Never write prose, explanations, or "
    "new teaching text. Never invent an id that is not in the list."
)

_SELECTOR_JSON_SCHEMA: dict[str, Any] = {
    "name": "first_person_span_selection",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["span_ids"],
        "properties": {
            "span_ids": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 0,
            }
        },
    },
}


def selector_enabled() -> bool:
    """Phase-D8 flag. Default false; a wired caller must check this first."""
    from app.config import settings

    return bool(settings.first_person_context_selector_enabled)


def selector_model() -> str:
    from app.config import settings

    return str(settings.first_person_context_selector_model or "").strip()


def _strip_optional_fence(raw: str) -> str:
    text = raw.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def parse_selection(raw: str, allowed_ids: Iterable[str]) -> tuple[str, ...] | None:
    """Validate a selector reply. ``None`` means "use deterministic order".

    Rules: the whole reply (after an optional enclosing Markdown fence) must be
    one JSON object; only ``span_ids`` is read; every id must be an allowed span
    ID; duplicates collapse; an empty selection is not a selection.
    """
    try:
        text = _strip_optional_fence(str(raw))
        if not (text.startswith("{") and text.endswith("}")):
            return None
        payload = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    ids = payload.get("span_ids")
    if not isinstance(ids, list):
        return None
    allowed = set(allowed_ids)
    picked: list[str] = []
    for candidate in ids:
        if not isinstance(candidate, str) or candidate not in allowed:
            # An unknown id means the model did not honour the contract.
            return None
        if candidate not in picked:
            picked.append(candidate)
    return tuple(picked) or None


def _build_prompt(question: str, spans: Iterable[Any]) -> str:
    body = "\n".join(
        f"[{index}] id={span.source_span_id} text={span.verbatim_text}"
        for index, span in enumerate(spans, 1)
    )
    return f"Question: {question}\n\nSpans:\n{body}"


def select_span_ids(
    question: str,
    spans: Iterable[Any],
    llm_service: Any = None,
) -> tuple[str, ...] | None:
    """Return selected span IDs, or ``None`` to keep deterministic order.

    Fails open on: flag off, no provider, provider error/refusal/timeout,
    malformed or prose-carrying output, unknown IDs.
    """
    span_list = list(spans)
    if not span_list or llm_service is None or not hasattr(llm_service, "generate"):
        return None
    if not selector_enabled():
        return None

    allowed_ids = [span.source_span_id for span in span_list]
    user_prompt = _build_prompt(question, span_list)
    gen_kwargs: dict[str, Any] = {
        "system_prompt": _SELECTOR_SYSTEM_PROMPT,
        "user_prompt": user_prompt,
        "temperature": 0.0,
        "response_format": {
            "type": "json_schema",
            "json_schema": _SELECTOR_JSON_SCHEMA,
        },
    }
    model = selector_model()
    if model:
        gen_kwargs["model"] = model
        gen_kwargs["max_tokens"] = 256

    _SELECTOR_TIMEOUT_S = 3.0

    async def _call() -> Any:
        res = llm_service.generate(**gen_kwargs)
        if inspect.isawaitable(res):
            return await res
        return res

    try:
        from services.first_person_pipeline import run_llm_coroutine

        result = run_llm_coroutine(_call, timeout_s=_SELECTOR_TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001 - the selector is optional by design
        # Covers provider refusal, timeout, and transport errors alike.
        logger.info("[FPSelector] selection skipped (%s); deterministic order kept", exc)
        return None
    return parse_selection(result, allowed_ids)


if __name__ == "__main__":
    _allowed = ["span_1", "span_2", "span_3"]
    # 1. Valid JSON
    _valid = parse_selection('{"span_ids": ["span_2", "span_1"]}', _allowed)
    assert _valid == ("span_2", "span_1"), f"Unexpected valid parse: {_valid}"

    # 2. Prose-wrapped output (rejected by design)
    _prose = parse_selection('Here are the spans: {"span_ids": ["span_1"]}', _allowed)
    assert _prose is None, f"Expected None for prose-wrapped output, got {_prose}"

    # 3. Unknown-ID reply
    _unknown = parse_selection('{"span_ids": ["unknown_span"]}', _allowed)
    assert _unknown is None, f"Expected None for unknown ID, got {_unknown}"

    print("first_person_context_selector self-check passed")
