"""L1 atomic memory extraction — Tencent-style layer-1 memory atoms."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from app.config import settings
from services.layered_memory.models import MemoryAtom, MemoryType
from services.layered_memory.prompts import L1_SYSTEM_PROMPT, build_l1_user_prompt

logger = logging.getLogger(__name__)

_MAX_TOKENS = 512
_TIMEOUT = 15.0


def _build_client() -> tuple[Any, str] | None:
    """Return an LLM client and model name based on active provider."""
    from openai import AsyncOpenAI

    provider = settings.llm_provider.lower()
    if settings.is_sarvam_cloud:
        return (
            AsyncOpenAI(
                base_url=settings.sarvam_base_url,
                api_key="api-key-not-used-by-bearer",
                default_headers={"api-subscription-key": settings.sarvam_api_key},
            ),
            settings.sarvam_cloud_classify_model or "sarvam-30b",
        )
    if provider == "openrouter":
        return AsyncOpenAI(
            base_url=settings.openrouter_base_url, api_key=settings.openrouter_api_key
        ), settings.model_for_classification
    if provider == "nim":
        return AsyncOpenAI(
            base_url=settings.nim_base_url, api_key=settings.nim_api_key
        ), settings.nim_classify_model
    if provider == "ollama":
        return AsyncOpenAI(
            base_url=settings.ollama_base_url, api_key="ollama"
        ), settings.model_for_classification
    return None


def _extract_json_array(text: str) -> list[dict]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?(.*?)\n?```$", r"\1", text, flags=re.DOTALL).strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []


def _normalize_type(value: Any) -> MemoryType:
    v = str(value).lower().strip()
    if v in {"persona", "episodic", "instruction"}:
        return v  # type: ignore[return-value]
    return "episodic"


async def extract_atoms(
    user_msg: str,
    assistant_msg: str,
    prior_messages: list[dict],
    previous_scene_name: str = "General",
) -> list[MemoryAtom]:
    cm = _build_client()
    if not cm:
        return []
    client, model = cm
    try:
        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": L1_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": build_l1_user_prompt(
                            user_msg, assistant_msg, prior_messages, previous_scene_name
                        ),
                    },
                ],
                temperature=0.0,
                max_tokens=_MAX_TOKENS,
            ),
            timeout=_TIMEOUT,
        )
        raw = resp.choices[0].message.content or "[]"
        atoms = _extract_json_array(raw)
        return [
            MemoryAtom(
                content=a["content"],
                type=_normalize_type(a.get("type")),
                priority=max(1, min(100, int(a.get("priority", 50)))),
                source_message_ids=a.get("source_message_ids", []),
                scene_name=a.get("scene_name", previous_scene_name),
                metadata=a.get("metadata", {}),
            )
            for a in atoms
            if a.get("content")
        ]
    except Exception as e:
        logger.warning(f"L1 extraction failed: {e}")
        return []


async def get_recent_atoms(
    memory_service: Any,
    user_id: str,
    limit: int = 50,
) -> list[MemoryAtom]:
    """Fetch recent L1 atoms for a user from the memory service."""
    try:
        result = await memory_service.list_memories(user_id, page=1, page_size=limit)
        atoms = []
        for m in result.get("memories", []):
            meta = m.get("metadata", {})
            if m.get("source") != "l1_atom":
                continue
            atoms.append(
                MemoryAtom(
                    id=str(m.get("id", "")),
                    content=m.get("content", ""),
                    type=_normalize_type(meta.get("atom_type")),
                    priority=int(meta.get("priority", 50)),
                    source_message_ids=meta.get("source_message_ids", []),
                    scene_name=meta.get("scene_name", "General"),
                    metadata=meta,
                )
            )
        return atoms
    except Exception as e:
        logger.warning(f"get_recent_atoms failed: {e}")
        return []


if __name__ == "__main__":
    atoms = asyncio.run(
        extract_atoms(
            "I meditate every morning for 20 minutes.", "That is a beautiful practice.", []
        )
    )
    for a in atoms:
        print(a)
