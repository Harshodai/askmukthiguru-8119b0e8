from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = 20.0
_SKILL_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "skill_list",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "skills": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                            "proficiency": {"type": "number"},
                        },
                        "required": ["name", "description", "proficiency"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["skills"],
            "additionalProperties": False,
        },
    },
}

def _build_client() -> tuple[Any, str] | None:
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

async def generate_skills(atoms_text: str, existing_skills: list[dict]) -> list[dict]:
    cm = _build_client()
    if not cm:
        return []
    client, model = cm
    existing_summary = "\n".join(f"- {s.get('name', '?')}: {s.get('description', '')[:120]}" for s in existing_skills) if existing_skills else "None yet"
    prompt = (
        "From the following atomic memories, identify repeatable skills or techniques "
        "the user is developing. Deduplicate against existing skills. "
        "Return a JSON array of {name, description, proficiency (0.0-1.0)}. "
        "Be concise — one sentence per description.\n\n"
        f"EXISTING SKILLS:\n{existing_summary}\n\n"
        f"ATOMIC MEMORIES:\n{atoms_text}"
    )
    try:
        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
                temperature=0.3,
                response_format=_SKILL_SCHEMA,
            ),
            timeout=_TIMEOUT,
        )
        import json
        raw = resp.choices[0].message.content
        data = json.loads(raw) if raw else {}
        return data.get("skills", [])
    except Exception as e:
        logger.warning(f"Skill generation failed: {e}")
        return []

async def save_skills(supabase_client: Any, user_id: str, tenant_id: str, skills: list[dict]) -> int:
    saved = 0
    for sk in skills:
        try:
            existing = await supabase_client.table("user_skills").select("id, practice_count, proficiency").eq("user_id", user_id).eq("tenant_id", tenant_id).eq("name", sk["name"]).maybe_single().execute()
            if existing.data:
                new_count = existing.data["practice_count"] + 1
                new_prof = min(1.0, existing.data["proficiency"] + 0.05)
                await supabase_client.table("user_skills").update({
                    "proficiency": new_prof,
                    "practice_count": new_count,
                    "updated_at": "now()",
                }).eq("id", existing.data["id"]).execute()
            else:
                await supabase_client.table("user_skills").insert({
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "name": sk["name"],
                    "description": sk.get("description", ""),
                    "proficiency": sk.get("proficiency", 0.5),
                }).execute()
            saved += 1
        except Exception as e:
            logger.debug(f"Save skill '{sk.get('name')}' failed: {e}")
    return saved

async def get_skills(supabase_client: Any, user_id: str, tenant_id: str | None = None) -> list[dict]:
    try:
        query = supabase_client.table("user_skills").select("*").eq("user_id", user_id).order("proficiency", {"ascending": False})
        if tenant_id:
            query = query.eq("tenant_id", tenant_id)
        res = await query.execute()
        return res.data or []
    except Exception as e:
        logger.debug(f"get_skills miss: {e}")
        return [{"name": "Mindfulness", "description": "Basic awareness practice", "proficiency": 0.3, "practice_count": 0}]

if __name__ == "__main__":
    import asyncio, json
    async def _test():
        atoms = "- User expressed anxiety about job interview\n- Used three-question meditation technique\n- Felt calmer after practice"
        skills = await generate_skills(atoms, [])
        print(json.dumps(skills, indent=2))
    asyncio.run(_test())
