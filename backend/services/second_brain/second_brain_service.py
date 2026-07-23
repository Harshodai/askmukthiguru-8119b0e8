"""
Mukthi Vault — Second Brain service (per-user, owner-blind knowledge graph).

Responsibilities
----------------
1. Provision + manage each user's vault key (DEK), in Mode A or Mode B.
2. Extract personal-knowledge artifacts from conversations (async, LLM).
3. Store them encrypted (AES-256-GCM) in Postgres; embeddings in the shared
   Second-Brain Qdrant collection (vault_index.py), filtered by user_id.
4. Retrieve them at query time, decrypt in memory only, and hand a bounded
   "personal context" block to the generation layer.
5. Honor erasure: per-item forget, full crypto-shredding (drop the DEK),
   and export (GDPR/DSAR) — export happens only in the owner's session.

Non-goals (enforced by design)
------------------------------
* No admin/operator read path. There is deliberately NO service method that
  takes a user_id and returns plaintext without that user's vault being
  unlocked in the same call. Support tooling gets ciphertext + metadata.
* No cross-user reads. Every query is scoped by user_id AND, in Mode B, is
  impossible without the user's passphrase.

Integration points (this codebase)
-----------------------------------
* `embedding_service`: services.embedding_service.EmbeddingService — uses
  its `encode_single_async(text)` method (not `.embed()` — that method
  doesn't exist on this service).
* `supabase_client`: the ServiceContainer's `self.supabase_client`
  (app.dependencies.get_container()), not a module-level `app.db.get_supabase`
  (no such module exists in this codebase).
* `qdrant_client`: a `vault_index.VaultIndex` instance (duck-typed: upsert /
  search / delete_item / delete_all), NOT the raw qdrant_client.QdrantClient
  and NOT services.qdrant_service.QdrantService (that facade is single-
  collection-per-process and has no per-name ensure_collection/upsert/search
  shape). Optional — personal_context() degrades to recency/confidence
  ordering when embedding_service/qdrant_client are falsy.
* `llm_service`: any services.llm.base.LLMProvider implementation (e.g. the
  container's `self.ollama`) — uses its `generate(system_prompt, user_prompt,
  **kwargs)` method (not `.complete()` — that method doesn't exist here).
* Called from `rag/nodes/generation.py` (context injection) and from the
  chat pipeline's post-response hook (memory write), same seam where
  `MemoryService.extract_and_write` is invoked today
  (app/pipeline/stages/memory_stage.py).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from app.config import settings

try:  # package import (services.second_brain)
    from .crypto import (
        UnlockedVault,
        VaultError,
        VaultIntegrityError,
        VaultLockedError,
        blind_index,
        decrypt_payload,
        derive_kek_from_passphrase,
        derive_server_kek,
        encrypt_payload,
        generate_dek,
        unwrap_dek,
        wrap_dek,
    )
except ImportError:  # standalone / test context
    from crypto import (  # type: ignore
        UnlockedVault,
        VaultError,
        VaultIntegrityError,
        VaultLockedError,
        blind_index,
        decrypt_payload,
        derive_kek_from_passphrase,
        derive_server_kek,
        encrypt_payload,
        generate_dek,
        unwrap_dek,
        wrap_dek,
    )

logger = logging.getLogger("second_brain")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_MODE_A = "server_wrapped"
_MODE_B = "session_unlock"

_MAX_CONTEXT_ITEMS = 8          # cap personal context injected into prompts
_MAX_TEXT_LEN = 8_000           # per-artifact plaintext cap (chars)
_DEFAULT_WRAP_MODE = _MODE_A


def _aad(user_id: str, kind: str, item_id: str) -> bytes:
    return f"{user_id}:{kind}:{item_id}".encode()


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

@dataclass
class BrainItem:
    id: str
    user_id: str
    kind: str            # reflection | entity | journal | preference | relationship
    text: str
    confidence: float
    created_at: float
    access_count: int = 0


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class SecondBrainService:
    def __init__(
        self,
        supabase_client=None,
        embedding_service=None,
        llm_service=None,
        qdrant_client=None,
    ) -> None:
        self._db = supabase_client
        self._embed = embedding_service
        self._llm = llm_service
        self._qdrant = qdrant_client  # a vault_index.VaultIndex, or None
        self._server_kek: Optional[bytes] = None
        env_kek = os.getenv("BRAIN_KEK", "") or os.getenv("brain_kek", "") or getattr(settings, "brain_kek", None)
        if env_kek:
            self._server_kek = derive_server_kek(env_kek)

    # ------------------------------------------------------------------
    # Key management
    # ------------------------------------------------------------------

    async def provision_vault(self, user_id: str) -> dict:
        """Idempotently create the user's vault key row (Mode A default)."""
        existing = await self._get_key_row(user_id)
        if existing:
            return {"user_id": user_id, "wrap_mode": existing["wrap_mode"], "created": False}
        if not self._server_kek:
            raise VaultError("BRAIN_KEK not configured; cannot provision Mode-A vault")
        dek = generate_dek()
        row = {
            "user_id": user_id,
            "wrapped_dek": wrap_dek(dek, self._server_kek),
            "wrap_mode": _MODE_A,
            "kdf": None,
            "version": 1,
        }
        try:
            await asyncio.to_thread(self._db.table("user_brain_keys").upsert(row).execute)
        except Exception:
            existing = await self._get_key_row(user_id)
            if existing:
                return {"user_id": user_id, "wrap_mode": existing["wrap_mode"], "created": False}
            raise
        self._audit(user_id, "vault_provisioned", {"wrap_mode": _MODE_A})
        return {"user_id": user_id, "wrap_mode": _MODE_A, "created": True}

    async def enable_session_unlock(self, user_id: str, passphrase: str) -> dict:
        """Upgrade a vault to Mode B (owner-blind).

        Re-wraps the existing DEK (or a new one) under an Argon2id KEK derived
        from the user's passphrase. After this call the server can no longer
        decrypt the brain on its own.
        """
        dek = await self._load_dek_mode_a(user_id) if await self._get_key_row(user_id) else generate_dek()
        salt = os.urandom(16)
        kdf = {"algo": "argon2id", "salt": salt.hex(), "time": 3, "mem_kib": 65536, "par": 2}
        kek = self._mode_b_kek(passphrase, kdf)
        row = {
            "user_id": user_id,
            "wrapped_dek": wrap_dek(dek, kek),
            "wrap_mode": _MODE_B,
            "kdf": kdf,
            "version": 2,
        }
        await asyncio.to_thread(self._db.table("user_brain_keys").upsert(row).execute)
        self._audit(user_id, "vault_upgraded_session_unlock", {})
        return {"user_id": user_id, "wrap_mode": _MODE_B}

    async def unlock(self, user_id: str, *, passphrase: Optional[str] = None) -> UnlockedVault:
        """Return a request-scoped unlocked vault for this user.

        Mode A: unwraps with the server KEK (passphrase ignored).
        Mode B: requires the passphrase; wrong passphrase → VaultLockedError.
        """
        key_row = await self._get_key_row(user_id)
        if not key_row:
            if not passphrase:
                await self.provision_vault(user_id)
                key_row = await self._get_key_row(user_id)
            else:
                raise VaultLockedError("Vault not provisioned")

        if key_row["wrap_mode"] == _MODE_A:
            if not self._server_kek:
                raise VaultLockedError("Server KEK unavailable")
            dek = unwrap_dek(key_row["wrapped_dek"], self._server_kek)
        else:
            if not passphrase:
                raise VaultLockedError("Passphrase required for session-unlock vault")
            try:
                kek = self._mode_b_kek(passphrase, key_row["kdf"])
                dek = unwrap_dek(key_row["wrapped_dek"], kek)
            except VaultIntegrityError as exc:
                self._audit(user_id, "vault_unlock_failed", {})
                raise VaultLockedError("Wrong passphrase") from exc

        self._audit(user_id, "vault_unlocked", {"wrap_mode": key_row["wrap_mode"]})
        return UnlockedVault.from_dek(dek)

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

    async def add_item(
        self,
        user_id: str,
        kind: str,
        text: str,
        *,
        vault: UnlockedVault,
        confidence: float = 0.8,
        embed: bool = True,
    ) -> str:
        """Encrypt + store one artifact; index its embedding in the shared
        vault collection (user_id-filtered). Returns the item id."""
        text = text.strip()[:_MAX_TEXT_LEN]
        if not text:
            raise ValueError("empty text")
        item_id = uuid.uuid4().hex
        aad = _aad(user_id, kind, item_id)
        blob = encrypt_payload(vault.dek, text.encode(), aad=aad)
        row = {
            "id": item_id,
            "user_id": user_id,
            "kind": kind,
            "ciphertext": blob,
            "blind": blind_index(vault.dek, text[:64]),
            "confidence": float(confidence),
            "updated_at": time.time(),
            "access_count": 0,
            "decay": 1.0,
        }
        await asyncio.to_thread(self._db.table("user_brain_nodes").insert(row).execute)
        if embed and self._embed and self._qdrant:
            await self._index_embedding(user_id, item_id, kind, text)
        return item_id

    async def add_edge(
        self,
        user_id: str,
        src_id: str,
        dst_id: str,
        relation: str,
        *,
        vault: UnlockedVault,
        weight: float = 1.0,
    ) -> str:
        """Store an encrypted relationship between two of the user's nodes."""
        edge_id = uuid.uuid4().hex
        blob = encrypt_payload(vault.dek, relation.encode(), aad=_aad(user_id, "edge", edge_id))
        row = {
            "id": edge_id,
            "user_id": user_id,
            "src": src_id,
            "dst": dst_id,
            "rel_cipher": blob,
            "weight": float(weight),
        }
        await asyncio.to_thread(self._db.table("user_brain_edges").insert(row).execute)
        return edge_id

    # ------------------------------------------------------------------
    # Extraction (async, called post-response from the chat pipeline)
    # ------------------------------------------------------------------

    async def extract_and_write(self, user_id: str, message: str, response: str, *, vault: UnlockedVault) -> int:
        """LLM-driven extraction of durable personal knowledge from one turn.

        Writes only items that clear a confidence bar. Returns count written.
        Runs inside the post-response hook — must never raise into the user
        path; failures are logged and swallowed by the caller.
        """
        if not self._llm:
            return 0
        system_prompt = (
            "You maintain a private, per-user personal knowledge graph for a spiritual "
            "guidance app. From a single conversation turn, extract ONLY durable, "
            "user-specific facts worth remembering long-term: life situations, goals, "
            "struggles, relationships, practices they follow, preferences, milestones. "
            "Do NOT store generic spiritual teachings, do NOT store ephemeral small talk, "
            "do NOT store anything the user would reasonably expect to be forgotten.\n\n"
            'Return strict JSON: {"items":[{"kind":"reflection|entity|preference|relationship|journal",'
            '"text":"<one sentence, third person>", "confidence":0.0-1.0}]}\n'
            'At most 5 items. If nothing is durable, return {"items":[]}. '
            "Return ONLY the JSON object, nothing else."
        )
        user_prompt = f"USER MESSAGE:\n{message[:2000]}\n\nASSISTANT RESPONSE:\n{response[:2000]}"
        try:
            # ponytail: this repo's LLMProvider contract is generate(system_prompt,
            # user_prompt, **kwargs) (services/llm/base.py) — not the pack's .complete().
            raw = await self._llm.generate(system_prompt, user_prompt, temperature=0.1, max_tokens=600)
            items = json.loads(_strip_code_fence(raw)).get("items", [])
        except Exception as exc:  # never break the chat path
            logger.warning("second-brain extraction failed: %s", exc)
            return 0

        written = 0
        for it in items[:5]:
            try:
                if float(it.get("confidence", 0)) < 0.6:
                    continue
                kind = str(it.get("kind", "reflection"))
                if kind not in {"reflection", "entity", "preference", "relationship", "journal"}:
                    kind = "reflection"
                await self.add_item(user_id, kind, str(it["text"]), vault=vault,
                                    confidence=float(it["confidence"]))
                written += 1
            except Exception as exc:
                logger.warning("second-brain write skipped: %s", exc)
        return written

    # ------------------------------------------------------------------
    # Read path
    # ------------------------------------------------------------------

    async def personal_context(self, user_id: str, query: str, *, vault: UnlockedVault,
                               limit: int = _MAX_CONTEXT_ITEMS) -> list[BrainItem]:
        """Semantic recall over the user's OWN brain. Returns decrypted items,
        most relevant first. This is the only read that feeds generation."""
        candidate_ids: list[str] = []
        candidate_scores: dict[str, float] = {}
        if self._embed and self._qdrant and query.strip():
            candidate_ids = await self._search_embedding(user_id, query, limit=limit * 2)
            for rank, cid in enumerate(candidate_ids):
                candidate_scores[cid] = 1.0 / (rank + 1)
        rows = await self._fetch_nodes(user_id, ids=candidate_ids or None, limit=limit * 2)
        items: list[BrainItem] = []
        for r in rows:
            try:
                text = decrypt_payload(vault.dek, r["ciphertext"], aad=_aad(user_id, r["kind"], r["id"])).decode()
            except VaultIntegrityError:
                continue
            items.append(BrainItem(
                id=r["id"], user_id=user_id, kind=r["kind"], text=text,
                confidence=float(r.get("confidence", 0.8)),
                created_at=float(r.get("created_at", 0)),
                access_count=int(r.get("access_count", 0)),
            ))
        items.sort(
            key=lambda x: (
                candidate_scores.get(x.id, 0),
                x.confidence,
                x.created_at,
            ),
            reverse=True,
        )
        chosen = items[:limit]
        if chosen:
            await self._touch([i.id for i in chosen])
        return chosen

    async def list_items(self, user_id: str, *, vault: UnlockedVault, kind: Optional[str] = None,
                         limit: int = 100, offset: int = 0) -> list[BrainItem]:
        """Owner-facing listing (the 'My Second Brain' screen)."""
        q = self._db.table("user_brain_nodes").select("*").eq("user_id", user_id)
        if kind:
            q = q.eq("kind", kind)
        q = q.order("created_at", desc=True).range(offset, offset + limit - 1)
        rows = (await asyncio.to_thread(q.execute)).data or []
        out = []
        for r in rows:
            try:
                text = decrypt_payload(vault.dek, r["ciphertext"], aad=_aad(user_id, r["kind"], r["id"])).decode()
                out.append(BrainItem(r["id"], user_id, r["kind"], text,
                                     float(r.get("confidence", 0.8)),
                                     float(r.get("created_at", 0)),
                                     int(r.get("access_count", 0))))
            except VaultIntegrityError:
                continue
        return out

    # ------------------------------------------------------------------
    # Erasure & export
    # ------------------------------------------------------------------

    async def forget_item(self, user_id: str, item_id: str) -> bool:
        """Delete one item + its vector. User-scoped; idempotent."""
        await asyncio.to_thread(
            self._db.table("user_brain_nodes").delete().eq("user_id", user_id).eq("id", item_id).execute
        )
        await asyncio.to_thread(
            self._db.table("user_brain_edges").delete().eq("user_id", user_id)
            .or_(f"src.eq.{item_id},dst.eq.{item_id}").execute
        )
        await self._delete_embedding(user_id, item_id)
        self._audit(user_id, "item_forgotten", {"item_id": item_id})
        return True

    async def crypto_shred(self, user_id: str) -> dict:
        """Irreversible full erasure: delete all rows, delete this user's
        vectors from the shared vault collection, and destroy the wrapped
        DEK. Even with backups of the ciphertext, nothing can ever be
        decrypted again."""
        await asyncio.to_thread(self._db.table("user_brain_nodes").delete().eq("user_id", user_id).execute)
        await asyncio.to_thread(self._db.table("user_brain_edges").delete().eq("user_id", user_id).execute)
        await asyncio.to_thread(self._db.table("user_brain_keys").delete().eq("user_id", user_id).execute)
        if self._qdrant:
            try:
                await self._drop_collection(user_id)
            except Exception as exc:
                logger.error(f"crypto_shred: vector deletion failed for {user_id}: {exc}")
                raise
        self._audit(user_id, "vault_crypto_shredded", {})
        return {"user_id": user_id, "shredded": True}

    async def export(self, user_id: str, *, vault: UnlockedVault) -> dict:
        """GDPR/DSAR export — only ever callable with the owner's unlocked
        vault in hand (i.e., from the owner's own authenticated session)."""
        all_items = []
        offset = 0
        page_size = 1000
        while True:
            page = await self.list_items(user_id, vault=vault, limit=page_size, offset=offset)
            if not page:
                break
            all_items.extend(page)
            offset += len(page)
        edges_raw = (await asyncio.to_thread(
            self._db.table("user_brain_edges").select("*")
            .eq("user_id", user_id).execute
        )).data or []
        edges = []
        for e in edges_raw:
            try:
                rel = decrypt_payload(vault.dek, e["rel_cipher"], aad=_aad(user_id, "edge", e["id"])).decode()
                edges.append({"src": e["src"], "dst": e["dst"], "relation": rel,
                              "weight": e.get("weight", 1.0)})
            except VaultIntegrityError:
                continue
        self._audit(user_id, "vault_exported", {"items": len(all_items)})
        return {
            "user_id": user_id,
            "exported_at": time.time(),
            "format": "mukthi-brain-export/v1",
            "items": [vars(i) for i in all_items],
            "edges": edges,
        }

    # ------------------------------------------------------------------
    # Internals: storage / vectors / audit
    # ------------------------------------------------------------------

    async def _get_key_row(self, user_id: str) -> Optional[dict]:
        res = await asyncio.to_thread(
            self._db.table("user_brain_keys").select("*").eq("user_id", user_id).execute
        )
        return (res.data or [None])[0]

    async def _load_dek_mode_a(self, user_id: str) -> bytes:
        row = await self._get_key_row(user_id)
        if not row or not self._server_kek:
            raise VaultLockedError("vault missing")
        return unwrap_dek(row["wrapped_dek"], self._server_kek)

    @staticmethod
    def _mode_b_kek(passphrase: str, kdf: dict) -> bytes:
        return derive_kek_from_passphrase(
            passphrase, bytes.fromhex(kdf["salt"]),
            time_cost=kdf.get("time", 3), memory_kib=kdf.get("mem_kib", 65536),
            parallelism=kdf.get("par", 2),
        )

    async def _fetch_nodes(self, user_id: str, *, ids: Optional[list[str]], limit: int) -> list[dict]:
        q = self._db.table("user_brain_nodes").select("*").eq("user_id", user_id)
        if ids:
            q = q.in_("id", ids)
        q = q.order("created_at", desc=True).limit(limit)
        return (await asyncio.to_thread(q.execute)).data or []

    async def _touch(self, ids: list[str]) -> None:
        # bump access_count + slight decay refresh; fire-and-forget
        for i in ids:
            try:
                await asyncio.to_thread(self._db.rpc("brain_touch", {"p_id": i}).execute)
            except Exception:
                pass

    # ---- vectors (shared vault collection, user_id-filtered — see vault_index.py) ----

    async def _index_embedding(self, user_id: str, item_id: str, kind: str, text: str) -> None:
        try:
            vec = await self._embed.encode_single_async(text)
            await self._qdrant.upsert(user_id, item_id, vec, kind)
        except Exception as exc:
            logger.warning("second-brain vector index failed: %s", exc)

    async def _search_embedding(self, user_id: str, query: str, *, limit: int) -> list[str]:
        try:
            vec = await self._embed.encode_single_async(query)
            return await self._qdrant.search(user_id, vec, limit=limit)
        except Exception:
            return []

    async def _delete_embedding(self, user_id: str, item_id: str) -> None:
        if not self._qdrant:
            return
        try:
            await self._qdrant.delete_item(user_id, item_id)
        except Exception:
            pass

    async def _drop_collection(self, user_id: str) -> None:
        """Despite the name (kept for parity with the erasure call site),
        this deletes the user's points from the shared collection — there is
        no more a per-user collection to drop. See vault_index.VaultIndex.delete_all."""
        if not self._qdrant:
            return
        try:
            await self._qdrant.delete_all(user_id)
        except Exception:
            pass

    def _audit(self, user_id: str, event: str, meta: dict) -> None:
        """Security audit trail — who unlocked/exported/shredded, never WHAT.
        Ship to your tamper-evident log sink. Never log plaintext or keys."""
        logger.info("brain_audit event=%s user=%s meta=%s", event, user_id, json.dumps(meta))


def _strip_code_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1]
        if t.startswith("json"):
            t = t[4:]
    return t.strip()


if __name__ == "__main__":
    # Self-check: module imports cleanly, service constructs with no deps
    # (Mode-A provisioning requires BRAIN_KEK; that path is exercised in
    # backend/tests/test_second_brain.py, not here).
    assert callable(SecondBrainService)
    assert BrainItem(id="x", user_id="u", kind="reflection", text="t", confidence=0.9, created_at=0.0)
    print("second_brain_service self-check: OK")
