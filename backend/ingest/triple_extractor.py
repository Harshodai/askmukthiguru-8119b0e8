"""Automated Information-Extraction (IE) pipeline stub (Task E4.1).

One function — `extract_triples(text, llm)` — uses an LLM to pull
(entity, relation, entity) triples out of ingested text, validated by a
Pydantic schema. Event-driven: call this on new content; don't build a
framework around it.

Ponytail: single function, single Pydantic model, single self-check.
LightRAG already does heavy graph extraction (`services/lightrag_service.py`);
this is the lighter, structured-output sibling for callers that want raw
triples (e.g. custom ontology writes, eval harnesses).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from pydantic import BaseModel, ValidationError, field_validator

logger = logging.getLogger(__name__)


class Triple(BaseModel):
    """One (subject, relation, object) triple."""

    subject: str
    relation: str
    object: str

    @field_validator("subject", "relation", "object")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("triple field must be non-empty")
        return v


class TripleSet(BaseModel):
    """Validated wrapper around a list of triples."""

    triples: list[Triple] = []

    def as_dicts(self) -> list[dict[str, str]]:
        return [t.model_dump() for t in self.triples]


_SYSTEM_PROMPT = (
    "You are a knowledge-graph information-extraction assistant. "
    "Read the user text and extract entity-relation-entity triples. "
    "Return ONLY a JSON object of the form "
    '{"triples": [{"subject": str, "relation": str, "object": str}, ...]}. '
    "No prose, no markdown fences, no commentary. "
    "Use short canonical relation verbs in UPPERCASE (e.g. EXPOUNDS, TEACHES, "
    "PRACTICE_FOR, CONTRASTS_WITH, RELATED_TO). Empty input -> {\"triples\": []}."
)


def _strip_code_fence(raw: str) -> str:
    """Strip ```json ... ``` fences if the model wrapped output."""
    raw = raw or ""
    raw = re.sub(r"^\s*```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```\s*$", "", raw)
    return raw.strip()


def _parse_triples(raw: str) -> list[dict[str, str]]:
    """Best-effort JSON parse + Pydantic validation. Never raises."""
    if not raw:
        return []
    cleaned = _strip_code_fence(raw)
    # Some models return a bare list; wrap it.
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find first { ... last }
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            logger.warning("extract_triples: JSON parse failed; returning []")
            return []
        try:
            data = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            logger.warning("extract_triples: JSON parse failed after slice; returning []")
            return []
    if isinstance(data, list):
        data = {"triples": data}
    try:
        ts = TripleSet.model_validate(data)
    except ValidationError as e:
        logger.warning(f"extract_triples: validation failed ({e}); returning []")
        return []
    return ts.as_dicts()


async def extract_triples(text: str, llm: Any) -> list[dict[str, str]]:
    """Extract (subject, relation, object) triples from `text` via `llm`.

    Args:
        text: Raw text to extract from. Empty/whitespace -> [].
        llm: An object exposing `async def generate(system_prompt, user_prompt,
            context="", **kwargs) -> str` (BaseLLMService protocol). Anything
            with that signature works (Ollama / Sarvam / OpenRouter / NIM).

    Returns:
        List of {"subject", "relation", "object"} dicts. Always a list —
        never raises on parse/validation failure (logs + returns []).
    """
    if not text or not text.strip():
        return []
    if llm is None:
        logger.warning("extract_triples: no llm provided; returning []")
        return []
    try:
        raw = await llm.generate(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=text,
            context="",
            max_tokens=1024,
        )
    except Exception as e:
        logger.warning(f"extract_triples: LLM call failed ({e}); returning []")
        return []
    return _parse_triples(raw)


def write_triples_to_neo4j(triples: list[dict[str, str]], driver=None) -> int:
    """Optional helper: MERGE triples into Neo4j as :base nodes + :RELATED_TO.

    Ponytail: one Cypher, MERGE idempotent. Returns count written.
    Caller passes a neo4j.Driver; if None, no-op (returns 0). Kept here so
    callers don't reinvent it, but `extract_triples` itself is storage-free.
    """
    if not triples or driver is None:
        return 0
    written = 0
    try:
        with driver.session() as session:
            for t in triples:
                session.run(
                    """
                    MERGE (s:base {entity_id: $subject})
                    MERGE (o:base {entity_id: $object})
                    MERGE (s)-[:RELATED_TO]->(o)
                    """,
                    subject=t["subject"],
                    object=t["object"],
                )
                written += 1
    except Exception as e:
        logger.warning(f"write_triples_to_neo4j failed: {e}")
    return written


if __name__ == "__main__":
    # Self-check: no live LLM needed — exercise the parser + validator directly.
    sample_text = "Sadhguru expounds Karma. Sri Preethaji teaches the Beautiful State."
    fake_raw = (
        '{"triples": ['
        '{"subject": "Sadhguru", "relation": "EXPOUNDS", "object": "Karma"},'
        '{"subject": "Sri Preethaji", "relation": "TEACHES", "object": "Beautiful State"}'
        "]}"
    )
    parsed = _parse_triples(fake_raw)
    assert len(parsed) == 2, f"expected 2 triples, got {len(parsed)}: {parsed}"
    assert parsed[0]["subject"] == "Sadhguru"
    assert parsed[1]["object"] == "Beautiful State"
    # Bad input must not raise
    assert _parse_triples("") == []
    assert _parse_triples("not json at all") == []
    assert _parse_triples('{"triples": [{"subject": "", "relation": "X", "object": "Y"}]}') == []
    print(f"extract_triples self-check OK — parsed {len(parsed)} triples from sample.")
    print(f"  sample: {parsed}")