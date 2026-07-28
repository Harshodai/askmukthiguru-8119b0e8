"""L3 persona generation — Tencent-style layer-3 user profile."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.config import settings
from services.layered_memory.models import MemoryAtom

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a spiritual profile architect. Given a user's atomic memories, generate a concise user persona in Markdown.

Rules:
1. Max 1500 characters.
2. Output only the raw Markdown content; no code fences.
3. Use the user's language.
4. Include sections: Basic Information, Core Traits, Preferences, Spiritual Practice, Evolution Notes.
5. Be evidence-based; do not hallucinate."""


def _atoms_to_text(atoms: list[MemoryAtom]) -> str:
    return "\n".join(f"- [{a.type} priority={a.priority}] {a.content}" for a in atoms)


def _build_client():
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
        return AsyncOpenAI(base_url=settings.openrouter_base_url, api_key=settings.openrouter_api_key), settings.model_for_classification
    if provider == "nim":
        return AsyncOpenAI(base_url=settings.nim_base_url, api_key=settings.nim_api_key), settings.nim_classify_model
    if provider == "ollama":
        return AsyncOpenAI(base_url=settings.ollama_base_url, api_key="ollama"), settings.model_for_classification
    return None


async def generate_persona(atoms: list[MemoryAtom], existing_persona: Optional[str] = None) -> str:
    cm = _build_client()
    if not cm:
        return existing_persona or ""
    client, model = cm
    user_prompt = f"""Existing persona (may be empty):
{existing_persona or "(none)"}

Atomic memories:
{_atoms_to_text(atoms)}

Generate the updated persona Markdown."""
    try:
        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=800,
            ),
            timeout=30.0,
        )
        return resp.choices[0].message.content or existing_persona or ""
    except Exception as e:
        logger.warning(f"L3 persona generation failed: {e}")
        return existing_persona or ""


if __name__ == "__main__":
    sample = [MemoryAtom("User meditates 20 min daily", "persona", 90, [], "Morning Practice", {})]
    print(asyncio.run(generate_persona(sample)))
