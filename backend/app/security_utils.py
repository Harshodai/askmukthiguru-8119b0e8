"""
Mukthi Guru — Security Utilities

Shared validation and sanitization helpers for critical security fixes:
- SQL injection prevention (Supabase query parameter validation)
- Command injection prevention (subprocess input sanitization)
- Log injection prevention (correlation ID / session ID validation)
- CSRF token generation and validation
"""

import hashlib
import hmac
import os
import re
import secrets
import time
from collections import deque
from typing import Optional

# YouTube video ID: exactly 11 characters, alphanumeric, hyphen, underscore
_YOUTUBE_VIDEO_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{11}$")

# Safe UUID / alphanumeric string for session IDs, user IDs, correlation IDs
_SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9_:-]{1,128}$")

# Strict correlation ID: alphanumeric, hyphen, underscore (no newlines, no control chars)
_CORRELATION_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

# ISO 8601 date substring (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?)?$")

# Safe path component (no path traversal)
_SAFE_PATH_RE = re.compile(r"^[a-zA-Z0-9_./-]+$")

# Safe email
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


def is_benchmark_request(request) -> bool:
    """
    Detect a benchmark/test request via the X-Test-Key header.

    The header only grants benchmark bypass when ALL of these hold:
    - ENABLE_TEST_AUTH=true  (settings.enable_test_auth)
    - IS_PRODUCTION=false    (settings.is_production is False)
    - BENCHMARK_SECRET is configured and non-empty
    - the X-Test-Key value matches BENCHMARK_SECRET (constant-time compare)

    JWT_SECRET is never accepted here — leaking it must not unlock benchmark
    bypass. This is the single guard shared by the rate limiter, the chat
    handlers, and the sync/stream orchestrators.

    Tests should patch settings attributes directly (e.g. settings.enable_test_auth = True)
    rather than patching os.environ, as this function reads from the settings object.
    """
    from app.config import settings

    benchmark_secret = getattr(settings, "benchmark_secret", "") or ""
    test_key = request.headers.get("X-Test-Key", "")
    if not (
        getattr(settings, "enable_test_auth", False)
        and not getattr(settings, "is_production", True)
    ):
        return False
    if not benchmark_secret or not test_key:
        return False
    return hmac.compare_digest(test_key, benchmark_secret)


def validate_video_id(video_id: str) -> str:
    """
    Validate a YouTube video ID.
    Raises ValueError if invalid.
    """
    if not video_id or not _YOUTUBE_VIDEO_ID_RE.match(video_id):
        raise ValueError(f"Invalid video ID: {video_id!r}")
    return video_id


def is_valid_youtube_url(url: str) -> bool:
    """Strict regex validation for scraped YouTube URLs to prevent SSRF and injection."""
    if not url or len(url) > 250:
        return False
    # Strict character set check: only allow standard URL characters
    if not re.match(r"^[a-zA-Z0-9_.:/?=&%#-]+$", url):
        return False
    # Domain check: must be youtube.com, youtu.be, or a valid subdomain of youtube.com
    domain_match = re.match(
        r"^https?://(?:[a-zA-Z0-9_-]+\.)?(?:youtube\.com|youtu\.be)(?:/|$)", url
    )
    return bool(domain_match)


def validate_session_id(session_id: Optional[str]) -> Optional[str]:
    """
    Validate a session ID before use in logs / DB queries.
    Returns None if input is None, otherwise a sanitized string.
    Raises ValueError if invalid characters or too long.
    """
    if session_id is None:
        return None
    session_id = session_id.strip()
    if not session_id:
        return None
    if not _SAFE_ID_RE.match(session_id):
        raise ValueError("Invalid session_id format")
    return session_id


def validate_correlation_id(cid: Optional[str]) -> Optional[str]:
    """
    Validate a correlation ID from X-Correlation-ID header.
    Returns a safe value or None if invalid (caller should generate a new one).
    """
    if not cid:
        return None
    cid = cid.strip()
    if not _CORRELATION_ID_RE.match(cid):
        return None
    return cid


def validate_iso_date(date_str: Optional[str]) -> Optional[str]:
    """
    Validate an ISO-8601 date string before using in DB queries.
    Returns None if input is None, otherwise the string.
    Raises ValueError if invalid.
    """
    if date_str is None:
        return None
    date_str = date_str.strip()
    if not date_str:
        return None
    if not _ISO_DATE_RE.match(date_str):
        raise ValueError(f"Invalid ISO date string: {date_str!r}")
    return date_str


def validate_user_id(user_id: Optional[str]) -> Optional[str]:
    """
    Validate a user ID before use in DB queries.
    Returns None if input is None, otherwise a sanitized string.
    Raises ValueError if invalid.
    """
    if user_id is None:
        return None
    user_id = user_id.strip()
    if not user_id:
        return None
    if not _SAFE_ID_RE.match(user_id):
        raise ValueError("Invalid user_id format")
    return user_id


def sanitize_path(path: str, base_dir: Optional[str] = None) -> str:
    """
    Sanitize a filesystem path to prevent path traversal.
    If base_dir is provided, ensures the resolved path is within base_dir.
    Raises ValueError if path is outside base_dir or contains invalid characters.
    """
    if not path:
        raise ValueError("Empty path")
    path = os.path.normpath(path)
    if ".." in path.split(os.sep):
        raise ValueError("Path traversal detected")
    if not _SAFE_PATH_RE.match(path):
        raise ValueError("Invalid path characters")
    if base_dir:
        abs_base = os.path.abspath(base_dir)
        abs_path = os.path.abspath(path)
        if not abs_path.startswith(abs_base + os.sep) and abs_path != abs_base:
            raise ValueError("Path outside allowed directory")
    return path


def generate_csrf_token(secret: str, session_or_user_id: str = "anonymous", ttl: int = 3600) -> str:
    """
    Generate a time-bound CSRF token signed with HMAC-SHA256.
    Format: <timestamp>.<random>.<signature>
    """
    if not secret:
        raise ValueError("CSRF secret is required")
    timestamp = str(int(time.time()))
    random_bits = secrets.token_hex(8)
    payload = f"{timestamp}.{random_bits}.{session_or_user_id}"
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{payload}.{signature}"


def validate_csrf_token(
    token: str, secret: str, session_or_user_id: str = "anonymous", ttl: int = 3600
) -> bool:
    """
    Validate a CSRF token generated by generate_csrf_token.
    """
    if not token or not secret:
        return False
    parts = token.split(".")
    if len(parts) != 4:
        return False
    timestamp_str, random_bits, token_user, signature = parts
    try:
        timestamp = int(timestamp_str)
    except ValueError:
        return False
    if time.time() - timestamp > ttl:
        return False
    payload = f"{timestamp_str}.{random_bits}.{token_user}"
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(expected, signature):
        return False
    return True


def validate_origin_referer(origin: Optional[str], allowed_origins: list[str]) -> bool:
    """
    Validate an Origin or Referer header against a list of allowed origins.
    """
    if not origin:
        return False
    origin = origin.strip().lower()
    for allowed in allowed_origins:
        allowed = allowed.strip().lower()
        if origin == allowed or origin.startswith(allowed.rstrip("/") + "/"):
            return True
    return False


# ── CSP Builder ──
def build_csp(nonce: str) -> str:
    """Return a nonce-based Content-Security-Policy header value."""
    return (
        f"default-src 'self'; "
        f"script-src 'self' 'nonce-{nonce}' https://fonts.googleapis.com; "
        f"style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://fonts.gstatic.com; "
        f"font-src 'self' https://fonts.gstatic.com; "
        f"img-src 'self' data: https:; "
        f"connect-src 'self' https://api.sarvam.ai https://*.supabase.co wss://*.supabase.co; "
        f"frame-ancestors 'none';"
    )


# ── TTL Rate Limiter ──
class TTLRateLimiter:
    """Simple TTL-backed rate limiter using per-key deques of timestamps."""

    def __init__(self, ttl: float, max_requests: int):
        self.ttl = ttl
        self.max_requests = max_requests
        self._store: dict[str, deque] = {}

    def is_allowed(self, key: str, now: Optional[float] = None) -> bool:
        now = now or time.time()
        ts = self._store.get(key)
        if ts is None:
            self._store[key] = deque([now], maxlen=self.max_requests + 1)
            return True
        cutoff = now - self.ttl
        while ts and ts[0] < cutoff:
            ts.popleft()
        if len(ts) >= self.max_requests:
            return False
        ts.append(now)
        return True

    def clear_expired(self, now: Optional[float] = None) -> None:
        now = now or time.time()
        cutoff = now - self.ttl
        for key in list(self._store.keys()):
            q = self._store[key]
            while q and q[0] < cutoff:
                q.popleft()
            if not q:
                del self._store[key]


import threading


class ExponentialBackoffRateLimiter:
    def __init__(
        self,
        ttl: float,
        max_requests: int,
        backoff_base: float = 2.0,
        backoff_multiplier: float = 2.0,
    ):
        self.ttl = ttl
        self.max_requests = max_requests
        self.backoff_base = backoff_base
        self.backoff_multiplier = backoff_multiplier
        self.max_backoff = ttl * 2
        self._attempts: dict[str, list[tuple[float, bool]]] = {}
        self._lock = threading.Lock()

    def is_allowed(self, key: str, now: Optional[float] = None) -> tuple[bool, float]:
        with self._lock:
            now = now or time.time()
            cutoff = now - self.ttl
            attempts = self._attempts.get(key, [])
            attempts = [a for a in attempts if a[0] > cutoff]

            failures = sum(1 for a in attempts if not a[1])
            successes = sum(1 for a in attempts if a[1])

            if successes >= self.max_requests:
                success_timestamps = [a[0] for a in attempts if a[1]]
                oldest_success_timestamp = min(success_timestamps) if success_timestamps else now
                wait = oldest_success_timestamp + self.ttl - now
                if wait < 0:
                    wait = 0.0
                return False, wait

            if failures > 0:
                last_failure_time = max(a[0] for a in attempts if not a[1])
                wait = self.backoff_base * (self.backoff_multiplier ** (failures - 1))
                wait = min(wait, self.max_backoff)
                if now - last_failure_time < wait:
                    return False, wait - (now - last_failure_time)

            return True, 0.0

    def record_attempt(self, key: str, success: bool, now: Optional[float] = None) -> None:
        with self._lock:
            now = now or time.time()
            if key not in self._attempts:
                self._attempts[key] = []
            self._attempts[key].append((now, success))
            cutoff = now - self.ttl
            self._attempts[key] = [a for a in self._attempts[key] if a[0] > cutoff]
            if not self._attempts[key]:
                del self._attempts[key]


_unkeyed_digest_warned = False


def _warn_unkeyed_digest() -> None:
    """Log (once per process) that rate-limit key digests are unkeyed."""
    global _unkeyed_digest_warned
    if _unkeyed_digest_warned:
        return
    import logging

    logging.getLogger(__name__).warning(
        "No signing secret configured (csrf_secret/jwt_secret/benchmark_secret) — "
        "rate-limit key digests are unkeyed SHA-256; identifiers are enumerable. "
        "Set at least one of these secrets."
    )
    _unkeyed_digest_warned = True


def _rate_limit_key_digest(key: str) -> str:
    """HMAC-SHA256 digest of a rate-limit key, truncated to 32 hex chars.

    Raw rate-limit keys embed account UUIDs or IPs (e.g.
    ``auth_rl:ip:/api/auth/login:1.2.3.4``). Embedding them verbatim in Redis
    key names lets anyone with Redis access (``KEYS *``, ``MONITOR``, key
    enumeration) harvest identifiers. HMAC-normalize instead so Redis only
    ever sees an opaque digest. Same truncation as ``generate_csrf_token``.

    Uses the first configured signing secret: ``settings.csrf_secret`` (a
    general-purpose signing secret; no dedicated rate-limit HMAC secret
    exists in config), else ``settings.jwt_secret``, else
    ``settings.benchmark_secret``. If none is set, falls back to a plain
    SHA-256 of the key — still opaque and deterministic across processes,
    so multi-worker rate limiting keeps working, but an unkeyed hash lets
    anyone with the key format precompute digests (offline dictionary
    checks). A WARNING is logged once; running unkeyed is preferred to
    crashing in environments with no secrets configured.
    """
    from app.config import settings

    secret = (
        getattr(settings, "csrf_secret", None)
        or getattr(settings, "jwt_secret", None)
        or getattr(settings, "benchmark_secret", None)
    )
    if secret:
        digest = hmac.new(secret.encode(), key.encode(), hashlib.sha256).hexdigest()
    else:
        _warn_unkeyed_digest()
        digest = hashlib.sha256(key.encode()).hexdigest()
    return digest[:32]


class RedisBackedRateLimiter:
    """Distributed sliding-window rate limiter backed by Redis ZADD.

    Uses the standard sorted-set pattern:
    - Key: ``rl:<key-digest>`` (one sorted set per rated entity — IP or
      account; the identifier portion is HMAC-digested, see
      :func:`_rate_limit_key_digest`)
    - Score: Unix timestamp (float)
    - Member: random UUID per event so duplicate scores don't collapse

    Includes exponential backoff tracking for failed attempts via a separate
    ``rl:fail:<key-digest>`` counter key with its own TTL.

    Falls back to :class:`ExponentialBackoffRateLimiter` when Redis is
    unavailable so the system degrades gracefully rather than open-gating
    all traffic.

    Usage::

        limiter = RedisBackedRateLimiter(
            redis_url="redis://...",
            ttl=60.0,
            max_requests=5,
            backoff_base=2.0,
            backoff_multiplier=2.0,
        )
        allowed, retry_after = limiter.is_allowed("auth_rl:ip:/api/auth/login:1.2.3.4")
        limiter.record_attempt("...", success=False)
    """

    def __init__(
        self,
        redis_url: str,
        ttl: float,
        max_requests: int,
        backoff_base: float = 2.0,
        backoff_multiplier: float = 2.0,
    ) -> None:
        self.ttl = ttl
        self.max_requests = max_requests
        self.backoff_base = backoff_base
        self.backoff_multiplier = backoff_multiplier
        self.max_backoff = ttl * 2
        self._redis: Optional[object] = None
        self._fallback = ExponentialBackoffRateLimiter(
            ttl=ttl,
            max_requests=max_requests,
            backoff_base=backoff_base,
            backoff_multiplier=backoff_multiplier,
        )
        self._fallback_active = False
        # Wall-clock timestamp of the last Redis reconnect attempt while in
        # fallback mode (0.0 = never attempted; see _maybe_reconnect).
        self._last_reconnect_attempt = 0.0

        # Lazy-init Redis connection — imports are deferred so this module
        # stays importable even if redis-py is not installed.
        self._redis_url = redis_url
        self._connect()

    # Minimum wall-clock gap between Redis reconnect attempts while in
    # fallback mode (seconds). Redis outage at boot would otherwise leave
    # _fallback_active True forever with no recovery path.
    _RECONNECT_INTERVAL = 30.0

    def _maybe_reconnect(self) -> None:
        """Retry Redis periodically while in fallback mode.

        _connect() runs only at construction time, so an outage at boot
        would otherwise leave the limiter on the process-local fallback
        forever. Throttled to one attempt per _RECONNECT_INTERVAL; on a
        successful ping _connect() resets _fallback_active and the Redis
        path resumes. If Redis is still down, _fallback_active stays True
        and the fallback limiter keeps being used (fail-open unchanged).
        """
        if not self._fallback_active:
            return
        if time.time() - self._last_reconnect_attempt < self._RECONNECT_INTERVAL:
            return
        self._last_reconnect_attempt = time.time()
        self._connect()

    def _connect(self) -> None:
        try:
            import redis

            self._redis = redis.Redis.from_url(
                self._redis_url,
                socket_timeout=0.5,
                socket_connect_timeout=0.5,
                decode_responses=True,
            )
            # Ping to verify connectivity at construction time.
            self._redis.ping()
            self._fallback_active = False
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning(
                "RedisBackedRateLimiter: Redis unavailable (%s) — falling back to process-local limiter",
                exc,
            )
            self._redis = None
            self._fallback_active = True

    # ── Public interface ────────────────────────────────────────────────────

    def is_allowed(self, key: str, now: Optional[float] = None) -> tuple[bool, float]:
        """Check whether *key* is within its rate limit.

        Returns:
            (allowed, retry_after_seconds)
        """
        now = now or time.time()
        self._maybe_reconnect()
        if self._fallback_active or self._redis is None:
            allowed, retry_after = self._fallback.is_allowed(key, now)
            if allowed:
                # Mirror the Lua path: the Redis script ZADDs the allowed
                # event atomically on allow. ExponentialBackoffRateLimiter
                # is_allowed is read-only, so record the success here.
                #
                # Kept despite the risk of double counting with callers
                # that also call record_attempt on success (the auth
                # middleware, main.py auth_rate_limit_middleware:917/919):
                # in fallback mode a success is then counted twice, versus
                # once in Redis mode (the Lua ZADD — a success
                # record_attempt only clears fail counters there). This is
                # deliberate: the admin middleware (main.py
                # admin_rate_limit_middleware:928-943) never calls
                # record_attempt, so is_allowed's synthetic record is its
                # ONLY counting hook. Removing it would silently disable
                # window enforcement for admin-style callers while Redis
                # is down — a regression pinned by
                # tests/test_redis_rate_limiter.py::TestRedisDownFallback
                # ::test_fallback_window_counts_allowed_events. The extra
                # count is fail-safe (limits earlier, never later).
                self._fallback.record_attempt(key, True, now)
            return allowed, retry_after

        try:
            return self._redis_is_allowed(key, now)
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning(
                "RedisBackedRateLimiter: Redis error on is_allowed (%s) — degrading to allow", exc
            )
            # Fail-open on transient Redis error to avoid locking out all users.
            return True, 0.0

    def record_attempt(self, key: str, success: bool, now: Optional[float] = None) -> None:
        """Record an attempt outcome for exponential-backoff tracking."""
        now = now or time.time()
        self._maybe_reconnect()
        if self._fallback_active or self._redis is None:
            # ExponentialBackoffRateLimiter.is_allowed is read-only; record the
            # outcome here so fallback backoff tracking works while Redis is down.
            self._fallback.record_attempt(key, success, now)
            return

        try:
            self._redis_record_attempt(key, success, now)
        except Exception as exc:
            import logging

            logging.getLogger(__name__).debug(
                "RedisBackedRateLimiter: record_attempt error: %s", exc
            )
            # Don't drop the outcome during a Redis hiccup — record it on the
            # fallback limiter so backoff tracking keeps working. Fail-safe,
            # not fail-open, for attempt outcomes.
            self._fallback.record_attempt(key, success, now)

    # ── Redis implementation ─────────────────────────────────────────────────

    # Atomic read+decide+insert for is_allowed. Executed server-side in one
    # r.eval() call so concurrent requests can never overshoot max_requests
    # (the pre-Lua pipeline read, then re-read, then ZADD outside the
    # transaction was a TOCTOU race). Returns {1, 0} when allowed, else
    # {0, retry_after_seconds}.
    _IS_ALLOWED_LUA = """
local now = tonumber(ARGV[1])
local cutoff = tonumber(ARGV[2])
local max_requests = tonumber(ARGV[3])
local ttl = tonumber(ARGV[4])
local backoff_base = tonumber(ARGV[5])
local backoff_multiplier = tonumber(ARGV[6])
local max_backoff = tonumber(ARGV[7])
local member = ARGV[8]

redis.call('zremrangebyscore', KEYS[1], '-inf', cutoff)
local count = redis.call('zcard', KEYS[1])

local fail_raw = redis.call('get', KEYS[2])
local failures = 0
if fail_raw then failures = tonumber(fail_raw) end
if failures > 0 then
    local last_fail_raw = redis.call('get', KEYS[3])
    if last_fail_raw then
        local last_fail = tonumber(last_fail_raw)
        local penalty = backoff_base * (backoff_multiplier ^ (failures - 1))
        if penalty > max_backoff then penalty = max_backoff end
        if now - last_fail < penalty then
            return {0, tostring(penalty - (now - last_fail))}
        end
    end
end

if count >= max_requests then
    local oldest = redis.call('zrange', KEYS[1], 0, 0, 'withscores')
    local retry_after = ttl
    if oldest[2] then
        retry_after = oldest[2] + ttl - now
        if retry_after < 0 then retry_after = 0 end
    end
    return {0, tostring(retry_after)}
end

redis.call('zadd', KEYS[1], now, member)
redis.call('expire', KEYS[1], math.floor(ttl) + 1)
return {1, 0}
"""

    def _redis_is_allowed(self, key: str, now: float) -> tuple[bool, float]:
        r = self._redis
        digest = _rate_limit_key_digest(key)
        zkey = f"rl:{digest}"
        fail_key = f"rl:fail:{digest}"
        last_fail_key = f"rl:lastfail:{digest}"

        import uuid

        member = str(uuid.uuid4())
        result = r.eval(
            self._IS_ALLOWED_LUA,
            3,
            zkey,
            fail_key,
            last_fail_key,
            now,
            now - self.ttl,
            self.max_requests,
            self.ttl,
            self.backoff_base,
            self.backoff_multiplier,
            self.max_backoff,
            member,
        )
        # redis-py (decode_responses=True) returns Lua numbers as int/float.
        # Lua NUMBERS are truncated to integers by Redis on return, so the
        # script sends fractional retry_after values as bulk strings via
        # tostring() to preserve precision; float() handles both forms.
        allowed = int(result[0]) == 1
        retry_after = float(result[1])
        return allowed, retry_after

    def _redis_record_attempt(self, key: str, success: bool, now: float) -> None:
        r = self._redis
        digest = _rate_limit_key_digest(key)
        if success:
            # Clear failure counter on success
            r.delete(f"rl:fail:{digest}")
            r.delete(f"rl:lastfail:{digest}")
        else:
            fail_key = f"rl:fail:{digest}"
            last_fail_key = f"rl:lastfail:{digest}"
            r.incr(fail_key)
            r.expire(fail_key, int(self.max_backoff) + 1)
            r.set(last_fail_key, str(now), ex=int(self.max_backoff) + 1)
