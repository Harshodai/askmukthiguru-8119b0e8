"""
FastAPI WhatsApp Integration Router.
===================================

Provides:
  1. Meta WhatsApp Cloud API Webhook Handling:
     - GET /api/whatsapp/webhook: Webhook verification challenge (hub.mode, hub.challenge, hub.verify_token)
     - POST /api/whatsapp/webhook: HMAC-SHA256 signature verification (X-Hub-Signature-256),
       idempotent event parsing, immediate commands (STOP/RESET/HELP/LINK/UNLINK),
       crisis preemption (Tele-MANAS 14416 / 112), and durable Celery task dispatch.
  2. Cryptographic Account Linking:
     - POST /api/whatsapp/link/start: Generate time-bounded single-use linking token.
     - POST /api/whatsapp/link/verify: Authenticated web user binds WhatsApp number to account.
     - GET /api/whatsapp/link/status: Retrieve connection status and masked phone.
     - POST /api/whatsapp/link/consent: Decoupled DPDP consent updates (history sync vs memory).
     - POST /api/whatsapp/link/unlink: Revoke channel binding.
"""

from __future__ import annotations

import collections
import logging
import os
import time
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field

from app.config import settings
from app.dependencies import ServiceContainer, get_container_async
from services.auth_service import get_current_user_from_supabase
from services.whatsapp_service import (
    CRISIS_HELPLINE_COPY,
    clean_phone,
    create_link_challenge,
    format_whatsapp_message,
    get_link_status,
    likely_crisis,
    mask_phone,
    unlink_account,
    update_link_consent,
    validate_meta_signature,
    verify_link_challenge,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WhatsApp"])

# In-memory deduplication cache for recent webhook message IDs (wamid)
_SEEN_MSG_IDS: collections.deque[str] = collections.deque(maxlen=1000)
_SEEN_SET: set[str] = set()


def _is_duplicate_event(event_id: str) -> bool:
    """Check and record event_id for deduplication."""
    if not event_id:
        return False
    if event_id in _SEEN_SET:
        return True
    if len(_SEEN_MSG_IDS) >= 1000:
        evicted = _SEEN_MSG_IDS.popleft()
        _SEEN_SET.discard(evicted)
    _SEEN_MSG_IDS.append(event_id)
    _SEEN_SET.add(event_id)
    return False


# ---------------------------------------------------------------------------
# Request / Response Schemas
# ---------------------------------------------------------------------------

class LinkStartRequest(BaseModel):
    phone: str = Field(..., description="E.164 phone number to link")


class LinkVerifyRequest(BaseModel):
    code: str = Field(..., description="Single-use challenge token from WhatsApp")


class LinkConsentRequest(BaseModel):
    sync_history_consent: bool | None = Field(None, description="DPDP consent for chat history sync")
    memory_write_consent: bool | None = Field(None, description="DPDP consent for long-term spiritual memory")


# ---------------------------------------------------------------------------
# Meta Cloud API Webhook Endpoints
# ---------------------------------------------------------------------------

@router.get("/webhook")
async def meta_webhook_verification(
    hub_mode: str | None = Query(None, alias="hub.mode"),
    hub_challenge: str | None = Query(None, alias="hub.challenge"),
    hub_verify_token: str | None = Query(None, alias="hub.verify_token"),
) -> Response:
    """
    Verification challenge endpoint for Meta WhatsApp Cloud API Webhook.
    Meta sends GET request with hub.mode, hub.challenge, hub.verify_token.
    """
    expected_token = (
        getattr(settings, "meta_verify_token", "")
        or os.environ.get("META_VERIFY_TOKEN", os.environ.get("WHATSAPP_VERIFY_TOKEN", ""))
    ).strip()

    if hub_mode == "subscribe" and hub_verify_token and hub_verify_token == expected_token:
        logger.info("Meta webhook verification challenge succeeded")
        return Response(content=str(hub_challenge or ""), media_type="text/plain", status_code=200)

    logger.warning("Meta webhook verification failed: Token mismatch or invalid mode")
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


@router.post("/webhook")
async def meta_webhook_receiver(
    request: Request,
    x_hub_signature_256: str | None = Header(None, alias="X-Hub-Signature-256"),
    container: ServiceContainer = Depends(get_container_async),
) -> dict[str, Any]:
    """
    Receives incoming WhatsApp Cloud API events (messages and status callbacks).
    Validates HMAC-SHA256 signature, deduplicates events, and routes through Celery.
    """
    raw_body = await request.body()
    app_secret = (
        getattr(settings, "meta_app_secret", "")
        or os.environ.get("META_APP_SECRET", "")
    ).strip()

    # If secret is configured, strictly enforce signature verification fail-closed
    if app_secret:
        if not validate_meta_signature(raw_body, x_hub_signature_256, app_secret):
            logger.warning("Meta signature validation failed — rejecting request")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature")

    try:
        payload = await request.json()
    except Exception:
        logger.warning("Malformed JSON in WhatsApp webhook")
        return {"status": "malformed_json"}

    entry_list = payload.get("entry") or []
    for entry in entry_list:
        changes = entry.get("changes") or []
        for change in changes:
            val = change.get("value") or {}
            phone_number_id = (val.get("metadata") or {}).get("phone_number_id", "")

            # 1. Status / Delivery callbacks
            statuses = val.get("statuses") or []
            for st in statuses:
                st_id = st.get("id", "")
                st_status = st.get("status", "")
                recipient_id = st.get("recipient_id", "")
                errors = st.get("errors") or []
                if errors:
                    for err in errors:
                        err_code = err.get("code")
                        err_title = err.get("title", "")
                        err_msg = err.get("message", "")
                        if err_code == 131047:
                            logger.warning(
                                "WhatsApp delivery window expired (code 131047): recipient=%s, msg_id=%s. User must initiate contact.",
                                mask_phone(recipient_id),
                                st_id,
                            )
                        else:
                            logger.error(
                                "WhatsApp delivery error: code=%s, title=%s, msg=%s, recipient=%s",
                                err_code,
                                err_title,
                                err_msg,
                                mask_phone(recipient_id),
                            )
                else:
                    logger.info(
                        "WhatsApp delivery callback: msg_id=%s, status=%s, recipient=%s",
                        st_id,
                        st_status,
                        mask_phone(recipient_id),
                    )

            # 2. Inbound Messages
            messages = val.get("messages") or []
            for msg in messages:
                wamid = msg.get("id", "")
                from_number = msg.get("from", "")
                msg_type = msg.get("type", "")

                if _is_duplicate_event(wamid):
                    logger.info("Ignoring duplicate WhatsApp message %s", wamid)
                    continue

                if msg_type != "text":
                    logger.info("Non-text WhatsApp message (%s) from %s", msg_type, mask_phone(from_number))
                    continue

                text_body = ((msg.get("text") or {}).get("body") or "").strip()
                if not text_body:
                    continue

                clean_from = clean_phone(from_number)
                upper_body = text_body.upper().strip()

                # A. Immediate Privacy Commands
                db = getattr(container, "supabase_client", None)
                base_url = getattr(settings, "whatsapp_link_base_url", "https://askmukthiguru.com").rstrip("/")

                if upper_body in ("LINK", "CONNECT"):
                    # Generate single-use linking challenge
                    try:
                        token = None
                        if db:
                            token, _ = await create_link_challenge(db, clean_from, confirmed_whatsapp=True)
                        if not token:
                            from services.whatsapp_service import generate_link_token
                            token = generate_link_token()

                        link_url = f"{base_url}/link-whatsapp#code={token}"
                        link_msg = (
                            "🔗 *Connect AskMukthiGuru Account*\n\n"
                            "To link this WhatsApp number with your website profile, open:\n"
                            f"{link_url}\n\n"
                            "⏳ This one-time link expires in 15 minutes.\n"
                            "🔒 Never share this link with anyone.\n"
                            "You can review and control chat sync and memory preferences in your Profile."
                        )
                        from tasks.whatsapp_tasks import _send_meta_outbound
                        _send_meta_outbound(phone_number_id, clean_from, link_msg)
                        continue
                    except Exception as e:
                        logger.exception("Failed generating link challenge: %s", e)

                if upper_body in ("STOP", "OPTOUT", "UNSUBSCRIBE"):
                    logger.info("WhatsApp user %s sent STOP", mask_phone(clean_from))
                    stop_msg = (
                        "🛑 You have opted out of AskMukthiGuru messages on WhatsApp. "
                        "No further automated messages will be sent. Send START at any time to resume."
                    )
                    from tasks.whatsapp_tasks import _send_meta_outbound
                    _send_meta_outbound(phone_number_id, clean_from, stop_msg)
                    continue

                if upper_body in ("RESET", "CLEAR"):
                    reset_msg = "🧹 Fresh page. Your WhatsApp conversation context has been reset. What would you like to ask?"
                    from tasks.whatsapp_tasks import _send_meta_outbound
                    _send_meta_outbound(phone_number_id, clean_from, reset_msg)
                    continue

                if upper_body in ("HELP", "INFO"):
                    help_msg = (
                        "🙏 *AskMukthiGuru on WhatsApp*\n\n"
                        "Ask any question regarding meditation, spiritual teachings, or inner peace.\n\n"
                        "• *LINK*: Connect your WhatsApp with your AskMukthiGuru web account.\n"
                        "• *RESET*: Clear active conversation context.\n"
                        "• *STOP*: Opt out from automated messages.\n\n"
                        "For urgent support, call Tele-MANAS at *14416* (24/7, India)."
                    )
                    from tasks.whatsapp_tasks import _send_meta_outbound
                    _send_meta_outbound(phone_number_id, clean_from, help_msg)
                    continue

                # B. Crisis Preemption
                if likely_crisis(text_body):
                    logger.warning("Crisis detected in WhatsApp message from %s; preempting", mask_phone(clean_from))
                    from tasks.whatsapp_tasks import _send_meta_outbound
                    _send_meta_outbound(phone_number_id, clean_from, CRISIS_HELPLINE_COPY)
                    continue

                # C. Dispatch to Celery for Durable Execution
                try:
                    from tasks.whatsapp_tasks import process_whatsapp_turn_task
                    process_whatsapp_turn_task.delay(
                        channel="meta",
                        phone=clean_from,
                        user_message=text_body,
                        metadata={"wamid": wamid, "phone_number_id": phone_number_id},
                    )
                    logger.info("Enqueued Celery task for WhatsApp message %s", wamid)
                except Exception as exc:
                    logger.warning("Celery dispatch unavailable (%s); executing inline", exc)
                    from tasks.whatsapp_tasks import process_whatsapp_turn_task
                    process_whatsapp_turn_task(
                        channel="meta",
                        phone=clean_from,
                        user_message=text_body,
                        metadata={"wamid": wamid, "phone_number_id": phone_number_id},
                    )

    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Account Linking & DPDP Consent Endpoints (Web App)
# ---------------------------------------------------------------------------

@router.post("/link/start")
async def start_account_link(
    body: LinkStartRequest,
    container: ServiceContainer = Depends(get_container_async),
) -> dict[str, Any]:
    """Generate a single-use linking token for a given phone number."""
    db = getattr(container, "supabase_client", None)
    if not db:
        raise HTTPException(status_code=501, detail="Database unavailable")

    try:
        raw_token, challenge = await create_link_challenge(
            db, body.phone, confirmed_whatsapp=False
        )
        base_url = getattr(settings, "whatsapp_link_base_url", "https://askmukthiguru.com").rstrip("/")
        return {
            "token": raw_token,
            "masked_phone": challenge["phone_number_masked"],
            "expires_at": challenge["expires_at"],
            "link_url": f"{base_url}/link-whatsapp#code={raw_token}",
        }
    except Exception as exc:
        logger.exception("Failed starting account link: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/link/verify")
async def verify_account_link(
    body: LinkVerifyRequest,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container_async),
) -> dict[str, Any]:
    """
    Verify single-use token and bind phone number to the authenticated web user.
    Enforces DPDP decoupling: channel history sync and long-term memory default to False.
    """
    db = getattr(container, "supabase_client", None)
    if not db:
        raise HTTPException(status_code=501, detail="Database unavailable")

    user_id = user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        link = await verify_link_challenge(db, body.code, user_id)
        return {
            "success": True,
            "masked_phone": link.get("phone_number_masked"),
            "sync_history_consent": False,
            "memory_write_consent": False,
            "linked_at": link.get("linked_at"),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error verifying link challenge: %s", exc)
        raise HTTPException(status_code=500, detail="Unable to complete account linking")


@router.get("/link/status")
async def account_link_status(
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container_async),
) -> dict[str, Any]:
    """Retrieve WhatsApp connection status and DPDP consent settings for current user."""
    db = getattr(container, "supabase_client", None)
    if not db:
        raise HTTPException(status_code=501, detail="Database unavailable")

    user_id = user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    return await get_link_status(db, user_id)


@router.post("/link/consent")
async def update_account_consent(
    body: LinkConsentRequest,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container_async),
) -> dict[str, Any]:
    """Update DPDP decoupled consent flags for WhatsApp channel."""
    db = getattr(container, "supabase_client", None)
    if not db:
        raise HTTPException(status_code=501, detail="Database unavailable")

    user_id = user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        return await update_link_consent(
            db,
            user_id,
            sync_history_consent=body.sync_history_consent,
            memory_write_consent=body.memory_write_consent,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("Failed updating consent: %s", exc)
        raise HTTPException(status_code=500, detail="Consent update failed")


@router.post("/link/unlink")
async def disconnect_account(
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container_async),
) -> dict[str, Any]:
    """Disconnect WhatsApp number and revoke channel binding."""
    db = getattr(container, "supabase_client", None)
    if not db:
        raise HTTPException(status_code=501, detail="Database unavailable")

    user_id = user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    success = await unlink_account(db, user_id)
    return {"success": success, "status": "unlinked"}
