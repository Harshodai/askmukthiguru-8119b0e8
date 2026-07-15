"""Cancel flow (Task B3a) — 5-stage churn prevention with real Supabase persistence.

Stages: cancel-intent -> exit-survey -> save-offer -> confirm-cancel -> cancel-status
Win-back emails: 4-email sequence (day 0, 3, 14, 30) dispatched by Celery beat task.

ponytail: thin router; all persistence goes through the existing supabase client pattern.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from app.config import settings
from app.core.limiter import limiter
from services.auth_service import get_current_user_from_supabase

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Account"])


# ===================================================================
# Static configuration (from the churn-prevention analysis)
# ===================================================================

REASON_TO_OFFER: dict[str, str] = {
    "journey_complete": "alumni_access",
    "too_expensive": "scholarship",
    "not_using": "personalized_reminders",
    "missing_feature": "roadmap_access",
    "found_alternative": "premium_unlock",
    "too_complicated": "simplified_mode",
    "taking_break": "pause_account",
    "technical_issues": "priority_support",
}

SAVE_OFFERS: dict[str, dict[str, str]] = {
    "alumni_access": {
        "headline": "Your journey continues, even after graduation",
        "description": "Get lifetime free access to daily wisdom and community features.",
        "cta": "Claim Alumni Access",
        "value": "Free forever",
    },
    "scholarship": {
        "headline": "Spiritual growth should be accessible to everyone",
        "description": "Pay what you can. Set your own price — even $0.",
        "cta": "Apply Scholarship",
        "value": "Up to 100% off",
    },
    "personalized_reminders": {
        "headline": "Let us gently remind you of your practice",
        "description": "Daily personalized nudges based on your interests and schedule.",
        "cta": "Enable Reminders",
        "value": "Customized to you",
    },
    "roadmap_access": {
        "headline": "Help us build what you need",
        "description": "Get exclusive early access to new features and direct input to our roadmap.",
        "cta": "Join Inner Circle",
        "value": "VIP access",
    },
    "premium_unlock": {
        "headline": "Unlock everything for 30 days — on us",
        "description": "Experience the full platform including advanced meditations and 1:1 guidance.",
        "cta": "Unlock Premium",
        "value": "30 days free",
    },
    "simplified_mode": {
        "headline": "Sometimes simpler is better",
        "description": "Switch to our simplified mode with just the essentials.",
        "cta": "Try Simple Mode",
        "value": "Distraction-free",
    },
    "pause_account": {
        "headline": "Your journey is paused, not ended",
        "description": "Pause for up to 90 days. All your data and progress will be preserved.",
        "cta": "Pause Account",
        "value": "90 days",
    },
    "priority_support": {
        "headline": "Let's fix this together",
        "description": "Get priority support with a 24-hour response guarantee.",
        "cta": "Get Help",
        "value": "24h response",
    },
}

# 4-email win-back sequence (delay_days relative to cancellation confirm).
# template_key is the slug stored in cancellations.win_back_emails_sent.
POST_CANCEL_EMAILS: list[dict[str, Any]] = [
    {"delay_days": 0, "template_key": "day0", "subject": "Your Mukthi Guru journey — what happens next"},
    {"delay_days": 3, "template_key": "day3", "subject": "A small gift for your journey ahead"},
    {"delay_days": 14, "template_key": "day14", "subject": "How are you feeling?"},
    {"delay_days": 30, "template_key": "day30", "subject": "Your scheduled deletion date is approaching"},
]

RETENTION_TO_DAYS: dict[str, int] = {
    "keep_30_days": 30,
    "keep_90_days": 90,
    "delete_immediately": 0,
}

# Benchmark targets for spiritual/wellness apps (churn-prevention analysis).
CHURN_BENCHMARKS: dict[str, float] = {
    "save_rate_target_min": 0.15,
    "save_rate_target_max": 0.25,
    "survey_completion_target": 0.85,
    "reactivation_rate_target_min": 0.10,
    "reactivation_rate_target_max": 0.20,
}


# ===================================================================
# Churn metrics dataclass (from the analysis)
# ===================================================================


@dataclass
class ChurnMetrics:
    """Track churn prevention effectiveness."""

    cancel_attempts: int = 0
    saves_via_offer: int = 0
    saves_via_survey: int = 0
    surveys_started: int = 0
    surveys_completed: int = 0
    reactivations_7d: int = 0
    reactivations_30d: int = 0
    reactivations_90d: int = 0

    @property
    def save_rate(self) -> float:
        if self.cancel_attempts == 0:
            return 0.0
        return (self.saves_via_offer + self.saves_via_survey) / self.cancel_attempts

    @property
    def survey_completion_rate(self) -> float:
        if self.surveys_started == 0:
            return 0.0
        return self.surveys_completed / self.surveys_started

    @property
    def reactivation_rate_30d(self) -> float:
        if self.cancel_attempts == 0:
            return 0.0
        return self.reactivations_30d / self.cancel_attempts


# In-process metrics counter (for quick introspection / tests).
_churn_metrics = ChurnMetrics()


# ===================================================================
# Prometheus metric (no-op fallback if prometheus_client missing)
# ===================================================================

try:
    from prometheus_client import Counter as _Counter

    CANCEL_FLOW_STAGE_REACHED = _Counter(
        "cancel_flow_stage_reached_total",
        "Cancel flow stages reached by users",
        ["stage"],
    )

    def _inc_stage(stage: str) -> None:
        try:
            CANCEL_FLOW_STAGE_REACHED.labels(stage=stage).inc()
        except Exception:  # no-op fallback
            pass
except Exception:  # pragma: no cover - prometheus unavailable
    CANCEL_FLOW_STAGE_REACHED = None  # type: ignore[assignment]

    def _inc_stage(stage: str) -> None:
        pass


# ===================================================================
# Supabase client helper (matches ingest.py pattern, carries caller JWT)
# ===================================================================


def _supabase_client(request: Optional[Request] = None) -> Any:
    """Build a supabase client carrying the caller's JWT so RLS sees auth.uid()."""
    if not settings.supabase_url or not settings.supabase_key:
        raise HTTPException(status_code=503, detail="Persistence backend unavailable.")
    from supabase import create_client

    client = create_client(settings.supabase_url, settings.supabase_key)
    if request is not None:
        _auth_header = request.headers.get("Authorization", "")
        if _auth_header.startswith("Bearer "):
            client.auth.set_session(_auth_header[7:], "")
    return client


def _supabase_service_client() -> Any:
    """Build a supabase client with the service-role key (bypasses RLS).

    Used only for admin-scoped reads (churn metrics) and background
    operations where the caller's JWT would be restricted by RLS to
    a single user's rows.
    """
    key = settings.supabase_service_key or settings.supabase_key
    if not settings.supabase_url or not key:
        raise HTTPException(status_code=503, detail="Persistence backend unavailable.")
    from supabase import create_client
    return create_client(settings.supabase_url, key)


def _calculate_deletion_date(retention: str) -> datetime:
    days = RETENTION_TO_DAYS.get(retention, 30)
    return datetime.now(UTC) + timedelta(days=days)


# ===================================================================
# Schemas
# ===================================================================

ReasonLiteral = Literal[
    "journey_complete",
    "too_expensive",
    "not_using",
    "missing_feature",
    "found_alternative",
    "too_complicated",
    "taking_break",
    "technical_issues",
]


from pydantic import BaseModel  # noqa: E402


class CancelIntentRequest(BaseModel):
    intent: Literal["exploring_options", "definite_cancel"]


class CancelIntentResponse(BaseModel):
    next_stage: Literal["exit_survey", "save_offer"]
    message: str


class ExitSurveyRequest(BaseModel):
    reason: ReasonLiteral
    details: str = Field("", max_length=500)


class ExitSurveyResponse(BaseModel):
    reason: str
    save_offer_type: str
    save_offer: dict[str, str]
    next_stage: str


class SaveOfferRequest(BaseModel):
    offer_type: str
    accepted: bool


class SaveOfferResponse(BaseModel):
    accepted: bool
    next_stage: Literal["confirmation_saved", "confirmation_cancelled"]
    message: str


class CancelConfirmationRequest(BaseModel):
    confirm: bool
    data_retention: Literal["keep_30_days", "keep_90_days", "delete_immediately"]


class CancelStatusResponse(BaseModel):
    status: str
    deletion_date: Optional[str] = None
    message: str


# ===================================================================
# Stage 1: cancel-intent
# ===================================================================


@router.post("/account/cancel-intent")
@limiter.limit("30/minute")
async def handle_cancel_intent(
    request: Request,
    payload: CancelIntentRequest,
    user: dict = Depends(get_current_user_from_supabase),
) -> CancelIntentResponse:
    """Stage 1: initial cancel intent — always route to exit survey."""
    _inc_stage("cancel_intent")
    if user.get("id") == "anonymous":
        raise HTTPException(status_code=401, detail="Authentication required.")
    _churn_metrics.cancel_attempts += 1
    if payload.intent == "exploring_options":
        return CancelIntentResponse(
            next_stage="exit_survey",
            message="We'd love your feedback to improve the experience.",
        )
    return CancelIntentResponse(
        next_stage="exit_survey",
        message="Before you go, help us understand what we could do better.",
    )


# ===================================================================
# Stage 2: exit-survey
# ===================================================================


@router.post("/account/exit-survey")
@limiter.limit("30/minute")
async def submit_exit_survey(
    request: Request,
    payload: ExitSurveyRequest,
    user: dict = Depends(get_current_user_from_supabase),
) -> ExitSurveyResponse:
    """Stage 2: collect exit reason, persist, and map to a save offer."""
    _inc_stage("exit_survey")
    uid = user.get("id")
    if not uid or uid == "anonymous":
        raise HTTPException(status_code=401, detail="Authentication required.")
    _churn_metrics.surveys_started += 1

    offer_type = REASON_TO_OFFER.get(payload.reason, "priority_support")

    try:
        client = _supabase_client(request)
        client.table("exit_surveys").insert(
            {
                "user_id": uid,
                "reason": payload.reason,
                "details": payload.details or "",
            }
        ).execute()
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"exit_surveys insert failed for {uid}: {e}")
        # Non-fatal: still return the mapped offer so the UI can continue.

    _churn_metrics.surveys_completed += 1
    return ExitSurveyResponse(
        reason=payload.reason,
        save_offer_type=offer_type,
        save_offer=SAVE_OFFERS[offer_type],
        next_stage="save_offer",
    )


# ===================================================================
# Stage 3: save-offer
# ===================================================================


@router.post("/account/save-offer")
@limiter.limit("30/minute")
async def handle_save_offer(
    request: Request,
    payload: SaveOfferRequest,
    user: dict = Depends(get_current_user_from_supabase),
) -> SaveOfferResponse:
    """Stage 3: persist the save-offer decision. Accepted => saved; declined => cancel."""
    _inc_stage("save_offer")
    uid = user.get("id")
    if not uid or uid == "anonymous":
        raise HTTPException(status_code=401, detail="Authentication required.")

    if payload.offer_type not in SAVE_OFFERS:
        raise HTTPException(status_code=400, detail="Unknown offer_type.")

    try:
        client = _supabase_client(request)
        client.table("save_offers").insert(
            {
                "user_id": uid,
                "offer_type": payload.offer_type,
                "accepted": payload.accepted,
            }
        ).execute()
        if payload.accepted:
            client.table("exit_surveys").update(
                {"responded_to": True, "response_type": "saved"}
            ).eq("user_id", uid).execute()
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"save_offers insert failed for {uid}: {e}")

    if payload.accepted:
        _churn_metrics.saves_via_offer += 1
        return SaveOfferResponse(
            accepted=True,
            next_stage="confirmation_saved",
            message="We're so glad you're staying. Your offer has been applied.",
        )
    return SaveOfferResponse(
        accepted=False,
        next_stage="confirmation_cancelled",
        message="We understand. Let's complete the process.",
    )


# ===================================================================
# Stage 4: confirm-cancel (120s timeout headroom for email enqueue)
# ===================================================================


@router.post("/account/confirm-cancel")
@limiter.limit("10/minute")
async def confirm_cancellation(
    request: Request,
    payload: CancelConfirmationRequest,
    user: dict = Depends(get_current_user_from_supabase),
) -> CancelStatusResponse:
    """Stage 4: final confirmation. Schedules deletion + enqueues win-back emails."""
    _inc_stage("confirm_cancel")
    uid = user.get("id")
    if not uid or uid == "anonymous":
        raise HTTPException(status_code=401, detail="Authentication required.")

    if not payload.confirm:
        # User changed mind — mark survey responded, no cancellation.
        try:
            client = _supabase_client(request)
            client.table("exit_surveys").update(
                {"responded_to": True, "response_type": "saved"}
            ).eq("user_id", uid).execute()
        except Exception as e:
            logger.warning(f"exit_surveys update (aborted) failed for {uid}: {e}")
        _churn_metrics.saves_via_survey += 1
        return CancelStatusResponse(
            status="cancelled_aborted",
            message="We're glad you decided to stay.",
        )

    deletion_date = _calculate_deletion_date(payload.data_retention)

    cancellation_id: Optional[str] = None
    try:
        client = _supabase_client(request)
        resp = client.table("cancellations").insert(
            {
                "user_id": uid,
                "status": "scheduled",
                "data_retention": payload.data_retention,
                "scheduled_deletion": deletion_date.isoformat(),
                "win_back_emails_sent": [],
            }
        ).execute()
        if resp.data:
            cancellation_id = resp.data[0].get("id")
        # Isolated best-effort — insertion success is the critical path.
        try:
            client.table("exit_surveys").update(
                {"responded_to": True, "response_type": "cancelled"}
            ).eq("user_id", uid).execute()
        except Exception as _survey_err:
            logger.warning("exit_surveys update failed after cancellation insert: %s", _survey_err)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"cancellations insert failed for {uid}: {e}")
        raise HTTPException(status_code=503, detail="Failed to schedule cancellation.")

    # Enqueue the 4 win-back emails via Celery (fire-and-forget, 120s headroom).
    try:
        from tasks.cancel_flow_tasks import send_win_back_email

        for email in POST_CANCEL_EMAILS:
            send_win_back_email.apply_async(
                kwargs={
                    "user_id": uid,
                    "delay_days": email["delay_days"],
                    "template_key": email["template_key"],
                    "cancellation_id": cancellation_id,
                },
                countdown=email["delay_days"] * 86400,
            )
    except Exception as e:
        # Non-fatal: daily beat task will pick up due emails as a safety net.
        logger.warning(f"Win-back email enqueue failed for {uid}: {e}")

    return CancelStatusResponse(
        status="cancelled_confirmed",
        deletion_date=deletion_date.isoformat(),
        message=f"Your account will be deleted on {deletion_date.date()}. You can reactivate anytime before then.",
    )


# ===================================================================
# Stage 5: cancel-status (read-only state lookup)
# ===================================================================


@router.get("/account/cancel-status")
@limiter.limit("30/minute")
async def cancel_status(
    request: Request,
    user: dict = Depends(get_current_user_from_supabase),
) -> CancelStatusResponse:
    """Stage 5: return the latest cancellation state for the caller."""
    _inc_stage("cancel_status")
    uid = user.get("id")
    if not uid or uid == "anonymous":
        raise HTTPException(status_code=401, detail="Authentication required.")
    try:
        client = _supabase_client(request)
        resp = (
            client.table("cancellations")
            .select("status,scheduled_deletion,reactivated_at")
            .eq("user_id", uid)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if resp.data:
            row = resp.data[0]
            return CancelStatusResponse(
                status=row.get("status", "unknown"),
                deletion_date=row.get("scheduled_deletion"),
                message="Cancellation record found.",
            )
    except Exception as e:
        logger.warning(f"cancel-status lookup failed for {uid}: {e}")
    return CancelStatusResponse(status="none", message="No cancellation on record.")


# ===================================================================
# Reactivation endpoint (marks cancellation reactivated_at)
# ===================================================================


@router.post("/account/reactivate")
@limiter.limit("10/minute")
async def reactivate_account(
    request: Request,
    user: dict = Depends(get_current_user_from_supabase),
) -> CancelStatusResponse:
    """Mark the latest scheduled cancellation as reactivated (win-back success)."""
    _inc_stage("reactivate")
    uid = user.get("id")
    if not uid or uid == "anonymous":
        raise HTTPException(status_code=401, detail="Authentication required.")
    try:
        client = _supabase_client(request)
        resp = client.table("cancellations").update(
            {"status": "reactivated", "reactivated_at": datetime.now(UTC).isoformat()}
        ).eq("user_id", uid).eq("status", "scheduled").execute()
        if resp.data:
            row = resp.data[0]
            created_str = row.get("created_at")
            if created_str:
                try:
                    elapsed = (datetime.now(UTC) - datetime.fromisoformat(created_str.replace("Z", "+00:00"))).days
                    if elapsed <= 7:
                        _churn_metrics.reactivations_7d += 1
                    elif elapsed <= 30:
                        _churn_metrics.reactivations_30d += 1
                    else:
                        _churn_metrics.reactivations_90d += 1
                except Exception:
                    _churn_metrics.reactivations_30d += 1
            else:
                _churn_metrics.reactivations_30d += 1
        else:
            logger.warning("reactivate: no scheduled cancellation found for %s", uid)
            return CancelStatusResponse(
                status="none",
                message="No active cancellation found to reactivate.",
            )
    except Exception as e:
        logger.warning(f"reactivate failed for {uid}: {e}")
        return CancelStatusResponse(
            status="error",
            message="Reactivation failed. Please try again later.",
        )
    return CancelStatusResponse(
        status="reactivated",
        message="Welcome back. Your account is reactivated.",
    )


# ===================================================================
# Admin analytics: churn-metrics snapshot vs benchmark targets
# ===================================================================


def _require_admin_or_dev(user: dict) -> None:
    """Admin-only in production; any authenticated user in dev (matches admin.py pattern)."""
    uid = user.get("id")
    if not uid or uid == "anonymous":
        raise HTTPException(status_code=401, detail="Authentication required.")
    if settings.is_production and not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")


def _load_churn_metrics_from_db(request: Request) -> ChurnMetrics:
    """Load authoritative churn metrics from Supabase tables.

    Queries cancellations, exit_surveys, and save_offers to compute
    cross-pod-consistent counts. Falls back to in-process counters
    when the DB is unreachable.
    """
    try:
        # Use service-role client to bypass RLS and read ALL rows across users.
        client = _supabase_service_client()

        # Cancellations count.
        all_cancellations = client.table("cancellations").select("created_at,reactivated_at,status").execute()
        cancel_rows = all_cancellations.data or []
        cancel_attempts = len(cancel_rows)

        # Reactivations bucketed by elapsed time.
        now_utc = datetime.now(UTC)
        reactivations_7d = 0
        reactivations_30d = 0
        reactivations_90d = 0
        for row in cancel_rows:
            if row.get("status") == "reactivated" and row.get("reactivated_at"):
                created_str = row.get("created_at")
                if created_str:
                    try:
                        elapsed = (now_utc - datetime.fromisoformat(created_str.replace("Z", "+00:00"))).days
                    except Exception:
                        elapsed = 999
                else:
                    elapsed = 999
                if elapsed <= 7:
                    reactivations_7d += 1
                elif elapsed <= 30:
                    reactivations_30d += 1
                else:
                    reactivations_90d += 1

        # Surveys.
        all_surveys = client.table("exit_surveys").select("responded_to,response_type").execute()
        survey_rows = all_surveys.data or []
        surveys_started = len(survey_rows)
        surveys_completed = sum(1 for r in survey_rows if r.get("responded_to"))

        # Save offers: saves_via_offer = accepted offers.
        all_offers = client.table("save_offers").select("accepted").execute()
        offer_rows = all_offers.data or []
        saves_via_offer = sum(1 for r in offer_rows if r.get("accepted"))
        saves_via_survey = sum(1 for r in survey_rows if r.get("response_type") == "saved")

        return ChurnMetrics(
            cancel_attempts=cancel_attempts,
            saves_via_offer=saves_via_offer,
            saves_via_survey=saves_via_survey,
            surveys_started=surveys_started,
            surveys_completed=surveys_completed,
            reactivations_7d=reactivations_7d,
            reactivations_30d=reactivations_30d,
            reactivations_90d=reactivations_90d,
        )
    except Exception as _db_err:
        logger.warning("churn-metrics DB query failed, falling back to in-process: %s", _db_err)
        return _churn_metrics


@router.get("/account/churn-metrics")
@limiter.limit("30/minute")
async def churn_metrics_snapshot(
    request: Request,
    user: dict = Depends(get_current_user_from_supabase),
) -> dict[str, Any]:
    """Admin-only snapshot of churn-prevention effectiveness vs benchmark targets.

    Production: requires superuser. Dev: any authenticated (non-anonymous) user.
    Reads authoritative counts from Supabase tables (all pods share the same data).
    Falls back to in-process counters on DB error.
    """
    _inc_stage("churn_metrics")
    _require_admin_or_dev(user)
    m = _load_churn_metrics_from_db(request)
    save_rate = m.save_rate
    survey_rate = m.survey_completion_rate
    react_rate = m.reactivation_rate_30d
    return {
        "metrics": {
            "cancel_attempts": m.cancel_attempts,
            "saves_via_offer": m.saves_via_offer,
            "saves_via_survey": m.saves_via_survey,
            "surveys_started": m.surveys_started,
            "surveys_completed": m.surveys_completed,
            "reactivations_7d": m.reactivations_7d,
            "reactivations_30d": m.reactivations_30d,
            "reactivations_90d": m.reactivations_90d,
            "save_rate": save_rate,
            "survey_completion_rate": survey_rate,
            "reactivation_rate_30d": react_rate,
        },
        "benchmarks": CHURN_BENCHMARKS,
        "meets_benchmark": {
            "save_rate": (
                CHURN_BENCHMARKS["save_rate_target_min"]
                <= save_rate
                <= CHURN_BENCHMARKS["save_rate_target_max"]
            ),
            "survey_completion": survey_rate >= CHURN_BENCHMARKS["survey_completion_target"],
            "reactivation_rate_30d": (
                CHURN_BENCHMARKS["reactivation_rate_target_min"]
                <= react_rate
                <= CHURN_BENCHMARKS["reactivation_rate_target_max"]
            ),
        },
    }


# ===================================================================
# Self-check
# ===================================================================


if __name__ == "__main__":
    print("SAVE_OFFERS keys:")
    for key in SAVE_OFFERS:
        print(f"  - {key}")
    print("\nREASON_TO_OFFER mapping:")
    for reason, offer in REASON_TO_OFFER.items():
        print(f"  {reason} -> {offer}")
    print("\nPOST_CANCEL_EMAILS:")
    for e in POST_CANCEL_EMAILS:
        print(f"  day {e['delay_days']:>2} | {e['template_key']:>5} | {e['subject']}")
    print("\nCHURN_BENCHMARKS:")
    required_keys = {
        "save_rate_target_min",
        "save_rate_target_max",
        "survey_completion_target",
        "reactivation_rate_target_min",
        "reactivation_rate_target_max",
    }
    assert set(CHURN_BENCHMARKS.keys()) == required_keys, (
        f"CHURN_BENCHMARKS keys mismatch: {set(CHURN_BENCHMARKS.keys())}"
    )
    for k, v in CHURN_BENCHMARKS.items():
        print(f"  {k} = {v}")
    print("\nB3a OK")