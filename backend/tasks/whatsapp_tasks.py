"""
Celery background tasks for durable WhatsApp message execution.
==============================================================

Ensures inbound WhatsApp messages are durably executed without risk of
data loss during server restarts or container recycling.
  1. Crisis Preemption: Detects acute distress and immediately dispatches
     authoritative helplines (Tele-MANAS 14416 / 112).
  2. Account Resolution: Resolves phone to linked user identity & DPDP consents.
  3. Core Orchestrator Execution: Routes through /api/chat preserving verbatim quotes,
     source citations, and safety notices.
  4. Outbound Delivery: Pushes responses via Meta Cloud API or Twilio.
  5. DPDP Consent Enforced: Only syncs conversation history when explicitly opted-in.
"""

from __future__ import annotations

import logging
import re
import urllib.parse
from typing import Any

from app.config import settings
from celery_config import celery_app
from services.whatsapp_service import (
    CRISIS_HELPLINE_COPY,
    clean_phone,
    format_whatsapp_message,
    hash_phone,
    is_whatsapp_ai_paused,
    likely_crisis,
    mask_phone,
)

logger = logging.getLogger(__name__)

BACKEND_INTERNAL_URL = getattr(settings, "backend_internal_url", "http://127.0.0.1:8000")
META_GRAPH_HOST = "graph.facebook.com"
META_GRAPH_VERSION = getattr(settings, "meta_graph_version", "v21.0")
_PHONE_NUMBER_ID_RE = re.compile(r"^\d{1,32}$")


def _split_whatsapp_message(text: str, max_chars: int = 4000) -> list[str]:
    """Split message into WhatsApp-friendly chunks without splitting sentences or quotes."""
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    current_chunk = ""
    paragraphs = text.split("\n\n")

    for para in paragraphs:
        if len(current_chunk) + len(para) + 2 <= max_chars:
            current_chunk = f"{current_chunk}\n\n{para}" if current_chunk else para
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            if len(para) <= max_chars:
                current_chunk = para
            else:
                lines = para.split("\n")
                for line in lines:
                    if len(current_chunk) + len(line) + 1 <= max_chars:
                        current_chunk = f"{current_chunk}\n{line}" if current_chunk else line
                    else:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                            current_chunk = ""
                        while len(line) > max_chars:
                            chunks.append(line[:max_chars])
                            line = line[max_chars:]
                        current_chunk = line

    if current_chunk:
        chunks.append(current_chunk.strip())
    return [c for c in chunks if c]


def _send_meta_outbound(phone_number_id: str, to_number: str, message_text: str) -> bool:
    """Send message via Meta Cloud API with strict SSRF guard and Graph v21+."""
    import requests

    token = getattr(settings, "meta_access_token", "")
    if not token:
        logger.error("Missing META_ACCESS_TOKEN; cannot send outbound WhatsApp message")
        return False

    clean_id = str(phone_number_id or getattr(settings, "meta_phone_number_id", "")).strip()
    if not clean_id.isdigit() or not _PHONE_NUMBER_ID_RE.match(clean_id):
        logger.error("Invalid phone_number_id rejected: %s", clean_id)
        return False

    url = f"https://{META_GRAPH_HOST}/{META_GRAPH_VERSION}/{int(clean_id)}/messages"
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != META_GRAPH_HOST:
        logger.error("SSRF guard blocked request to %s", url)
        return False

    target_phone = clean_phone(to_number)
    payload = {
        "messaging_product": "whatsapp",
        "to": target_phone,
        "type": "text",
        "text": {"body": message_text[:4096]},
    }
    try:
        resp = requests.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=10,
        )
        if resp.status_code in (200, 201):
            data = resp.json() if resp.content else {}
            msg_id = (data.get("messages") or [{}])[0].get("id", "unknown")
            logger.info(
                "Outbound WhatsApp accepted by Meta API (id=%s) for %s",
                msg_id,
                mask_phone(target_phone),
            )
            return True
        logger.error("Meta API error %d: %s", resp.status_code, resp.text)
        return False
    except Exception as exc:
        logger.exception(
            "Failed sending outbound WhatsApp to %s: %s", mask_phone(target_phone), exc
        )
        return False


def _send_meta_interactive(phone_number_id: str, payload: dict[str, Any]) -> bool:
    """Send interactive message (e.g. quick reply buttons) via Meta Cloud API."""
    import requests

    token = getattr(settings, "meta_access_token", "")
    if not token:
        logger.error("Missing META_ACCESS_TOKEN; cannot send interactive WhatsApp message")
        return False

    clean_id = str(phone_number_id or getattr(settings, "meta_phone_number_id", "")).strip()
    if not clean_id.isdigit() or not _PHONE_NUMBER_ID_RE.match(clean_id):
        logger.error("Invalid phone_number_id rejected: %s", clean_id)
        return False

    url = f"https://{META_GRAPH_HOST}/{META_GRAPH_VERSION}/{int(clean_id)}/messages"
    try:
        resp = requests.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=10,
        )
        if resp.status_code in (200, 201):
            return True
        logger.error("Meta API interactive error %d: %s", resp.status_code, resp.text)
        return False
    except Exception as exc:
        logger.exception("Failed sending interactive WhatsApp: %s", exc)
        return False


def _send_twilio_outbound(to_number: str, message_text: str) -> bool:
    """Send message via Twilio REST API."""
    import requests

    account_sid = getattr(settings, "twilio_account_sid", "")
    auth_token = getattr(settings, "twilio_auth_token", "")
    from_number = getattr(settings, "twilio_from", "")
    if not (account_sid and auth_token and from_number):
        logger.warning("Twilio credentials not configured; skipping outbound send")
        return False

    target = f"whatsapp:{clean_phone(to_number)}"
    sender = f"whatsapp:{clean_phone(from_number)}"
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    try:
        resp = requests.post(
            url,
            data={"From": sender, "To": target, "Body": message_text[:1600]},
            auth=(account_sid, auth_token),
            timeout=10,
        )
        return resp.status_code in (200, 201)
    except Exception as exc:
        logger.exception("Failed Twilio outbound to %s: %s", mask_phone(to_number), exc)
        return False


@celery_app.task(
    bind=True,
    name="tasks.whatsapp_tasks.process_whatsapp_turn_task",
    max_retries=2,
    default_retry_delay=5,
)
def process_whatsapp_turn_task(
    self,
    channel: str,
    phone: str,
    user_message: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Durable Celery task to execute a full WhatsApp turn.
    Guarantees:
      - Crisis preemption with Tele-MANAS (14416) / 112
      - Verbatim quotes preservation
      - Decoupled DPDP history consent
    """
    meta = metadata or {}
    clean_p = clean_phone(phone)
    phone_id = meta.get("phone_number_id") or getattr(settings, "meta_phone_number_id", "")

    # 1. Crisis Preemption
    if likely_crisis(user_message):
        logger.warning(
            "Acute crisis detected for %s; preempting with helplines", mask_phone(clean_p)
        )
        if channel == "meta":
            _send_meta_outbound(phone_id, clean_p, CRISIS_HELPLINE_COPY)
        else:
            _send_twilio_outbound(clean_p, CRISIS_HELPLINE_COPY)
        return {"status": "crisis_preempted", "phone": mask_phone(clean_p)}

    # 2. Check for linked account and DPDP consents in DB
    p_hash = hash_phone(clean_p)

    # Preempt if automated AI is temporarily paused for human handoff
    if is_whatsapp_ai_paused(p_hash):
        logger.info(
            "WhatsApp AI is paused for human interaction on %s; skipping automated turn",
            mask_phone(clean_p),
        )
        return {"status": "ai_paused_for_human", "phone": mask_phone(clean_p)}

    user_id: str | None = None
    sync_history = False
    memory_write = False

    try:
        from app.dependencies import get_container

        container = get_container()
        db = getattr(container, "supabase_client", None)
        if db:
            res = (
                db.table("whatsapp_account_links")
                .select("user_id,sync_history_consent,memory_write_consent,status")
                .eq("phone_number_hash", p_hash)
                .eq("status", "active")
                .limit(1)
                .execute()
            )
            rows = getattr(res, "data", []) or []
            if rows:
                user_id = rows[0].get("user_id")
                sync_history = bool(rows[0].get("sync_history_consent", False))
                memory_write = bool(rows[0].get("memory_write_consent", False))
                logger.info(
                    "WhatsApp %s resolved to linked user %s (sync_history=%s, memory_write=%s)",
                    mask_phone(clean_p),
                    user_id,
                    sync_history,
                    memory_write,
                )
    except Exception as exc:
        logger.warning("Failed checking account link for %s: %s", mask_phone(clean_p), exc)

    # 3. Execute teaching turn via internal PipelineCoordinator or fallback HTTP
    effective_user = (
        {"id": user_id, "is_anonymous": False}
        if user_id
        else {"id": "anonymous", "is_anonymous": True}
    )
    session_id = f"wa_{user_id}" if user_id else f"wa_{p_hash[:16]}"
    incognito_mode = not memory_write

    answer_text = ""
    try:
        import asyncio

        from app.pipeline.pipeline_coordinator import PipelineCoordinator
        from app.schemas import ChatRequest

        container = get_container()
        coordinator = PipelineCoordinator(container)
        chat_req = ChatRequest(
            user_message=user_message,
            session_id=session_id,
            messages=[],
            incognito=incognito_mode,
        )

        async def _run_pipeline():
            return await coordinator.execute(
                user_msg=user_message,
                preferred_lang="en",
                chat_body=chat_req,
                session_id=session_id,
                user=effective_user,
            )

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import nest_asyncio

                nest_asyncio.apply()
                pipeline_res = loop.run_until_complete(_run_pipeline())
            else:
                pipeline_res = loop.run_until_complete(_run_pipeline())
        except RuntimeError:
            pipeline_res = asyncio.run(_run_pipeline())

        raw_response = getattr(pipeline_res, "final_answer", "") or ""
        citations = getattr(pipeline_res, "citations", []) or []
        answer_text = format_whatsapp_message(raw_response, citations)
    except Exception as exc:
        logger.warning(
            "In-process pipeline execution failed for %s (%s); falling back to internal HTTP",
            mask_phone(clean_p),
            exc,
        )
        try:
            import requests

            chat_url = f"{BACKEND_INTERNAL_URL}/api/chat?wait=true"
            payload = {
                "user_message": user_message,
                "messages": [],
                "session_id": session_id,
                "incognito": incognito_mode,
            }
            resp = requests.post(chat_url, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            raw_response = data.get("response", "") or ""
            citations = data.get("citations") or []
            answer_text = format_whatsapp_message(raw_response, citations)
        except Exception as http_exc:
            logger.exception("HTTP fallback also failed for %s: %s", mask_phone(clean_p), http_exc)
            answer_text = (
                "🙏 I am momentarily unable to reach the teachings. "
                "Please pause, take a deep breath, and try asking again shortly."
            )

    # 4. Outbound delivery in WhatsApp-sized chunks
    chunks = _split_whatsapp_message(answer_text)
    sent = True
    for chunk in chunks:
        if channel == "meta":
            ok = _send_meta_outbound(phone_id, clean_p, chunk)
        else:
            ok = _send_twilio_outbound(clean_p, chunk)
        if not ok:
            sent = False

    # 5. DPDP-compliant conversation sync (if user explicitly consented)
    if sync_history and user_id and db:
        try:
            conv_res = (
                db.table("conversations")
                .select("id")
                .eq("user_id", user_id)
                .eq("title", "WhatsApp Companion")
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            rows = getattr(conv_res, "data", []) or []
            if rows:
                conv_id = rows[0]["id"]
            else:
                new_conv = (
                    db.table("conversations")
                    .insert(
                        {
                            "user_id": user_id,
                            "title": "WhatsApp Companion",
                            "preview": user_message[:120],
                        }
                    )
                    .execute()
                )
                conv_id = (getattr(new_conv, "data", []) or [{}])[0].get("id")

            if conv_id:
                db.table("chat_messages").insert(
                    [
                        {
                            "conversation_id": conv_id,
                            "role": "user",
                            "content": user_message,
                        },
                        {
                            "conversation_id": conv_id,
                            "role": "guru",
                            "content": answer_text,
                        },
                    ]
                ).execute()
                logger.info(
                    "Synced WhatsApp conversation turn into chat_messages for user %s", user_id
                )
        except Exception as e:
            logger.warning("History sync note: %s", e)

    # 6. DPDP-compliant second-brain memory writing (if user explicitly opted-in)
    if memory_write and user_id and db:
        try:
            from services.memory.canonical_memory_service import CanonicalMemoryStore

            # Check for personal spiritual practice / reflection keywords
            mem_triggers = (
                "remember",
                "my practice",
                "daily practice",
                "i feel",
                "struggling with",
                "my intent",
                "soul sync",
            )
            if any(t in user_message.lower() for t in mem_triggers):
                store = CanonicalMemoryStore(db)
                store.add_memory(
                    user_id=user_id,
                    fact=f"Shared via WhatsApp: {user_message[:280]}",
                    category="reflection",
                    source_turn=f"wa_turn_{session_id}",
                )
                logger.info(
                    "Saved consented second-brain memory for user %s from WhatsApp", user_id
                )
        except Exception as e:
            logger.debug("Memory write note: %s", e)

    return {
        "status": "delivered" if sent else "delivery_failed",
        "phone": mask_phone(clean_p),
        "linked": bool(user_id),
    }
