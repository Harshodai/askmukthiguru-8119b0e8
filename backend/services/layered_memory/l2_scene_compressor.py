from __future__ import annotations

import asyncio
import logging
from typing import Any

from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

_MAX_SCENES_PER_SESSION = 15
_TIMEOUT = 15.0


class SceneBlock(BaseModel):
    intent: str
    emotional_state: str
    key_insight: str
    decision: str | None = None
    turn_count: int = 1


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


async def compress_turns_to_scene(
    turns: list[dict[str, Any]],
) -> SceneBlock | None:
    cm = _build_client()
    if not cm:
        return None
    client, model = cm
    prompt = _build_compression_prompt(turns)
    try:
        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=512,
                temperature=0.3,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "scene_block",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "intent": {"type": "string"},
                                "emotional_state": {"type": "string"},
                                "key_insight": {"type": "string"},
                                "decision": {"type": ["string", "null"]},
                            },
                            "required": ["intent", "emotional_state", "key_insight"],
                            "additionalProperties": False,
                        },
                    },
                },
            ),
            timeout=_TIMEOUT,
        )
        import json

        raw = resp.choices[0].message.content
        data = json.loads(raw) if raw else {}
        return SceneBlock(**data, turn_count=len(turns))
    except Exception as e:
        logger.warning(f"L2 scene compression failed: {e}")
        return None


async def get_scene_blocks(
    supabase_client: Any, user_id: str, tenant_id: str | None = None
) -> list[SceneBlock]:
    try:
        query = (
            supabase_client.table("user_scene_blocks")
            .select("compressed_blocks, turn_count")
            .eq("user_id", user_id)
            .order("created_at", {"ascending": False})
            .limit(_MAX_SCENES_PER_SESSION)
        )
        if tenant_id:
            query = query.eq("tenant_id", tenant_id)
        res = await query.execute()
        if not res.data:
            return []
        from .persona_store import decrypt

        blocks = []
        for row in res.data:
            try:
                plain = decrypt(row["compressed_blocks"], user_id)
                parsed = SceneBlock.model_validate_json(plain)
                parsed.turn_count = row.get("turn_count", 1)
                blocks.append(parsed)
            except Exception:
                continue
        return blocks
    except Exception as e:
        logger.debug(f"get_scene_blocks miss: {e}")
        return []


async def save_scene_block(
    supabase_client: Any,
    user_id: str,
    tenant_id: str,
    session_id: str | None,
    block: SceneBlock,
) -> bool:
    try:
        from .persona_store import encrypt

        encrypted = encrypt(block.model_dump_json(), user_id)
        existing = (
            await supabase_client.table("user_scene_blocks")
            .select("id, turn_count")
            .eq("user_id", user_id)
            .eq("session_id", session_id)
            .order("created_at", {"ascending": False})
            .limit(1)
            .maybe_single()
            .execute()
        )
        if existing.data:
            await (
                supabase_client.table("user_scene_blocks")
                .update(
                    {
                        "compressed_blocks": encrypted,
                        "turn_count": existing.data["turn_count"] + block.turn_count,
                        "scene_type": block.intent[:64],
                        "ended_at": "now()",
                    }
                )
                .eq("id", existing.data["id"])
                .execute()
            )
        else:
            await (
                supabase_client.table("user_scene_blocks")
                .insert(
                    {
                        "user_id": user_id,
                        "tenant_id": tenant_id,
                        "session_id": session_id,
                        "compressed_blocks": encrypted,
                        "turn_count": block.turn_count,
                        "scene_type": block.intent[:64],
                    }
                )
                .execute()
            )
        _enforce_max_scenes(supabase_client, user_id, tenant_id)
        return True
    except Exception as e:
        logger.warning(f"save_scene_block failed: {e}")
        return False


async def _enforce_max_scenes(supabase_client: Any, user_id: str, tenant_id: str) -> None:
    try:
        res = (
            await supabase_client.table("user_scene_blocks")
            .select("id")
            .eq("user_id", user_id)
            .eq("tenant_id", tenant_id)
            .order("created_at", {"ascending": False})
            .execute()
        )
        if res.data and len(res.data) > _MAX_SCENES_PER_SESSION:
            excess_ids = [r["id"] for r in res.data[_MAX_SCENES_PER_SESSION:]]
            for eid in excess_ids:
                await supabase_client.table("user_scene_blocks").delete().eq("id", eid).execute()
    except Exception as _e:
        logger.debug("[l2 compressor] suppressed non-critical error: %s", _e)


def _build_compression_prompt(turns: list[dict[str, Any]]) -> str:
    lines = []
    for t in turns:
        lines.append(f"[{t.get('role', 'user')}]: {t.get('content', '')}")
    dialog = "\n".join(lines)
    return (
        "You are a session analyzer. Compress the following conversation turns into a structured scene block.\n"
        "Respond in JSON with: intent, emotional_state, key_insight, decision (or null).\n"
        "Be concise — one sentence per field.\n\n"
        f"TURNS:\n{dialog}"
    )


if __name__ == "__main__":
    import asyncio
    import json

    async def _test():
        turns = [
            {"role": "user", "content": "I feel anxious about my job interview tomorrow."},
            {
                "role": "assistant",
                "content": "That's natural. Try the three-question meditation: What am I grateful for? What is my intention? What is my True Self?",
            },
            {"role": "user", "content": "That helped. I'll practice tonight."},
        ]
        block = await compress_turns_to_scene(turns)
        if block:
            print(json.dumps(block.model_dump(), indent=2))
        else:
            print("Compression returned None (expected if no LLM available)")

    asyncio.run(_test())
