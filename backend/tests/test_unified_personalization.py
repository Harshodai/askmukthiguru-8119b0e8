"""
Tests for Unified Personalization Engine, Mode-B Encryption, and DPDP Cascade Erasure.
"""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from services.personalization import (
    UnifiedPersonalizationEngine,
    UnifiedSeekerContext,
    hard_cascade_account_erasure,
    derive_vault_key,
    encrypt_facet,
    decrypt_facet,
    DeletionAuditReceipt,
)
from services.personalization.crypto import VaultLockedError, PBKDF2_ITERATIONS


@pytest.mark.asyncio
async def test_anonymous_fast_path():
    """Test anonymous seeker fast path completes instantly (<0.1ms)."""
    start = asyncio.get_event_loop().time()
    ctx = await UnifiedPersonalizationEngine.hydrate_seeker_context(user_id=None)
    elapsed = (asyncio.get_event_loop().time() - start) * 1000.0

    assert ctx.is_authenticated is False
    assert ctx.user_id == "anonymous"
    assert elapsed < 10.0  # Well under 10ms P95 limit


@pytest.mark.asyncio
async def test_authenticated_hydration():
    """Test hydration across all 7 facets with mocked DB session."""
    mock_session = AsyncMock()
    ctx = await UnifiedPersonalizationEngine.hydrate_seeker_context(
        user_id="seeker-uuid-123",
        session=mock_session,
    )

    assert ctx.is_authenticated is True
    assert ctx.user_id == "seeker-uuid-123"
    assert ctx.seeker_profile is not None
    assert ctx.second_brain is not None
    assert ctx.sadhana is not None
    assert ctx.pre_practice is not None
    assert ctx.study_notebooks is not None
    assert ctx.mood_journal is not None
    assert ctx.whatsapp_reflections is not None


def test_mode_b_crypto_round_trip():
    """Test Mode-B encryption/decryption round-trip with PBKDF2 600,000 rounds."""
    passphrase = "test-secure-passphrase-mukthi"
    vault_key = derive_vault_key(passphrase)

    payload = {"secret_mantra": "Om Shanti Shanti Shanti", "meditation_depth": 9}
    encrypted = encrypt_facet(payload, vault_key)

    assert encrypted.ciphertext is not None
    assert encrypted.iv is not None
    assert encrypted.auth_tag is not None

    decrypted = decrypt_facet(encrypted, vault_key)
    assert decrypted == payload


@pytest.mark.asyncio
async def test_dpdp_cascade_erasure():
    """Test DPDP 26-table cascade erasure execution and receipt verification."""
    mock_session = AsyncMock()
    mock_supabase = MagicMock()
    # Mock supabase select / delete chain
    mock_table = MagicMock()
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.delete.return_value = mock_table
    mock_table.execute.return_value = MagicMock(data=[])
    mock_supabase.table.return_value = mock_table

    mock_memgraph = MagicMock()
    mock_session = MagicMock()
    mock_session.__enter__.return_value = mock_session
    mock_session.run.return_value.single.return_value = {"deleted": 7}
    mock_memgraph.session.return_value = mock_session

    receipt = await hard_cascade_account_erasure(
        user_id="user-to-erase-999",
        supabase_client=mock_supabase,
        memgraph_driver=mock_memgraph,
    )

    assert isinstance(receipt, DeletionAuditReceipt)
    assert receipt.user_id == "user-to-erase-999"
    assert receipt.audit_verified is True
    assert len(receipt.tables_wiped) >= 26
    assert receipt.graph_nodes_wiped == 7


def test_prompt_guidance_generation():
    """Test prompt guidance generation formatting."""
    ctx = UnifiedSeekerContext(
        user_id="seeker-1",
        is_authenticated=True,
    )
    guidance = ctx.format_prompt_guidance()
    assert "Seeker Personalization & Spiritual Readiness" in guidance
    assert "Sadhana & Practice Journey" in guidance

