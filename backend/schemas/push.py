from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

# Mirrors public/push-sw.js and PushNotificationsManager.tsx's client-side
# allowlists. An admin/cron sender must not be able to point a push
# notification at an arbitrary external URL. (OH-P1-06, 2026-08-24)
_SAFE_DEEP_LINK = re.compile(r"^/(chat|practices|profile|notebooks|knowledge-graph)(/[a-zA-Z0-9_-]*)?$")


class PushRegisterRequest(BaseModel):
    platform: str = Field(..., description="Device platform: 'android' or 'ios'")
    token: str = Field(..., min_length=16, max_length=4096, description="FCM or APNs token")
    # user_id is derived from the authenticated session (Authorization header), never client-supplied.

    @field_validator("platform")
    @classmethod
    def _platform(cls, v: str) -> str:
        v = v.lower()
        if v not in ("android", "ios"):
            raise ValueError("platform must be 'android' or 'ios'")
        return v


class PushRegisterResponse(BaseModel):
    ok: bool
    device_id: str | None = None


class PushUnregisterRequest(BaseModel):
    token: str = Field(..., min_length=16, max_length=4096, description="FCM or APNs token to deactivate")


class PushUnregisterResponse(BaseModel):
    ok: bool


class PushSendRequest(BaseModel):
    user_id: str | None = Field(
        None, description="Target user; if None, broadcast to all active devices"
    )
    title: str = Field(..., min_length=1, max_length=120)
    body: str = Field(..., min_length=1, max_length=500)
    deep_link: str | None = Field(None, description="In-app route, e.g. '/chat' or '/practices'")
    data: dict | None = None

    @field_validator("deep_link")
    @classmethod
    def _deep_link(cls, v: str | None) -> str | None:
        if v is not None and not _SAFE_DEEP_LINK.match(v):
            raise ValueError("deep_link must be an allowlisted in-app route")
        return v


class PushSendResponse(BaseModel):
    ok: bool
    sent: int
    failed: int
    errors: list[str] = Field(default_factory=list)
