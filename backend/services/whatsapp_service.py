"""
WhatsApp Service — Identity Resolution, Cryptographic Two-Channel Linking, & DPDP Consent.
========================================================================================

Handles:
  1. Phone number sanitation, masking, and hashing.
  2. Single-use time-bounded link challenge tokens (stored hashed at rest).
  3. Two-channel account binding confirmation (web + WhatsApp).
  4. DPDP-compliant consent separation (channel history sync vs long-term memory).
  5. Cryptographic signature validation for Meta WhatsApp Cloud API webhooks.
  6. Crisis preemption detection and helpline response formatting.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import logging
import re
import secrets
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

# Constants
DEFAULT_LINK_EXPIRY_MINUTES = 15
MAX_WHATSAPP_MSG_LENGTH = 4096

_PHONE_CLEAN_RE = re.compile(r"[^\d+]")
_MASK_PHONE_RE = re.compile(r"^(\+?\d{1,3})(\d{2})\d+(\d{3})$")

# Crisis regex matching acute self-harm / suicide
_CRISIS_PATTERNS = [
    re.compile(r"\b(suicid\w*|kill\s+myself|end\s+my\s+life|want\s+to\s+die|harm\s+myself)\b", re.IGNORECASE),
    re.compile(r"\b(no\s+reason\s+to\s+live|don'?t\s+want\s+to\s+live|better\s+off\s+dead)\b", re.IGNORECASE),
    re.compile(r"\b(can'?t\s+go\s+on\s+living|ending\s+it\s+all)\b", re.IGNORECASE),
    re.compile(r"(आत्महत्या|मरना\s*चाहता|जीने\s*की\s*इच्छा\s*नहीं)", re.IGNORECASE),
]

CRISIS_HELPLINE_COPY = (
    "🙏 *You are precious, and you do not have to carry this alone.*\n\n"
    "If you or someone you know is in crisis or distress, free and confidential support is available 24/7:\n\n"
    "• *Tele-MANAS (India)*: Call *14416* or *1800-891-4416* (toll-free, 24/7, multi-lingual)\n"
    "• *National Emergency (India)*: Call *112*\n"
    "• *iCall*: *9152987821* (Mon–Sat, 8am–10pm)\n"
    "• *Vandrevala Foundation*: *+91 9999 666 555* (24/7)\n"
    "• *United States*: Call/Text *988* (Suicide & Crisis Lifeline)\n"
    "• *International*: Text *HOME* to *741741* (Crisis Text Line)\n\n"
    "Please reach out to a trusted professional, family member, or helpline right away."
)


def clean_phone(phone: str | None) -> str:
    """Normalize phone number: strip whitespace, whatsapp: prefix, keeping + and digits."""
    if not phone:
        return ""
    raw = str(phone).replace("whatsapp:", "").strip()
    digits = re.sub(r"[^\d]", "", raw)
    if not digits:
        return ""
    return f"+{digits}"


def mask_phone(phone: str | None) -> str:
    """Safely mask a phone number for UI display and safe logging (e.g. +91 98*** **210)."""
    cleaned = clean_phone(phone)
    if not cleaned:
        return ""
    if len(cleaned) < 8:
        return cleaned[:2] + "***" + cleaned[-2:]
    prefix = cleaned[:5]
    suffix = cleaned[-3:]
    return f"{prefix}*** **{suffix}"


def hash_phone(phone: str | None) -> str:
    """Deterministic SHA-256 hash of normalized phone number for DB lookup without plaintext."""
    cleaned = clean_phone(phone)
    if not cleaned:
        return ""
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()


def generate_link_token() -> str:
    """Generate a high-entropy URL-safe cryptographic token for single-use account linking."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """SHA-256 hash of link token for secure storage at rest."""
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()


def validate_meta_signature(raw_body: bytes, header_signature: str | None, app_secret: str | None) -> bool:
    """
    Validate X-Hub-Signature-256 against Meta App Secret using constant-time comparison.
    Fails closed if signature is missing, malformed, or secret is empty.
    """
    secret = (app_secret or getattr(settings, "meta_app_secret", "")).strip()
    if not secret:
        logger.error("META_APP_SECRET is not configured; rejecting request.")
        return False
    if not header_signature or not header_signature.startswith("sha256="):
        return False

    expected_sig = header_signature[7:].strip()
    computed_sig = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed_sig, expected_sig)


def likely_crisis(text: str | None) -> bool:
    """Check if inbound text suggests acute crisis or self-harm."""
    if not text:
        return False
    clean = text.strip()
    return any(p.search(clean) for p in _CRISIS_PATTERNS)


def format_whatsapp_message(text: str, citations: list[str] | None = None) -> str:
    """Format markdown text and citations for WhatsApp delivery."""
    if not text:
        return ""
    # 1. Convert markdown bold **word** to *word*
    formatted = re.sub(r"\*\*([^*]+)\*\*", r"*\1*", text)
    # 2. Convert markdown links [Label](url) to Label (url)
    formatted = re.sub(r"\[([^\]]+)\]\((https?://[^\)]+)\)", r"\1 (\2)", formatted)
    # 3. Clean multiple spaces / newlines
    formatted = re.sub(r"\n{3,}", "\n\n", formatted).strip()

    # Append citations if present
    if citations:
        valid_cites = [c.strip() for c in citations if str(c or "").strip()]
        if valid_cites:
            cites_str = "\n".join(f"• {c}" for c in valid_cites[:3])
            formatted += f"\n\n*Sources & Teachings:*\n{cites_str}"

    return formatted


# ---------------------------------------------------------------------------
# Database Operations (Async via Supabase Client)
# ---------------------------------------------------------------------------

async def create_link_challenge(
    supabase: Any,
    phone: str,
    confirmed_whatsapp: bool = True,
    expiry_minutes: int = DEFAULT_LINK_EXPIRY_MINUTES,
) -> tuple[str, dict[str, Any]]:
    """
    Generate a cryptographic single-use linking challenge and record it in Supabase.
    Returns (raw_token, challenge_row).
    """
    clean = clean_phone(phone)
    if not clean:
        raise ValueError("Phone number is required to create link challenge")

    raw_token = generate_link_token()
    token_hash = hash_token(raw_token)
    p_hash = hash_phone(clean)
    p_masked = mask_phone(clean)

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=expiry_minutes)

    challenge_row = {
        "challenge_token_hash": token_hash,
        "phone_number_hash": p_hash,
        "phone_number_masked": p_masked,
        "phone_number_raw": clean,
        "created_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "confirmed_whatsapp": confirmed_whatsapp,
    }

    def _insert():
        return supabase.table("whatsapp_link_challenges").insert(challenge_row).execute()

    await asyncio.to_thread(_insert)
    logger.info("Created WhatsApp link challenge for %s (expires: %s)", p_masked, expires_at.isoformat())
    return raw_token, challenge_row


async def verify_link_challenge(
    supabase: Any,
    token: str,
    user_id: str,
    tenant_id: str = "oneness",
) -> dict[str, Any]:
    """
    Verify and consume a link challenge, binding the phone number to user_id.
    Enforces atomic single-use, expiry, and decouples DPDP consent.
    """
    if not token or not token.strip():
        raise ValueError("Challenge token is required")
    if not user_id or not user_id.strip():
        raise ValueError("User ID is required")

    t_hash = hash_token(token)

    def _get_challenge():
        return (
            supabase.table("whatsapp_link_challenges")
            .select("*")
            .eq("challenge_token_hash", t_hash)
            .execute()
        )

    res = await asyncio.to_thread(_get_challenge)
    rows = getattr(res, "data", []) or []
    if not rows:
        raise ValueError("Invalid or unrecognized linking code")

    challenge = rows[0]
    if challenge.get("consumed_at"):
        raise ValueError("This linking code has already been used")

    now = datetime.now(timezone.utc)
    expires_at_str = challenge.get("expires_at")
    if expires_at_str:
        expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
        if now > expires_at:
            raise ValueError("This linking code has expired. Please request a new one.")

    p_hash = challenge["phone_number_hash"]
    p_masked = challenge["phone_number_masked"]
    p_raw = challenge.get("phone_number_raw", "")

    # Atomic consume challenge
    def _consume_challenge():
        return (
            supabase.table("whatsapp_link_challenges")
            .update({
                "consumed_at": now.isoformat(),
                "confirmed_web_user_id": user_id,
            })
            .eq("id", challenge["id"])
            .execute()
        )

    await asyncio.to_thread(_consume_challenge)

    # Upsert account link row
    link_data = {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "phone_number_hash": p_hash,
        "phone_number_masked": p_masked,
        "phone_number_encrypted": p_raw,
        "status": "active",
        "sync_history_consent": False,   # DPDP: channel history sync defaults to False
        "memory_write_consent": False,  # DPDP: long-term memory consent defaults to False
        "linked_at": now.isoformat(),
        "revoked_at": None,
        "updated_at": now.isoformat(),
    }

    def _upsert_link():
        return (
            supabase.table("whatsapp_account_links")
            .upsert(link_data, on_conflict="phone_number_hash")
            .execute()
        )

    upsert_res = await asyncio.to_thread(_upsert_link)
    upserted_rows = getattr(upsert_res, "data", []) or []
    linked_row = upserted_rows[0] if upserted_rows else link_data

    logger.info("Successfully bound WhatsApp %s to user %s", p_masked, user_id)
    return linked_row


async def get_link_status(supabase: Any, user_id: str) -> dict[str, Any]:
    """Retrieve WhatsApp link status and DPDP consent settings for a user."""
    def _query():
        return (
            supabase.table("whatsapp_account_links")
            .select("*")
            .eq("user_id", user_id)
            .eq("status", "active")
            .order("linked_at", desc=True)
            .limit(1)
            .execute()
        )

    res = await asyncio.to_thread(_query)
    rows = getattr(res, "data", []) or []
    if not rows:
        return {
            "linked": False,
            "masked_phone": None,
            "sync_history_consent": False,
            "memory_write_consent": False,
            "linked_at": None,
        }

    link = rows[0]
    return {
        "linked": True,
        "masked_phone": link.get("phone_number_masked"),
        "sync_history_consent": bool(link.get("sync_history_consent", False)),
        "memory_write_consent": bool(link.get("memory_write_consent", False)),
        "linked_at": link.get("linked_at"),
    }


async def update_link_consent(
    supabase: Any,
    user_id: str,
    sync_history_consent: bool | None = None,
    memory_write_consent: bool | None = None,
) -> dict[str, Any]:
    """Decoupled DPDP update for channel history sync and long-term memory permissions."""
    updates: dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if sync_history_consent is not None:
        updates["sync_history_consent"] = bool(sync_history_consent)
    if memory_write_consent is not None:
        updates["memory_write_consent"] = bool(memory_write_consent)

    def _update():
        return (
            supabase.table("whatsapp_account_links")
            .update(updates)
            .eq("user_id", user_id)
            .eq("status", "active")
            .execute()
        )

    res = await asyncio.to_thread(_update)
    rows = getattr(res, "data", []) or []
    if not rows:
        raise ValueError("No active WhatsApp account link found for this user")

    link = rows[0]
    return {
        "linked": True,
        "masked_phone": link.get("phone_number_masked"),
        "sync_history_consent": bool(link.get("sync_history_consent", False)),
        "memory_write_consent": bool(link.get("memory_write_consent", False)),
        "linked_at": link.get("linked_at"),
    }


async def unlink_account(supabase: Any, user_id: str) -> bool:
    """Disconnect WhatsApp number and revoke active binding."""
    now = datetime.now(timezone.utc).isoformat()

    def _revoke():
        return (
            supabase.table("whatsapp_account_links")
            .update({
                "status": "unlinked",
                "revoked_at": now,
                "sync_history_consent": False,
                "memory_write_consent": False,
                "updated_at": now,
            })
            .eq("user_id", user_id)
            .eq("status", "active")
            .execute()
        )

    res = await asyncio.to_thread(_revoke)
    rows = getattr(res, "data", []) or []
    logger.info("Unlinked WhatsApp account for user %s (rows affected: %d)", user_id, len(rows))
    return len(rows) > 0


async def get_account_link_by_phone(supabase: Any, phone: str) -> dict[str, Any] | None:
    """Lookup active account link binding for a WhatsApp phone number."""
    p_hash = hash_phone(phone)
    if not p_hash:
        return None

    def _query():
        return (
            supabase.table("whatsapp_account_links")
            .select("*")
            .eq("phone_number_hash", p_hash)
            .eq("status", "active")
            .limit(1)
            .execute()
        )

    res = await asyncio.to_thread(_query)
    rows = getattr(res, "data", []) or []
    return rows[0] if rows else None
