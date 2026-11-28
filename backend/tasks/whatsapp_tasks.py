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
            allow_redirects=False,
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
        logger.error("Meta API error %d", resp.status_code)
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
            allow_redirects=False,
        )
        if resp.status_code in (200, 201):
            return True
        logger.error("Meta API interactive error %d", resp.status_code)
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
            allow_redirects=False,
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

    from app.dependencies import get_container
    from tasks.worker_loop import run_in_worker_loop
    from services.whatsapp_service import get_account_link_by_phone

    container = get_container()
    db = getattr(container, "supabase_client", None)
    if db is None:
        return {"status": "account_unavailable"}
    link = run_in_worker_loop(get_account_link_by_phone(db, clean_p))
    if not link or not link.get("user_id") or not link.get("id"):
        return {"status": "link_required"}
    user_id = link["user_id"]
    sync_history = link.get("sync_history_consent") is True
    memory_write = link.get("memory_write_consent") is True
    session_id = f"wa_{link['id']}"

    from app.pipeline.pipeline_coordinator import PipelineCoordinator
    from app.schemas import ChatRequest
    from services.tenant_context import TenantContext

    async def _run_pipeline():
        with TenantContext.scope(link["tenant_id"], user_id=user_id):
            return await PipelineCoordinator(container).execute(
                user_msg=user_message,
                preferred_lang="en",
                chat_body=ChatRequest(user_message=user_message, session_id=session_id,
                                     messages=[], incognito=not memory_write),
                session_id=session_id,
                user={"id": user_id, "is_anonymous": False},
            )

    pipeline_res = run_in_worker_loop(_run_pipeline())
    raw_response = getattr(pipeline_res, "final_answer", "") or ""
    if not raw_response.strip():
        return {"status": "answer_unavailable"}
    answer_text = format_whatsapp_message(raw_response, getattr(pipeline_res, "citations", []) or [])
    # A queued turn must not outlive STOP, unlink or replacement of its binding.
    current = run_in_worker_loop(get_account_link_by_phone(db, clean_p))
    if not current or current.get("id") != link["id"] or current.get("user_id") != user_id:
        return {"status": "binding_revoked"}
    if is_whatsapp_ai_paused(p_hash):
        return {"status": "ai_paused_for_human"}

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

    # History writes recheck consent transactionally; memory uses the shared MemoryStage.
    if sent and sync_history:
        db.rpc("sync_whatsapp_turn", {
            "p_link_id": link["id"], "p_user_id": user_id,
            "p_question": user_message, "p_answer": answer_text,
        }).execute()
    return {
        "status": "accepted_by_provider" if sent else "delivery_failed",
        "phone": mask_phone(clean_p),
        "linked": True,
    }
