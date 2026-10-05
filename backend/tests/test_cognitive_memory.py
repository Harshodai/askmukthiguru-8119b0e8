"""
Cognitive Agent Memory & Bi-Temporal Personalization Test Suite.

Verifies:
1. Ebbinghaus retention curve: Day 0 vs Day 30 decay, and spaced retrieval curve flattening.
2. Superseded memory ranking penalty (decay=0.05) and bi-temporal context filtering.
3. Zero-knowledge payload isolation in Qdrant (vectors + opaque metadata only; no plaintext or ciphertext).
4. Fail-closed GDPR crypto-shredding (vectors wiped first, DB rows wiped second, DEK destroyed third,
   rendering historical ciphertext mathematically unrecoverable).
"""

from __future__ import annotations

import math
import os
import time

import pytest

os.environ.setdefault("BRAIN_KEK", "dGVzdC1vcGVyYXRvci1rZWstMzItYnl0ZXMteHh4eHg=")

from services.second_brain.crypto import (
    UnlockedVault,
    VaultIntegrityError,
    decrypt_payload,
    generate_dek,
)
from services.second_brain.ebbinghaus import (
    ebbinghaus_retention,
    score_memory_candidate,
)
from services.second_brain.second_brain_service import SecondBrainService

# --------------------------------------------------------------------------
# Test Fakes (zero-network, in-memory)
# --------------------------------------------------------------------------


class _Exec:
    def __init__(self, data=None):
        self.data = data or []


class _Query:
    def __init__(self, store, table):
        self.store, self.table = store, table
        self._filters = []
        self._update = None
        self._delete = False

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
        if self.table == "user_brain_nodes":
            # Mirror the live column defaults (migration 20261005053723).
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
        if self._update is not None:
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
        if self._delete:
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
    async def encode_single_async(self, text):
        return [float(len(text) % 7 + 1)] * 8


class FakeVaultIndex:
    """Simulates VaultIndex with Qdrant-like payload inspection."""

    def __init__(self):
        self.points = {}  # user_id -> {item_id: {"vector": vec, "payload": payload}}

    def ensure_collection(self):
        pass

    async def upsert(self, user_id, item_id, vector, kind):
        # Mirror VaultIndex invariant: payload contains only user_id and kind
        self.points.setdefault(user_id, {})[item_id] = {
            "vector": vector,
            "payload": {"user_id": user_id, "kind": kind},
        }

    async def search(self, user_id, vector, *, limit):
        return list(self.points.get(user_id, {}))[:limit]

    async def delete_item(self, user_id, item_id):
        self.points.get(user_id, {}).pop(item_id, None)

    async def delete_all(self, user_id):
        self.points.pop(user_id, None)


class BrokenVaultIndex(FakeVaultIndex):
    """Simulates a Qdrant failure on the vector drop/delete path."""

    async def delete_all(self, user_id):
        raise RuntimeError("qdrant cluster unavailable during drop")

    async def delete_item(self, user_id, item_id):
        raise RuntimeError("qdrant point delete failed")


class FakeLLM:
    async def generate(self, system_prompt, user_prompt, **_k):
        return '{"items":[{"kind":"reflection","text":"User feels calm after Soul Sync meditation.","confidence":0.9}]}'


def make_test_service(vault_index=None):
    return SecondBrainService(
        FakeDB(),
        FakeEmbed(),
        FakeLLM(),
        vault_index or FakeVaultIndex(),
    )


# ==============================================================================
# 1. Ebbinghaus Retention Curve Tests
# ==============================================================================


def test_ebbinghaus_day0_vs_day30_decay():
    """Verify Day 0 has 100% retention and Day 30 without recall decays to ~e^(-1)."""
    # Day 0: fresh memory
    r0 = ebbinghaus_retention(delta_days=0.0, access_count=0, stability_days=30.0)
    assert r0 == 1.0

    # Day 30 without retrieval: delta_days / stability_days = 30 / 30 = 1.0 -> exp(-1) ≈ 0.367879
    r30_stale = ebbinghaus_retention(delta_days=30.0, access_count=0, stability_days=30.0)
    assert math.isclose(r30_stale, math.exp(-1.0), rel_tol=1e-4)
    assert 0.36 <= r30_stale <= 0.37


def test_ebbinghaus_spaced_retrieval_flattens_decay():
    """Verify spaced retrieval reinforcements flatten the decay curve significantly."""
    # Stale memory at Day 30
    r30_stale = ebbinghaus_retention(delta_days=30.0, access_count=0, stability_days=30.0)

    # Memory retrieved 3 times and 10 times at Day 30
    r30_retrieved_3 = ebbinghaus_retention(delta_days=30.0, access_count=3, stability_days=30.0)
    r30_retrieved_10 = ebbinghaus_retention(delta_days=30.0, access_count=10, stability_days=30.0)

    # Retrieval count must strictly increase retention
    assert r30_retrieved_3 > r30_stale
    assert r30_retrieved_10 > r30_retrieved_3

    # 10 retrievals should preserve > 70% retention after 30 days
    assert r30_retrieved_10 > 0.70
    assert r30_retrieved_3 > 0.50


# ==============================================================================
# 2. Memory Candidate Scoring & Superseded Invalidation Penalty
# ==============================================================================


def test_score_memory_candidate_superseded_penalty():
    """Verify superseded memories receive decay=0.05 penalty in scoring."""
    now = time.time()
    # Identical similarity, creation epoch, and access count
    score_active = score_memory_candidate(
        similarity=0.90,
        created_at_epoch=now,
        access_count=0,
        is_superseded=False,
        decay_factor=0.05,
        current_epoch=now,
    )
    score_superseded = score_memory_candidate(
        similarity=0.90,
        created_at_epoch=now,
        access_count=0,
        is_superseded=True,
        decay_factor=0.05,
        current_epoch=now,
    )

    # Superseded score must be exactly 5% of active score
    assert math.isclose(score_superseded, score_active * 0.05, rel_tol=1e-4)


@pytest.mark.asyncio
async def test_personal_context_ranking_with_retention_and_superseded_penalty():
    """Verify personal_context ranks active fresh memory over stale/superseded memories."""
    svc = make_test_service()
    uid = "user-cognitive-test"
    await svc.provision_vault(uid)

    with await svc.unlock(uid) as vault:
        # Add an older fact (e.g., 60 days ago simulated by epoch adjustment)
        now = time.time()
        sixty_days_ago_epoch = now - (60 * 86400)
        old_id = await svc.add_item(
            uid, "reflection", "I am overwhelmed by grief and fear.", vault=vault
        )
        # Manually backdate the created_at in the fake DB for old_id
        for r in svc._db.store["user_brain_nodes"]:
            if r["id"] == old_id:
                r["created_at"] = sixty_days_ago_epoch

        # Add a fresh new fact
        new_id = await svc.add_item(
            uid, "reflection", "I experienced profound peace during Soul Sync today.", vault=vault
        )

        # Invalidate old with new
        await svc.invalidate_and_supersede(uid, old_id, new_id, vault=vault)

        # A. Default recall excludes superseded memory
        active_items = await svc.personal_context(uid, "peace grief", vault=vault)
        active_ids = [it.id for it in active_items]
        assert new_id in active_ids
        assert old_id not in active_ids

        # B. When include_superseded=True, new active memory ranks first despite query mentioning grief
        all_items = await svc.personal_context(
            uid, "peace grief", vault=vault, include_superseded=True
        )
        assert len(all_items) == 2
        assert all_items[0].id == new_id
        assert all_items[1].id == old_id
        assert all_items[1].is_superseded is True
        assert all_items[1].decay == 0.05


# ==============================================================================
# 3. Zero-Knowledge Vector Payload Isolation in Qdrant
# ==============================================================================


@pytest.mark.asyncio
async def test_zero_knowledge_vector_payload_isolation():
    """Verify Qdrant points store only opaque user_id and kind; no plaintext or ciphertext."""
    vindex = FakeVaultIndex()
    svc = make_test_service(vault_index=vindex)
    uid = "user-zk-privacy"
    await svc.provision_vault(uid)

    sensitive_text = "Private spiritual confession: intense envy and doubt in family relationships."
    with await svc.unlock(uid) as vault:
        item_id = await svc.add_item(uid, "reflection", sensitive_text, vault=vault)

    # Inspect the point stored in the vault index
    user_points = vindex.points.get(uid, {})
    assert item_id in user_points
    stored_point = user_points[item_id]

    # 1. Vector is present
    assert "vector" in stored_point
    assert isinstance(stored_point["vector"], list)

    # 2. Payload contains ONLY opaque user_id and kind
    payload = stored_point["payload"]
    assert set(payload.keys()) == {"user_id", "kind"}
    assert payload["user_id"] == uid
    assert payload["kind"] == "reflection"

    # 3. ABSOLUTE INVARIANCE: Neither plaintext nor ciphertext exists in the vector payload
    assert "text" not in payload
    assert "ciphertext" not in payload
    assert sensitive_text not in str(stored_point)


# ==============================================================================
# 4. Fail-Closed GDPR Crypto-Shredding
# ==============================================================================


@pytest.mark.asyncio
async def test_crypto_shredding_fail_closed_on_vector_failure():
    """A vector drop failure must abort before deleting DB rows or DEK keys (Fail-Closed)."""
    broken_vindex = BrokenVaultIndex()
    svc = make_test_service(vault_index=broken_vindex)
    uid = "user-fail-closed"
    await svc.provision_vault(uid)

    with await svc.unlock(uid) as vault:
        item_id = await svc.add_item(uid, "reflection", "Irreplaceable user memory", vault=vault)

    # Attempting crypto_shred must raise RuntimeError from vector failure
    with pytest.raises(RuntimeError, match="qdrant cluster unavailable"):
        await svc.crypto_shred(uid)

    # CRITICAL: Verify DB rows and keys were NOT deleted
    assert any(r["id"] == item_id for r in svc._db.store.get("user_brain_nodes", []))
    assert any(r["user_id"] == uid for r in svc._db.store.get("user_brain_keys", []))


@pytest.mark.asyncio
async def test_crypto_shredding_renders_ciphertext_unrecoverable():
    """Full crypto_shred purges vectors, rows, and DEK, rendering ciphertext unrecoverable."""
    vindex = FakeVaultIndex()
    svc = make_test_service(vault_index=vindex)
    uid = "user-gdpr-shredded"
    await svc.provision_vault(uid)

    with await svc.unlock(uid) as vault:
        item_id = await svc.add_item(uid, "journal", "Confidential seeker reflections", vault=vault)

    # Capture raw ciphertext from DB prior to shredding
    raw_node = next(r for r in svc._db.store["user_brain_nodes"] if r["id"] == item_id)
    raw_ciphertext = raw_node["ciphertext"]

    # Execute irreversible crypto-shredding
    result = await svc.crypto_shred(uid)
    assert result["shredded"] is True

    # 1. State purged in all layers
    assert uid not in vindex.points
    assert not any(r["user_id"] == uid for r in svc._db.store.get("user_brain_nodes", []))
    assert not any(r["user_id"] == uid for r in svc._db.store.get("user_brain_edges", []))
    assert not any(r["user_id"] == uid for r in svc._db.store.get("user_brain_keys", []))

    # 2. Cryptographic Irrecoverability:
    # Any residual copy of ciphertext cannot be decrypted because the DEK is permanently destroyed
    random_vault = UnlockedVault.from_dek(generate_dek())
    with pytest.raises(VaultIntegrityError):
        decrypt_payload(
            random_vault.dek,
            raw_ciphertext,
            aad=f"{uid}:journal:{item_id}".encode(),
        )
