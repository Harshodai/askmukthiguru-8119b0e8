"""
Push notification service for AskMukthiGuru mobile app (Task 7).

Handles:
  - Device token registration (FCM / APNs) via Supabase `push_devices` table.
  - Send dispatch: FCM via firebase-admin, APNs via httpx + JWT-signed requests.

Graceful degradation: if push credentials are not configured, `send()` returns
a no-op result `{ok: True, sent: 0, failed: 0, errors: [...]}` — never raises.
This keeps the chat pipeline and admin tools running on hosts without creds.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any

import httpx
from supabase import create_client

from app.config import settings

logger = logging.getLogger(__name__)

# Module-level lazy singletons — created on first use, reused across calls.
_firebase_app_initialized: bool = False
_apns_jwt_cache: dict[str, Any] = {}


def _supabase_client():
    """Build a Supabase client using the service key (bypasses RLS)."""
    url = settings.supabase_url
    key = settings.supabase_key
    if not url or not key:
        raise RuntimeError("supabase_url / supabase_key not configured")
    return create_client(url, key)


def _firebase_creds_dict() -> dict | None:
    """Parse FIREBASE_CREDENTIALS_JSON — either raw JSON or a path to a file."""
    raw = (settings.firebase_credentials_json or os.environ.get("FIREBASE_CREDENTIALS_JSON", "")).strip()
    if not raw:
        return None
    # Path form
    if raw.startswith("/") or raw.startswith("./") or raw.startswith("../"):
        try:
            with open(raw, "r", encoding="utf-8") as f:
                return json.load(f)
        except OSError as e:
            logger.warning("firebase credentials path unreadable: %s (%s)", raw, e)
            return None
    # Raw JSON form
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("firebase credentials JSON parse failed: %s", e)
        return None


def _ensure_firebase() -> bool:
    """Idempotently initialize the firebase-admin default app. Returns True if ready."""
    global _firebase_app_initialized
    if _firebase_app_initialized:
        return True
    creds = _firebase_creds_dict()
    if not creds:
        return False
    try:
        import firebase_admin
        from firebase_admin import credentials
        try:
            firebase_admin.get_app()
        except ValueError:
            firebase_admin.initialize_app(credentials.Certificate(creds))
        _firebase_app_initialized = True
        logger.info("firebase-admin initialized")
        return True
    except Exception as e:  # import error or init failure
        logger.warning("firebase-admin init failed: %s", e)
        return False


def _apns_jwt() -> str | None:
    """Build a provider JWT for APNs. Cached for ~50 minutes (Apple max 1h)."""
    cache = _apns_jwt_cache
    now = time.time()
    if cache.get("exp", 0) - now > 300:
        return cache.get("token")

    key_id = settings.apns_key_id
    team_id = settings.apns_team_id
    if not key_id or not team_id:
        return None

    # Load key PEM (path or raw)
    pem = (settings.apns_key_pem or "").strip()
    if not pem and settings.apns_key_path:
        try:
            with open(settings.apns_key_path, "r", encoding="utf-8") as f:
                pem = f.read()
        except OSError as e:
            logger.warning("apns key path unreadable: %s (%s)", settings.apns_key_path, e)
            return None
    if not pem:
        return None

    try:
        import jwt as pyjwt
        payload = {"iss": team_id, "iat": now, "exp": now + 60 * 50}
        headers = {"kid": key_id, "alg": "ES256"}
        token = pyjwt.encode(payload, pem, algorithm="ES256", headers=headers)
        if isinstance(token, bytes):
            token = token.decode("utf-8")
        cache["token"] = token
        cache["exp"] = now + 60 * 50
        return token
    except Exception as e:
        logger.warning("apns jwt signing failed: %s", e)
        return None


def _apns_host() -> str:
    """Resolve the APNs host: explicit override → sandbox flag → production default."""
    if settings.apns_host:
        return settings.apns_host
    return "api.sandbox.push.apple.com" if settings.apns_use_sandbox else "api.push.apple.com"


class PushService:
    """Register devices and dispatch push notifications via FCM / APNs."""

    def __init__(self, supabase_client=None) -> None:
        self._supabase = supabase_client

    # --- Supabase access -------------------------------------------------

    def _client(self):
        if self._supabase is not None:
            return self._supabase
        return _supabase_client()

    # --- Public API ------------------------------------------------------

    async def register_device(self, platform: str, token: str, user_id: str | None) -> str:
        """Upsert a device token into push_devices. Returns the device id.

        Never raises — transient DB/network failures are logged and returned as
        an empty string, consistent with send()'s graceful-degradation pattern.
        """
        platform = platform.lower()
        if platform not in ("android", "ios"):
            raise ValueError("platform must be 'android' or 'ios'")
        row = {
            "platform": platform,
            "token": token,
            "user_id": user_id,
            "active": True,
        }
        try:
            client = self._client()
            # Upsert: re-activates a deactivated row on re-registration.
            resp = (
                client.table("push_devices")
                .upsert(row, on_conflict="platform,token")
                .execute()
            )
            data = getattr(resp, "data", None) or []
            if not data:
                # Fallback: select the row to get its id.
                sel = (
                    client.table("push_devices")
                    .select("id")
                    .eq("platform", platform)
                    .eq("token", token)
                    .limit(1)
                    .execute()
                )
                data = getattr(sel, "data", None) or []
            device_id = data[0].get("id") if data else None
            return str(device_id) if device_id else ""
        except Exception as e:
            logger.warning("push device registration failed: %s", e)
            return ""

    async def send(
        self,
        user_id: str | None,
        title: str,
        body: str,
        deep_link: str | None,
        data: dict | None,
    ) -> dict:
        """Fetch tokens for the target (or all active) and dispatch. Never raises."""
        try:
            tokens_by_platform = await self._fetch_tokens(user_id)
        except Exception as e:
            logger.warning("push token fetch failed: %s", e)
            return {"ok": True, "sent": 0, "failed": 0, "errors": [f"token fetch failed: {e}"]}

        android = tokens_by_platform.get("android", [])
        ios = tokens_by_platform.get("ios", [])
        if not android and not ios:
            return {"ok": True, "sent": 0, "failed": 0, "errors": ["no active devices"]}

        sent = 0
        failed = 0
        errors: list[str] = []

        if android:
            r = await self._send_fcm(android, title, body, deep_link, data)
            sent += r["sent"]
            failed += r["failed"]
            errors.extend(r["errors"])
        if ios:
            r = await self._send_apns(ios, title, body, deep_link, data)
            sent += r["sent"]
            failed += r["failed"]
            errors.extend(r["errors"])

        return {"ok": True, "sent": sent, "failed": failed, "errors": errors}

    # --- Token fetch -----------------------------------------------------

    async def _fetch_tokens(self, user_id: str | None) -> dict[str, list[str]]:
        """Return {platform: [tokens]} for active devices."""
        client = self._client()
        query = client.table("push_devices").select("platform,token").eq("active", True)
        if user_id:
            query = query.eq("user_id", user_id)
        resp = query.execute()
        rows = getattr(resp, "data", None) or []
        out: dict[str, list[str]] = {"android": [], "ios": []}
        for r in rows:
            p = (r.get("platform") or "").lower()
            t = r.get("token")
            if p in out and t:
                out[p].append(t)
        return out

    # --- FCM (firebase-admin) -------------------------------------------

    async def _send_fcm(
        self,
        tokens: list[str],
        title: str,
        body: str,
        deep_link: str | None,
        data: dict | None,
    ) -> dict:
        if not _ensure_firebase():
            logger.warning("firebase credentials not configured — skipping FCM send")
            return {"sent": 0, "failed": 0, "errors": ["firebase credentials not configured"]}
        try:
            from firebase_admin import messaging
            payload_data = dict(data or {})
            if deep_link:
                payload_data["deep_link"] = deep_link
            # firebase-admin multicast caps at 500 tokens per call — batch and aggregate.
            batch_size = max(1, int(getattr(settings, "fcm_multicast_batch_size", 500) or 500))
            sent = 0
            failed = 0
            errors: list[str] = []
            for i in range(0, len(tokens), batch_size):
                batch = tokens[i : i + batch_size]
                message = messaging.MulticastMessage(
                    notification=messaging.Notification(title=title, body=body),
                    data={k: str(v) for k, v in payload_data.items()},
                    tokens=batch,
                )
                resp = await asyncio.to_thread(messaging.send_each_for_multicast, message)
                sent += resp.success_count
                failed += resp.failure_count
                for j, r in enumerate(resp.responses):
                    if not r.success:
                        errors.append(f"fcm:{batch[j]}:{getattr(r.exception, 'code', 'error')}")
            return {"sent": sent, "failed": failed, "errors": errors}
        except Exception as e:
            logger.warning("FCM send failed: %s", e)
            return {"sent": 0, "failed": len(tokens), "errors": [f"fcm error: {e}"]}

    # --- APNs (httpx + JWT) ---------------------------------------------

    async def _send_apns(
        self,
        tokens: list[str],
        title: str,
        body: str,
        deep_link: str | None,
        data: dict | None,
    ) -> dict:
        jwt_token = _apns_jwt()
        if not jwt_token:
            logger.warning("apns credentials not configured — skipping APNs send")
            return {"sent": 0, "failed": 0, "errors": ["apns credentials not configured"]}

        bundle = settings.apns_bundle_id
        headers = {
            "authorization": f"bearer {jwt_token}",
            "apns-topic": bundle,
            "apns-push-type": "alert",
            "apns-priority": "10",
        }
        aps: dict[str, Any] = {
            "alert": {"title": title, "body": body},
            "sound": "default",
            "mutable-content": 1,
        }
        payload: dict[str, Any] = {"aps": aps}
        if data:
            payload["data"] = data
        if deep_link:
            payload["deep_link"] = deep_link

        host = _apns_host()

        async def _send_one(client: httpx.AsyncClient, tok: str) -> tuple[bool, str | None]:
            url = f"https://{host}/3/device/{tok}"
            try:
                r = await client.post(url, headers=headers, json=payload)
                if 200 <= r.status_code < 300:
                    return True, None
                return False, f"apns:{tok}:{r.status_code}:{r.text[:120]}"
            except Exception as e:
                return False, f"apns:{tok}:{e}"

        sent = 0
        failed = 0
        errors: list[str] = []
        async with httpx.AsyncClient(http2=True, timeout=30.0) as client:
            # Dispatch per-token APNs requests concurrently instead of serially.
            results = await asyncio.gather(*[_send_one(client, tok) for tok in tokens])
            for ok, err in results:
                if ok:
                    sent += 1
                else:
                    failed += 1
                    if err:
                        errors.append(err)
        return {"sent": sent, "failed": failed, "errors": errors}


if __name__ == "__main__":
    # Smoke-test: graceful no-creds response.
    result = asyncio.run(PushService().send(None, "test", "test", None, None))
    print(result)