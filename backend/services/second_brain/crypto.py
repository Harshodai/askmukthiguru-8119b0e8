"""
Mukthi Vault — envelope encryption primitives for the per-user Second Brain.

Drop-in module. Depends only on `cryptography` (already pinned in
requirements.txt) and `argon2-cffi` (Mode B only; already present
transitively — see backend/tests/test_second_brain.py for the import check).

Design
------
Every user gets their own Data-Encryption-Key (DEK): 32 random bytes.
All of that user's Second-Brain payloads (reflections, entities, edges,
journal entries) are encrypted with AES-256-GCM under that DEK.

The DEK itself is *wrapped* (encrypted) by a Key-Encryption-Key (KEK) before
it is stored. Two wrap modes are supported:

  Mode A — "server-wrapped" (default, zero-friction):
      KEK comes from the server environment (BRAIN_KEK env var or a KMS).
      Guarantees: ciphertext at rest in Postgres/Qdrant/backups/logs.
      A database dump, a stolen backup, or a read replica NEVER contains
      plaintext. Only the live request path (which holds the KEK) can
      decrypt, and only for the authenticated owner.
      Residual trust: an operator who holds *both* the DB and the env KEK
      could decrypt. Mitigate with the audit log + KEK in a real KMS
      (AWS KMS / GCP KMS / Supabase Vault) instead of a bare env var.

  Mode B — "session-unlock" (owner-blind / zero-knowledge):
      The KEK is derived from a user passphrase with Argon2id. The server
      stores only the wrapped DEK. The passphrase never leaves the client;
      the *unwrapped DEK* is sent per-request over TLS in a header, held in
      memory for the duration of the request, and zeroized after.
      The operator — even with full prod access — cannot read the graph.
      Trade-off: if the user forgets the passphrase, the brain is
      unrecoverable (crypto-shredded by design). This is the same model
      used by Standard Notes / Reflect / Nevernote.

Wire format (versioned, authenticated):
      v1 || nonce(12B) || ciphertext || tag(16B)   — base64url for storage

Nothing here logs plaintext. Nothing here writes plaintext to disk.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

VERSION = 1
_NONCE_LEN = 12
_KEY_LEN = 32  # AES-256
_PREAMBLE = bytes([VERSION])


class VaultError(Exception):
    """Base error for all vault operations."""


class VaultLockedError(VaultError):
    """Raised when an operation needs a DEK that is not available."""


class VaultIntegrityError(VaultError):
    """Raised when ciphertext fails authentication (tampered / wrong key)."""


# ---------------------------------------------------------------------------
# Encoding helpers
# ---------------------------------------------------------------------------

def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _b64d(data: str) -> bytes:
    return base64.b64decode(data.encode("ascii"), altchars=b"-_", validate=True)


def zeroize(buf: bytearray) -> None:
    """Best-effort in-place scrub of mutable key material."""
    for i in range(len(buf)):
        buf[i] = 0


# ---------------------------------------------------------------------------
# DEK generation / wrap / unwrap
# ---------------------------------------------------------------------------

def generate_dek() -> bytes:
    """Generate a fresh 256-bit Data-Encryption-Key."""
    return os.urandom(_KEY_LEN)


def wrap_dek(dek: bytes, kek: bytes) -> str:
    """Wrap (encrypt) a DEK with a KEK. Returns a versioned b64 blob."""
    aes = AESGCM(kek)
    nonce = os.urandom(_NONCE_LEN)
    ct = aes.encrypt(nonce, dek, associated_data=_PREAMBLE)
    return _b64e(_PREAMBLE + nonce + ct)


def unwrap_dek(blob: str, kek: bytes) -> bytes:
    """Unwrap a DEK. Raises VaultIntegrityError on tamper/wrong key."""
    try:
        raw = _b64d(blob)
    except Exception as exc:
        raise VaultIntegrityError("Corrupt wrapped-DEK blob (invalid encoding)") from exc
    if len(raw) < 1 + _NONCE_LEN + 16 or raw[0] != VERSION:
        raise VaultIntegrityError("Unsupported or corrupt wrapped-DEK blob")
    aes = AESGCM(kek)
    nonce, ct = raw[1 : 1 + _NONCE_LEN], raw[1 + _NONCE_LEN :]
    try:
        return aes.decrypt(nonce, ct, associated_data=_PREAMBLE)
    except Exception as exc:
        raise VaultIntegrityError("DEK unwrap failed — wrong KEK or tampered blob") from exc


# ---------------------------------------------------------------------------
# Payload encryption (AES-256-GCM, versioned, AAD-bound)
# ---------------------------------------------------------------------------

def encrypt_payload(dek: bytes, plaintext: bytes, *, aad: bytes = b"") -> str:
    """Encrypt arbitrary bytes under the user DEK. AAD binds the ciphertext
    to its context (e.g. b"<user_id>:node:<node_id>") so a ciphertext row
    cannot be cut-and-pasted into another user's scope undetected."""
    aes = AESGCM(dek)
    nonce = os.urandom(_NONCE_LEN)
    ct = aes.encrypt(nonce, plaintext, associated_data=_PREAMBLE + aad)
    return _b64e(_PREAMBLE + nonce + ct)


def decrypt_payload(dek: bytes, blob: str, *, aad: bytes = b"") -> bytes:
    """Decrypt a payload blob. Raises VaultIntegrityError on tamper."""
    try:
        raw = _b64d(blob)
    except Exception as exc:
        raise VaultIntegrityError("Corrupt payload blob (invalid encoding)") from exc
    if len(raw) < 1 + _NONCE_LEN + 16 or raw[0] != VERSION:
        raise VaultIntegrityError("Unsupported or corrupt payload blob")
    aes = AESGCM(dek)
    nonce, ct = raw[1 : 1 + _NONCE_LEN], raw[1 + _NONCE_LEN :]
    try:
        return aes.decrypt(nonce, ct, associated_data=_PREAMBLE + aad)
    except Exception as exc:
        raise VaultIntegrityError("Payload decrypt failed — tampered or wrong DEK") from exc


# ---------------------------------------------------------------------------
# Mode B: passphrase-derived KEK (Argon2id)
# ---------------------------------------------------------------------------

def derive_kek_from_passphrase(
    passphrase: str,
    salt: bytes,
    *,
    time_cost: int = 3,
    memory_kib: int = 64 * 1024,
    parallelism: int = 2,
) -> bytes:
    """Derive a 256-bit KEK from a user passphrase using Argon2id.

    Parameters are stored alongside the wrapped DEK so cost factors can be
    raised later without invalidating existing rows (re-wrap on next unlock).
    """
    from argon2.low_level import Type, hash_secret_raw  # argon2-cffi

    return hash_secret_raw(
        secret=passphrase.encode("utf-8"),
        salt=salt,
        time_cost=time_cost,
        memory_cost=memory_kib,
        parallelism=parallelism,
        hash_len=_KEY_LEN,
        type=Type.ID,
    )


def derive_server_kek(env_value: str) -> bytes:
    """Normalize the server KEK from an env var.
    
    Accepts only a base64url-encoded 32-byte key. Raises ValueError
    for invalid or wrong-length values so misconfiguration causes
    startup failure rather than silently producing a weak key.
    """
    try:
        raw = _b64d(env_value)
    except Exception as exc:
        raise ValueError(
            f"BRAIN_KEK must be base64url-encoded 32-byte key, got un-decodable value: {exc}"
        ) from exc
    if len(raw) != _KEY_LEN:
        raise ValueError(
            f"BRAIN_KEK must decode to exactly {_KEY_LEN} bytes, got {len(raw)}"
        )
    return raw


# ---------------------------------------------------------------------------
# Deterministic blind index (search without decryption)
# ---------------------------------------------------------------------------

def blind_index(dek: bytes, term: str) -> str:
    """HMAC-based blind index for exact-match lookups over encrypted rows.

    Lets the DB deduplicate entities without storing the term in plaintext.
    NOT for semantic search — that runs over embeddings. HMAC output is
    truncated to 16 bytes (b64) to save space.
    """
    digest = hmac.new(dek, f"blind:{term.strip().lower()}".encode(), hashlib.sha256).digest()
    return _b64e(digest[:16])


# ---------------------------------------------------------------------------
# Session unlock token (Mode B request-scoped key transport)
# ---------------------------------------------------------------------------

@dataclass
class UnlockedVault:
    """Request-scoped handle holding an unwrapped DEK.

    Use as a context manager; zeroizes the DEK copy on exit. Never store
    this object beyond the request lifecycle — never in caches, never in
    module state.
    """

    _dek: bytearray

    @classmethod
    def from_dek(cls, dek: bytes) -> "UnlockedVault":
        return cls(bytearray(dek))

    @property
    def dek(self) -> bytes:
        return bytes(self._dek)

    def encrypt_text(self, text: str, *, aad: bytes = b"") -> str:
        return encrypt_payload(self.dek, text.encode("utf-8"), aad=aad)

    def decrypt_text(self, blob: str, *, aad: bytes = b"") -> str:
        return decrypt_payload(self.dek, blob, aad=aad).decode("utf-8")

    def close(self) -> None:
        zeroize(self._dek)

    def __enter__(self) -> "UnlockedVault":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    dek = generate_dek()
    kek = derive_server_kek("1V9Sqomm-WYxic9b-N9usvKJjMGB2JL4zt6P-DdYJoA=")
    wrapped = wrap_dek(dek, kek)
    assert unwrap_dek(wrapped, kek) == dek

    with UnlockedVault.from_dek(dek) as vault:
        blob = vault.encrypt_text("suffering arises from attachment", aad=b"u1:node:42")
        assert vault.decrypt_text(blob, aad=b"u1:node:42") == "suffering arises from attachment"
        try:
            vault.decrypt_text(blob, aad=b"u2:node:42")  # wrong AAD → must fail
            raise AssertionError("AAD bypass!")
        except VaultIntegrityError:
            pass

    # Mode B round-trip
    salt = os.urandom(16)
    kek_b = derive_kek_from_passphrase("correct horse battery staple", salt)
    wrapped_b = wrap_dek(dek, kek_b)
    assert unwrap_dek(wrapped_b, derive_kek_from_passphrase("correct horse battery staple", salt)) == dek

    print("vault crypto self-test: OK")
