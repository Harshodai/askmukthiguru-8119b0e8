"""Mukthi Vault — Second Brain API router.

Mount in app/main.py:

    from app.api.second_brain import router as second_brain_router
    app.include_router(second_brain_router, prefix="/api")

Every endpoint requires the caller's own Supabase JWT — the dev-mode
"anonymous" fallback user (services.auth_service.get_current_user_from_supabase)
is explicitly rejected, since a per-user encrypted vault has no meaning for a
shared placeholder id. The vault is unlocked per-request and zeroized at the
end of the request — keys never touch caches, logs, or disk.

Mode-B clients send the passphrase-derived unlock via the `X-Brain-Unlock`
header (the passphrase itself never crosses the wire as-is — see
src/pages/SecondBrainPage.tsx for the client-side derivation). For Mode-A
vaults the header is simply omitted.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.dependencies import get_container
from services.auth_service import get_current_user_from_supabase
from services.second_brain.crypto import UnlockedVault, VaultLockedError
from services.second_brain.second_brain_service import SecondBrainService

router = APIRouter(tags=["Second Brain"])


def _svc() -> SecondBrainService:
    svc = get_container().second_brain
    if svc is None:
        raise HTTPException(status_code=503, detail="Second Brain is not initialized.")
    return svc


async def _authed_user_id(user: dict = Depends(get_current_user_from_supabase)) -> str:
    """Real per-user id only — rejects the anonymous dev-mode fallback."""
    user_id = user.get("id")
    if not user_id or user.get("is_anonymous") or user_id == "anonymous":
        raise HTTPException(status_code=401, detail="Authentication required.")
    return user_id


async def _vault(
    user_id: str = Depends(_authed_user_id),
    x_brain_unlock: Optional[str] = Header(default=None),
) -> UnlockedVault:
    try:
        return await _svc().unlock(user_id, passphrase=x_brain_unlock)
    except VaultLockedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ProvisionResponse(BaseModel):
    user_id: str
    wrap_mode: str
    created: bool


class EnableUnlockRequest(BaseModel):
    passphrase: str = Field(min_length=8, max_length=256)


class AddItemRequest(BaseModel):
    kind: str = Field(pattern="^(reflection|entity|preference|relationship|journal)$")
    text: str = Field(min_length=1, max_length=8000)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class BrainItemOut(BaseModel):
    id: str
    kind: str
    text: str
    confidence: float
    created_at: float
    access_count: int


# ---------------------------------------------------------------------------
# Vault lifecycle
# ---------------------------------------------------------------------------

@router.post("/brain/vault", response_model=ProvisionResponse)
async def provision(user_id: str = Depends(_authed_user_id)):
    return await _svc().provision_vault(user_id)


@router.post("/brain/vault/session-unlock")
async def enable_session_unlock(
    body: EnableUnlockRequest,
    user_id: str = Depends(_authed_user_id),
):
    """Upgrade to owner-blind mode. Irreversible without the passphrase."""
    return await _svc().enable_session_unlock(user_id, body.passphrase)


@router.delete("/brain/vault")
async def shred(user_id: str = Depends(_authed_user_id)):
    """Permanently destroy the entire Second Brain (crypto-shredding)."""
    return await _svc().crypto_shred(user_id)


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------

@router.post("/brain/items", response_model=dict)
async def add_item(
    body: AddItemRequest,
    user_id: str = Depends(_authed_user_id),
    vault: UnlockedVault = Depends(_vault),
):
    with vault:
        item_id = await _svc().add_item(
            user_id, body.kind, body.text, vault=vault, confidence=body.confidence
        )
    return {"id": item_id}


@router.get("/brain/items", response_model=list[BrainItemOut])
async def list_items(
    kind: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    user_id: str = Depends(_authed_user_id),
    vault: UnlockedVault = Depends(_vault),
):
    with vault:
        items = await _svc().list_items(user_id, vault=vault, kind=kind,
                                        limit=min(limit, 500), offset=offset)
    return [BrainItemOut(**vars(i)) for i in items]


@router.delete("/brain/items/{item_id}")
async def forget_item(item_id: str, user_id: str = Depends(_authed_user_id)):
    ok = await _svc().forget_item(user_id, item_id)
    return {"forgotten": ok}


# ---------------------------------------------------------------------------
# Recall (used by the chat pipeline; also powers the 'brain recap' screen)
# ---------------------------------------------------------------------------

@router.get("/brain/recall", response_model=list[BrainItemOut])
async def recall(
    q: str = "",
    limit: int = 8,
    user_id: str = Depends(_authed_user_id),
    vault: UnlockedVault = Depends(_vault),
):
    with vault:
        items = await _svc().personal_context(user_id, q, vault=vault, limit=min(limit, 20))
    return [BrainItemOut(**vars(i)) for i in items]


# ---------------------------------------------------------------------------
# Export (GDPR/DSAR) — owner session only
# ---------------------------------------------------------------------------

@router.get("/brain/export")
async def export_brain(
    user_id: str = Depends(_authed_user_id),
    vault: UnlockedVault = Depends(_vault),
):
    with vault:
        return await _svc().export(user_id, vault=vault)


# ---------------------------------------------------------------------------
# There is deliberately NO admin read endpoint here.
# Support tooling must operate on ciphertext/metadata only.
# ---------------------------------------------------------------------------
