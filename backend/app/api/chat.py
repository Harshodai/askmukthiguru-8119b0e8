"""Chat, streaming chat, and breath-teaching routes."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from functools import wraps
from typing import Any, Optional

from cachetools import TTLCache
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import JSONResponse, StreamingResponse

from app.assistant_authorization import authorize_chat_assistant
from app.chat_uploads import MAX_SINGLE_BYTES, extract_chat_attachments
from app.config import settings
from app.core.limiter import limiter
from app.core.user_usage_monitor import get_user_monitor
from app.dependencies import ServiceContainer, get_container_async
from app.grounding import grounding_state_for
from app.pipeline.stages.distress_stage import has_crisis_keywords, has_severe_crisis_keywords
from app.release_manifest import to_public_manifest_dict
from app.sanitization import sanitize_log_input, sanitize_user_input
from app.schemas import ChatRequest, ChatResponse, Citation, MessagePayload
from app.security_utils import is_benchmark_request
from services.anon_quota_port import QuotaResult
from services.auth_service import (
    get_current_user_from_supabase,
    get_optional_user,
    require_scoped_identity,
    resolve_anon_identity,
)
from services.chat_context_budget import CONTEXT_ERROR_CODE, assess_conversation_context
from services.cost_tracker import TokenAccumulator, get_cost_tracker, token_accumulator_var
from services.tenant_context import TenantContext, set_tenant_from_request

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Chat"])
# Extraction/OCR is CPU- and provider-intensive. Keep anonymous uploads from
# occupying every worker even when the per-client limiter is bypassed.
_ATTACHMENT_EXTRACTION_SEMAPHORE = asyncio.Semaphore(2)


@router.post("/chat/upload")
@limiter.limit(settings.chat_upload_rate_limit)
async def chat_upload_endpoint(
    request: Request,
    user: dict = Depends(get_optional_user),
    files: list[UploadFile] = File(...),
    language_code: Optional[str] = Form(None),
    session_id: Optional[str] = Form(None),
    container: ServiceContainer = Depends(get_container_async),
):
    """Extract bounded evidence for the next chat turn without persisting uploads.

    Anonymous callers are allowed because this endpoint returns only bounded,
    ephemeral evidence. When supplied, the server-signed anonymous session
    token is verified so the upload contract stays aligned with chat/job routes.
    """
    user = resolve_anon_identity(user, session_id)
    if not files:
        raise HTTPException(status_code=422, detail="At least one attachment is required.")
    if len(files) > 5:
        raise HTTPException(status_code=413, detail="A maximum of 5 attachments is allowed.")

    uploads: list[tuple[str, str, bytes]] = []
    for upload in files:
        if upload.size is not None and upload.size > MAX_SINGLE_BYTES:
            raise HTTPException(status_code=413, detail="Each attachment must be 10MB or smaller.")
        payload = await upload.read(MAX_SINGLE_BYTES + 1)
        if len(payload) > MAX_SINGLE_BYTES:
            raise HTTPException(status_code=413, detail="Each attachment must be 10MB or smaller.")
        if not payload:
            raise HTTPException(status_code=422, detail="Empty attachments are not supported.")
        uploads.append((upload.filename or "attachment", upload.content_type or "", payload))

    try:
        async with _ATTACHMENT_EXTRACTION_SEMAPHORE:
            return await asyncio.wait_for(
                extract_chat_attachments(
                    uploads,
                    language=language_code,
                    ocr_service=getattr(container, "ocr", None),
                ),
                timeout=45.0,
            )
    except TimeoutError as exc:
        raise HTTPException(status_code=408, detail="Attachment processing timed out") from exc
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Anonymous chat quota (progressive auth)
# ---------------------------------------------------------------------------


def _anon_quota_response(quota: QuotaResult) -> JSONResponse:
    """Standard 429 response when an anonymous session hits its message quota."""
    headers = {}
    if quota.retry_after_seconds:
        headers["Retry-After"] = str(quota.retry_after_seconds)
    return JSONResponse(
        status_code=429,
        content={
            "error": "Anonymous quota exceeded",
            "detail": "Sign in to continue the conversation.",
            "quota_exceeded": True,
            "remaining": quota.remaining,
            "total_limit": quota.total_limit,
            "retry_after_seconds": quota.retry_after_seconds,
        },
        headers=headers,
    )


async def _enforce_anon_quota(
    user: dict,
    container: ServiceContainer,
) -> QuotaResult:
    """Reserve one anonymous turn atomically at admission.

    The reservation is recorded immediately (sliding-window check_and_record),
    so concurrent requests cannot overshoot the limit. Callers return
    ``_anon_quota_response(quota)`` when ``quota.quota_exceeded``. A completed
    interaction keeps its reservation (commit via ``_charge_anon_quota``);
    failed or cancelled interactions return it via ``_release_anon_quota``.
    No-op for authenticated users and disabled quotas — the service records
    nothing and returns an allowed result.
    """
    return await container.anon_quota_service.check_and_record(user)


async def _charge_anon_quota(
    user: dict,
    container: ServiceContainer,
    quota: QuotaResult | None = None,
) -> None:
    """Commit the admission-time reservation.

    The turn was recorded atomically by ``_enforce_anon_quota`` at admission;
    this marks the reservation claimed so it counts against the window until
    natural expiry. Failures and cancellations release it via
    ``_release_anon_quota`` instead.
    """
    if quota is None or quota.reservation_id is None:
        return
    try:
        await container.anon_quota_service.claim(user, quota.reservation_id)
    except Exception as exc:
        logger.debug(f"anon quota claim failed (non-fatal): {exc}")


async def _release_anon_quota(
    user: dict,
    container: ServiceContainer,
    quota: QuotaResult | None,
) -> None:
    """Give the reserved slot back when the interaction failed/cancelled."""
    if quota is None or quota.reservation_id is None:
        return
    try:
        await container.anon_quota_service.release(user, quota.reservation_id)
    except Exception as exc:
        logger.debug(f"anon quota release failed (non-fatal): {exc}")


# P1-OPS-8: upstream backpressure for chat. A single replica can be
# overwhelmed by concurrent chat requests; the LLM circuit breaker only
# protects downstream. When MAX_CONCURRENT_CHAT requests are in flight we
# reject immediately with 503 + Retry-After instead of queueing (the Redis
# job queue already provides the queued path). The semaphore is created
# lazily because asyncio primitives bind to the running event loop at
# construction, so module-import time is not safe. The loop is tracked so
# a semaphore from a dead/different loop (e.g. across TestClient instances)
# is transparently rebuilt instead of raising "bound to a different event loop".
#
# RP-A1/RP-A3: this cap is PER WORKER, not per replica. Each uvicorn worker
# is a separate process with its own module-level semaphore (see
# start_railway.py WEB_CONCURRENCY), so the effective replica-wide cap is
# approximately workers x max_concurrent_chat. /api/health reports both.
_chat_semaphore: Optional[asyncio.Semaphore] = None
_chat_semaphore_loop: Optional[asyncio.AbstractEventLoop] = None
# RP-A2 (review): crisis requests get their OWN bounded semaphore at the same
# per-worker size — a separate pool so a crisis flood is bounded and visible
# instead of unbounded, while never competing with ordinary traffic.
_crisis_semaphore: Optional[asyncio.Semaphore] = None
_crisis_semaphore_loop: Optional[asyncio.AbstractEventLoop] = None
_CRISIS_ADMISSION_TIMEOUT_S = 0.05

# Process-lifetime count of never-shed crisis admissions that ran without a
# pool slot (mirrors CRISIS_UNBOUNDED_TOTAL for the /api/health readout,
# which cannot rely on a cumulative Prometheus Counter value alone).
_crisis_unbounded_total = 0


def _get_chat_semaphore() -> asyncio.Semaphore:
    global _chat_semaphore, _chat_semaphore_loop
    loop = asyncio.get_running_loop()
    if _chat_semaphore is None or _chat_semaphore_loop is not loop:
        _chat_semaphore = asyncio.Semaphore(settings.max_concurrent_chat)
        _chat_semaphore_loop = loop
    return _chat_semaphore


def _get_crisis_semaphore() -> asyncio.Semaphore:
    """Separate crisis admission pool (RP-A2), rebuilt across event loops
    exactly like the ordinary semaphore."""
    global _crisis_semaphore, _crisis_semaphore_loop
    loop = asyncio.get_running_loop()
    if _crisis_semaphore is None or _crisis_semaphore_loop is not loop:
        _crisis_semaphore = asyncio.Semaphore(settings.max_concurrent_chat)
        _crisis_semaphore_loop = loop
    return _crisis_semaphore


# RP-A8: shed clients must not all return at once. A constant Retry-After
# herds every shed client into the same retry instant and re-overloads the
# replica in waves; randomize across 3-8s (client adds up to 1s jitter).
_BACKPRESSURE_RETRY_AFTER_MIN_S = 3
_BACKPRESSURE_RETRY_AFTER_MAX_S = 8


def backpressure_retry_after_seconds() -> int:
    """Randomized Retry-After for admission-control 503s (RP-A8)."""
    return random.randint(_BACKPRESSURE_RETRY_AFTER_MIN_S, _BACKPRESSURE_RETRY_AFTER_MAX_S)


def _crisis_bypass_requested(chat_body: Any) -> bool:
    """True when the request carries crisis keywords (RP-A2).

    Cheap (<1ms) pre-screen on the raw user message, checked BEFORE the
    admission semaphore so a crisis-flagged request is never 503-shed. This
    does NOT decide the response — the pipeline's own DistressStage still
    runs its full assessment (crisis pre-check and topic rail keep their
    ordering before retrieval; untouched). Fail-closed: a regex failure
    admits (a missed crisis costs more than a miscounted bypass).
    Only regex errors take that path — has_severe_crisis_keywords already
    fail-closes its own assessor internally, so any other exception here is
    a bug and must surface, not silently bypass the cap.
    """
    text = getattr(chat_body, "user_message", None)
    if not isinstance(text, str) or not text.strip():
        return False
    try:
        # RP-A2 (narrowed): only SEVERE/CRISIS patterns bypass the semaphore.
        # The broad `has_crisis_keywords` also matches moderate terms such as
        # "anxiety" or "alone" and is intentionally NOT used here; those stay
        # subject to the normal admission cap.
        return has_severe_crisis_keywords(text)
    except re.error as exc:
        logger.warning("Crisis bypass pre-screen regex failed; admitting (fail-closed): %s", exc)
        try:
            from app.metrics import CRISIS_BYPASS_TOTAL

            CRISIS_BYPASS_TOTAL.inc()
        except Exception:  # noqa: BLE001 - observability must not shed crisis
            pass
        return True


async def _admit_chat(chat_body: Any) -> tuple[asyncio.Semaphore | None, JSONResponse | None]:
    """Admit one chat request under the concurrency cap.

    Returns ``(slot, None)`` when admitted (caller must ``slot.release()``
    exactly once; a None slot means a crisis admission that could not take a
    crisis-pool slot and is running unbounded — never shed), or
    ``(None, shed_response)`` when the ordinary cap is full and the request
    carries no crisis keywords.
    """
    if _crisis_bypass_requested(chat_body):
        # RP-A2 (review): bypass admissions take a slot from the SEPARATE
        # crisis pool — bounded and counted, immune to ordinary load shedding.
        # They are still counted for the health readout. Never let metrics
        # break the admission itself, and never shed a crisis: if the crisis
        # pool is itself exhausted, admit without a slot (fail-open) rather
        # than 503 — the invariant is "crisis never shed", not "crisis is
        # bounded at all costs".
        try:
            from app.metrics import CRISIS_BYPASS_TOTAL

            CRISIS_BYPASS_TOTAL.inc()
        except Exception as exc:  # noqa: BLE001 - observability must not shed crisis
            logger.debug("Crisis bypass counter unavailable: %s", exc)
        crisis_sem = _get_crisis_semaphore()
        try:
            await asyncio.wait_for(crisis_sem.acquire(), timeout=_CRISIS_ADMISSION_TIMEOUT_S)
        except TimeoutError:
            global _crisis_unbounded_total
            _crisis_unbounded_total += 1
            try:
                from app.metrics import CRISIS_UNBOUNDED_TOTAL

                CRISIS_UNBOUNDED_TOTAL.inc()
            except Exception as exc:  # noqa: BLE001 - observability must not shed crisis
                logger.debug("Crisis unbounded counter unavailable: %s", exc)
            logger.warning("Crisis admission pool exhausted; admitting without a slot (never-shed)")
            return None, None
        return crisis_sem, None
    sem = _get_chat_semaphore()
    try:
        await asyncio.wait_for(sem.acquire(), timeout=0.01)
    except TimeoutError:
        return None, JSONResponse(
            status_code=503,
            content={"detail": "Server busy, try again shortly"},
            headers={"Retry-After": str(backpressure_retry_after_seconds())},
        )
    return sem, None


def backpressure_semaphore(
    func: Callable[..., Awaitable[Any]],
) -> Callable[..., Awaitable[Any]]:
    """Reject with 503 + Retry-After when the chat concurrency cap is hit.

    Uses try-acquire: an exhausted semaphore rejects the request almost
    immediately rather than waiting, so a thundering herd fails fast.
    Crisis-keyword requests bypass the ordinary cap via the separate crisis
    pool (RP-A2) — they are never shed.
    """

    @wraps(func)
    async def wrapper(*args, **kwargs):
        chat_body = kwargs.get("chat_body") or next(
            (arg for arg in args if hasattr(arg, "user_message")), None
        )
        slot, shed = await _admit_chat(chat_body)
        if shed is not None:
            return shed
        try:
            return await func(*args, **kwargs)
        finally:
            if slot is not None:
                slot.release()

    return wrapper


def get_chat_backpressure() -> dict:
    """Current chat admission-control state, surfaced in /api/health.

    ``max_concurrent`` is the PER-WORKER cap (RP-A3): each uvicorn worker
    enforces its own semaphore, so the replica-wide ceiling is roughly
    workers x max_concurrent. ``workers`` is the live WEB_CONCURRENCY value
    (start_railway.py); None when it cannot be determined — reported as
    unknown, never fabricated. ``crisis_in_flight`` is the same readout for
    the separate crisis pool; ``crisis_unbounded_total`` counts never-shed
    admissions that ran without a slot (the flood-economics signal).
    """
    try:
        from start_railway import get_web_concurrency

        workers: int | None = get_web_concurrency()
    except (Exception, SystemExit) as exc:
        # get_web_concurrency fails closed with SystemExit on a garbage value;
        # that is right at boot, but a health readout must report unknown.
        logger.warning("Could not determine WEB_CONCURRENCY for health readout: %s", exc)
        workers = None
    base = {
        "max_concurrent": settings.max_concurrent_chat,
        "per_worker": True,
        "workers": workers,
    }
    crisis_sem = _crisis_semaphore
    crisis_state = {
        "crisis_in_flight": (
            max(0, settings.max_concurrent_chat - crisis_sem._value)
            if crisis_sem is not None
            else 0
        ),
        "crisis_unbounded_total": _crisis_unbounded_total,
    }
    sem = _chat_semaphore
    if sem is None:
        return {
            **base,
            **crisis_state,
            "in_flight": 0,
            "admission_limited": False,
        }
    return {
        **base,
        **crisis_state,
        "in_flight": max(0, settings.max_concurrent_chat - sem._value),
        "admission_limited": sem.locked(),
    }


async def populate_server_side_history(
    chat_body: ChatRequest, user: dict, container: ServiceContainer, is_benchmark: bool
) -> None:
    """Retrieves conversation history from Supabase for security (prevents client history injection)."""
    if chat_body.incognito:
        # An ephemeral request must not read a prior durable conversation.
        chat_body.messages = []
        return
    if is_benchmark:
        logger.info("Bypassing server-side history retrieval for benchmark client")
        return

    user_id = user.get("id", "anonymous") if user else "anonymous"

    # If session_id is missing or user is anonymous, we force history to be empty.
    # Check is_anonymous rather than the resolved id: resolve_anon_identity()
    # rewrites anonymous ids to "anon:<session_id>", so a literal "anonymous"
    # comparison never matches and anonymous requests would otherwise fall
    # through to a live Supabase lookup instead of staying local-only.
    if not user or user.get("is_anonymous") or user_id == "anonymous" or not chat_body.session_id:
        chat_body.messages = []
        return

    sc = container.supabase_client
    if not sc:
        # Client-supplied assistant messages are untrusted. If authoritative
        # history cannot be loaded, continue with no prior history rather than
        # letting a client fabricate assistant turns or inject another context.
        logger.warning(
            "Supabase client unavailable; dropping client-supplied conversation history."
        )
        chat_body.messages = []
        return

    try:
        # Check if conversation exists and belongs to the user.
        # PERF-2 TODO: Migrate to an async Postgres client (e.g. asyncpg or
        # supabase-py v2 async mode) to eliminate thread pool pressure.
        # asyncio.to_thread() is correct but consumes a thread per call.
        resp = await asyncio.to_thread(
            sc.table("conversations").select("user_id").eq("id", chat_body.session_id).execute
        )
        if not resp.data:
            # A missing row is a NEW conversation, not a forbidden one, and 404
            # here is a live race: the frontend's Supabase upsert is
            # fire-and-forget (`void syncConversationToDb(...)`,
            # src/lib/chatStorage.ts:560) while `saveConversation` awaits only
            # the local write, so the chat POST can reach us before the row
            # commits. Locally the upsert usually wins; against a remote
            # Supabase it often does not, which made a signed-in seeker's FIRST
            # message in a new conversation fail with
            # "Conversation not found". Serving it as an empty history is both
            # correct (a conversation with no row has no history) and leaks
            # nothing. The ownership check below is untouched: a row that
            # exists and belongs to someone else still gets 403.
            logger.info(
                "No conversation row for session_id yet; treating as a new "
                "conversation and continuing with empty history."
            )
            chat_body.messages = []
            return

        owner_id = resp.data[0].get("user_id")
        if str(owner_id) != str(user_id):
            raise HTTPException(
                status_code=403, detail="Unauthorized access to conversation history"
            )

        # Fetch actual messages for the session.
        # PERF-2 TODO: Same async migration applies here.
        # Keep durable-history loading bounded. The request schema's 50-turn
        # limit must remain true after server-side hydration as well.
        msg_resp = await asyncio.to_thread(
            sc.table("chat_messages")
            .select("role", "content")
            .eq("conversation_id", chat_body.session_id)
            .order("created_at", desc=True)
            .limit(50)
            .execute
        )

        rows = list(msg_resp.data or [])
        rows.reverse()

        db_messages = []
        for row in rows:
            db_role = row.get("role", "user")
            role = "assistant" if db_role in ("guru", "assistant") else "user"
            content = row.get("content") or ""
            db_messages.append(MessagePayload(role=role, content=content))

        chat_body.messages = db_messages
        logger.info(
            "Loaded %d messages for session %s",
            len(chat_body.messages),
            sanitize_log_input(chat_body.session_id),
        )

    except HTTPException:
        raise
    except Exception as e:
        # conversations.id is a uuid column, so a session_id that is not a UUID
        # comes back as 22P02 "invalid input syntax for type uuid". That is a
        # malformed client identifier, not a server fault, and it was being
        # reported as a 500. There is no stored history for an id the table
        # cannot hold, so start the turn without it. Checked on the error rather
        # than pre-validating, so ids the database does accept keep working.
        if "22P02" in str(e) or "invalid input syntax for type uuid" in str(e):
            logger.warning(
                "Session id %s is not a conversation uuid; continuing without stored history",
                sanitize_log_input(str(chat_body.session_id)),
            )
            # A malformed session cannot authenticate any client-supplied history.
            chat_body.messages = []
            return
        # Logging only the exception CLASS made this a dead end: every storage
        # fault — a missing column, a denied grant, a transport error — arrived
        # as the single word "APIError" with no way to tell them apart. The
        # client still gets the generic message; the operator gets the cause.
        logger.exception("Error loading chat history from database: %s", e)
        raise HTTPException(status_code=500, detail="Failed to load conversation history")


def _reject_if_queue_unattended() -> None:
    """Refuse chat traffic when the job worker was never started.

    `/api/chat` enqueues and returns 202. If lifespan's background init raised
    before `job_queue.start()` — as a failed Neo4j constraint assert does, since
    the worker start lives further down the same block — the queue has NO
    consumer. The request is then accepted, queued, and never answered: the
    seeker waits forever and nothing logs an error.

    Observed 2026-09-13: a job sat `queued` for 400s+ while /api/health honestly
    reported `ready: false` and /api/chat kept returning 202. Fail closed, and
    say why, rather than silently swallowing the request.
    """
    from app import dependencies as _app_deps

    if not getattr(_app_deps, "startup_complete", False):
        detail = "Service is still starting; no chat worker is attached yet."
        err = getattr(_app_deps, "startup_error", None)
        if err:
            detail = f"Service is not ready: {err}"
        logger.warning("Rejecting chat request — startup incomplete: %s", err or "in progress")
        raise HTTPException(status_code=503, detail=detail, headers={"Retry-After": "15"})


def record_token_usage(endpoint: str):
    """Decorator that records token usage for a request after the handler returns."""

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            kwargs.get("request") or next((arg for arg in args if isinstance(arg, Request)), None)
            chat_body = kwargs.get("chat_body") or next(
                (arg for arg in args if hasattr(arg, "user_message")), None
            )
            user = kwargs.get("user") or {}

            user_id = user.get("id", "anonymous") if isinstance(user, dict) else "anonymous"
            session_id = chat_body.session_id or "" if chat_body else ""

            get_user_monitor().record(user_id)

            accumulator = TokenAccumulator()
            token = token_accumulator_var.set(accumulator)
            try:
                return await func(*args, **kwargs)
            finally:
                acc = token_accumulator_var.get()
                if acc and (acc.tokens_in > 0 or acc.tokens_out > 0):
                    try:
                        tracked_cost = acc.cost_usd + acc.estimated_cost_usd
                        await asyncio.to_thread(
                            get_cost_tracker().record,
                            tenant_id=TenantContext.get(),
                            user_id=user_id,
                            session_id=session_id,
                            model=acc.model,
                            provider=acc.provider,
                            tokens_in=acc.tokens_in,
                            tokens_out=acc.tokens_out,
                            endpoint=endpoint,
                            cost_override=tracked_cost if tracked_cost > 0 else None,
                        )
                        # Per-request cost was recorded but never surfaced, so
                        # "what does a query cost?" could only be answered by
                        # querying the tracker. One line per request makes the
                        # distribution readable straight from the logs.
                        logger.info(
                            "CHAT_COST endpoint=%s tenant_id=%s user_id=%s model=%s "
                            "tokens_in=%d tokens_out=%d cost_usd=%.6f",
                            endpoint,
                            TenantContext.get(),
                            user_id,
                            acc.model,
                            acc.tokens_in,
                            acc.tokens_out,
                            tracked_cost,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to record token usage: {e}")
                token_accumulator_var.reset(token)

        return wrapper

    return decorator


def _cache_language_key(message: str, language: str) -> str:
    normalized_lang = (language or "en").lower().strip()
    return f"{normalized_lang}:{message.strip()}"


from pydantic import BaseModel, Field

# A title needs the opening of a message, never the whole thing. The field was
# an unbounded `str` on an endpoint that is anonymous-accessible, rate-limited
# only by request count, and outside the anonymous chat quota — so one caller
# could bill 20 LLM calls a minute on arbitrarily large prompts.
_TITLE_INPUT_MAX_CHARS = 2000


class TitleRequest(BaseModel):
    first_message: str = Field(..., max_length=_TITLE_INPUT_MAX_CHARS)


@router.post("/chat/title")
@limiter.limit("20/minute")
async def generate_title_endpoint(
    request: Request,
    body: TitleRequest,
    user: dict = Depends(get_optional_user),
    container: ServiceContainer = Depends(get_container_async),
):
    """
    Synchronously generate a short 3-6 word title for a conversation
    using the active LLM service.
    """
    first_message = body.first_message.strip()
    if not first_message:
        return {"title": "New conversation"}

    # This endpoint invokes the LLM on behalf of an anonymous caller, so it has
    # to sit behind the same admission controls as /api/chat. Previously it was
    # rate-limited by request count only and skipped the anonymous quota
    # entirely, leaving a provider-spend vector open. The reservation is
    # deliberately not released: a title is a real LLM call and counts as a turn.
    user = resolve_anon_identity(user, request.headers.get("X-Session-Id"))
    quota = await _enforce_anon_quota(user, container)
    if quota.quota_exceeded:
        return _anon_quota_response(quota)

    try:
        system_prompt = "Create a concise, meaningful chat title. Return ONLY the title, no quotes, no punctuation, and keep it under 6 words."
        user_prompt = f"Title this conversation: {first_message}"

        raw_title = await container.ollama.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

        title = raw_title.strip().replace('"', "").replace("'", "").strip()
        if title:
            if len(title) > 50:
                title = title[:47] + "..."
            return {"title": title}
    except Exception as e:
        logger.warning(f"Failed to generate conversation title via LLM: {e}")

    fallback = first_message[:47] + "..." if len(first_message) > 50 else first_message
    return {"title": fallback}


def _conversation_context_limit_response(chat_body: ChatRequest) -> JSONResponse | None:
    """Return a stable 409 when the durable thread exceeds the safe input budget.

    Never blocks a message carrying acute crisis language. Without this
    check, a long-running conversation that trips the token budget on the
    SAME turn a user expresses suicidal ideation would return a generic
    "start a new chat" 409 before DistressStage ever runs — silently
    skipping crisis preemption for exactly the population this app most
    needs to catch.

    NOTE: `has_crisis_keywords()` reuses `_DISTRESS_KEYWORD_RE`, which is
    broader than acute crisis language (it also matches MODERATE-level words
    like "anxiety", "alone", "overwhelm" per serene_mind_engine.py's severity
    map). DistressStage only terminates the pipeline early (cheaply) for
    SEVERE/CRISIS-level assessments — a MODERATE-only match here still falls
    through to full retrieval/generation. So this bypass does NOT "stay
    cheap" for every word it matches; it only avoids the safety failure mode
    above. A bypassed, budget-exhausted conversation runs the full pipeline
    cost on every turn that contains one of these common words instead of
    getting the 409 that would otherwise force a new chat. Deliberate
    safety-over-cost tradeoff — re-derive `has_crisis_keywords()` from the
    SEVERE+CRISIS pattern set only if this cost becomes a measured problem.
    """
    if has_crisis_keywords(chat_body.user_message):
        return None

    budget = assess_conversation_context(
        [message.model_dump() for message in chat_body.messages],
        chat_body.user_message,
        chat_body.language or "en",
        conversation_summary=chat_body.conversation_summary if not chat_body.incognito else None,
        attachment_context=chat_body.attachment_context if not chat_body.incognito else None,
    )
    if not budget.exhausted:
        return None

    logger.warning(
        "CHAT_CONTEXT_LIMIT_EXCEEDED estimated_tokens=%d max_input_tokens=%d session_id=%s",
        budget.estimated_tokens,
        budget.max_input_tokens,
        "present" if chat_body.session_id else "absent",
    )
    return JSONResponse(
        status_code=409,
        content={
            "error": "Conversation context exhausted",
            "error_code": CONTEXT_ERROR_CODE,
            "detail": "This conversation has reached its safe context limit. Start a new chat to continue.",
            "context_budget": budget.to_dict(),
        },
    )


@router.post("/chat", response_model=None)
@limiter.limit(settings.chat_rate_limit)
@record_token_usage(endpoint="/api/chat")
@backpressure_semaphore
async def chat_endpoint(
    request: Request,
    chat_body: ChatRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_optional_user),
    container: ServiceContainer = Depends(get_container_async),
    _tenant=Depends(set_tenant_from_request),
) -> ChatResponse | JSONResponse:
    """
    Main conversational endpoint.

    When queue is enabled (default), returns 202 with job_id immediately.
    Add ?wait=true to block for result (backward compat).
    Delegates inline to ChatRequestOrchestrator when queue is disabled.
    """
    chat_body.user_message = sanitize_user_input(chat_body.user_message, max_length=10000)

    is_benchmark = is_benchmark_request(request)

    user = resolve_anon_identity(user, chat_body.session_id)

    # Per-user daily spend cap — prevent a single abusive user from draining
    # the entire tenant budget.
    _check_user_id = user.get("id", "anonymous") if user else "anonymous"
    if get_cost_tracker().is_user_over_budget(_check_user_id):
        return JSONResponse(
            status_code=429,
            content={
                "error": "User daily budget exceeded",
                "detail": "You have reached your daily usage limit. Please try again tomorrow.",
                "user_budget_exceeded": True,
            },
            headers={"Retry-After": "3600"},
        )

    if getattr(chat_body, "assistant", None) is not None:
        await authorize_chat_assistant(chat_body, user, container)

    quota = await _enforce_anon_quota(user, container)
    if quota.quota_exceeded:
        return _anon_quota_response(quota)

    try:
        await populate_server_side_history(chat_body, user, container, is_benchmark)
    except Exception:
        # History population is optional enrichment; a failure here must not
        # leak the quota reservation taken at admission.
        await _release_anon_quota(user, container, quota)
        raise

    context_limit_response = _conversation_context_limit_response(chat_body)
    if context_limit_response is not None:
        await _release_anon_quota(user, container, quota)
        return context_limit_response

    if (
        container.job_queue
        and settings.queue_enabled
        and not is_benchmark
        and not chat_body.incognito
    ):
        from app.services.job_queue import QueueFullError

        _reject_if_queue_unattended()
        chat_body_dict = chat_body.model_dump()
        user_dict = (
            {"id": user.get("id", "anonymous"), "is_anonymous": bool(user.get("is_anonymous"))}
            if user
            else {"id": "anonymous", "is_anonymous": False}
        )
        request_data = {
            "chat_body": chat_body_dict,
            "user": user_dict,
            "is_benchmark": False,
            # Lets the queued worker release the reservation when the job
            # fails; a successful job keeps it (commit on completion).
            "quota_reservation_id": quota.reservation_id,
        }
        try:
            job_id, queue_pos = await container.job_queue.enqueue(
                request_data, user.get("id", "anonymous"), is_stream=False
            )
        except QueueFullError:
            # The reservation was recorded at admission; give it back since
            # the interaction never entered the queue.
            await _release_anon_quota(user, container, quota)
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too Many Requests",
                    "detail": "Server is busy. Please try again shortly.",
                },
                # P3-3 (review): same herd-spreading as admission shed.
                headers={"Retry-After": str(backpressure_retry_after_seconds())},
            )
        except Exception as exc:
            # Live chaos-testing discovery (2026-09-05): JobQueue.enqueue() is
            # Redis-backed with NO fallback — a Redis outage previously raised
            # an uncaught redis.exceptions.ConnectionError here, turning into
            # a generic, cause-hiding HTTP 500 for every chat request. This is
            # a genuine architectural SPOF (root CLAUDE.md's Redis-degradation
            # section only documented cache/quota degrading gracefully, not
            # that the entire chat job queue hard-depends on Redis with none).
            # An in-memory fallback queue is a real feature, not a hotfix;
            # until built, at minimum give an honest, retryable 503 instead of
            # an opaque 500 that looks like an application bug.
            # Module-scoped check only — matching bare "ConnectionError" by name
            # also caught Python's builtin ConnectionError raised for unrelated
            # reasons elsewhere in enqueue(), misclassifying real bugs as a
            # transient Redis outage (code-review finding, 2026-09-05).
            is_redis_error = "redis" in type(exc).__module__.lower()
            if not is_redis_error:
                raise
            logger.error(f"Chat job enqueue failed — queue backend unavailable: {exc}")
            await _release_anon_quota(user, container, quota)
            return JSONResponse(
                status_code=503,
                content={
                    "error": "Service Temporarily Unavailable",
                    "detail": "Chat is briefly unavailable. Please try again in a few seconds.",
                },
                # P3-3 (review): same herd-spreading as admission shed.
                headers={"Retry-After": str(backpressure_retry_after_seconds())},
            )

        if request.query_params.get("wait", "").lower() == "true":
            deadline = time.time() + settings.queue_default_timeout
            while time.time() < deadline:
                job = await container.job_queue.get_job(job_id)
                if job and job["status"] == "completed" and job["result"]:
                    return ChatResponse(**job["result"])
                if job and job["status"] == "failed":
                    from app.sanitization import sanitize_client_error

                    raw_err = job.get("error", "Pipeline failed")
                    logger.error(
                        "Synchronous wait on failed job %s: %s",
                        sanitize_log_input(job_id),
                        sanitize_log_input(str(raw_err)),
                    )
                    raise HTTPException(status_code=500, detail=sanitize_client_error(raw_err))
                await asyncio.sleep(0.5)
            raise HTTPException(status_code=504, detail="Pipeline timeout")

        return JSONResponse(
            status_code=202,
            content={
                "job_id": job_id,
                "status": "queued",
                "queue_position": queue_pos,
                "poll_url": f"/api/jobs/{job_id}",
            },
        )

    from app.orchestrator import ChatRequestOrchestrator

    orchestrator = ChatRequestOrchestrator(container)
    try:
        response = await orchestrator.orchestrate(request, chat_body, background_tasks, user)
    except Exception:
        await _release_anon_quota(user, container, quota)
        raise
    if getattr(response, "blocked", False):
        await _release_anon_quota(user, container, quota)
    else:
        await _charge_anon_quota(user, container, quota)
    return response


@router.post("/chat/v2", response_model=None)
@limiter.limit(settings.chat_rate_limit)
@record_token_usage(endpoint="/api/chat/v2")
@backpressure_semaphore
async def chat_v2_endpoint(
    request: Request,
    chat_body: ChatRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_optional_user),
    container: ServiceContainer = Depends(get_container_async),
    _tenant=Depends(set_tenant_from_request),
) -> ChatResponse | JSONResponse:
    """Alternative chat endpoint backed by the ChatEngine facade (C3).

    A/B surface for the unified ``app.chat_engine.ChatEngine`` deep-module
    facade. Delegates to the SAME ``PipelineCoordinator.execute`` as the
    primary ``/api/chat`` route — only the wrapping surface differs. The
    legacy route stays untouched; this exists purely for low-risk rollout.
    """
    chat_body.user_message = sanitize_user_input(chat_body.user_message, max_length=10000)
    is_benchmark = is_benchmark_request(request)
    user = resolve_anon_identity(user, chat_body.session_id)

    # Per-user daily spend cap — prevent a single abusive user from draining
    # the entire tenant budget.
    _check_user_id = user.get("id", "anonymous") if user else "anonymous"
    if get_cost_tracker().is_user_over_budget(_check_user_id):
        return JSONResponse(
            status_code=429,
            content={
                "error": "User daily budget exceeded",
                "detail": "You have reached your daily usage limit. Please try again tomorrow.",
                "user_budget_exceeded": True,
            },
            headers={"Retry-After": "3600"},
        )

    if getattr(chat_body, "assistant", None) is not None:
        await authorize_chat_assistant(chat_body, user, container)

    quota = await _enforce_anon_quota(user, container)
    if quota.quota_exceeded:
        return _anon_quota_response(quota)

    try:
        await populate_server_side_history(chat_body, user, container, is_benchmark)
    except Exception:
        # History population is optional enrichment; a failure here must not
        # leak the quota reservation taken at admission.
        await _release_anon_quota(user, container, quota)
        raise

    context_limit_response = _conversation_context_limit_response(chat_body)
    if context_limit_response is not None:
        await _release_anon_quota(user, container, quota)
        return context_limit_response

    from app.chat_engine import ChatEngine
    from app.orchestrator import _provenance_manifest_for_result, _strict_provenance_manifest

    engine = ChatEngine(container)
    try:
        result = await engine.chat_advanced(
            chat_body,
            user=user or {"id": "anonymous"},
            is_benchmark=is_benchmark,
        )
    except Exception:
        await _release_anon_quota(user, container, quota)
        raise
    if result.blocked:
        await _release_anon_quota(user, container, quota)
    else:
        await _charge_anon_quota(user, container, quota)
    return ChatResponse(
        response=result.final_answer,
        intent=result.intent,
        meditation_step=result.meditation_step,
        citations=[Citation(**c) for c in result.citations],
        blocked=result.blocked,
        block_reason=result.block_reason or None,
        trace_id=result.trace_id,
        latency_ms=result.latency_ms,
        model_used=result.model_used or None,
        model_provider=result.model_provider or None,
        route_decision=result.route_decision or None,
        query_tier=result.query_tier or None,
        cache_hit=result.cache_hit,
        proactive_serene_mind=result.proactive_serene_mind,
        faithfulness_score=result.faithfulness_score,
        hallucination_flag=result.hallucination_flag,
        verification=result.verification,
        citations_verified=result.citations_verified,
        orphan_citations_stripped=result.orphan_citations_stripped,
        node_timings=result.node_timings or None,
        # Retrieval provenance reaches the caller. Both fields were already
        # populated on PipelineResult and forwarded to the telemetry sink, but
        # omitted here — so no consumer could tell which lane (Qdrant dense/
        # sparse, OKF, Neo4j subgraph, LightRAG) produced an answer, and any
        # "the graph improved this" claim was unverifiable from the API.
        # TrustNLP 2026 F21 Auditability Gaps; docs/EVAL_PRECONDITIONS.md §4.
        evaluation_trace=getattr(result, "evaluation_trace", None) or None,
        retrieval_metadata=getattr(result, "retrieval_metadata", None) or None,
        audio_url=result.audio_url,
        kg_concept_nodes=result.kg_concept_nodes,
        daily_practice_card=result.daily_practice_card,
        live_logistics_events=getattr(result, "live_logistics_events", []),
        answer_evidence=(
            None
            if getattr(result, "answer_evidence", None) is None
            else asdict(result.answer_evidence)
        ),
        guidance_plan=(
            None if getattr(result, "guidance_plan", None) is None else asdict(result.guidance_plan)
        ),
        grounding_state=grounding_state_for(result),
        release_manifest=to_public_manifest_dict(getattr(result, "release_manifest", None)),
        provenance_manifest=_strict_provenance_manifest(result),
        # TrustNLP 2026 F21/F33: this field was declared on the schema and
        # assigned nowhere in production code (only in
        # tests/test_provenance_api.py), so it was structurally always null.
        # Same projection already used for provenance_manifest above —
        # ai_provenance is the loosely-typed dict[str, Any] twin of that
        # strict model, not a second computation.
        ai_provenance=_provenance_manifest_for_result(result),
    )


@router.post("/chat/stream", response_model=None)
@limiter.limit(settings.chat_rate_limit)
async def chat_stream_endpoint(
    request: Request,
    chat_body: ChatRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_optional_user),
    container: ServiceContainer = Depends(get_container_async),
    _tenant=Depends(set_tenant_from_request),
) -> JSONResponse | StreamingResponse:
    """
    Streaming chat endpoint using Server-Sent Events (SSE).

    When queue enabled (default), returns 202 with stream_url immediately.
    Client then connects to GET /api/chat/stream/{job_id} for SSE.
    Delegates inline to ChatStreamRequestOrchestrator when queue is disabled.

    Admission control is manual here (RP-A1), not the shared decorator: the
    decorator releases the slot when the handler returns, but the inline
    stream's pipeline task outlives that return. The slot is held for the
    life of the stream instead — ownership transfers to the stream
    orchestrator, which releases it in the SSE generator's finally
    (including client disconnect). Crisis-keyword requests bypass the cap.
    """
    chat_body.user_message = sanitize_user_input(chat_body.user_message, max_length=10000)

    is_benchmark = is_benchmark_request(request)

    user = resolve_anon_identity(user, chat_body.session_id)

    # Per-user daily spend cap — prevent a single abusive user from draining
    # the entire tenant budget.
    _check_user_id = user.get("id", "anonymous") if user else "anonymous"
    if get_cost_tracker().is_user_over_budget(_check_user_id):
        return JSONResponse(
            status_code=429,
            content={
                "error": "User daily budget exceeded",
                "detail": "You have reached your daily usage limit. Please try again tomorrow.",
                "user_budget_exceeded": True,
            },
            headers={"Retry-After": "3600"},
        )

    if getattr(chat_body, "assistant", None) is not None:
        await authorize_chat_assistant(chat_body, user, container)

    # RP-A1/RP-A2: manual admission (not the shared decorator), and admission
    # runs FIRST (review 2026-10-15): a shed request must do no quota
    # reservation and no history work — rejection happens before any
    # per-seeker side effect, so the shed path has nothing to roll back.
    # The decorator releases the slot when the handler returns, but the
    # inline stream's pipeline task outlives that return — so the slot is
    # held for the life of the stream instead. Ownership rule: the
    # ``finally`` below releases ``slot`` on every exit (return, raise,
    # cancellation) EXCEPT a successful inline hand-off, which transfers
    # ownership to the stream orchestrator (it releases when the pipeline
    # task or the SSE body ends). A None slot is a crisis-bypass admission
    # with nothing to release.
    slot, shed = await _admit_chat(chat_body)
    if shed is not None:
        return shed

    slot_transferred = False
    try:
        quota = await _enforce_anon_quota(user, container)
        if quota.quota_exceeded:
            return _anon_quota_response(quota)

        try:
            await populate_server_side_history(chat_body, user, container, is_benchmark)
        except Exception:
            # History population is optional enrichment; a failure here must not
            # leak the quota reservation taken at admission.
            await _release_anon_quota(user, container, quota)
            raise

        context_limit_response = _conversation_context_limit_response(chat_body)
        if context_limit_response is not None:
            await _release_anon_quota(user, container, quota)
            return context_limit_response

        if (
            container.job_queue
            and settings.queue_enabled
            and not is_benchmark
            and not chat_body.incognito
        ):
            from app.services.job_queue import QueueFullError

            _reject_if_queue_unattended()
            chat_body_dict = chat_body.model_dump()
            user_dict = (
                {"id": user.get("id", "anonymous"), "is_anonymous": bool(user.get("is_anonymous"))}
                if user
                else {"id": "anonymous", "is_anonymous": False}
            )
            request_data = {
                "chat_body": chat_body_dict,
                "user": user_dict,
                "is_benchmark": False,
                # Lets the queued worker release the reservation when the job
                # fails; a successful job keeps it (commit on completion).
                "quota_reservation_id": quota.reservation_id,
            }
            try:
                job_id, queue_pos = await container.job_queue.enqueue(
                    request_data, user.get("id", "anonymous"), is_stream=True
                )
            except QueueFullError:
                # The reservation was recorded at admission; give it back since
                # the interaction never entered the queue.
                await _release_anon_quota(user, container, quota)
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "Too Many Requests",
                        "detail": "Server is busy. Please try again shortly.",
                    },
                    # P3-3 (review): same herd-spreading as admission shed.
                    headers={"Retry-After": str(backpressure_retry_after_seconds())},
                )
            except Exception as exc:
                # See the non-stream enqueue call site above for the full
                # rationale — same live chaos-testing discovery, same fix.
                # Module-scoped check only — matching bare "ConnectionError" by name
                # also caught Python's builtin ConnectionError raised for unrelated
                # reasons elsewhere in enqueue(), misclassifying real bugs as a
                # transient Redis outage (code-review finding, 2026-09-05).
                is_redis_error = "redis" in type(exc).__module__.lower()
                if not is_redis_error:
                    raise
                logger.error(f"Chat stream job enqueue failed — queue backend unavailable: {exc}")
                await _release_anon_quota(user, container, quota)
                return JSONResponse(
                    status_code=503,
                    content={
                        "error": "Service Temporarily Unavailable",
                        "detail": "Chat is briefly unavailable. Please try again in a few seconds.",
                    },
                    # P3-3 (review): same herd-spreading as admission shed.
                    headers={"Retry-After": str(backpressure_retry_after_seconds())},
                )

            return JSONResponse(
                status_code=202,
                content={
                    "job_id": job_id,
                    "status": "queued",
                    "queue_position": queue_pos,
                    "stream_url": f"/api/chat/stream/{job_id}",
                },
            )

        from app.stream_orchestrator import ChatStreamRequestOrchestrator

        orchestrator = ChatStreamRequestOrchestrator(container)
        response = await orchestrator.orchestrate_stream(
            request,
            chat_body,
            background_tasks,
            user,
            anon_quota=quota,
            admission_slot=slot,
        )
        slot_transferred = True
        return response
    finally:
        if slot is not None and not slot_transferred:
            slot.release()


@router.get("/chat/stream/{job_id}")
async def chat_stream_poll(
    job_id: str,
    request: Request,
    container: ServiceContainer = Depends(get_container_async),
    user: dict = Depends(get_optional_user),
):
    """
    SSE endpoint for queued streaming jobs. Only the job owner may stream.

    Reads events from Redis Stream (populated by worker) and streams them as SSE.
    """
    if not container.job_queue:
        raise HTTPException(status_code=503, detail="Job tracking is not available.")

    # For anonymous (incognito) users, derive per-session identity from the
    # X-Session-Id header so ownership checks isolate incognito sessions.
    session_id = request.headers.get("X-Session-Id")
    user = resolve_anon_identity(user, session_id)
    require_scoped_identity(user)

    # Ownership check — return 404 on mismatch to avoid confirming existence.
    job_meta = await container.job_queue.get_job(job_id)
    if not job_meta or str(job_meta.get("user_id") or "") != str(user.get("id") or ""):
        raise HTTPException(status_code=404, detail="Job not found or expired")

    import redis.asyncio as aioredis

    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    stream_key = f"job:stream:{job_id}:events"
    requested_last_id = (request.headers.get("last-event-id") or "0").strip()
    last_event_id = requested_last_id if re.fullmatch(r"\d+-\d+", requested_last_id) else "0"

    async def _sse():
        last_id = last_event_id
        last_done_data: str | None = None
        timeout = settings.queue_default_timeout
        deadline = time.time() + timeout
        try:
            while time.time() < deadline:
                try:
                    results = await r.xread({stream_key: last_id}, count=10, block=2000)
                except Exception as e:
                    logger.debug("SSE Redis xread failed (retrying): %s", e)
                    await asyncio.sleep(0.5)
                    continue

                if not results:
                    job_meta = await r.hgetall(f"job:{job_id}:meta")
                    if job_meta:
                        status = job_meta.get("status", "")
                        if status == "failed":
                            yield "event: error\ndata: Pipeline failed\n\n"
                            return
                        if status == "cancelled":
                            yield "event: error\ndata: Job cancelled\n\n"
                            return
                        if status == "completed" and last_id == "0":
                            await asyncio.sleep(0.5)
                            continue
                        if status in ("completed", "failed") and last_id != "0":
                            # A terminal done entry was already delivered from
                            # the Redis stream. Do not synthesize a second done
                            # event; duplicate completion events can make the
                            # browser persist metadata twice and obscure the
                            # authoritative final event.
                            if last_done_data is not None:
                                return
                            fallback = json.dumps({"grounding_state": "system_error"})
                            yield f"event: done\\ndata: {fallback}\\n\\n"
                            return
                    continue

                for _stream_name, entries in results:
                    for entry_id, fields in entries:
                        last_id = entry_id
                        data = fields.get("data", "")
                        event_id = f"id: {entry_id}\n"
                        if data == "__COMPLETE__":
                            fallback = last_done_data or json.dumps(
                                {"grounding_state": "system_error"}
                            )
                            yield f"{event_id}event: done\ndata: {fallback}\n\n"
                            return
                        if data == "__ERROR__":
                            yield f"{event_id}event: error\ndata: Pipeline failed\n\n"
                            return
                        try:
                            parsed = json.loads(data)
                            if isinstance(parsed, dict):
                                evt = parsed.get("event", "status")
                                dat = parsed.get("data", "")
                                if evt == "done":
                                    last_done_data = str(dat)
                                    yield f"{event_id}event: {evt}\ndata: {dat}\n\n"
                                    return
                                yield f"{event_id}event: {evt}\ndata: {dat}\n\n"
                            else:
                                yield f"{event_id}event: token\ndata: {str(parsed)}\n\n"
                        except (json.JSONDecodeError, TypeError):
                            yield f"{event_id}event: token\ndata: {data}\n\n"
                await asyncio.sleep(0.1)
            yield "event: error\ndata: Stream timeout\n\n"
        finally:
            await r.close()

    return StreamingResponse(
        _sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# === Breath Technique Teaching ===

# 1-hr TTL, bounded to 256 entries to prevent unbounded memory growth
_breath_teaching_cache = TTLCache(maxsize=256, ttl=3600)

_TECHNIQUE_QUERIES: dict[str, str] = {
    "serene_mind": "What do the recorded teachings say about conscious breathing and the long exhale as a path to the beautiful state?",
    "box": "What do the recorded teachings say about equanimity, balance, and equal-phase breathing?",
    "4_7_8": "What do the recorded teachings say about deep rest, surrender, and releasing tension through the breath?",
    "deep_vitality": "What do the recorded teachings say about prana, life force, and breath awareness?",
}
_DEFAULT_TECHNIQUE_QUERY = "What do the recorded teachings say about the role of conscious breathing in spiritual practice?"


@router.get("/breath-teaching/{technique_id}", tags=["Meditation"])
@limiter.limit("10/minute")
async def get_breath_teaching(
    request: Request,
    technique_id: str,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container_async),
) -> dict:
    """Return a source-verified passage for a breathing practice.

    This route intentionally reuses the first-person serving pipeline. It does
    not call a free-form generator when retrieval is empty or unavailable:
    teacher-attributed text must come from an integrity-checked recorded clip.
    """
    if technique_id not in _TECHNIQUE_QUERIES:
        raise HTTPException(status_code=404, detail="Unknown breathing technique")

    if (
        not getattr(settings, "first_person_route_enabled", False)
        or getattr(settings, "first_person_mode", "disabled") == "disabled"
    ):
        raise HTTPException(
            status_code=503,
            detail="Verified recorded teachings are currently unavailable.",
        )

    # The snippet is independent of the user's identity, but it is scoped to
    # the immutable first-person collection/config so a collection switch cannot
    # return a stale snippet from the previous release.
    cache_key = (
        f"{settings.first_person_collection}:"
        f"{settings.first_person_mode}:{technique_id}"
    )
    cached = _breath_teaching_cache.get(cache_key)
    if cached is not None:
        return {"technique_id": technique_id, "teaching": cached, "cached": True}

    query = _TECHNIQUE_QUERIES[technique_id]
    try:
        # Reuse the same store, integrity/relevance gates, rights filter,
        # attribution contract and embedder as the first-person API. Do not use
        # the general teaching corpus for a response labelled as a recorded
        # teacher passage.
        from app.api.first_person import _english_query, _output_rail_passes, _pipeline
        from services.attribution import clean_wire_speaker

        embedding = getattr(container, "embedding", None)
        if embedding is None:
            raise HTTPException(
                status_code=503, detail="Verified teaching retrieval is unavailable."
            )

        llm_service = (
            getattr(container, "openrouter", None)
            or getattr(container, "nim", None)
            or getattr(container, "ollama", None)
        )
        pipeline = _pipeline(
            settings.first_person_collection,
            getattr(container, "serene_mind", None),
            embedding if settings.first_person_rerank_enabled else None,
            llm_service,
        )
        retrieval_query = await _english_query(query, container)
        encoded = await embedding.encode_single_full_async(retrieval_query)
        dense_vec = encoded.get("dense")
        if not isinstance(dense_vec, list) or not dense_vec:
            raise RuntimeError("embedding service returned no dense vector")
        raw_sparse = encoded.get("sparse") or {}
        sparse_vec = (
            {
                "indices": [int(k) for k in raw_sparse.keys()],
                "values": [float(v) for v in raw_sparse.values()],
            }
            if raw_sparse
            else None
        )

        result = await asyncio.wait_for(
            asyncio.to_thread(
                pipeline.execute,
                query=query,
                query_dense_vector=dense_vec,
                query_sparse_vector=sparse_vec,
                teacher_id="both",
                max_clips=1,
                retrieval_query=retrieval_query,
                language="en",
                cache_bypass=False,
            ),
            timeout=float(settings.pipeline_timeout),
        )
    except HTTPException:
        raise
    except TimeoutError as exc:
        logger.warning(
            "Verified breath teaching timed out for technique=%s",
            sanitize_log_input(technique_id),
        )
        raise HTTPException(
            status_code=503, detail="Verified teaching retrieval timed out."
        ) from exc
    except Exception as exc:
        logger.warning(
            "Verified breath teaching failed for technique=%s error=%s",
            sanitize_log_input(technique_id),
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=503, detail="Verified teaching retrieval is unavailable."
        ) from None

    citations = getattr(result, "citations", None)
    if getattr(result, "status", None) == "error" or not isinstance(citations, list):
        raise HTTPException(status_code=503, detail="Verified teaching retrieval is unavailable.")

    # FirstPersonPipeline has already validated clip integrity and eligibility.
    # Recheck the public contract at this API boundary so malformed/stale
    # citations can never be turned into an apparently authentic teaching.
    citation = next(
        (
            item
            for item in citations
            if isinstance(item, dict)
            and item.get("is_verbatim") is True
            and isinstance(item.get("verbatim_text"), str)
            and item.get("verbatim_text", "").strip()
            and isinstance(item.get("transcript_hash"), str)
            and hashlib.sha256(item["verbatim_text"].encode("utf-8")).hexdigest()
            == item["transcript_hash"]
            and isinstance(item.get("video_id"), str)
            and item.get("video_id", "").strip()
            and isinstance(item.get("start_ms"), int)
            and isinstance(item.get("end_ms"), int)
            and item["start_ms"] >= 0
            and item["end_ms"] > item["start_ms"]
        ),
        None,
    )
    if citation is None:
        # An abstention or empty/invalid evidence result is not a reason to
        # generate a substitute teaching. Keep it visible as unavailable.
        raise HTTPException(
            status_code=503,
            detail="No verified recorded passage was found for this practice.",
        )

    quote = citation["verbatim_text"].strip()
    speaker_label = clean_wire_speaker(
        citation.get("speaker"),
        citation.get("speaker_verified") if isinstance(citation.get("speaker_verified"), bool) else None,
        citation.get("channel"),
    )
    # Weak matches are shown as related excerpts, never as direct answers.
    prefix = (
        "Related, not a direct answer:\n\n"
        if getattr(result, "status", None) != "success"
        or getattr(result, "is_direct_answer", False) is not True
        else ""
    )
    teaching_parts = [f"{prefix}“{quote}”"]
    teaching_parts.append(f"— {speaker_label or 'unverified clip'}")
    source_url = citation.get("url") or citation.get("source_url")
    if isinstance(source_url, str) and source_url.startswith("https://"):
        teaching_parts.append(source_url)
    teaching = "\n\n".join(teaching_parts)

    # A missing/crashed output rail is not treated as approval.
    if not await _output_rail_passes(container, teaching):
        raise HTTPException(
            status_code=503, detail="The recorded passage did not pass output safety checks."
        )

    _breath_teaching_cache[cache_key] = teaching
    return {"technique_id": technique_id, "teaching": teaching, "cached": False}


@router.get("/admin/concept-graph")
async def get_concept_graph(
    container: ServiceContainer = Depends(get_container_async),
    user: dict = Depends(get_current_user_from_supabase),
):
    """Return live graph data only; never substitute fabricated mock nodes."""
    if not user or not user.get("is_superuser"):
        raise HTTPException(status_code=403, detail="Admin access required")
    if not settings.neo4j_uri:
        raise HTTPException(
            status_code=503,
            detail="Concept graph service is not configured.",
        )

    try:
        def _query_graph():
            driver = container.neo4j_driver
            if driver is None:
                raise RuntimeError("graph_driver_unavailable")
            nodes = {}
            links = []
            with driver.session() as session:
                result = session.run(
                    """
                    MATCH (n)-[r]->(m)
                    RETURN n.entity_id AS source_name, labels(n)[0] AS source_label,
                           type(r) AS rel_type,
                           m.entity_id AS target_name, labels(m)[0] AS target_label
                    LIMIT 100
                    """
                )
                for record in result:
                    src = record["source_name"]
                    tgt = record["target_name"]
                    if not src or not tgt:
                        continue
                    nodes.setdefault(
                        src, {"id": src, "group": record["source_label"] or "Concept"}
                    )
                    nodes.setdefault(
                        tgt, {"id": tgt, "group": record["target_label"] or "Concept"}
                    )
                    links.append(
                        {"source": src, "target": tgt, "type": record["rel_type"]}
                    )
            return {
                "nodes": list(nodes.values()),
                "links": links,
                "available": True,
                "source": "memgraph",
            }

        return await asyncio.to_thread(_query_graph)
    except Exception as exc:
        # Avoid leaking database connection details while making degraded
        # service status explicit to the authenticated admin client.
        logger.warning("Failed to query concept graph: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Concept graph data is currently unavailable.",
        ) from None
