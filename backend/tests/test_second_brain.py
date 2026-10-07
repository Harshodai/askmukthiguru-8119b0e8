"""Second Brain test suite — run with: .venv/bin/pytest tests/test_second_brain.py -q

Uses fakes for Supabase/Qdrant(VaultIndex)/LLM so the whole vault lifecycle
is tested in-process with zero network. The crypto layer is tested for real.
"""

from __future__ import annotations

import asyncio
import os

import pytest

os.environ.setdefault(
    "BRAIN_KEK", "dGVzdC1vcGVyYXRvci1rZWstMzItYnl0ZXMteHh4eHg="
)  # test only, decodes to 32B

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

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def in_(self, col, vals):
        self._filters.append(("in", col, vals))
        return self

    def order(self, *_a, **_k):
        return self

    def range(self, start, end):
        self._filters.append(("range", start, end))
        return self

    def limit(self, n):
        self._filters.append(("limit", None, n))
        return self

    def insert(self, row):
        self.store.setdefault("__payloads__", []).append((self.table, dict(row)))
        if self.table == "user_brain_nodes":
            # Mirror the live column defaults (migration 20261005053723) so
            # filters on omitted columns behave like PostgREST does.
            row = {"is_superseded": False, "valid_to": None, "superseded_by": None, **row}
        self.store.setdefault(self.table, []).append(row)
        return self

    def upsert(self, row):
        rows = self.store.setdefault(self.table, [])
        rows[:] = [r for r in rows if r.get("user_id") != row.get("user_id")]
        rows.append(row)
        return self

    def update(self, values):
        self._update = values
        return self

    def delete(self):
        self._delete = True
        return self

    def or_(self, *_a):
        return self

    def execute(self):
        if getattr(self, "_update", None) is not None:
            values = self._update
            rows = self.store.get(self.table, [])
            for r in rows:
                match = True
                for op, col, val in self._filters:
                    if op == "eq" and r.get(col) != val:
                        match = False
                        break
                if match:
                    r.update(values)
            return _Exec([])
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
            elif op == "range":
                rows = rows[col : val + 1]
        return _Exec(rows)


class FakeDB:
    def __init__(self):
        self.store = {}

    def table(self, name):
        return _Query(self.store, name)

    def rpc(self, *_a, **_k):
        return _Query(self.store, "rpc")


class FakeEmbed:
    """Matches services.embedding_service.EmbeddingService.encode_single_async."""

    async def encode_single_async(self, text):
        return [float(len(text) % 7 + 1)] * 8


class FakeVaultIndex:
    """Matches services.second_brain.vault_index.VaultIndex's duck-typed shape:
    one shared collection, everything keyed/filtered by user_id."""

    def __init__(self):
        self.points = {}  # user_id -> {item_id: vector}

    def ensure_collection(self):
        pass

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


class BrokenVaultIndex(FakeVaultIndex):
    """delete_item raises — simulates a Qdrant failure on the erasure path."""

    async def delete_item(self, user_id, item_id):
        raise RuntimeError("qdrant delete failed")


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
            iid = await svc.add_item(
                uid, "reflection", "User feels anxious about interviews.", vault=vault
            )
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
            n = await svc.extract_and_write(
                uid,
                "I have a job interview tomorrow, so nervous",
                "That's understandable...",
                vault=vault,
            )
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
            from services.second_brain.crypto import VaultIntegrityError, decrypt_payload

            with pytest.raises(VaultIntegrityError):
                decrypt_payload(
                    vb.dek, raw["ciphertext"], aad=b"alice:journal:" + raw["id"].encode()
                )
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


def test_vector_delete_failure_fails_erasure_closed():
    """A Qdrant delete failure must propagate, and forget_item must abort
    BEFORE the plaintext row is deleted — never report a successful forget
    while the vector survives in the shared vault collection."""
    svc = SecondBrainService(FakeDB(), FakeEmbed(), FakeLLM(), BrokenVaultIndex())
    uid = "user-erase"
    asyncio.run(svc.provision_vault(uid))

    async def go():
        with await svc.unlock(uid) as vault:
            iid = await svc.add_item(uid, "reflection", "sensitive memory", vault=vault)
        with pytest.raises(RuntimeError):
            await svc._delete_embedding(uid, iid)
        with pytest.raises(RuntimeError):
            await svc.forget_item(uid, iid)
        # plaintext row survives the aborted erase -> retry-safe, no orphan vector
        assert [r for r in svc._db.store["user_brain_nodes"] if r["id"] == iid]

    asyncio.run(go())


def test_default_add_item_writes_only_migrated_columns():
    """supabase/migrations/20260717191006_second_brain_vault.sql has no
    bi-temporal columns; PostgREST rejects an insert naming an unknown column,
    so a plain add_item must not send them."""
    svc = make_svc()
    uid = "user-schema"
    asyncio.run(svc.provision_vault(uid))

    async def go():
        with await svc.unlock(uid) as vault:
            iid = await svc.add_item(uid, "reflection", "plain note", vault=vault)
        row = next(
            p
            for t, p in svc._db.store["__payloads__"]
            if t == "user_brain_nodes" and p["id"] == iid
        )
        assert set(row) <= {
            "id",
            "user_id",
            "kind",
            "ciphertext",
            "blind",
            "confidence",
            "decay",
            "access_count",
            "created_at",
            "updated_at",
        }

    asyncio.run(go())


def test_bi_temporal_invalidation_and_superseding():
    """Verify Section 2.4 Bi-Temporal Knowledge Graph & Fact Invalidation (Graphiti/HippoRAG pattern).
    1. Historical fact ('I am in deep grief') is NOT deleted.
    2. Fact is bi-temporally invalidated: valid_to is set, is_superseded=True, decay=0.05.
    3. An encrypted edge (old)-[:SUPERSEDED_BY]->(new) is stored.
    4. By default, personal_context filters out superseded facts and returns only the active fact.
    5. When include_superseded=True, superseded facts are decayed by 0.05 in ranking.
    """
    svc = make_svc()
    uid = "user-bitemporal"
    asyncio.run(svc.provision_vault(uid))

    async def go():
        with await svc.unlock(uid) as vault:
            old_id = await svc.add_item(
                uid, "reflection", "I am suffering from intense grief and loneliness", vault=vault
            )
            new_id = await svc.add_item(
                uid,
                "reflection",
                "I experienced deep peace during Soul Sync meditation today",
                vault=vault,
            )
            edge_id = await svc.invalidate_and_supersede(uid, old_id, new_id, vault=vault)
            assert edge_id is not None

            # 1. Verify old node row exists in user_brain_nodes (never deleted)
            old_rows = [r for r in svc._db.store["user_brain_nodes"] if r["id"] == old_id]
            assert len(old_rows) == 1
            old_row = old_rows[0]
            assert old_row["is_superseded"] is True
            assert old_row["superseded_by"] == new_id
            assert old_row["decay"] == 0.05
            assert old_row["valid_to"] is not None

            # 2. Verify edge row exists in user_brain_edges
            edge_rows = [
                r
                for r in svc._db.store.get("user_brain_edges", [])
                if r["src"] == old_id and r["dst"] == new_id
            ]
            assert len(edge_rows) == 1
            assert edge_rows[0]["weight"] == 0.05

            # 3. Default personal_context (include_superseded=False) excludes old_id
            active_items = await svc.personal_context(uid, "peace grief", vault=vault)
            active_ids = [it.id for it in active_items]
            assert new_id in active_ids
            assert old_id not in active_ids

            # 4. personal_context with include_superseded=True includes both, decayed appropriately
            all_items = await svc.personal_context(
                uid, "peace grief", vault=vault, include_superseded=True
            )
            all_ids = [it.id for it in all_items]
            assert new_id in all_ids
            assert old_id in all_ids
            old_item = next(it for it in all_items if it.id == old_id)
            assert old_item.is_superseded is True
            assert old_item.decay == 0.05

            # 5. Export includes both nodes and decrypted edge
            export_data = await svc.export(uid, vault=vault)
            exported_items = export_data["items"]
            assert len(exported_items) == 2
            exported_edges = export_data["edges"]
            assert len(exported_edges) == 1
            assert exported_edges[0]["relation"] == "SUPERSEDED_BY"
            assert exported_edges[0]["src"] == old_id
            assert exported_edges[0]["dst"] == new_id

    asyncio.run(go())


def test_supersede_rejects_self_and_foreign_ids():
    svc = make_svc()
    a, b = "user-a", "user-b"
    asyncio.run(svc.provision_vault(a))
    asyncio.run(svc.provision_vault(b))

    async def go():
        with await svc.unlock(a) as va:
            a1 = await svc.add_item(a, "reflection", "a old", vault=va)
        with await svc.unlock(b) as vb:
            b1 = await svc.add_item(b, "reflection", "b new", vault=vb)
        with await svc.unlock(a) as va:
            with pytest.raises(ValueError):
                await svc.invalidate_and_supersede(a, a1, a1, vault=va)
            # FK on id alone would accept b's node; the service must not.
            with pytest.raises(KeyError):
                await svc.invalidate_and_supersede(a, a1, b1, vault=va)
            with pytest.raises(KeyError):
                await svc.invalidate_and_supersede(a, "nope", a1, vault=va)
        row = next(r for r in svc._db.store["user_brain_nodes"] if r["id"] == a1)
        assert row["is_superseded"] is False and row["superseded_by"] is None
        assert not svc._db.store.get("user_brain_edges")

    asyncio.run(go())


def test_superseded_rows_do_not_crowd_out_active_ones():
    """Filtering happens in the query, so a run of recent superseded facts
    can't fill the LIMIT window and hide the active memories."""
    svc = make_svc()
    uid = "user-crowd"
    asyncio.run(svc.provision_vault(uid))

    async def go():
        with await svc.unlock(uid) as vault:
            active = await svc.add_item(uid, "reflection", "still true", vault=vault)
            for i in range(12):
                old = await svc.add_item(uid, "reflection", f"stale {i}", vault=vault)
                await svc.invalidate_and_supersede(uid, old, active, vault=vault)
            got = await svc.personal_context(uid, "", vault=vault, limit=2)
        assert [i.id for i in got] == [active]

    asyncio.run(go())


@pytest.mark.parametrize(
    "valid_to, expect_kept",
    [
        ("2000-01-01T00:00:00+00:00", False),  # expired
        ("2999-01-01T00:00:00.123456+05:30", True),  # future, other offset/precision
        ("2999-01-01T00:00:00Z", True),
        ("not-a-date", False),  # unparseable: fail closed
    ],
)
def test_valid_to_is_parsed_not_string_compared(valid_to, expect_kept):
    svc = make_svc()
    uid = "user-validto"
    asyncio.run(svc.provision_vault(uid))

    async def go():
        with await svc.unlock(uid) as vault:
            iid = await svc.add_item(
                uid, "reflection", "time-bounded fact", vault=vault, valid_to=valid_to
            )
            got = await svc.personal_context(uid, "", vault=vault)
        return iid, [i.id for i in got]

    iid, ids = asyncio.run(go())
    assert (iid in ids) is expect_kept


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-q"]))
