"""L3 persona generation — user-stated preferences and interests synthesis (T6-03 / MEM-004)."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.config import settings
from services.layered_memory.models import MemoryAtom

logger = logging.getLogger(__name__)

# T6-03 (MEM-004): Synthesize only user-stated facts and preferences.
# Never infer spiritual stages, emotional diagnoses, or psychological profiles.
_SYSTEM_PROMPT = """You are a user-stated preferences synthesizer. Given a user's atomic memories, compile a factual summary of user-stated preferences, practices, and topics of interest.

Rules:
1. Max 1500 characters.
2. Output only factual, user-stated preferences, explicit interests, and requested practices.
3. NEVER infer, speculate on, or invent spiritual stages, emotional diagnoses, or psychological profiles.
4. Use the user's language.
5. Format sections: Stated Topics & Interests, Explicit Preferences, Practices Undertaken.
6. Strictly ground every item in the provided atomic memories; do not extrapolate."""


def compile_user_preferences(atoms: list[MemoryAtom]) -> dict[str, list[str]]:
    """T6-03 (MEM-004): Extract structured, factual user-stated preferences directly from atoms."""
    topics: list[str] = []
    preferences: list[str] = []
    practices: list[str] = []

    for a in atoms:
        content = a.content.strip()
        if not content:
            continue
        atom_type = (a.type or "").lower()
        if atom_type in ("preference", "pref"):
            preferences.append(content)
        elif atom_type in ("practice", "meditation", "sadhana"):
            practices.append(content)
        elif atom_type in ("topic", "interest", "persona"):
            topics.append(content)
        else:
            topics.append(content)

    return {
        "stated_topics": topics,
        "explicit_preferences": preferences,
        "practices_undertaken": practices,
    }


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
