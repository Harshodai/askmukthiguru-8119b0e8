"""Second Brain test suite — run with: .venv/bin/pytest tests/test_second_brain.py -q

Uses fakes for Supabase/Qdrant(VaultIndex)/LLM so the whole vault lifecycle
is tested in-process with zero network. The crypto layer is tested for real.
"""

from __future__ import annotations

import asyncio
import os

import pytest

os.environ.setdefault("BRAIN_KEK", "dGVzdC1vcGVyYXRvci1rZWstMzItYnl0ZXMteHh4eHg=")  # test only, decodes to 32B

from services.second_brain.crypto import UnlockedVault, VaultLockedError  # noqa: E402
from services.second_brain.second_brain_service import SecondBrainService  # noqa: E402


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------

class _Exec:
    def __init__(self, data=None):
        self.data = data or []

class _Query:
    def __init__(self, store, table):
        self.store, self.table = store, table
        self._filters = []
    def select(self, *_a, **_k): return self
    def eq(self, col, val): self._filters.append(("eq", col, val)); return self
    def in_(self, col, vals): self._filters.append(("in", col, vals)); return self
    def order(self, *_a, **_k): return self
    def range(self, *_a, **_k): return self
    def limit(self, n): self._filters.append(("limit", None, n)); return self
    def insert(self, row): self.store.setdefault(self.table, []).append(row); return self
    def upsert(self, row):
        rows = self.store.setdefault(self.table, [])
        rows[:] = [r for r in rows if r.get("user_id") != row.get("user_id")]
        rows.append(row); return self
    def delete(self): self._delete = True; return self
    def or_(self, *_a): return self
    async def execute(self):
        if getattr(self, "_delete", False):
            rows = self.store.get(self.table, [])
            keep = rows[:]
            for op, col, val in self._filters:
                if op == "eq":
                    keep = [r for r in keep if r.get(col) != val]
            self.store[self.table] = keep
            return _Exec([])
        rows = list(self.store.get(self.table, []))
        for op, col, val in self._filters:
            if op == "eq":
                rows = [r for r in rows if r.get(col) == val]
            elif op == "in":
                rows = [r for r in rows if r.get(col) in val]
            elif op == "limit":
                rows = rows[:val]
        return _Exec(rows)

class FakeDB:
    def __init__(self): self.store = {}
    def table(self, name): return _Query(self.store, name)
    def rpc(self, *_a, **_k): return _Query(self.store, "rpc")

class FakeEmbed:
    """Matches services.embedding_service.EmbeddingService.encode_single_async."""
    async def encode_single_async(self, text): return [float(len(text) % 7 + 1)] * 8

class FakeVaultIndex:
    """Matches services.second_brain.vault_index.VaultIndex's duck-typed shape:
    one shared collection, everything keyed/filtered by user_id."""
    def __init__(self): self.points = {}  # user_id -> {item_id: vector}
    def ensure_collection(self): pass
    async def upsert(self, user_id, item_id, vector, kind):
        self.points.setdefault(user_id, {})[item_id] = vector
    async def search(self, user_id, vector, *, limit):
        return list(self.points.get(user_id, {}))[:limit]
    async def delete_item(self, user_id, item_id):
        self.points.get(user_id, {}).pop(item_id, None)
    async def delete_all(self, user_id):
        self.points.pop(user_id, None)

class FakeLLM:
    """Matches services.llm.base.LLMProvider.generate(system_prompt, user_prompt, **kwargs)."""
    async def generate(self, system_prompt, user_prompt, **_k):
        return '{"items":[{"kind":"reflection","text":"User is preparing for a job interview and feels anxious.","confidence":0.9}]}'


def make_svc():
    return SecondBrainService(FakeDB(), FakeEmbed(), FakeLLM(), FakeVaultIndex())


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------

def test_provision_and_recall_roundtrip():
    svc = make_svc()
    uid = "user-1"
    asyncio.run(svc.provision_vault(uid))

    async def go():
        with await svc.unlock(uid) as vault:
            iid = await svc.add_item(uid, "reflection", "User feels anxious about interviews.", vault=vault)
            assert iid
            items = await svc.personal_context(uid, "interview anxiety", vault=vault)
            assert any("anxious" in i.text for i in items)
            # ciphertext at rest — the DB must never hold plaintext
            raw = svc._db.store["user_brain_nodes"][0]["ciphertext"]
            assert "anxious" not in raw
            # vector index only ever sees {user_id, kind} — never plaintext (payload
            # isn't modeled by FakeVaultIndex at all; asserting the vector was written
            # is the meaningful check here)
            assert iid in svc._qdrant.points[uid]
    asyncio.run(go())


def test_extraction_writes_durable_item():
    svc = make_svc()
    uid = "user-2"
    asyncio.run(svc.provision_vault(uid))

    async def go():
        with await svc.unlock(uid) as vault:
            n = await svc.extract_and_write(uid, "I have a job interview tomorrow, so nervous",
                                            "That's understandable...", vault=vault)
            assert n == 1
            items = await svc.list_items(uid, vault=vault)
            assert len(items) == 1 and "job interview" in items[0].text
    asyncio.run(go())


def test_mode_b_wrong_passphrase_denied():
    svc = make_svc()
    uid = "user-3"
    asyncio.run(svc.provision_vault(uid))
    asyncio.run(svc.enable_session_unlock(uid, "correct horse battery staple"))

    with pytest.raises(VaultLockedError):
        asyncio.run(svc.unlock(uid, passphrase="wrong passphrase"))

    async def go():
        with await svc.unlock(uid, passphrase="correct horse battery staple") as vault:
            iid = await svc.add_item(uid, "journal", "Private entry", vault=vault)
            assert iid
    asyncio.run(go())


def test_user_isolation_other_user_cannot_read():
    svc = make_svc()
    asyncio.run(svc.provision_vault("alice"))
    asyncio.run(svc.provision_vault("bob"))

    async def go():
        with await svc.unlock("alice") as va:
            await svc.add_item("alice", "journal", "Alice secret", vault=va)
        with await svc.unlock("bob") as vb:
            bob_items = await svc.list_items("bob", vault=vb)
            assert bob_items == []
            # bob's vault cannot decrypt alice's row (AAD mismatch too)
            raw = [r for r in svc._db.store["user_brain_nodes"] if r["user_id"] == "alice"][0]
            from services.second_brain.crypto import decrypt_payload, VaultIntegrityError
            with pytest.raises(VaultIntegrityError):
                decrypt_payload(vb.dek, raw["ciphertext"], aad=b"alice:journal:" + raw["id"].encode())
        # bob's vector search never sees alice's points (separate user_id key
        # in the fake; the real VaultIndex enforces this via a Qdrant Filter)
        assert svc._qdrant.points.get("bob", {}) == {}
    asyncio.run(go())


def test_crypto_shred_is_irreversible():
    svc = make_svc()
    uid = "user-4"
    asyncio.run(svc.provision_vault(uid))

    async def go():
        with await svc.unlock(uid) as vault:
            await svc.add_item(uid, "reflection", "to be shredded", vault=vault)
    asyncio.run(go())

    res = asyncio.run(svc.crypto_shred(uid))
    assert res["shredded"] is True
    assert svc._db.store.get("user_brain_nodes", []) == []
    assert svc._db.store.get("user_brain_keys", []) == []
    assert svc._qdrant.points.get(uid, {}) == {}


def test_vault_zeroizes_on_close():
    dek = b"k" * 32
    v = UnlockedVault.from_dek(dek)
    v.close()
    assert bytes(v._dek) == b"\x00" * 32


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
