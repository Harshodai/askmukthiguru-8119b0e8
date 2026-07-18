"""Mukthi Vault — per-user, owner-blind encrypted knowledge graph (Second Brain).

- crypto: envelope encryption primitives (DEK/KEK, AES-256-GCM, Argon2id).
- second_brain_service: provisioning, extraction, encrypted CRUD, erasure, export.
- vault_index: shared Qdrant collection for semantic recall, user_id-filtered.

Mode A (default): server-wrapped DEK (BRAIN_KEK env). Mode B (opt-in,
"Private Mode"): passphrase-derived KEK via Argon2id — owner-blind, even an
operator holding the DB and BRAIN_KEK cannot decrypt without the passphrase.
"""

from services.second_brain.crypto import (
    UnlockedVault,
    VaultError,
    VaultIntegrityError,
    VaultLockedError,
)
from services.second_brain.second_brain_service import BrainItem, SecondBrainService
from services.second_brain.vault_index import VaultIndex

__all__ = [
    "BrainItem",
    "SecondBrainService",
    "UnlockedVault",
    "VaultError",
    "VaultIndex",
    "VaultIntegrityError",
    "VaultLockedError",
]
