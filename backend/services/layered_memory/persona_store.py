"""Encrypted persona storage using Second Brain vault primitives."""

from __future__ import annotations

import base64
import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from services.second_brain.crypto import AESGCM, _KEY_LEN, _NONCE_LEN, _PREAMBLE, _b64d, _b64e
from services.tenant_context import TenantContext

logger = logging.getLogger(__name__)

_TABLE = "user_personas"


def _kek() -> bytes:
    """Derive a stable server KEK for persona encryption.

    Reuses the same BRAIN_KEK env var as Second Brain when present; otherwise
    derives a deterministic 32-byte key from PERSONA_ENCRYPTION_SECRET so a
    missing Second-Brain config does not leave personas unencrypted.
    """
    env_value = os.environ.get("BRAIN_KEK") or os.environ.get("PERSONA_ENCRYPTION_SECRET", "")
    if not env_value:
        raise ValueError("PERSONA_ENCRYPTION_SECRET or BRAIN_KEK must be set to encrypt personas")
    try:
        raw = _b64d(env_value)
        if len(raw) == _KEY_LEN:
            return raw
    except Exception as _e:
        logger.debug("[persona store] suppressed non-critical error: %s", _e)
    # Deterministic derivation from a plain secret string
    return hashlib.sha256(env_value.encode("utf-8")).digest()


def encrypt(plaintext: str, user_id: str) -> str:
    """Encrypt persona Markdown with AAD bound to user_id."""
    kek = _kek()
    aes = AESGCM(kek)
    nonce = os.urandom(_NONCE_LEN)
    aad = _PREAMBLE + f"persona:{user_id}".encode("utf-8")
    ct = aes.encrypt(nonce, plaintext.encode("utf-8"), associated_data=aad)
    return _b64e(_PREAMBLE + nonce + ct)


def decrypt(blob: str, user_id: str) -> str:
    """Decrypt persona Markdown; raise on tamper/wrong key."""
    kek = _kek()
    raw = _b64d(blob)
    if len(raw) < 1 + _NONCE_LEN + 16 or raw[0] != _PREAMBLE[0]:
        raise ValueError("Corrupt persona ciphertext")
    aes = AESGCM(kek)
    nonce, ct = raw[1 : 1 + _NONCE_LEN], raw[1 + _NONCE_LEN :]
    aad = _PREAMBLE + f"persona:{user_id}".encode("utf-8")
    return aes.decrypt(nonce, ct, associated_data=aad).decode("utf-8")


async def get_persona(supabase, user_id: str) -> tuple[Optional[str], Optional[str]]:
    """Return (decrypted persona content, updated_at ISO timestamp) or (None, None)."""
    try:
        tenant_id = TenantContext.get()
        res = await supabase.table(_TABLE).select("content, updated_at").eq("user_id", user_id).eq("tenant_id", tenant_id).maybe_single().execute()
        if res.data and res.data.get("content"):
            return decrypt(res.data["content"], user_id), res.data.get("updated_at")
    except Exception as e:
        logger.debug(f"get_persona miss: {e}")
    return None, None


async def save_persona(supabase, user_id: str, content: str) -> bool:
    try:
        tenant_id = TenantContext.get()
        encrypted = encrypt(content, user_id)
        await supabase.table(_TABLE).upsert(
            {
                "user_id": user_id,
                "tenant_id": tenant_id,
                "content": encrypted,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="user_id,tenant_id",
        ).execute()
        return True
    except Exception as e:
        logger.warning(f"save_persona failed: {e}")
        return False


if __name__ == "__main__":
    os.environ.setdefault("PERSONA_ENCRYPTION_SECRET", "a" * 32)
    ct = encrypt("# User Persona\nLikes meditation.", "user-1")
    pt = decrypt(ct, "user-1")
    assert pt == "# User Persona\nLikes meditation."
    print("persona_store OK")
