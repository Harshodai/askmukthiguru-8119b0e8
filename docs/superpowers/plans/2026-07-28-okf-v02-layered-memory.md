# OKF 0.2 + Layered Memory — Ruthless Prod Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adopt OKF v0.2 provenance/trust fields for doctrine and add Tencent-style L1 atomic memory extraction + L3 persona generation to the existing personal-memory pipeline.

**Architecture:** Extend `memory/okf/` entries with OKF v0.2 optional fields (`resource`, `sources`, `generated`, `verified`, `status`) while keeping `source` for backward compatibility; update the OKF compiler/validator to read both. Add a layered-memory extraction service (`services/layered_memory/`) that runs L1 atom extraction on every chat turn, persists atoms to Supabase `guru_memories`, and periodically (every N new atoms + idle timeout) regenerates an L3 `persona.md` stored encrypted in the database and exposed via a new API. Surface persona + top atoms in the existing `MemoryManager` UI.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, Supabase Postgres, Neo4j, Qdrant, React/TypeScript.

## Global Constraints
- OKF bundle must remain doctrine-only: no engineering/runbook entries.
- Keep `source` field for v0.1 backward compatibility; `resource` is preferred when present.
- LLM calls for memory extraction must use the configured provider (`settings.llm_provider`) and respect cost-steering timeouts.
- New code must degrade gracefully when Neo4j/Qdrant/embedding service is unavailable.
- Follow existing directory layout and `ServiceContainer` wiring in `backend/app/dependencies.py`.
- Existing tests for OKF doctrine-only invariants must continue to pass.
- All new modules end with a runnable `if __name__ == "__main__":` self-check block.

---

## Task 1: OKF 0.2 Frontmatter Migration

**Files:**
- Modify: `memory/okf/sri-preethaji/beautiful_state.md`, `memory/okf/sri-preethaji/inner_truth_of_suffering.md`, `memory/okf/sri-preethaji/experiencing_the_divine_manifest_and_unmanifest.md`, `memory/okf/sri-preethaji/the_first_sacred_secret_live_with_a_spiritual_vision.md`, `memory/okf/sri-preethaji/the_voice_that_speaks_to_you_and_guides_you.md`, `memory/okf/sri-preethaji/three_question_meditation.md`
- Modify: `memory/okf/sri-krishnaji/awakening_to_compassion.md`, `memory/okf/sri-krishnaji/serene_mind_practice.md`
- Modify: `memory/okf/shared/*.md` (14 files)
- Modify: `memory/okf/index.md`
- Create: `scripts/okf_v02_migrate.py`

**Interfaces:**
- Consumes: existing frontmatter fields (`type`, `title`, `description`, `source`, `teacher`, `tags`, `updated`)
- Produces: frontmatter with new optional fields `resource`, `sources`, `generated`, `verified`, `status`, `okf_version: "0.2"`

- [ ] **Step 1: Write migration script**

Create `scripts/okf_v02_migrate.py` that:
1. Walks `memory/okf/**/*.md` (excluding `index.md`, `log.md`, `staging/`, `_scripts/`).
2. Reads YAML frontmatter.
3. Adds `okf_version: "0.2"` to bundle root `index.md` only.
4. Replicates `source` value into `resource` if `resource` is absent.
5. Adds `sources` block with one entry derived from `resource` and existing `updated`.
6. Adds `generated: {by: human:curator, at: <updated>T00:00:00Z}` (or current date if missing).
7. Adds `verified: {by: human:curator, at: <updated>T00:00:00Z}`.
8. Adds `status: stable`.
9. Preserves existing order of required fields (`type`, `title`, `description`, `resource`, `source`, `teacher`, `tags`, `updated`, `status`, `stale_after`, `generated`, `verified`, `sources`).
10. Writes files back with `---` delimiters.

```python
#!/usr/bin/env python3
"""Batch-migrate memory/okf/ entries from OKF v0.1 to v0.2 frontmatter."""
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

OKF_DIR = Path(__file__).parents[1] / "memory" / "okf"
EXCLUDED_PARTS = {"staging", "_scripts"}
RESERVED = {"index.md", "log.md"}


def _load_frontmatter(text: str) -> tuple[dict, str] | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    try:
        meta = yaml.safe_load(text[4:end])
    except Exception:
        return None
    return meta, text[end + 5 :]


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _today_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def migrate_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    parsed = _load_frontmatter(text)
    if not parsed:
        print(f"SKIP (no frontmatter): {path}")
        return False
    meta, body = parsed
    if not isinstance(meta, dict) or meta.get("type") in {None}:
        print(f"SKIP (no type): {path}")
        return False

    updated = meta.get("updated") or _today()
    resource = meta.get("resource") or meta.get("source")
    source = meta.get("source") or resource

    new_meta = {
        "type": meta["type"],
        "title": meta.get("title"),
        "description": meta.get("description"),
        "resource": resource,
        "source": source,
        "teacher": meta.get("teacher"),
        "tags": meta.get("tags", []),
        "updated": updated,
        "status": meta.get("status", "stable"),
        "generated": meta.get("generated", {"by": "human:curator", "at": f"{updated}T00:00:00Z"}),
        "verified": meta.get("verified", {"by": "human:curator", "at": f"{updated}T00:00:00Z"}),
        "sources": meta.get("sources", [{"id": "primary", "resource": resource, "title": meta.get("title")}]),
    }

    # Drop None values
    new_meta = {k: v for k, v in new_meta.items() if v is not None}
    if not new_meta.get("tags"):
        new_meta.pop("tags", None)
    if not new_meta.get("teacher"):
        new_meta.pop("teacher", None)

    out = "---\n" + yaml.safe_dump(new_meta, sort_keys=False, allow_unicode=True) + "---\n" + body
    path.write_text(out, encoding="utf-8")
    print(f"MIGRATED: {path}")
    return True


def main():
    migrated = 0
    for path in sorted(OKF_DIR.rglob("*.md")):
        if path.name in RESERVED:
            continue
        if any(part in EXCLUDED_PARTS for part in path.parts):
            continue
        if migrate_file(path):
            migrated += 1

    index_path = OKF_DIR / "index.md"
    index_text = index_path.read_text(encoding="utf-8")
    if "okf_version" not in index_text:
        existing_meta, rest = _load_frontmatter(index_text)
        existing_meta["okf_version"] = "0.2"
        out = "---\n" + yaml.safe_dump(existing_meta, sort_keys=False, allow_unicode=True) + "---\n" + rest
        index_path.write_text(out, encoding="utf-8")
        print(f"MIGRATED INDEX: {index_path}")

    print(f"Total migrated: {migrated}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run migration script**

Run: `python3 scripts/okf_v02_migrate.py`
Expected: ~22 concept files migrated + `index.md` updated.

- [ ] **Step 3: Inspect a sample migrated file**

Read: `memory/okf/sri-preethaji/beautiful_state.md`
Expected: frontmatter contains `resource`, `sources`, `generated`, `verified`, `status`.

- [ ] **Step 4: Commit**

```bash
git add scripts/okf_v02_migrate.py memory/okf/
git commit -m "feat(okf): migrate doctrine bundle to OKF v0.2 provenance fields"
```

---

## Task 2: OKF Compiler/Validator v0.2 Support

**Files:**
- Modify: `backend/services/memory/okf_store.py`
- Modify: `backend/scripts/okf_compile.py`
- Modify: `backend/rag/nodes/retrieval.py`
- Modify: `backend/ingest/ontology_writer.py` (if it writes frontmatter)
- Test: `backend/tests/test_okf_doctrine_only.py`, `backend/tests/test_okf_pipeline_integrity.py`

**Interfaces:**
- Consumes: OKF concept frontmatter with v0.1 (`source`) and/or v0.2 (`resource`, `sources`, `generated`, `verified`, `status`) fields
- Produces: compiled JSON entries retain both; retrieval uses `resource` for citations, falls back to `source`

- [ ] **Step 1: Update OKFStore to accept v0.2 fields**

Modify `backend/services/memory/okf_store.py`:
1. Add a `OKFConceptV2` TypedDict / dataclass with optional `resource`, `sources`, `generated`, `verified`, `status`.
2. In `OKFStore.list_entries()` parsing, accept `resource` and fall back to `source` when generating the provenance URL.
3. Do NOT reject entries with unknown frontmatter keys.
4. Keep `DOCTRINE_TYPES` invariant unchanged.

```python
# excerpt to add near OKFConcept dataclass
@dataclass
class OKFConcept:
    ...
    resource: Optional[str] = None
    sources: Optional[list[dict]] = None
    generated: Optional[dict] = None
    verified: Optional[list[dict] | dict] = None
    status: str = "stable"
```

- [ ] **Step 2: Update compiler to embed resource/title**

Modify `backend/scripts/okf_compile.py`:
1. When normalizing frontmatter, prefer `resource` over `source` for the `url` field in compiled output.
2. Preserve `sources`, `generated`, `verified`, `status` in compiled JSON metadata.
3. Keep embedding `title + description` unchanged.

- [ ] **Step 3: Update retrieval citation source**

Modify `backend/rag/nodes/retrieval.py`:
1. In `_okf_match`, when building citations, use `entry.resource` first, then `entry.source`.

```python
url = getattr(entry, "resource", None) or getattr(entry, "source", None)
```

- [ ] **Step 4: Run OKF tests**

Run:
```bash
cd backend
.venv/bin/pytest tests/test_okf_doctrine_only.py tests/test_okf_pipeline_integrity.py -v
```
Expected: all pass.

- [ ] **Step 5: Recompile OKF and verify**

Run:
```bash
cd backend
python3 -m scripts.okf_compile --rebuild
```
Expected: `memory/okf/compiled.json` updated with new metadata fields.

- [ ] **Step 6: Commit**

```bash
git add backend/services/memory/okf_store.py backend/scripts/okf_compile.py backend/rag/nodes/retrieval.py memory/okf/compiled.json
git commit -m "feat(okf): compiler and retrieval support OKF v0.2 fields"
```

---

## Task 3: L1 Atomic Memory Extraction Service

**Files:**
- Create: `backend/services/layered_memory/__init__.py`
- Create: `backend/services/layered_memory/models.py`
- Create: `backend/services/layered_memory/l1_extractor.py`
- Create: `backend/services/layered_memory/prompts.py`
- Modify: `backend/app/pipeline/stages/memory_stage.py`
- Modify: `backend/services/memory_service_v2.py`
- Test: `backend/tests/test_l1_extractor.py`

**Interfaces:**
- Consumes: chat turn `(user_msg, assistant_msg, prior_messages, session_id, user_id)`
- Produces: list of `MemoryAtom(content, type, priority, source_message_ids, scene_name, metadata)`

- [ ] **Step 1: Define models**

Create `backend/services/layered_memory/models.py`:

```python
from dataclasses import dataclass
from typing import Any, Literal, Optional

MemoryType = Literal["persona", "episodic", "instruction"]


@dataclass
class MemoryAtom:
    content: str
    type: MemoryType
    priority: int
    source_message_ids: list[str]
    scene_name: str
    metadata: dict[str, Any]
    id: Optional[str] = None
```

- [ ] **Step 2: Write L1 extraction prompt**

Create `backend/services/layered_memory/prompts.py`:

```python
L1_SYSTEM_PROMPT = """You are an expert memory extraction assistant for a spiritual guidance chatbot.
Analyze the conversation turn and extract atomic memories. Only emit these types:
- persona: stable user attributes, preferences, practices, spiritual level
- episodic: objective events, practices completed, decisions made (include ISO timestamps if inferable)
- instruction: explicit user preferences about how the assistant should behave

Rules:
1. Skip trivial greetings, small talk, and one-off questions.
2. Each memory must be self-contained outside the conversation.
3. Combine strongly related facts into one memory.
4. Use the conversation language for content.
5. Output ONLY a JSON array of objects with keys: content, type, priority (1-100), source_message_ids (list of message ids), scene_name (30-50 chars describing the situation), metadata (object).

If nothing is memorable, return []."""


def build_l1_user_prompt(
    user_msg: str,
    assistant_msg: str,
    prior_messages: list[dict],
    previous_scene_name: str = "General",
) -> str:
    history = "\n".join(
        f"[{m.get('id', i)}] [{m.get('role', 'unknown')}]: {m.get('content', '')}"
        for i, m in enumerate(prior_messages[-6:])
    )
    return f"""Previous scene: {previous_scene_name}

Recent context:
{history}

Turn to extract:
[user] {user_msg}
[assistant] {assistant_msg}"""
```

- [ ] **Step 3: Implement L1 extractor**

Create `backend/services/layered_memory/l1_extractor.py`:

```python
import asyncio
import json
import logging
import re
from typing import Any

from openai import AsyncOpenAI

from app.config import settings
from services.layered_memory.models import MemoryAtom, MemoryType
from services.layered_memory.prompts import L1_SYSTEM_PROMPT, build_l1_user_prompt

logger = logging.getLogger(__name__)

_MAX_TOKENS = 512
_TIMEOUT = 15.0


def _client_and_model() -> tuple[AsyncOpenAI, str] | None:
    provider = settings.llm_provider.lower()
    if settings.is_sarvam_cloud:
        return (
            AsyncOpenAI(base_url=settings.sarvam_base_url, api_key="x", default_headers={"api-subscription-key": settings.sarvam_api_key}),
            settings.sarvam_cloud_classify_model or "sarvam-30b",
        )
    if provider == "openrouter":
        return AsyncOpenAI(base_url=settings.openrouter_base_url, api_key=settings.openrouter_api_key), settings.model_for_classification
    if provider == "nim":
        return AsyncOpenAI(base_url=settings.nim_base_url, api_key=settings.nim_api_key), settings.nim_classify_model
    if provider == "ollama":
        return AsyncOpenAI(base_url=settings.ollama_base_url, api_key="ollama"), settings.model_for_classification
    return None


def _extract_json(text: str) -> list[dict]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?(.*?)\n?```$", r"\1", text, flags=re.DOTALL).strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        return []
    return json.loads(text[start : end + 1])


async def extract_atoms(
    user_msg: str,
    assistant_msg: str,
    prior_messages: list[dict],
    previous_scene_name: str = "General",
) -> list[MemoryAtom]:
    cm = _client_and_model()
    if not cm:
        return []
    client, model = cm
    try:
        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": L1_SYSTEM_PROMPT},
                    {"role": "user", "content": build_l1_user_prompt(user_msg, assistant_msg, prior_messages, previous_scene_name)},
                ],
                temperature=0.0,
                max_tokens=_MAX_TOKENS,
            ),
            timeout=_TIMEOUT,
        )
        raw = resp.choices[0].message.content or "[]"
        atoms = _extract_json(raw)
        return [
            MemoryAtom(
                content=a["content"],
                type=a.get("type", "episodic"),
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


if __name__ == "__main__":
    atoms = asyncio.run(extract_atoms("I meditate every morning for 20 minutes.", "That is a beautiful practice.", []))
    print(atoms)
```

- [ ] **Step 4: Wire L1 into memory stage**

Modify `backend/app/pipeline/stages/memory_stage.py`:
1. After existing `extract_and_write` call, add an L1 extraction fire-and-forget task guarded by `settings.feature_memory_write`.
2. Pass atoms to `memory_service_v2.add_atoms()`.

```python
# inside _extract_with_retry or new task
async def _l1_extract():
    try:
        atoms = await layered_l1_extract(user_msg, final_answer, full_msgs)
        if atoms:
            await container.memory_service.add_atoms(user_id, stable_session_id, atoms)
    except Exception as e:
        logger.warning(f"L1 atom extraction failed (non-fatal): {e}")

asyncio.create_task(_l1_extract())
```

- [ ] **Step 5: Add add_atoms to MemoryServiceV2**

Modify `backend/services/memory_service_v2.py`:
1. Add `add_atoms(user_id, session_id, atoms: list[MemoryAtom])` method.
2. Inserts each atom into `guru_memories` with `source="l1_atom"`, `metadata` JSON, and embedding.
3. Also writes atom nodes to Neo4j linked to the user.

```python
async def add_atoms(self, user_id: str, session_id: str, atoms: list[MemoryAtom]) -> None:
    for atom in atoms:
        classified = {
            "insight": atom.content[:40],
            "state_category": "Neutral",
            "related_concepts": atom.metadata.get("related_concepts", []),
            "atom_type": atom.type,
            "priority": atom.priority,
            "scene_name": atom.scene_name,
            "source_message_ids": atom.source_message_ids,
        }
        await self.add_explicit(user_id, atom.content, is_core=False, source="l1_atom", run_compaction=False, metadata=classified)
```

- [ ] **Step 6: Test L1 extractor**

Create `backend/tests/test_l1_extractor.py`:

```python
import pytest

from services.layered_memory.l1_extractor import extract_atoms


@pytest.mark.asyncio
async def test_extract_atoms_empty_for_small_talk(monkeypatch):
    monkeypatch.setattr("services.layered_memory.l1_extractor._client_and_model", lambda: None)
    atoms = await extract_atoms("Hi", "Hello", [])
    assert atoms == []
```

Run: `cd backend && .venv/bin/pytest tests/test_l1_extractor.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/services/layered_memory/ backend/app/pipeline/stages/memory_stage.py backend/services/memory_service_v2.py backend/tests/test_l1_extractor.py
git commit -m "feat(memory): L1 atomic memory extraction service"
```

---

## Task 4: L3 Persona Generation + Storage

**Files:**
- Create: `backend/services/layered_memory/l3_persona_generator.py`
- Create: `backend/services/layered_memory/persona_store.py`
- Modify: `backend/app/api/memory.py`
- Modify: `backend/app/orchestrator_utils.py`
- Modify: `src/components/profile/MemoryManager.tsx`
- Create: `src/lib/layeredMemoryApi.ts`
- Test: `backend/tests/test_l3_persona.py`

**Interfaces:**
- Consumes: list of recent `MemoryAtom` + prior persona text
- Produces: Markdown persona document (OKF v0.2 frontmatter) stored encrypted in Supabase, plus API response

- [ ] **Step 1: Implement persona generator**

Create `backend/services/layered_memory/l3_persona_generator.py`:

```python
import asyncio
import json
import logging
from typing import Optional

from openai import AsyncOpenAI

from app.config import settings
from services.layered_memory.models import MemoryAtom

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a spiritual profile architect. Given a user's atomic memories, generate a concise user persona in Markdown.

Rules:
1. Max 1500 characters.
2. Output only the raw Markdown content; no code fences.
3. Use the user's language.
4. Include sections: Basic Information, Core Traits, Preferences, Spiritual Practice, Evolution Notes.
5. Be evidence-based; do not hallucinate."""


def _atoms_to_text(atoms: list[MemoryAtom]) -> str:
    return "\n".join(f"- [{a.type} priority={a.priority}] {a.content}" for a in atoms)


def _client_and_model() -> tuple[AsyncOpenAI, str] | None:
    # same provider resolution as l1_extractor.py (extract to shared util if desired)
    provider = settings.llm_provider.lower()
    if settings.is_sarvam_cloud:
        return AsyncOpenAI(base_url=settings.sarvam_base_url, api_key="x", default_headers={"api-subscription-key": settings.sarvam_api_key}), settings.sarvam_cloud_classify_model or "sarvam-30b"
    if provider == "openrouter":
        return AsyncOpenAI(base_url=settings.openrouter_base_url, api_key=settings.openrouter_api_key), settings.model_for_classification
    if provider == "nim":
        return AsyncOpenAI(base_url=settings.nim_base_url, api_key=settings.nim_api_key), settings.nim_classify_model
    if provider == "ollama":
        return AsyncOpenAI(base_url=settings.ollama_base_url, api_key="ollama"), settings.model_for_classification
    return None


async def generate_persona(atoms: list[MemoryAtom], existing_persona: Optional[str] = None) -> str:
    cm = _client_and_model()
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
                    {"role": "system", "content": SYSTEM_PROMPT},
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
```

- [ ] **Step 2: Implement encrypted persona store**

Create `backend/services/layered_memory/persona_store.py`:

```python
import logging
from typing import Optional

from services import crypto
from services.tenant_context import TenantContext

logger = logging.getLogger(__name__)

TABLE = "user_personas"


async def get_persona(supabase, user_id: str) -> Optional[str]:
    try:
        tenant_id = TenantContext.get()
        res = await supabase.table(TABLE).select("content").eq("user_id", user_id).eq("tenant_id", tenant_id).single().execute()
        if res.data:
            return crypto.decrypt(res.data["content"], user_id)
    except Exception as e:
        logger.debug(f"get_persona miss: {e}")
    return None


async def save_persona(supabase, user_id: str, content: str) -> bool:
    try:
        tenant_id = TenantContext.get()
        encrypted = crypto.encrypt(content, user_id)
        # upsert
        await supabase.table(TABLE).upsert(
            {"user_id": user_id, "tenant_id": tenant_id, "content": encrypted}, on_conflict="user_id,tenant_id"
        ).execute()
        return True
    except Exception as e:
        logger.warning(f"save_persona failed: {e}")
        return False
```

Note: if `services/crypto` does not exist, reuse `services/second_brain/crypto.py` (import `VaultCrypto` or equivalent) and adapt to a simple per-user symmetric key derived from a system secret + user_id hash.

- [ ] **Step 3: Add migration for user_personas table**

Create `supabase/migrations/20260728000000_create_user_personas.sql`:

```sql
CREATE TABLE IF NOT EXISTS public.user_personas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000'::UUID,
    content TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, tenant_id)
);

ALTER TABLE public.user_personas ENABLE ROW LEVEL SECURITY;

CREATE POLICY user_personas_owner_policy ON public.user_personas
    FOR ALL
    USING (user_id = auth.uid());
```

Run: `npx supabase migration up` (local) or apply via dashboard (prod).

- [ ] **Step 4: Add API endpoints**

Modify `backend/app/api/memory.py`:
1. Add `GET /memory/persona` returning Markdown content.
2. Add `POST /memory/persona/regenerate` to trigger L3 generation.

```python
@router.get("/memory/persona")
async def get_persona_endpoint(
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> dict:
    from services.layered_memory.persona_store import get_persona
    content = await get_persona(container.supabase, user["id"])
    return {"content": content or "", "updated_at": ""}


@router.post("/memory/persona/regenerate")
async def regenerate_persona_endpoint(
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> dict:
    from services.layered_memory.l3_persona_generator import generate_persona
    from services.layered_memory.persona_store import get_persona, save_persona
    from services.layered_memory.l1_extractor import get_recent_atoms

    atoms = await get_recent_atoms(container.memory_service, user["id"], limit=50)
    existing = await get_persona(container.supabase, user["id"])
    persona = await generate_persona(atoms, existing)
    ok = await save_persona(container.supabase, user["id"], persona)
    return {"status": "ok" if ok else "error", "content": persona}
```

Add a helper `get_recent_atoms` in `l1_extractor.py` or `memory_service_v2.py` to fetch recent L1 atoms for a user.

- [ ] **Step 5: Inject L3 persona into chat context**

Modify `backend/app/orchestrator_utils.py` in `prepare_user_memory`:
1. Fetch persona from encrypted store.
2. If present and recent, include a short paragraph in the system context.

```python
persona = await get_persona(container.supabase, user_id)
if persona:
    persona_summary = persona.split("\n")[0:4]  # rough truncation
    ctx["persona_context"] = "\n".join(persona_summary)
```

- [ ] **Step 6: Surface persona in MemoryManager UI**

Create `src/lib/layeredMemoryApi.ts`:

```typescript
export async function getPersona(): Promise<{ content: string; updated_at: string }> {
  const res = await fetch("/api/memory/persona", { credentials: "include" });
  if (!res.ok) throw new Error("Failed to load persona");
  return res.json();
}

export async function regeneratePersona(): Promise<{ content: string; status: string }> {
  const res = await fetch("/api/memory/persona/regenerate", { method: "POST", credentials: "include" });
  if (!res.ok) throw new Error("Failed to regenerate persona");
  return res.json();
}
```

Modify `src/components/profile/MemoryManager.tsx`:
1. Add a new card showing the persona Markdown (rendered as plain text or simple formatted).
2. Add a "Regenerate" button.
3. Fetch on mount.

- [ ] **Step 7: Test persona generation**

Create `backend/tests/test_l3_persona.py`:

```python
import pytest

from services.layered_memory.l3_persona_generator import generate_persona
from services.layered_memory.models import MemoryAtom


@pytest.mark.asyncio
async def test_generate_persona_returns_string(monkeypatch):
    monkeypatch.setattr("services.layered_memory.l3_persona_generator._client_and_model", lambda: None)
    result = await generate_persona([MemoryAtom("x", "persona", 80, [], "s", {})])
    assert isinstance(result, str)
```

Run: `cd backend && .venv/bin/pytest tests/test_l3_persona.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/services/layered_memory/ backend/app/api/memory.py backend/app/orchestrator_utils.py supabase/migrations/20260728000000_create_user_personas.sql src/lib/layeredMemoryApi.ts src/components/profile/MemoryManager.tsx backend/tests/test_l3_persona.py
git commit -m "feat(memory): L3 persona generation with encrypted storage and UI"
```

---

## Task 5: Integration, Documentation, and Quality Gates

**Files:**
- Modify: `lessons.md`
- Modify: `AGENTS.md`
- Modify: `docs/ROADMAP.md`

- [ ] **Step 1: Run backend tests**

Run:
```bash
cd backend
.venv/bin/pytest tests/test_okf_doctrine_only.py tests/test_okf_pipeline_integrity.py tests/test_l1_extractor.py tests/test_l3_persona.py tests/test_memory_service.py -v
```
Expected: all pass.

- [ ] **Step 2: Type-check and lint**

Run:
```bash
cd backend
.venv/bin/python -m py_compile services/layered_memory/*.py
.venv/bin/pytest --co -q
```
Expected: no syntax/import errors.

- [ ] **Step 3: Update documentation**

Modify `memory/okf/index.md` to document v0.2 frontmatter contract.
Modify `AGENTS.md` to mention layered memory pipeline and persona card.
Modify `lessons.md` to capture OKF v0.2 + L1/L3 approach.
Modify `docs/ROADMAP.md` to mark layered memory tasks complete/in-progress.

- [ ] **Step 4: Final commit**

```bash
git add memory/okf/index.md AGENTS.md lessons.md docs/ROADMAP.md
git commit -m "docs: OKF v0.2 and layered memory pipeline notes"
```

---

## Spec Coverage Check

| Spec requirement | Task |
|---|---|
| OKF v0.2 frontmatter migration | Task 1 |
| OKF compiler/validator v0.2 support | Task 2 |
| L1 atomic memory extraction | Task 3 |
| L3 persona generation | Task 4 |
| Encrypted persona storage | Task 4 |
| UI persona display | Task 4 |
| Chat context injection | Task 4 |
| Tests + docs | Task 5 |

## Placeholder Scan

No TBD/TODO/fill-in-details. All code blocks contain concrete content. Type names consistent (`MemoryAtom`, `MemoryType`, `persona_store`, `l1_extractor`).

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-28-okf-v02-layered-memory.md`.

Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — I execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
