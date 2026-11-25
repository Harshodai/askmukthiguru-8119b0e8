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
    build_meta_interactive_buttons,
    clean_phone,
    clear_whatsapp_session,
    create_link_challenge,
    format_whatsapp_message,
    get_account_link_by_phone,
    get_link_status,
    hash_phone,
    is_whatsapp_ai_paused,
    likely_crisis,
    mask_phone,
    optout_account_by_phone,
    pause_whatsapp_ai,
    resume_account_by_phone,
    resume_whatsapp_ai,
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
    sync_history_consent: bool | None = Field(None, description="DPDP consent for chat history sync")
    memory_write_consent: bool | None = Field(None, description="DPDP consent for long-term spiritual memory")


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
    expected_token = getattr(settings, "meta_verify_token", "").strip()

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
    app_secret = getattr(settings, "meta_app_secret", "").strip()

    # If secret is configured, strictly enforce signature verification fail-closed
    if app_secret:
        if not validate_meta_signature(raw_body, x_hub_signature_256, app_secret):
            logger.warning("Meta signature validation failed — rejecting request")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature")
    elif getattr(settings, "is_production", False):
        logger.error("META_APP_SECRET is not configured in production — rejecting unverified webhook")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Signature verification required")

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
            configured_phone_id = getattr(settings, "meta_phone_number_id", "").strip()
            if configured_phone_id and phone_number_id and str(phone_number_id).strip() != configured_phone_id:
                logger.warning(
                    "Mismatched phone_number_id rejected: received=%s, configured=%s",
                    phone_number_id,
                    configured_phone_id,
                )
                continue

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

                text_body = ""
                if msg_type == "interactive":
                    interactive_obj = msg.get("interactive") or {}
                    reply_obj = interactive_obj.get("button_reply") or interactive_obj.get("list_reply") or {}
                    text_body = (reply_obj.get("id") or reply_obj.get("title") or "").strip()
                    logger.info("WhatsApp interactive reply received: %s from %s", text_body, mask_phone(from_number))
                elif msg_type == "text":
                    text_body = ((msg.get("text") or {}).get("body") or "").strip()
                else:
                    logger.info("Non-text WhatsApp message (%s) from %s", msg_type, mask_phone(from_number))
                    continue

                if not text_body:
                    continue

                clean_from = clean_phone(from_number)
                p_hash = hash_phone(clean_from)
                upper_body = text_body.upper().strip()

                # A. Immediate Privacy & Coexistence Commands
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
                    if db:
                        try:
                            await optout_account_by_phone(db, clean_from)
                        except Exception as e:
                            logger.error("Failed persisting STOP opt-out: %s", e)
                    clear_whatsapp_session(p_hash)
                    stop_msg = (
                        "🛑 You have opted out of AskMukthiGuru messages on WhatsApp. "
                        "No further automated messages will be sent. Send START at any time to resume."
                    )
                    from tasks.whatsapp_tasks import _send_meta_outbound
                    _send_meta_outbound(phone_number_id, clean_from, stop_msg)
                    continue

                if upper_body in ("RESET", "CLEAR"):
                    clear_whatsapp_session(p_hash)
                    reset_msg = "🧹 Fresh page. Your WhatsApp conversation context has been reset. What would you like to ask?"
                    from tasks.whatsapp_tasks import _send_meta_outbound
                    _send_meta_outbound(phone_number_id, clean_from, reset_msg)
                    continue

                # Human Coexistence Handoff: Pause automated AI for 60 min to let phone app operator reply directly
                if upper_body in ("HUMAN", "SUPPORT", "AGENT", "HELP_HUMAN", "BTN_HUMAN"):
                    pause_whatsapp_ai(p_hash, duration_seconds=3600)
                    human_msg = (
                        "🤝 *Connecting you to a Guide / Team Member*\n\n"
                        "Automated AI responses are paused for the next 60 minutes so our team can personally assist you directly on this chat.\n\n"
                        "To resume automated wisdom guidance sooner at any point, simply send *RESUME*."
                    )
                    from tasks.whatsapp_tasks import _send_meta_outbound
                    _send_meta_outbound(phone_number_id, clean_from, human_msg)
                    continue

                if upper_body in ("RESUME", "BTN_RESUME"):
                    resume_whatsapp_ai(p_hash)
                    resume_msg = (
                        "🙏 Welcome back! Automated guidance has been resumed. What reflection or inquiry is on your mind?"
                    )
                    from tasks.whatsapp_tasks import _send_meta_outbound
                    _send_meta_outbound(phone_number_id, clean_from, resume_msg)
                    continue

                # If AI is currently paused for human coexistence, ignore inbound turns
                if is_whatsapp_ai_paused(p_hash):
                    logger.info("WhatsApp AI paused for human coexistence on %s; ignoring turn", mask_phone(clean_from))
                    continue

                if upper_body in ("HELP", "INFO"):
                    help_msg = (
                        "🙏 *AskMukthiGuru on WhatsApp*\n\n"
                        "Ask any question regarding meditation, spiritual teachings, or inner peace.\n\n"
                        "• *LINK*: Connect your WhatsApp with your AskMukthiGuru web account.\n"
                        "• *RESET*: Clear active conversation context.\n"
                        "• *HUMAN*: Pause AI to speak with a human team member.\n"
                        "• *STOP*: Opt out from automated messages.\n\n"
                        "For urgent crisis support, call Tele-MANAS at *14416* (24/7, toll-free India)."
                    )
                    from tasks.whatsapp_tasks import _send_meta_outbound
                    _send_meta_outbound(phone_number_id, clean_from, help_msg)
                    continue

                # Interactive Quick Menu
                if upper_body in ("MENU", "OPTIONS"):
                    buttons = [
                        ("btn_ask", "Ask a Question"),
                        ("btn_practice", "Today's Practice"),
                        ("btn_human", "Human Help"),
                    ]
                    btn_payload = build_meta_interactive_buttons(
                        to_number=clean_from,
                        header_text="🙏 AskMukthiGuru Menu",
                        body_text="Choose an option below or type your spiritual question directly:",
                        buttons=buttons,
                    )
                    from tasks.whatsapp_tasks import _send_meta_interactive
                    _send_meta_interactive(phone_number_id, btn_payload)
                    continue

                if upper_body in ("BTN_ASK", "ASK A QUESTION"):
                    prompt_msg = "Please type any question you have on meditation, relationships, stress, or spiritual teachings from Sri Preethaji and Sri Krishnaji."
                    from tasks.whatsapp_tasks import _send_meta_outbound
                    _send_meta_outbound(phone_number_id, clean_from, prompt_msg)
                    continue

                if upper_body in ("BTN_PRACTICE", "TODAY'S PRACTICE"):
                    text_body = "Can you share today's 3-minute Soul Sync meditation practice?"

                # B. Crisis Preemption
                if likely_crisis(text_body):
                    logger.warning("Crisis detected in WhatsApp message from %s; preempting", mask_phone(clean_from))
                    from tasks.whatsapp_tasks import _send_meta_outbound
                    _send_meta_outbound(phone_number_id, clean_from, CRISIS_HELPLINE_COPY)
                    continue

                # C. Account Linking Verification Gate
                is_linked = False
                if db:
                    try:
                        link_row = await get_account_link_by_phone(db, clean_from)
                        if link_row and link_row.get("status") == "active":
                            is_linked = True
                    except Exception as exc:
                        logger.warning("Error checking account link for %s: %s", mask_phone(clean_from), exc)

                if not is_linked:
                    logger.info("Unlinked user %s attempted conversation; issuing web auth challenge", mask_phone(clean_from))
                    token = None
                    if db:
                        try:
                            token, _ = await create_link_challenge(db, clean_from, confirmed_whatsapp=True)
                        except Exception as exc:
                            logger.exception("Failed generating link challenge: %s", exc)
                    if not token:
                        from services.whatsapp_service import generate_link_token
                        token = generate_link_token()

                    link_url = f"{base_url}/link-whatsapp#code={token}"
                    auth_prompt_msg = (
                        "🙏 *Welcome to AskMukthiGuru on WhatsApp*\n\n"
                        "To converse with the wisdom of Sri Preethaji & Sri Krishnaji and access teachings, "
                        "please authenticate and connect your AskMukthiGuru account:\n\n"
                        "🔗 *Connect Your Account:*\n"
                        f"{link_url}\n\n"
                        "⏳ This secure link expires in 15 minutes.\n"
                        "Once you sign in and confirm on our website, you will be automatically returned to WhatsApp to begin your conversation!"
                    )
                    from tasks.whatsapp_tasks import _send_meta_outbound
                    _send_meta_outbound(phone_number_id, clean_from, auth_prompt_msg)
                    continue

                # D. Connected/Returning Greetings
                if upper_body in ("START", "CONFIRM"):
                    if db:
                        try:
                            await resume_account_by_phone(db, clean_from)
                        except Exception as e:
                            logger.debug("Resume status note: %s", e)
                    buttons = [
                        ("btn_ask", "Ask a Question"),
                        ("btn_practice", "Today's Practice"),
                        ("btn_human", "Human Help"),
                    ]
                    welcome_btn_payload = build_meta_interactive_buttons(
                        to_number=clean_from,
                        header_text="🙏 Welcome to AskMukthiGuru",
                        body_text=(
                            "Your WhatsApp is connected to your AskMukthiGuru account.\n\n"
                            "You can now ask questions on meditation, inner peace, and spiritual teachings—just like on our website.\n\n"
                            "Choose an option below or type your inquiry directly:"
                        ),
                        buttons=buttons,
                    )
                    from tasks.whatsapp_tasks import _send_meta_interactive
                    _send_meta_interactive(phone_number_id, welcome_btn_payload)
                    continue

                # E. Dispatch to Celery for Durable Execution
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
    Enforces DPDP decoupling: channel history sync and long-term memory default to False unless specified.
    Returns return_url (wa.me deep link) to redirect back to WhatsApp.
    """
    db = getattr(container, "supabase_client", None)
    if not db:
        raise HTTPException(status_code=501, detail="Database unavailable")

    user_id = user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        link = await verify_link_challenge(db, body.code, user_id)

        sync_consent = False
        memory_consent = False
        if body.sync_history_consent is not None or body.memory_write_consent is not None:
            updated = await update_link_consent(
                db,
                user_id,
                sync_history_consent=body.sync_history_consent,
                memory_write_consent=body.memory_write_consent,
            )
            sync_consent = updated.get("sync_history_consent", False)
            memory_consent = updated.get("memory_write_consent", False)
        else:
            sync_consent = bool(link.get("sync_history_consent", False))
            memory_consent = bool(link.get("memory_write_consent", False))

        waba_phone = getattr(settings, "meta_phone_number", "").strip().lstrip("+")
        return_url = f"https://wa.me/{waba_phone}?text=START" if waba_phone else "https://wa.me/?text=START"

        return {
            "success": True,
            "masked_phone": link.get("phone_number_masked"),
            "sync_history_consent": sync_consent,
            "memory_write_consent": memory_consent,
            "linked_at": link.get("linked_at"),
            "return_url": return_url,
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

    try:
        link_status = await get_link_status(db, user_id)
        if link_status.get("masked_phone"):
            clear_whatsapp_session(user_id)
    except Exception as exc:
        logger.debug("Unlink session clearing note: %s", exc)

    success = await unlink_account(db, user_id)
    return {"success": success, "status": "unlinked"}
