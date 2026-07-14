from pydantic import BaseModel, Field, field_validator


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


class PushSendRequest(BaseModel):
    user_id: str | None = Field(None, description="Target user; if None, broadcast to all active devices")
    title: str = Field(..., min_length=1, max_length=120)
    body: str = Field(..., min_length=1, max_length=500)
    deep_link: str | None = Field(None, description="In-app route, e.g. '/chat' or '/practices'")
    data: dict | None = None


class PushSendResponse(BaseModel):
    ok: bool
    sent: int
    failed: int
    errors: list[str] = Field(default_factory=list)