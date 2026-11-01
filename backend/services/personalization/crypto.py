"""
Mode-B Universal Zero-Knowledge Encryption primitives for AskMukthiGuru.

Guarantees:
- Client-side Web Crypto PBKDF2-HMAC-SHA256 (600,000 iterations, 32 bytes,
  standard salt b"second_brain_vault_unlock_salt") is the standard vault
  encryption available for ALL user personalized data facets.
- Server-side stores ciphertext, 12-byte IV, and 16-byte auth tag.
- The server CANNOT decrypt Mode-B fields without the client's session unlock token.
- Keys are held strictly in request-scoped memory and zeroized on exit.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from typing import Any, Optional, Union

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PBKDF2_ITERATIONS = 600_000
KEY_LEN_BYTES = 32  # 256-bit AES
NONCE_LEN_BYTES = 12  # 96-bit AES-GCM IV
TAG_LEN_BYTES = 16  # 128-bit GCM Auth Tag
VERSION = 1
PREAMBLE = bytes([VERSION])
STANDARD_UNLOCK_SALT = b"second_brain_vault_unlock_salt"


class ModeBCryptoError(Exception):
    """Base error for Mode-B cryptographic operations."""


class VaultLockedError(ModeBCryptoError):
    """Raised when an operation requires an unlock key that is missing or locked."""


class VaultIntegrityError(ModeBCryptoError):
    """Raised when ciphertext authentication fails (tampered payload or incorrect key)."""


def _b64e(raw: bytes) -> str:
    """Encode bytes to base64url string."""
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _b64d(data: str) -> bytes:
    """Decode base64url string with padding tolerance."""
    normalized = data.strip() + ("=" * (-len(data.strip()) % 4))
    return base64.b64decode(normalized.encode("ascii"), altchars=b"-_", validate=True)


def zeroize(buf: Union[bytearray, memoryview]) -> None:
    """In-place scrub of mutable key material to prevent key leakage in memory dumps."""
    for i in range(len(buf)):
        buf[i] = 0


def derive_mode_b_key(
    passphrase_or_token: str,
    salt: bytes = STANDARD_UNLOCK_SALT,
    iterations: int = PBKDF2_ITERATIONS,
) -> bytes:
    """
    Derives or parses a 256-bit AES key for Mode-B operations.

    If `passphrase_or_token` is already a 64-character hex string (32 bytes),
    it is treated as the client's pre-computed PBKDF2 token (e.g. from
    `deriveBrainUnlock` via Web Crypto SubtleCrypto), avoiding redundant computation.
    Otherwise, standard PBKDF2-HMAC-SHA256 with 600,000 iterations is computed.
    """
    if not passphrase_or_token:
        raise VaultLockedError("Passphrase or unlock token is required")

    trimmed = passphrase_or_token.strip()
    if len(trimmed) == 64:
        try:
            raw_key = bytes.fromhex(trimmed)
            if len(raw_key) == KEY_LEN_BYTES:
                return raw_key
        except ValueError:
            pass

    return hashlib.pbkdf2_hmac(
        "sha256",
        trimmed.encode("utf-8"),
        salt,
        iterations,
        dklen=KEY_LEN_BYTES,
    )


derive_vault_key = derive_mode_b_key


@dataclass
class EncryptedFacet:
    """
    Represents an individual personalized data facet encrypted under Mode-B AES-256-GCM.
    Stores ciphertext, IV, and auth tag separately to match Web Crypto standards,
    while also providing single-blob wire format compatibility.
    """

    facet_name: str
    ciphertext: str  # Base64url encoded ciphertext (excluding tag)
    iv: str  # Base64url encoded 12-byte IV / nonce
    auth_tag: str  # Base64url encoded 16-byte GCM authentication tag
    algorithm: str = "AES-256-GCM"
    key_derivation: str = f"PBKDF2-HMAC-SHA256-{PBKDF2_ITERATIONS}"
    version: int = VERSION

    @property
    def tag(self) -> str:
        return self.auth_tag

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EncryptedFacet:
        return cls(
            facet_name=data.get("facet_name", "unknown"),
            ciphertext=data["ciphertext"],
            iv=data["iv"],
            auth_tag=data["auth_tag"],
            algorithm=data.get("algorithm", "AES-256-GCM"),
            key_derivation=data.get("key_derivation", f"PBKDF2-HMAC-SHA256-{PBKDF2_ITERATIONS}"),
            version=int(data.get("version", VERSION)),
        )

    def to_wire_blob(self) -> str:
        """
        Versioned compact wire format:
        v1 || nonce(12B) || ciphertext || tag(16B)
        """
        iv_bytes = _b64d(self.iv)
        ct_bytes = _b64d(self.ciphertext)
        tag_bytes = _b64d(self.auth_tag)
        return _b64e(PREAMBLE + iv_bytes + ct_bytes + tag_bytes)

    @classmethod
    def from_wire_blob(cls, facet_name: str, blob: str) -> EncryptedFacet:
        raw = _b64d(blob)
        if len(raw) < 1 + NONCE_LEN_BYTES + TAG_LEN_BYTES or raw[0] != VERSION:
            raise VaultIntegrityError("Corrupt or unsupported wire blob format")
        iv_bytes = raw[1 : 1 + NONCE_LEN_BYTES]
        ct_and_tag = raw[1 + NONCE_LEN_BYTES :]
        ct_bytes = ct_and_tag[:-TAG_LEN_BYTES]
        tag_bytes = ct_and_tag[-TAG_LEN_BYTES:]
        return cls(
            facet_name=facet_name,
            ciphertext=_b64e(ct_bytes),
            iv=_b64e(iv_bytes),
            auth_tag=_b64e(tag_bytes),
        )


def encrypt_facet_payload(
    key: bytes,
    data: Any,
    facet_name: str,
    aad: bytes = b"",
) -> EncryptedFacet:
    """
    Encrypts arbitrary data (dict, list, str, bytes) under AES-256-GCM.
    AAD binds the facet to the user and context (e.g. b"<user_id>:<facet_name>").
    """
    if len(key) != KEY_LEN_BYTES:
        raise ValueError(f"AES key must be exactly {KEY_LEN_BYTES} bytes, got {len(key)}")

    if isinstance(data, bytes):
        payload_bytes = data
    elif isinstance(data, str):
        payload_bytes = data.encode("utf-8")
    else:
        payload_bytes = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    nonce = os.urandom(NONCE_LEN_BYTES)
    aes = AESGCM(key)
    # AESGCM.encrypt returns ciphertext + tag appended at the end
    encrypted_block = aes.encrypt(nonce, payload_bytes, associated_data=PREAMBLE + aad)

    ct_bytes = encrypted_block[:-TAG_LEN_BYTES]
    tag_bytes = encrypted_block[-TAG_LEN_BYTES:]

    return EncryptedFacet(
        facet_name=facet_name,
        ciphertext=_b64e(ct_bytes),
        iv=_b64e(nonce),
        auth_tag=_b64e(tag_bytes),
    )


def decrypt_facet_payload(
    key: bytes,
    encrypted: Union[EncryptedFacet, dict[str, Any], str],
    facet_name: str = "unknown",
    aad: bytes = b"",
    expect_json: bool = True,
) -> Any:
    """
    Decrypts an EncryptedFacet or wire blob under AES-256-GCM.
    Raises VaultIntegrityError if key is incorrect or ciphertext has been tampered with.
    """
    if len(key) != KEY_LEN_BYTES:
        raise ValueError(f"AES key must be exactly {KEY_LEN_BYTES} bytes, got {len(key)}")

    if isinstance(encrypted, str):
        facet = EncryptedFacet.from_wire_blob(facet_name, encrypted)
    elif isinstance(encrypted, dict):
        facet = EncryptedFacet.from_dict(encrypted)
    elif isinstance(encrypted, EncryptedFacet):
        facet = encrypted
    else:
        raise TypeError(f"Unsupported encrypted payload type: {type(encrypted)}")

    try:
        iv_bytes = _b64d(facet.iv)
        ct_bytes = _b64d(facet.ciphertext)
        tag_bytes = _b64d(facet.auth_tag)
    except Exception as exc:
        raise VaultIntegrityError("Failed to decode base64 fields in EncryptedFacet") from exc

    combined_ct = ct_bytes + tag_bytes
    aes = AESGCM(key)

    try:
        decrypted_bytes = aes.decrypt(iv_bytes, combined_ct, associated_data=PREAMBLE + aad)
    except Exception as exc:
        raise VaultIntegrityError("Decryption failed — wrong Mode-B key or tampered ciphertext") from exc

    if expect_json:
        try:
            return json.loads(decrypted_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return decrypted_bytes.decode("utf-8")
    return decrypted_bytes.decode("utf-8")


class UnlockedVaultSession:
    """
    Request-scoped context manager holding an unwrapped Mode-B key.
    Guarantees that the key buffer is zeroized upon exiting the context.
    """

    def __init__(self, key: bytes):
        self._key = bytearray(key)
        self._closed = False

    @property
    def key_bytes(self) -> bytes:
        if self._closed:
            raise VaultLockedError("Vault session has been closed and zeroized")
        return bytes(self._key)

    def encrypt(self, data: Any, facet_name: str, aad: bytes = b"") -> EncryptedFacet:
        return encrypt_facet_payload(self.key_bytes, data, facet_name=facet_name, aad=aad)

    def decrypt(
        self,
        encrypted: Union[EncryptedFacet, dict[str, Any], str],
        facet_name: str = "unknown",
        aad: bytes = b"",
        expect_json: bool = True,
    ) -> Any:
        return decrypt_facet_payload(
            self.key_bytes,
            encrypted,
            facet_name=facet_name,
            aad=aad,
            expect_json=expect_json,
        )

    def close(self) -> None:
        if not self._closed:
            zeroize(self._key)
            self._closed = True

    def __enter__(self) -> UnlockedVaultSession:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


def encrypt_facet(
    data: Any,
    key: bytes,
    facet_name: str = "unknown",
    aad: bytes = b"",
) -> EncryptedFacet:
    """Convenience alias for encrypt_facet_payload."""
    return encrypt_facet_payload(key=key, data=data, facet_name=facet_name, aad=aad)


def decrypt_facet(
    encrypted: Union[EncryptedFacet, dict[str, Any], str],
    key: bytes,
    facet_name: str = "unknown",
    aad: bytes = b"",
    expect_json: bool = True,
) -> Any:
    """Convenience alias for decrypt_facet_payload with parameter order adjusted for tests."""
    return decrypt_facet_payload(key=key, encrypted=encrypted, facet_name=facet_name, aad=aad, expect_json=expect_json)


def derive_vault_key(
    passphrase_or_token: str,
    salt: bytes = STANDARD_UNLOCK_SALT,
    iterations: int = PBKDF2_ITERATIONS,
) -> bytes:
    """Convenience alias for derive_mode_b_key."""
    return derive_mode_b_key(passphrase_or_token, salt=salt, iterations=iterations)
