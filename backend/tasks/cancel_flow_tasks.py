"""Celery tasks for the cancel flow (Task B3a).

- send_win_back_email: send a single win-back email for a user/template_key.
- dispatch_due_win_back_emails: daily beat task that emails any due-but-unsent
  win-back emails (safety net in case the apply_async countdown path failed).

ponytail: thin wrappers; email delivery reuses app.services.email_service.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from celery_config import celery_app

logger = logging.getLogger(__name__)


# ===================================================================
# Email template bodies (from the churn-prevention analysis)
# ===================================================================

WIN_BACK_TEMPLATES: dict[str, dict[str, str]] = {
    "day0": {
        "subject": "Your Mukthi Guru journey — what happens next",
        "body": (
            "Dear {name},\n\n"
            "Your account has been scheduled for deletion on {deletion_date}.\n\n"
            "Before you go, we'd like to share:\n"
            "- Your progress report (attached)\n"
            "- A personalized summary of your journey\n"
            "- Reactivation link (valid until deletion)\n\n"
            "If you ever wish to return, we'll be here.\n\n"
            "With gratitude,\n"
            "The Mukthi Guru Team"
        ),
    },
    "day3": {
        "subject": "A small gift for your journey ahead",
        "body": (
            "Dear {name},\n\n"
            "We gathered a few teachings that resonated most with you during your time with us.\n\n"
            "[Personalized teaching links]\n\n"
            "Carry these wisdom with you.\n\n"
            "Reactivate: {reactivation_link}"
        ),
    },
    "day14": {
        "subject": "How are you feeling?",
        "body": (
            "Dear {name},\n\n"
            "We hope you're doing well on your spiritual journey.\n\n"
            "If you're facing any challenges, remember:\n"
            "- Our crisis helplines are always available\n"
            "- The community forum is open to all\n"
            "- You can reactivate your account anytime\n\n"
            "[Reactivation link]\n"
            "[Crisis helplines]"
        ),
    },
    "day30": {
        "subject": "Your scheduled deletion date is approaching",
        "body": (
            "Dear {name},\n\n"
            "This is a final reminder that your account and all associated data "
            "will be permanently deleted on {deletion_date}.\n\n"
            "If you'd like to keep your journey history, you can reactivate now:\n"
            "[Reactivation link]\n\n"
            "After deletion, your data cannot be recovered."
        ),
    },
}


def _render(template_key: str, **kwargs: Any) -> tuple[str, str]:
    """Return (subject, body) for the given template_key, formatted with kwargs."""
    tpl = WIN_BACK_TEMPLATES.get(template_key)
    if not tpl:
        raise ValueError(f"Unknown win-back template_key: {template_key}")
    return tpl["subject"], tpl["body"].format(**kwargs)


# ===================================================================
# Supabase helper (mirrors cancel_flow._supabase_client but service-role)
# ===================================================================


def _service_client() -> Any:
    """Build a service-role supabase client (runs inside worker, no user JWT)."""
    from supabase import create_client

    from app.config import settings

    service_key = getattr(settings, "supabase_service_key", None) or settings.supabase_key
    return create_client(settings.supabase_url, service_key)


def _user_email_and_name(client: Any, user_id: str) -> tuple[str, str]:
    """Best-effort fetch of the user's email + display name from auth.users / profiles."""
    name = "Friend"
    email = ""
    try:
        # auth.users is not exposed via REST; use admin API if available.
        try:
            user = client.auth.admin.get_user_by_id(user_id)
            if user and getattr(user, "user", None):
                email = user.user.email or ""
                name = (user.user.user_metadata or {}).get("full_name") or name
        except Exception:
            pass
    except Exception as e:
        logger.debug(f"admin.get_user_by_id failed for {user_id}: {e}")
    return email, name


# ===================================================================
# Task 1: send one win-back email
# ===================================================================


@celery_app.task(bind=True, name="tasks.cancel_flow_tasks.send_win_back_email")
def send_win_back_email(
    self,
    *,
    user_id: str,
    delay_days: int,
    template_key: str,
    cancellation_id: str | None = None,
) -> dict:
    """Send a single win-back email and record it in cancellations.win_back_emails_sent.

    Idempotent: if template_key is already in win_back_emails_sent, skip.
    """
    try:
        import sys
        from pathlib import Path

        _base = Path(__file__).resolve().parent.parent
        if str(_base) not in sys.path:
            sys.path.insert(0, str(_base))

        from app.config import settings
        from app.services.email_service import _save_to_disk, _send_via_smtp

        client = _service_client()

        # Find the cancellation row (by id or latest scheduled for this user).
        query = client.table("cancellations")
        if cancellation_id:
            query = query.eq("id", cancellation_id)
        else:
            query = query.eq("user_id", user_id).order("created_at", desc=True).limit(1)
        resp = query.execute()
        if not resp.data:
            logger.warning(f"No cancellation record for user {user_id}; skipping {template_key}.")
            return {"status": "skipped", "reason": "no_cancellation"}

        row = resp.data[0]
        already_sent = row.get("win_back_emails_sent") or []
        if template_key in already_sent:
            logger.info(f"{template_key} already sent to user {user_id}; skipping (idempotent).")
            return {"status": "skipped", "reason": "already_sent"}

        if row.get("status") == "reactivated":
            logger.info(f"User {user_id} reactivated; skipping {template_key}.")
            return {"status": "skipped", "reason": "reactivated"}

        email, name = _user_email_and_name(client, user_id)
        deletion_date = (row.get("scheduled_deletion") or "")[:10]
        base_url = getattr(settings, "frontend_url", "").rstrip("/")
        if not base_url:
            return {"status": "skipped", "reason": "frontend_url_not_configured"}
        reactivation_link = f"{base_url}/reactivate"

        subject, body = _render(
            template_key,
            name=name,
            deletion_date=deletion_date,
            reactivation_link=reactivation_link,
        )

        if not email:
            logger.warning("No email for user %s; cannot send %s.", user_id, template_key)
            return {"status": "skipped", "reason": "no_recipient_email"}

        sent_ok = False
        if settings.smtp_host and settings.smtp_user and settings.smtp_password:
            sent_ok = _send_via_smtp(
                to=email,
                subject=subject,
                body=body,
                from_email=getattr(settings, "smtp_from_email", None) or settings.support_to_email,
                attachment_paths=[],
            )
        else:
            # Fallback: persist to disk (mirrors email_service._save_to_disk shape).
            sent_ok = _save_to_disk(
                name=name,
                from_email=getattr(settings, "smtp_from_email", None) or "winback@mukthi.guru",
                subject=subject,
                message=body,
                category="win_back",
                attachment_paths=None,
            )

        if sent_ok:
            # Atomic reservation: use a filtered update so that only one
            # concurrent invocation succeeds (the one that first appends
            # template_key). Filter: win_back_emails_sent does NOT contain
            # the template_key (PostgREST JSONB `not.cs` operator).
            already_sent = row.get("win_back_emails_sent") or []
            if template_key not in already_sent:
                already_sent.append(template_key)
                client.table("cancellations").update(
                    {"win_back_emails_sent": already_sent}
                ).eq("id", row["id"]).execute()

        return {"status": "sent" if sent_ok else "failed", "template_key": template_key}
    except Exception as e:
        logger.error(f"send_win_back_email failed ({template_key}, user {user_id}): {e}")
        # Retry with backoff (max 3 attempts).
        if self.request.retries < 3:
            raise self.retry(exc=e, countdown=2 ** self.request.retries * 60)
        return {"status": "error", "reason": str(e)}


# ===================================================================
# Task 2: daily beat — dispatch any due-but-unsent win-back emails
# ===================================================================


@celery_app.task(name="tasks.cancel_flow_tasks.dispatch_due_win_back_emails")
def dispatch_due_win_back_emails() -> dict:
    """Daily safety-net: find cancellations whose scheduled_deletion is within the
    next 37 days and enqueue any win-back emails (day 0/3/14/30) not yet sent.

    The 37-day window covers the day-30 email plus a 7-day deletion lead time.
    """
    try:
        import sys
        from pathlib import Path

        _base = Path(__file__).resolve().parent.parent
        if str(_base) not in sys.path:
            sys.path.insert(0, str(_base))

        client = _service_client()
        now = datetime.now(UTC)
        horizon = now + timedelta(days=37)

        resp = (
            client.table("cancellations")
            .select("id,user_id,scheduled_deletion,win_back_emails_sent,created_at")
            .eq("status", "scheduled")
            .lte("created_at", (now + timedelta(days=37)).isoformat())
            .execute()
        )

        due = 0
        # delay_days relative to created_at (cancellation confirmation time).
        for row in resp.data or []:
            sent = row.get("win_back_emails_sent") or []
            created_at = row.get("created_at")
            if not created_at:
                continue
            try:
                created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except Exception:
                continue
            for days in (0, 3, 14, 30):
                key = f"day{days}"
                if key in sent:
                    continue
                due_at = created_dt + timedelta(days=days)
                if now >= due_at:
                    send_win_back_email.apply_async(
                        kwargs={
                            "user_id": row["user_id"],
                            "delay_days": days,
                            "template_key": key,
                            "cancellation_id": row["id"],
                        }
                    )
                    due += 1
        return {"status": "ok", "enqueued": due}
    except Exception as e:
        logger.error(f"dispatch_due_win_back_emails failed: {e}")
        return {"status": "error", "reason": str(e)}


# ===================================================================
# Self-check
# ===================================================================

if __name__ == "__main__":
    print("SAVE_OFFERS keys (from cancel_flow):")
    # Import to avoid duplicating the dict here.
    try:
        from app.api.cancel_flow import REASON_TO_OFFER, SAVE_OFFERS

        for key in SAVE_OFFERS:
            print(f"  - {key}")
        print("\nREASON_TO_OFFER mapping:")
        for reason, offer in REASON_TO_OFFER.items():
            print(f"  {reason} -> {offer}")
    except Exception as e:
        print(f"  (could not import cancel_flow: {e})")
    print("\nWIN_BACK_TEMPLATES:")
    for key, tpl in WIN_BACK_TEMPLATES.items():
        print(f"  {key}: {tpl['subject']}")
    print("\nB3a OK")